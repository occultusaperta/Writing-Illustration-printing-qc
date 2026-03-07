from __future__ import annotations

import base64
import os
import threading
import time
from pathlib import Path

from PIL import Image

from bookforge.illustration.composition import compute_golden_ratio_points, compute_rule_of_thirds_grid
from bookforge.illustration.luxury_finish import apply_canvas_grain, apply_microtexture_enhancement, apply_paint_variance
from bookforge.illustration.prompt_contract import build_prompt_contract
from bookforge.illustration.providers.flux_local_contract import FluxGenerateRequest, cache_key_for_request, parse_generate_response
from bookforge.illustration.providers.flux_local_service import run_flux_local_service
from bookforge.illustration.upscale import upscale_image
from bookforge.illustration.visual_lock import normalize_visual_lock, validate_visual_lock
from bookforge.qc.premium_visual_qc import run_premium_visual_qc


def _mk_img(path: Path, color=(100, 120, 140), size=(128, 128)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def test_composition_engine_outputs():
    thirds = compute_rule_of_thirds_grid(900, 600)
    golden = compute_golden_ratio_points(900, 600)
    assert thirds["thirds_top_left"] == (300, 200)
    assert "golden_ratio_top_left" in golden


def test_visual_lock_normalization_backward_compatible(tmp_path: Path):
    char = tmp_path / "char.png"
    style = tmp_path / "style.png"
    cover = tmp_path / "cover.png"
    _mk_img(char)
    _mk_img(style)
    _mk_img(cover)
    lock = {
        "approved_variant": 1,
        "approved_character": str(char),
        "approved_style": str(style),
        "approved_cover": str(cover),
        "locked_prompt_prefix": "LOCK",
        "locked_negative_prompt": "NEG",
        "storyboard": {"pages": []},
        "print": {"safe_in": 0.25},
        "fal": {},
        "qa": {},
        "seeds": {"base_seed": 1, "per_page_seed": {"1": 101}},
        "spreads": {"mode": "none", "pairs": []},
    }
    parsed = {"pages": [{"page_number": 1, "illustration_notes": "keep moon", "required_hidden_details": ["red sock"], "text": "hello"}]}
    normalized, prov = normalize_visual_lock(lock, parsed_story=parsed)
    assert "premium_visual_contract" in normalized
    pvc = normalized["premium_visual_contract"]
    assert pvc["approved_variant_id"] == 1
    assert pvc["locked_character_sheet"] == str(char)
    assert "locked_line_style" in pvc
    assert "applied_fields" in prov
    assert validate_visual_lock(normalized, require_lock=True).ok


def test_prompt_contract_construction_extensions():
    parsed = {"title": "T", "pages": [{"page_number": 1, "text": "A quiet room.", "illustration_notes": "must show lamp and Patch", "required_hidden_details": ["tiny star"]}]}
    lock = {
        "approved_variant": 1,
        "approved_character": "char.png",
        "approved_style": "style.png",
        "locked_prompt_prefix": "LOCK",
        "locked_negative_prompt": "NEG",
        "seeds": {"per_page_seed": {"1": 123}},
        "print": {"required_pixels": [1024, 1024]},
        "premium_visual_contract": {
            "lens_framing_cues": ["eye-level"],
            "texture_finish_cues": ["grain"],
            "negative_prompt_rules": ["no watermark"],
            "character_reference_pack": {"primary": "char.png"},
            "style_reference_pack": {"primary": "style.png"},
            "trim_typography_safe_rules": {},
            "composition_guidance": {
                "primary_subject": "Mara",
                "secondary_subject": "Patch",
                "focal_zone": "golden_ratio_top_left",
                "camera_height": "child_eye_level",
                "eye_flow_direction": "left_to_right",
            },
            "character_proportions": {"head_body_ratio": 0.33, "eye_size_multiplier": 1.25, "cheek_roundness": 0.8},
        },
    }
    payload = build_prompt_contract(parsed, lock, spread_pairs=[[1, 2]])
    assert payload["version"].startswith("premium_prompt_contract")
    assert any(o["page_type"] == "front_cover" for o in payload["objects"])
    p1 = next(o for o in payload["objects"] if o["page_number"] == 1)
    assert p1["deterministic_seed"] == 123
    assert "non_negotiable_constraints" in p1["hierarchy"]
    assert "composition_guidance" in p1["metadata"]
    assert "reference_images" in p1["metadata"]


def test_luxury_finish_pipeline_toggle(monkeypatch):
    img = Image.new("RGB", (64, 64), (120, 130, 140))
    monkeypatch.setenv("BOOKFORGE_LUXURY_FINISH", "false")
    off = apply_paint_variance(apply_canvas_grain(apply_microtexture_enhancement(img)))
    monkeypatch.setenv("BOOKFORGE_LUXURY_FINISH", "true")
    on = apply_paint_variance(apply_canvas_grain(apply_microtexture_enhancement(img)))
    assert off.size == on.size


def test_upscale_pipeline(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BOOKFORGE_UPSCALE_TARGET", "4096")
    monkeypatch.setenv("BOOKFORGE_UPSCALE_MODE", "esrgan")
    monkeypatch.delenv("BOOKFORGE_ESRGAN_MODEL_PATH", raising=False)
    src = tmp_path / "page_001.png"
    _mk_img(src, size=(256, 128))
    out = upscale_image(src)
    assert out.exists()
    with Image.open(out) as im:
        assert max(im.size) >= 4096


def test_flux_local_contract_schema_roundtrip():
    req = FluxGenerateRequest(prompt="hello", width=512, height=512, seed=7, quality_preset="premium")
    payload = req.to_payload()
    key = cache_key_for_request("http://127.0.0.1:8188/generate", payload)
    resp = parse_generate_response({"image_b64": base64.b64encode(b"png").decode("utf-8"), "seed": 7, "provider": "flux_local", "model": "flux", "elapsed_ms": 12, "cache_key": key, "provenance": {"a": 1}})
    assert resp.seed == 7
    assert resp.cache_key == key


def test_premium_qc_report_schema_and_visual_critic(tmp_path: Path):
    style = tmp_path / "style.png"
    _mk_img(style, (90, 100, 110))
    pages = []
    for i in range(2):
        p = tmp_path / f"p{i}.png"
        _mk_img(p, (90 + i, 100, 110))
        pages.append(p)
    lock = {"approved_style": str(style), "qa": {"max_face_like_regions": 3, "max_focus_bleed_overlap": 0.2, "max_out_of_gamut_risk": 0.9}, "premium_visual_contract": {"required_hidden_details": {"1": ["star"]}}}
    parsed = {"pages": [{"page_number": 1, "illustration_notes": "note with Patch and Mara slipper"}, {"page_number": 2, "illustration_notes": ""}]}
    report = run_premium_visual_qc(pages, lock=lock, parsed_story=parsed)
    assert "pages" in report and isinstance(report["pages"], list)
    assert "hard_fail_threshold" in report
    assert "visual_critic_thresholds" in report
    assert "visual_critic_scores" in report["pages"][0]
    assert report["status"] in {"PASS", "FAIL"}


def test_flux_local_service_scaffold_health_and_generate(monkeypatch):
    monkeypatch.setenv("BOOKFORGE_FLUX_RUNTIME_MODE", "fallback")
    t = threading.Thread(target=run_flux_local_service, kwargs={"host": "127.0.0.1", "port": 8191}, daemon=True)
    t.start()
    time.sleep(0.5)
    import requests

    health = requests.get("http://127.0.0.1:8191/health", timeout=5).json()
    assert health["status"] == "ok"
    gen = requests.post("http://127.0.0.1:8191/generate", json={"prompt": "x", "width": 64, "height": 64, "seed": 3, "reference_images": ["a", "b"]}, timeout=5).json()
    assert "image_b64" in gen
