import json
from pathlib import Path

import pytest
from PIL import Image

from bookforge.illustration.providers import OPENAI_DISABLED_MESSAGE, resolve_image_provider
from bookforge.pipeline import BookforgePipeline


def _minimal_lock(tmp_path: Path) -> dict:
    char = tmp_path / "char.png"
    style = tmp_path / "style.png"
    cover = tmp_path / "cover.png"
    for p, c in [(char, (10, 20, 30)), (style, (40, 50, 60)), (cover, (70, 80, 90))]:
        Image.new("RGB", (64, 64), c).save(p)
    return {
        "approved_variant": 1,
        "approved_character": str(char),
        "approved_style": str(style),
        "approved_cover": str(cover),
        "locked_prompt_prefix": "LOCK",
        "locked_negative_prompt": "NEG",
        "storyboard": {"pages": []},
        "print": {"required_pixels": [128, 128], "dpi": 300},
        "fal": {"endpoint": "https://fal.run/fal-ai/flux/schnell", "steps": 1, "page_variants": 1},
        "qa": {"max_regen_rounds": 0, "max_focus_bleed_overlap": 1.0, "max_text_likelihood": 1.0, "max_watermark_likelihood": 1.0, "max_logo_likelihood": 1.0},
        "seeds": {"per_page_seed": {"1": 123}},
        "cover_layout_preset": "front_title_top_back_blurb",
        "interior_layout_preset": "cinematic_panel_bottom",
        "typography_preset": "storybook_large",
        "cover": {"spine_w_in": 0.06},
        "post": {},
        "editorial": {"editorial_mode": True},
    }


def test_provider_resolution_env_switch(monkeypatch):
    monkeypatch.delenv("BOOKFORGE_FLUX_LOCAL_URL", raising=False)
    monkeypatch.setenv("BOOKFORGE_IMAGE_PROVIDER", "fal")
    provider, name = resolve_image_provider("auto")
    assert name == "fal"
    assert provider.name == "fal"

    monkeypatch.setenv("BOOKFORGE_IMAGE_PROVIDER", "flux_local")
    monkeypatch.setenv("BOOKFORGE_FLUX_LOCAL_URL", "http://127.0.0.1:9999/generate")
    provider, name = resolve_image_provider("auto")
    assert name == "flux_local"
    assert provider.name == "flux_local"


def test_openai_provider_is_hard_blocked(monkeypatch):
    monkeypatch.setenv("BOOKFORGE_IMAGE_PROVIDER", "openai")
    with pytest.raises(RuntimeError, match=OPENAI_DISABLED_MESSAGE):
        resolve_image_provider("auto")


def test_require_lock_fails_when_required_fields_missing(tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir(parents=True)
    (out / "LOCK.json").write_text(json.dumps({"approved_variant": 1}), encoding="utf-8")
    story = tmp_path / "story.md"
    story.write_text("## Page 1\nhello", encoding="utf-8")

    with pytest.raises(RuntimeError, match="LOCK.json missing required fields"):
        BookforgePipeline().studio(str(story), str(out), "8.5x8.5", 1, "fal", True)


def test_studio_uses_locked_reference_paths(monkeypatch, tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir(parents=True)
    lock = _minimal_lock(tmp_path)
    (out / "LOCK.json").write_text(json.dumps(lock), encoding="utf-8")
    story = tmp_path / "story.md"
    story.write_text("## Page 1\nA fox and moon.", encoding="utf-8")

    captured = {}

    def fake_generate(self, prompts, variants_dir, image_size_px, variants=2, reference_image=None, style_image=None, palette_tile=None, steps=4, seeds=None, cache_dir=None):
        captured["reference_image"] = str(reference_image)
        captured["style_image"] = str(style_image)
        variants_dir.mkdir(parents=True, exist_ok=True)
        img = variants_dir / "page_001_v1.png"
        Image.new("RGB", (128, 128), (111, 111, 111)).save(img)
        return {"provider": "fal", "endpoint": "fake", "variants": {1: [str(img)]}, "cache_hits": {1: [False]}, "cache_keys": {1: ["k"]}}

    def fake_choose(paths, qa, style_ref, prev_ref):
        return paths[0], {"passes": True, "best": {"color_drift_vs_style": 0.1, "focus_bleed_overlap": 0.0}}

    monkeypatch.setattr("bookforge.illustration.fal_flux.FalFluxIllustrator.generate_page_variants", fake_generate)
    monkeypatch.setattr("bookforge.pipeline.choose_best_variant", fake_choose)
    monkeypatch.setattr("bookforge.pipeline.KDPPreflight.run", lambda *args, **kwargs: {"status": "PASS"})
    monkeypatch.setattr("bookforge.pipeline.PDFLayoutEngine.__init__", lambda self, font_path: None)
    monkeypatch.setattr("bookforge.pipeline.PDFLayoutEngine.render_interior", lambda *args, **kwargs: Path(args[3]).write_bytes(b"pdf"))
    monkeypatch.setattr("bookforge.pipeline.PDFLayoutEngine.render_cover_wrap", lambda *args, **kwargs: (Path(args[1]).write_bytes(b"pdf"), Path(args[2]).write_bytes(b"pdf")))
    monkeypatch.setattr("bookforge.pipeline.generate_proof_pack", lambda *args, **kwargs: Path(args[0]).write_bytes(b"pdf"))
    monkeypatch.setattr("bookforge.pipeline.generate_html_report", lambda *args, **kwargs: (Path(args[0]) / "review" / "report.html").write_text("ok", encoding="utf-8"))

    res = BookforgePipeline().studio(str(story), str(out), "8.5x8.5", 1, "fal", True)
    assert res["status"] == "PASS"
    assert captured["reference_image"] == lock["approved_character"]
    assert captured["style_image"] == lock["approved_style"]
    production = json.loads((out / "review" / "production_report.json").read_text(encoding="utf-8"))
    assert production["lock_summary"]["locked_references_used"] is True
