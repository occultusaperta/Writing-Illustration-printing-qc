from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image

from bookforge.page_architecture.scoring import score_architecture_variant
from bookforge.qc.composition_qc import focus_bleed_overlap
from bookforge.color_script.postprocess import apply_color_postprocess
from bookforge.color_script.scoring import score_candidate_image_colors
from bookforge.qc.gpu_batch_scoring import gpu_batch_scoring_enabled, score_candidate_batch
from bookforge.qc.ensemble_visual import evaluate_visual_ensemble
from bookforge.camera_language.scoring import score_shot_adherence
from bookforge.saliency_flow import score_saliency_flow
from bookforge.hidden_world import score_hidden_world_adherence
from bookforge.dual_audience import score_dual_audience
from bookforge.character_scoring import score_character_commercial
from bookforge.page_turn import score_page_turn_tension
from bookforge.qc.print_qc import analyze_print_qc, print_qc_warnings
from bookforge.qc.visual_integrity import (
    border_artifact_score,
    face_like_regions,
    logo_likelihood,
    text_likelihood,
    watermark_likelihood,
)


def _gray(arr: np.ndarray) -> np.ndarray:
    return 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]


def sharpness(path: Path) -> float:
    with Image.open(path) as im:
        arr = np.asarray(im.convert("RGB"), dtype=np.float32)
    g = _gray(arr)
    lap = -4 * g + np.roll(g, 1, 0) + np.roll(g, -1, 0) + np.roll(g, 1, 1) + np.roll(g, -1, 1)
    return float(np.var(lap[1:-1, 1:-1]))


def entropy(path: Path) -> float:
    with Image.open(path) as im:
        hist = np.asarray(im.convert("L").histogram(), dtype=np.float64)
    p = hist / max(hist.sum(), 1)
    p = p[p > 0]
    return float(-np.sum(p * np.log2(p)))


def contrast(path: Path) -> float:
    with Image.open(path) as im:
        arr = np.asarray(im.convert("L"), dtype=np.float32)
    return float(np.std(arr))


def border_bar_score(path: Path, edge_frac: float = 0.08) -> float:
    with Image.open(path) as im:
        arr = np.asarray(im.convert("L"), dtype=np.float32)
    h, w = arr.shape
    b = max(1, int(min(h, w) * edge_frac))
    strips = [arr[:b, :], arr[-b:, :], arr[:, :b], arr[:, -b:]]
    lows = [float(np.std(s) < 5.0) for s in strips]
    return float(np.mean(lows))


def _hist(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        arr = np.asarray(im.convert("RGB"))
    out = []
    for ch in range(3):
        hist, _ = np.histogram(arr[:, :, ch], bins=32, range=(0, 256), density=True)
        out.append(hist)
    vec = np.concatenate(out)
    denom = np.linalg.norm(vec)
    return vec / denom if denom else vec


def style_hist_similarity(image: Path, style_ref: Path) -> float:
    a = _hist(image)
    b = _hist(style_ref)
    return float(np.clip(np.dot(a, b), 0.0, 1.0))


def page_to_page_hist_drift(image: Path, prev_image: Path) -> float:
    sim = style_hist_similarity(image, prev_image)
    return float(max(0.0, 1.0 - sim))


def _variant_report(path: Path, qa_config: Dict[str, Any], style_ref: Path | None, prev_ref: Path | None) -> Dict[str, Any]:
    faces = face_like_regions(path)
    focus = focus_bleed_overlap(path)
    report = {
        "path": str(path),
        "sharpness": sharpness(path),
        "entropy": entropy(path),
        "contrast": contrast(path),
        "border_bar_score": border_bar_score(path),
        "text_likelihood": text_likelihood(path),
        "watermark_likelihood": watermark_likelihood(path),
        "logo_likelihood": logo_likelihood(path),
        "border_artifact_score": border_artifact_score(path),
        "face_like_regions": faces,
        "style_hist_similarity": style_hist_similarity(path, style_ref) if style_ref else 1.0,
        "page_to_page_hist_drift": page_to_page_hist_drift(path, prev_ref) if prev_ref else 0.0,
        "focus_bleed_overlap": focus["overlap"],
        "focus_box": focus["focus_box"],
    }
    print_metrics = analyze_print_qc(path, style_ref)
    report.update(print_metrics)
    face_limit = int(qa_config.get("max_face_like_regions", 3))
    face_fail = faces > face_limit
    report["warnings"] = []
    report["warnings"].extend(print_qc_warnings(report, qa_config))
    if face_fail:
        report["warnings"].append(f"face_like_regions>{face_limit}")
    max_focus_overlap = float(qa_config.get("max_focus_bleed_overlap", 0.15))
    focus_fail = report["focus_bleed_overlap"] > max_focus_overlap
    if focus_fail:
        report["warnings"].append(f"focus_bleed_overlap>{max_focus_overlap}")
    extreme_dark_fail = report["brightness_p95"] < 80
    report["passes"] = (
        report["sharpness"] >= qa_config["min_sharpness"]
        and report["entropy"] >= qa_config["min_entropy"]
        and report["contrast"] >= qa_config["min_contrast"]
        and report["border_bar_score"] <= qa_config["max_border_bar_score"]
        and report["text_likelihood"] <= qa_config["max_text_likelihood"]
        and report["watermark_likelihood"] <= qa_config["max_watermark_likelihood"]
        and report["logo_likelihood"] <= qa_config["max_logo_likelihood"]
        and report["border_artifact_score"] <= qa_config["max_border_artifact_score"]
        and not face_fail
        and report["style_hist_similarity"] >= qa_config["min_style_hist_similarity"]
        and report["page_to_page_hist_drift"] <= qa_config["max_page_to_page_hist_drift"]
        and not focus_fail
        and not extreme_dark_fail
    )
    return report


def choose_best_variant(
    paths: List[Path],
    qa_config: Dict[str, Any],
    style_ref: Path | None,
    prev_ref: Path | None,
    page_number: int | None = None,
    page_color_spec: Dict[str, Any] | None = None,
    master_palette: Dict[str, Any] | None = None,
    page_text: str = "",
    architecture_variant: Dict[str, Any] | None = None,
    age_range: str | None = None,
    shot_plan_entry: Dict[str, Any] | None = None,
    prompt_metadata: Dict[str, Any] | None = None,
    hidden_world_guidance: Dict[str, Any] | None = None,
    illustration_notes: str = "",
    page_count: int | None = None,
) -> Tuple[Path, Dict[str, Any]]:
    character_commercial_enabled = str(os.getenv("BOOKFORGE_CHARACTER_COMMERCIAL_SCORING", "true")).strip().lower() in {"1", "true", "yes", "on"}
    saliency_flow_enabled = str(os.getenv("BOOKFORGE_SALIENCY_FLOW", "true")).strip().lower() in {"1", "true", "yes", "on"}
    dual_audience_enabled = str(os.getenv("BOOKFORGE_DUAL_AUDIENCE", "true")).strip().lower() in {"1", "true", "yes", "on"}
    page_turn_tension_enabled = str(os.getenv("BOOKFORGE_PAGE_TURN_TENSION", "true")).strip().lower() in {"1", "true", "yes", "on"}
    batch_scores: Dict[str, Dict[str, float]] = {}
    if gpu_batch_scoring_enabled():
        batch_scores = score_candidate_batch(paths)

    reports = [_variant_report(p, qa_config, style_ref, prev_ref) for p in paths]
    for report in reports:
        gpu = batch_scores.get(report["path"])
        if gpu:
            report["gpu_batch_scores"] = gpu
        metadata = report.setdefault("metadata", {})
        if page_number is not None:
            color_score = score_candidate_image_colors(report["path"], page_number=page_number, page_spec=page_color_spec, master_palette=master_palette)
            metadata["color_score"] = color_score.to_dict()
            if color_score.disposition == "POST_PROCESS":
                correction_spec = dict(page_color_spec or {})
                if master_palette is not None:
                    correction_spec["_master_palette"] = master_palette
                postprocess = apply_color_postprocess(report["path"], color_score, correction_spec)
                corrected_path = Path(report["path"]).with_name(f"{Path(report['path']).stem}__cse_pp.png")
                postprocess.corrected_image.save(corrected_path)
                metadata["color_postprocess"] = {
                    "actions": postprocess.actions_applied,
                    "delta_score": postprocess.delta_scores_estimate.get("composite_delta", 0.0),
                }
                metadata["corrected_variant"] = {
                    "path": str(corrected_path),
                    "postprocess_score_delta": postprocess.delta_scores_estimate.get("composite_delta", 0.0),
                }

        ensemble = evaluate_visual_ensemble(report["path"])
        metadata["visual_ensemble"] = {
            "critic_scores": {
                "composition_score": ensemble.composition_score,
                "clarity_score": ensemble.clarity_score,
                "texture_score": ensemble.texture_score,
                "artifact_score": ensemble.artifact_score,
                "perceptual_quality": ensemble.perceptual_quality,
            },
            "ensemble_score": ensemble.ensemble_score,
        }
        if architecture_variant:
            arch_score = score_architecture_variant(
                architecture_variant,
                page_text=page_text,
                image=Path(report["path"]),
                page_color_spec=page_color_spec,
                age_range=age_range,
            )
            metadata["page_architecture_score"] = arch_score.to_dict()

        shot_score = score_shot_adherence(report, shot_plan_entry)
        if shot_score is not None:
            metadata["shot_adherence_score"] = shot_score.to_dict()
        if saliency_flow_enabled:
            saliency_score = score_saliency_flow(
                report["path"],
                page_number=page_number,
                architecture_variant=architecture_variant,
                shot_plan_entry=shot_plan_entry,
                prompt_metadata=prompt_metadata,
            )
            metadata["saliency_flow_score"] = saliency_score.to_dict()

        hidden_world_score = score_hidden_world_adherence(
            page_number=page_number or 0,
            hidden_world_guidance=hidden_world_guidance,
            prompt_metadata=prompt_metadata,
            saliency_score=(metadata.get("saliency_flow_score") if isinstance(metadata.get("saliency_flow_score"), dict) else {}),
            architecture_variant=architecture_variant,
            illustration_notes=illustration_notes,
        )
        metadata["hidden_world_score"] = hidden_world_score.to_dict()
        if character_commercial_enabled:
            try:
                commercial_score = score_character_commercial(report["path"])
                metadata["baby_schema_score"] = commercial_score.baby_schema.to_dict()
                metadata["toyetic_score"] = commercial_score.toyetic.to_dict()
                metadata["silhouette_score"] = commercial_score.silhouette.to_dict()
                metadata["character_commercial_score"] = commercial_score.to_dict()
            except Exception as exc:
                metadata["character_commercial_score"] = {
                    "composite_score": 0.0,
                    "confidence": 0.0,
                    "warnings": [f"Character commercial scoring unavailable: {exc}"],
                    "notes": ["Scoring skipped due to bounded safe no-op behavior."],
                }
        if dual_audience_enabled:
            metadata["dual_audience_score"] = score_dual_audience(report).to_dict()
        if page_turn_tension_enabled and page_number is not None:
            turn_score = score_page_turn_tension(
                report["path"],
                page_number=int(page_number),
                page_count=int(page_count or max(1, page_number)),
                page_text=page_text,
                prompt_metadata=(prompt_metadata if isinstance(prompt_metadata, dict) else {}),
                architecture_variant=(architecture_variant if isinstance(architecture_variant, dict) else {}),
                shot_plan_entry=(shot_plan_entry if isinstance(shot_plan_entry, dict) else {}),
                saliency_score=(metadata.get("saliency_flow_score") if isinstance(metadata.get("saliency_flow_score"), dict) else {}),
                illustration_notes=illustration_notes,
            )
            metadata["page_turn_tension_score"] = turn_score.to_dict()

    scored = sorted(
        reports,
        key=lambda r: (
            r["passes"],
            -4.0 * r["text_likelihood"] - 4.0 * r["watermark_likelihood"] - 3.0 * r["logo_likelihood"] - 3.0 * r["border_artifact_score"],
            r["style_hist_similarity"] - r["page_to_page_hist_drift"] - 0.6 * r.get("color_drift_vs_style", 0.0),
            r["sharpness"] + r["contrast"] + r["entropy"] - 0.2 * max(0.0, 100 - r.get("brightness_p95", 100)) - 5.0 * r.get("out_of_gamut_risk", 0.0),
            (r.get("gpu_batch_scores") or {}).get("ranking_score", 0.0),
            ((r.get("metadata") or {}).get("visual_ensemble") or {}).get("ensemble_score", 0.0),
            ((r.get("metadata") or {}).get("page_architecture_score") or {}).get("composite_score", 0.0),
            0.15 * (((r.get("metadata") or {}).get("shot_adherence_score") or {}).get("composite_score", 0.0)),
            0.05 * (((r.get("metadata") or {}).get("saliency_flow_score") or {}).get("composite_score", 0.0)),
            0.04 * (((r.get("metadata") or {}).get("character_commercial_score") or {}).get("composite_score", 0.0)),
            0.035 * (((r.get("metadata") or {}).get("dual_audience_score") or {}).get("composite_score", 0.0)),
            0.02 * (((r.get("metadata") or {}).get("page_turn_tension_score") or {}).get("page_turn_tension_score", 0.0)),
        ),
        reverse=True,
    )
    best = scored[0]
    return Path(best["path"]), {"variants": reports, "best": best, "passes": bool(best["passes"])}


def write_qa_report(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
