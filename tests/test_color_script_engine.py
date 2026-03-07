import json
from pathlib import Path

import pytest

from bookforge.color_script.color_script import plan_color_script
from bookforge.color_script.lab import LABColor, cie_de2000, lab_to_srgb, srgb_to_lab
from bookforge.color_script.master_palette import generate_master_palette, validate_master_palette
from bookforge.color_script.types import EmotionType, MasterPalette
from bookforge.pipeline import BookforgePipeline


def test_lab_roundtrip_and_delta_e_sanity():
    red = srgb_to_lab((255, 0, 0))
    red2 = srgb_to_lab(lab_to_srgb(red))
    blue = srgb_to_lab((0, 0, 255))
    assert cie_de2000(red, red2) < 2.0
    assert cie_de2000(red, blue) > 30.0


def test_emotion_mapping_and_palette_generation():
    pages = [
        {"page_number": 1, "text": "They laugh and smile in warm light."},
        {"page_number": 2, "text": "A secret shadow appears."},
    ]
    analyses, palette, page_specs, transitions = plan_color_script(pages)
    assert analyses[0].emotion == EmotionType.JOY
    assert palette.dominant_colors_lab
    assert len(page_specs) == 2
    assert len(transitions) == 1


def test_palette_validation_rejects_extreme_lightness():
    bad = MasterPalette(
        dominant_emotion=EmotionType.JOY,
        harmony="analogous",  # type: ignore[arg-type]
        base_hue=20.0,
        dominant_colors_lab=[[2.0, 0.0, 0.0]],
        accent_colors_lab=[[95.0, 20.0, 10.0]],
        neutrals_lab=[[90.0, 0.0, 0.0]],
    )
    with pytest.raises(ValueError):
        validate_master_palette(bad)


def test_preprod_writes_color_script_planning_artifacts(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BOOKFORGE_COLOR_SCRIPT", "true")
    monkeypatch.setenv("BOOKFORGE_PAGE_ARCHITECTURE", "false")
    monkeypatch.setenv("FAL_KEY", "x")
    out = tmp_path / "out"
    story = tmp_path / "story.md"
    story.write_text("## Page 1\nquiet soft sleep\n## Page 2\nthen brave smile", encoding="utf-8")

    from bookforge.pipeline import BookforgePipeline

    def _noop(*args, **kwargs):
        p = args[1]
        p.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image

        Image.new("RGB", (64, 64), (120, 130, 140)).save(p)

    import bookforge.pipeline as bp

    class FakeIll:
        def generate_option_image(self, *args, **kwargs):
            return _noop(*args, **kwargs)

    monkeypatch.setattr(bp, "resolve_image_provider", lambda *_args, **_kwargs: (FakeIll(), "fake"))
    monkeypatch.setattr(bp, "generate_contact_sheet", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bp.PDFLayoutEngine, "render_interior_preview", lambda *a, **k: None)
    monkeypatch.setattr(bp.PDFLayoutEngine, "render_cover_preview", lambda *a, **k: None)

    res = BookforgePipeline().preprod(str(story), str(out), "8.5x8.5", 2, 1)
    assert res["status"] == "PASS"
    planning = out / "preprod" / "planning"
    assert (planning / "emotion_analysis.json").exists()
    assert (planning / "master_palette.json").exists()
    assert (planning / "color_script.json").exists()
    payload = json.loads((planning / "color_script.json").read_text(encoding="utf-8"))
    assert len(payload["pages"]) == 2
