from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np
from PIL import Image

from bookforge.color_script.lab import LABColor, cie_de2000, srgb_to_lab, temperature_proxy

MAX_PIXEL_SAMPLE = 50_000
MAX_PALETTE_SAMPLE = 20_000
KMEANS_K = 5
DOMINANT_TOP_N = 3

PALETTE_ADHERENCE_DE_THRESHOLD = 14.0
FORBIDDEN_DE_THRESHOLD = 10.0
TARGET_DE_SOFT_MAX = 28.0

COMPOSITE_WEIGHTS: Dict[str, float] = {
    "lightness": 0.15,
    "chroma": 0.12,
    "temperature": 0.18,
    "contrast": 0.10,
    "dominant_match": 0.20,
    "palette_adherence": 0.15,
    "forbidden": 0.10,
}

ACCEPT_THRESHOLD = 0.78
POST_PROCESS_THRESHOLD = 0.55


@dataclass(frozen=True)
class ImageColorProfile:
    measured_lightness: float
    measured_chroma: float
    measured_temperature: float
    measured_contrast: float
    extracted_dominants: List[List[float]]
    dominant_proportions: List[float]


@dataclass(frozen=True)
class ColorAdherenceScore:
    lightness_score: float
    chroma_score: float
    temperature_score: float
    contrast_score: float
    dominant_match_score: float
    palette_adherence_score: float
    forbidden_color_score: float
    palette_adherence_pct: float


@dataclass(frozen=True)
class ColorScoreResult:
    page_number: int
    lightness_score: float
    chroma_score: float
    temperature_score: float
    contrast_score: float
    dominant_match_score: float
    palette_adherence_score: float
    forbidden_color_score: float
    composite_score: float
    extracted_dominants: List[List[float]]
    measured_lightness: float
    measured_chroma: float
    measured_temperature: float
    measured_contrast: float
    palette_adherence_pct: float
    disposition: str
    post_process_actions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _image_to_lab_pixels(image: Image.Image) -> np.ndarray:
    arr = np.asarray(image.convert("RGB"), dtype=np.uint8).reshape(-1, 3)
    return rgb_array_to_lab(arr)


def _stable_subsample(arr: np.ndarray, max_samples: int) -> np.ndarray:
    if arr.shape[0] <= max_samples:
        return arr
    idx = np.linspace(0, arr.shape[0] - 1, max_samples, dtype=np.int64)
    return arr[idx]


def rgb_array_to_lab(rgb_pixels: np.ndarray) -> np.ndarray:
    if rgb_pixels.size == 0:
        return np.zeros((0, 3), dtype=np.float32)
    labs = np.asarray([srgb_to_lab((int(r), int(g), int(b))).as_tuple() for r, g, b in rgb_pixels], dtype=np.float32)
    return labs


def _kmeans_lab(points: np.ndarray, k: int, max_iter: int = 12) -> tuple[np.ndarray, np.ndarray]:
    if points.shape[0] == 0:
        return np.zeros((0, 3), dtype=np.float32), np.zeros((0,), dtype=np.int64)
    k_eff = max(1, min(k, points.shape[0]))
    initial_idx = np.linspace(0, points.shape[0] - 1, k_eff, dtype=np.int64)
    centers = points[initial_idx].copy()
    labels = np.zeros((points.shape[0],), dtype=np.int64)
    for _ in range(max_iter):
        dists = np.sum((points[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        next_labels = np.argmin(dists, axis=1)
        if np.array_equal(next_labels, labels):
            break
        labels = next_labels
        for i in range(k_eff):
            mask = labels == i
            if np.any(mask):
                centers[i] = np.mean(points[mask], axis=0)
    return centers, labels


def extract_image_color_profile(image: Image.Image | np.ndarray | Path | str) -> ImageColorProfile:
    if isinstance(image, (str, Path)):
        with Image.open(image) as im:
            return extract_image_color_profile(im)
    if isinstance(image, np.ndarray):
        im = Image.fromarray(image.astype(np.uint8), mode="RGB")
        return extract_image_color_profile(im)
    lab = _image_to_lab_pixels(image)
    sample = _stable_subsample(lab, MAX_PIXEL_SAMPLE)
    if sample.size == 0:
        return ImageColorProfile(0.0, 0.0, 0.0, 0.0, [], [])

    l_vals = sample[:, 0]
    chroma_vals = np.sqrt(sample[:, 1] ** 2 + sample[:, 2] ** 2)
    temps = np.clip((sample[:, 2] - 0.1 * sample[:, 1]) / 128.0, -1.0, 1.0)
    contrast = float(np.std(l_vals) / 100.0)

    centers, labels = _kmeans_lab(sample, KMEANS_K)
    counts = np.bincount(labels, minlength=centers.shape[0]).astype(np.float32)
    proportions = counts / max(1.0, float(np.sum(counts)))
    order = np.argsort(-proportions)
    top_idx = order[:DOMINANT_TOP_N]
    doms = centers[top_idx].tolist()
    dom_props = proportions[top_idx].tolist()

    return ImageColorProfile(
        measured_lightness=float(np.mean(l_vals)),
        measured_chroma=float(np.mean(chroma_vals)),
        measured_temperature=float(np.mean(temps)),
        measured_contrast=contrast,
        extracted_dominants=[[float(c) for c in d] for d in doms],
        dominant_proportions=[float(p) for p in dom_props],
    )


def _target_score(measured: float, target: float, tolerance: float) -> float:
    delta = abs(measured - target)
    return float(np.clip(1.0 - (delta / max(1e-6, tolerance)), 0.0, 1.0))


def _to_labcolor(seq: Sequence[float]) -> LABColor:
    return LABColor(float(seq[0]), float(seq[1]), float(seq[2]))


def _min_delta_e(lab: LABColor, palette: Iterable[Sequence[float]]) -> float:
    values = [cie_de2000(lab, _to_labcolor(p)) for p in palette]
    return min(values) if values else 100.0


def _dominant_match_score(dominants: Sequence[Sequence[float]], targets: Sequence[Sequence[float]]) -> float:
    if not dominants or not targets:
        return 0.0
    scores = []
    for d in dominants:
        delta = _min_delta_e(_to_labcolor(d), targets)
        scores.append(float(np.clip(1.0 - delta / TARGET_DE_SOFT_MAX, 0.0, 1.0)))
    return float(np.mean(scores)) if scores else 0.0


def _palette_membership_pct(sample_pixels: np.ndarray, palette: Sequence[Sequence[float]], threshold: float) -> float:
    if sample_pixels.size == 0 or not palette:
        return 0.0
    pal = [_to_labcolor(p) for p in palette]
    chunk = 512
    matches = 0
    total = sample_pixels.shape[0]
    for i in range(0, total, chunk):
        window = sample_pixels[i : i + chunk]
        for px in window:
            delta = min(cie_de2000(LABColor(float(px[0]), float(px[1]), float(px[2])), p) for p in pal)
            if delta <= threshold:
                matches += 1
    return float(matches / max(1, total))


def score_color_adherence(image_profile: ImageColorProfile, page_spec: Dict[str, Any] | None, master_palette: Dict[str, Any] | None, image: Image.Image | np.ndarray | Path | str | None = None) -> ColorAdherenceScore:
    page_spec = page_spec or {}
    master_palette = master_palette or {}

    lightness_score = _target_score(image_profile.measured_lightness, float(page_spec.get("target_lightness", image_profile.measured_lightness)), tolerance=28.0)
    chroma_score = _target_score(image_profile.measured_chroma, float(page_spec.get("target_chroma", image_profile.measured_chroma)), tolerance=38.0)
    temperature_score = _target_score(image_profile.measured_temperature, float(page_spec.get("target_temperature", image_profile.measured_temperature)), tolerance=0.65)
    contrast_score = _target_score(image_profile.measured_contrast, float(page_spec.get("target_contrast", image_profile.measured_contrast)), tolerance=0.40)

    target_dominants = [x for x in page_spec.get("dominant_colors_lab", []) if isinstance(x, list) and len(x) >= 3]
    if not target_dominants:
        target_dominants = [x for x in master_palette.get("dominant_colors_lab", []) if isinstance(x, list) and len(x) >= 3]
    dominant_match_score = _dominant_match_score(image_profile.extracted_dominants, target_dominants)

    allowed_palette = []
    for key in ("dominant_colors_lab", "accent_colors_lab", "neutrals_lab"):
        allowed_palette.extend([x for x in master_palette.get(key, []) if isinstance(x, list) and len(x) >= 3])
    if not allowed_palette:
        allowed_palette = target_dominants

    forbidden = [x for x in page_spec.get("forbidden_colors_lab", []) if isinstance(x, list) and len(x) >= 3]

    if image is None:
        adherence_pct = _dominant_match_score(image_profile.extracted_dominants, allowed_palette)
        forbidden_pct = _dominant_match_score(image_profile.extracted_dominants, forbidden) if forbidden else 0.0
    else:
        if isinstance(image, (str, Path)):
            with Image.open(image) as im:
                lab = _image_to_lab_pixels(im)
        elif isinstance(image, np.ndarray):
            lab = rgb_array_to_lab(image.reshape(-1, 3))
        else:
            lab = _image_to_lab_pixels(image)
        lab = _stable_subsample(lab, MAX_PALETTE_SAMPLE)
        adherence_pct = _palette_membership_pct(lab, allowed_palette, PALETTE_ADHERENCE_DE_THRESHOLD)
        forbidden_pct = _palette_membership_pct(lab, forbidden, FORBIDDEN_DE_THRESHOLD) if forbidden else 0.0

    palette_adherence_score = float(np.clip(adherence_pct, 0.0, 1.0))
    forbidden_color_score = float(np.clip(1.0 - forbidden_pct * 3.0, 0.0, 1.0))

    return ColorAdherenceScore(
        lightness_score=lightness_score,
        chroma_score=chroma_score,
        temperature_score=temperature_score,
        contrast_score=contrast_score,
        dominant_match_score=dominant_match_score,
        palette_adherence_score=palette_adherence_score,
        forbidden_color_score=forbidden_color_score,
        palette_adherence_pct=float(np.clip(adherence_pct, 0.0, 1.0)),
    )


def compute_color_composite_score(score: ColorAdherenceScore) -> float:
    return float(
        score.lightness_score * COMPOSITE_WEIGHTS["lightness"]
        + score.chroma_score * COMPOSITE_WEIGHTS["chroma"]
        + score.temperature_score * COMPOSITE_WEIGHTS["temperature"]
        + score.contrast_score * COMPOSITE_WEIGHTS["contrast"]
        + score.dominant_match_score * COMPOSITE_WEIGHTS["dominant_match"]
        + score.palette_adherence_score * COMPOSITE_WEIGHTS["palette_adherence"]
        + score.forbidden_color_score * COMPOSITE_WEIGHTS["forbidden"]
    )


def classify_color_disposition(composite_score: float) -> str:
    if composite_score >= ACCEPT_THRESHOLD:
        return "ACCEPT"
    if composite_score >= POST_PROCESS_THRESHOLD:
        return "POST_PROCESS"
    return "REJECT"


def _suggest_post_process_actions(score: ColorAdherenceScore, profile: ImageColorProfile) -> List[str]:
    actions: List[str] = []
    if score.temperature_score < 0.55:
        actions.append("temperature_rebalance")
    if score.lightness_score < 0.55:
        actions.append("lightness_tune")
    if score.chroma_score < 0.55:
        actions.append("chroma_tune")
    if score.palette_adherence_score < 0.55:
        actions.append("palette_harmonize")
    if score.forbidden_color_score < 0.8:
        actions.append("forbidden_color_suppression")
    if profile.measured_contrast < 0.18:
        actions.append("contrast_lift")
    return actions


def score_candidate_image_colors(image: Image.Image | np.ndarray | Path | str, page_number: int, page_spec: Dict[str, Any] | None, master_palette: Dict[str, Any] | None) -> ColorScoreResult:
    profile = extract_image_color_profile(image)
    adherence = score_color_adherence(profile, page_spec, master_palette, image=image)
    composite = compute_color_composite_score(adherence)
    disposition = classify_color_disposition(composite)
    return ColorScoreResult(
        page_number=int(page_number),
        lightness_score=adherence.lightness_score,
        chroma_score=adherence.chroma_score,
        temperature_score=adherence.temperature_score,
        contrast_score=adherence.contrast_score,
        dominant_match_score=adherence.dominant_match_score,
        palette_adherence_score=adherence.palette_adherence_score,
        forbidden_color_score=adherence.forbidden_color_score,
        composite_score=composite,
        extracted_dominants=profile.extracted_dominants,
        measured_lightness=profile.measured_lightness,
        measured_chroma=profile.measured_chroma,
        measured_temperature=profile.measured_temperature,
        measured_contrast=profile.measured_contrast,
        palette_adherence_pct=adherence.palette_adherence_pct,
        disposition=disposition,
        post_process_actions=_suggest_post_process_actions(adherence, profile),
    )
