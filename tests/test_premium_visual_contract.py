from __future__ import annotations

import base64
import threading
import time
from pathlib import Path

from PIL import Image

from bookforge.illustration.prompt_contract import build_prompt_contract
from bookforge.illustration.providers.flux_local_contract import FluxGenerateRequest, cache_key_for_request, parse_generate_response
from bookforge.illustration.providers.flux_local_service import run_flux_local_service
from bookforge.illustration.visual_lock import normalize_visual_lock, validate_visual_lock
from bookforge.qc.premium_visual_qc import run_premium_visual_qc


def _mk_img(path: Path, color=(100, 120, 140)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (128, 128), color).save(path)


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
    assert normalized["premium_visual_contract"]["approved_variant_id"] == 1
    assert "palette_lock" in normalized["premium_visual_contract"]
    assert "applied_fields" in prov
    assert validate_visual_lock(normalized, require_lock=True).ok


def test_prompt_contract_construction():
    parsed = {"title": "T", "pages": [{"page_number": 1, "text": "A quiet room.", "illustration_notes": "must show lamp", "required_hidden_details": ["tiny star"]}]}
    lock = {
        "approved_variant": 1,
        "approved_character": "char.png",
        "approved_style": "style.png",
        "locked_prompt_prefix": "LOCK",
        "locked_negative_prompt": "NEG",
        "seeds": {"per_page_seed": {"1": 123}},
        "premium_visual_contract": {"lens_framing_cues": ["eye-level"], "texture_finish_cues": ["grain"], "negative_prompt_rules": ["no watermark"], "character_reference_pack": {"primary": "char.png"}, "style_reference_pack": {"primary": "style.png"}, "trim_typography_safe_rules": {}},
    }
    payload = build_prompt_contract(parsed, lock, spread_pairs=[[1, 2]])
    assert payload["version"].startswith("premium_prompt_contract")
    assert any(o["page_type"] == "front_cover" for o in payload["objects"])
    p1 = next(o for o in payload["objects"] if o["page_number"] == 1)
    assert p1["deterministic_seed"] == 123
    assert "non_negotiable_constraints" in p1["hierarchy"]


def test_flux_local_contract_schema_roundtrip():
    req = FluxGenerateRequest(prompt="hello", width=512, height=512, seed=7, quality_preset="premium")
    payload = req.to_payload()
    key = cache_key_for_request("http://127.0.0.1:8188/generate", payload)
    resp = parse_generate_response({"image_b64": base64.b64encode(b"png").decode("utf-8"), "seed": 7, "provider": "flux_local", "model": "flux", "elapsed_ms": 12, "cache_key": key, "provenance": {"a": 1}})
    assert resp.seed == 7
    assert resp.cache_key == key


def test_premium_qc_report_schema_and_threshold(tmp_path: Path):
    style = tmp_path / "style.png"
    _mk_img(style, (90, 100, 110))
    pages = []
    for i in range(2):
        p = tmp_path / f"p{i}.png"
        _mk_img(p, (90 + i, 100, 110))
        pages.append(p)
    lock = {"approved_style": str(style), "qa": {"max_face_like_regions": 3, "max_focus_bleed_overlap": 0.2, "max_out_of_gamut_risk": 0.9}, "premium_visual_contract": {"required_hidden_details": {"1": ["star"]}}}
    parsed = {"pages": [{"page_number": 1, "illustration_notes": "note"}, {"page_number": 2, "illustration_notes": ""}]}
    report = run_premium_visual_qc(pages, lock=lock, parsed_story=parsed)
    assert "pages" in report and isinstance(report["pages"], list)
    assert "hard_fail_threshold" in report
    assert report["status"] in {"PASS", "FAIL"}


def test_flux_local_service_scaffold_health_and_generate():
    t = threading.Thread(target=run_flux_local_service, kwargs={"host": "127.0.0.1", "port": 8191}, daemon=True)
    t.start()
    time.sleep(0.5)
    import requests

    health = requests.get("http://127.0.0.1:8191/health", timeout=5).json()
    assert health["status"] == "ok"
    gen = requests.post("http://127.0.0.1:8191/generate", json={"prompt": "x", "width": 64, "height": 64, "seed": 3}, timeout=5).json()
    assert "image_b64" in gen
