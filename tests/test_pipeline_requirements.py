from pathlib import Path

import pytest

from bookforge.layout.presets import COVER_LAYOUT_PRESETS, INTERIOR_LAYOUT_PRESETS, TYPOGRAPHY_PRESETS
from bookforge.pipeline import BookforgePipeline
from bookforge.story.story_spec import parse_story


def test_parse_story_markdown_pages(tmp_path: Path):
    p = tmp_path / "story.md"
    p.write_text("## Page 1\nHello.\n## Page 2\nWorld.", encoding="utf-8")
    parsed = parse_story(p, 2)
    assert parsed["pages"][0]["text"] == "Hello."
    assert parsed["pages"][1]["text"] == "World."


def test_split_story_never_empty(tmp_path: Path):
    p = tmp_path / "story.txt"
    p.write_text("A short line.", encoding="utf-8")
    parsed = parse_story(p, 4)
    assert all(page["text"].strip() for page in parsed["pages"])


def test_approval_schema_contains_presets(tmp_path: Path, monkeypatch):
    import bookforge.layout.pdf as pdf_mod

    def fake_engine_init(self, font_path):
        self.font_name = "Helvetica"
        self.font_path = font_path

    monkeypatch.setattr(pdf_mod.PDFLayoutEngine, "__init__", fake_engine_init)
    monkeypatch.setenv("FAL_KEY", "dummy")
    from bookforge.illustration.fal_flux import FalFluxIllustrator

    def fake_gen(*args, **kwargs):
        out_path = args[2]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image

        Image.new("RGB", (300, 300), (10, 20, 30)).save(out_path)

    monkeypatch.setattr(FalFluxIllustrator, "generate_option_image", fake_gen)
    story = tmp_path / "s.md"
    story.write_text("hello world.", encoding="utf-8")
    out = tmp_path / "out"
    BookforgePipeline().preprod(str(story), str(out), "8.5x8.5", 2, 2)
    approval = __import__("json").loads((out / "preprod" / "APPROVAL.json").read_text(encoding="utf-8"))
    assert "interior_layout_preset" in approval and "typography_preset" in approval and "cover_layout_preset" in approval


def test_lock_fails_when_not_approved(tmp_path: Path):
    preprod = tmp_path / "preprod"
    preprod.mkdir(parents=True)
    (preprod / "APPROVAL.json").write_text('{"approved": false}', encoding="utf-8")
    with pytest.raises(RuntimeError):
        BookforgePipeline().lock(str(tmp_path))


def test_layout_presets_exist_and_have_required_fields():
    assert len(INTERIOR_LAYOUT_PRESETS) >= 4
    assert len(TYPOGRAPHY_PRESETS) >= 3
    assert len(COVER_LAYOUT_PRESETS) >= 4
    assert all(p.panel_position in {"top", "bottom"} for p in INTERIOR_LAYOUT_PRESETS)


def test_pdf_layout_no_alpha_usage():
    src = Path("bookforge/layout/pdf.py").read_text(encoding="utf-8")
    assert "alpha=" not in src


def test_cover_dimension_math(tmp_path: Path, monkeypatch):
    import bookforge.layout.pdf as pdf_mod

    def fake_engine_init(self, font_path):
        self.font_name = "Helvetica"
        self.font_path = font_path

    monkeypatch.setattr(pdf_mod.PDFLayoutEngine, "__init__", fake_engine_init)
    from bookforge.layout.pdf import PDFLayoutEngine
    from PIL import Image

    eng = PDFLayoutEngine(Path("assets/fonts/NotoSans-Regular.ttf"))
    eng.font_name = "Helvetica"
    cov = tmp_path / "cover.pdf"
    guides = tmp_path / "guides.pdf"
    art = tmp_path / "art.png"
    style = tmp_path / "style.png"
    Image.new("RGB", (1000, 1000), (255, 0, 0)).save(art)
    Image.new("RGB", (1000, 1000), (0, 0, 255)).save(style)
    out = eng.render_cover_wrap(cov, guides, 8.5, 8.5, 0.125, 0.375, 24, 0.1, "T", "A", art, style, {"title_placement": "front_top", "author_placement": "front_bottom", "back_background_mode": "solid", "barcode_box_in": [0.6, 0.6, 2.0, 1.2]}, {"spine_text_min_in": 0.1})
    assert out["cover_w_in"] == pytest.approx(2 * 8.5 + 0.1 + 2 * 0.125)


def test_lock_persists_fal_endpoint(tmp_path: Path):
    preprod = tmp_path / "preprod"
    vv = preprod / "bible_variants" / "v1"
    (preprod / "character_options").mkdir(parents=True)
    (preprod / "style_options").mkdir(parents=True)
    (preprod / "cover_options").mkdir(parents=True)
    vv.mkdir(parents=True)

    for folder, name in [("character_options", "char_v1.png"), ("style_options", "style_v1.png"), ("cover_options", "cover_v1.png")]:
        path = preprod / folder / name
        from PIL import Image

        Image.new("RGB", (100, 100), (10, 10, 10)).save(path)

    (vv / "character_bible.json").write_text("{}", encoding="utf-8")
    (vv / "style_bible.json").write_text('{"visual_mode":"storybook","palette":["#111111"]}', encoding="utf-8")
    (vv / "prompt_prefix.txt").write_text("prefix", encoding="utf-8")
    (vv / "negative_prompt.txt").write_text("negative", encoding="utf-8")

    approval = {
        "approved": True,
        "approved_variant": 1,
        "approved_character": "char_v1.png",
        "approved_style": "style_v1.png",
        "approved_cover": "cover_v1.png",
        "interior_layout_preset": INTERIOR_LAYOUT_PRESETS[0].id,
        "typography_preset": TYPOGRAPHY_PRESETS[0].id,
        "cover_layout_preset": COVER_LAYOUT_PRESETS[0].id,
        "paper_thickness_in": 0.002252,
        "spine_min_in": 0.06,
        "image_steps": 6,
        "page_variants": 2,
        "fal_endpoint": "https://fal.run/fal-ai/flux/dev",
    }
    import json

    (preprod / "APPROVAL.json").write_text(json.dumps(approval), encoding="utf-8")
    BookforgePipeline().lock(str(tmp_path), page_count=8)
    lock = json.loads((tmp_path / "LOCK.json").read_text(encoding="utf-8"))
    assert lock["fal"]["endpoint"] == "https://fal.run/fal-ai/flux/dev"


def test_pdf_engine_requires_font(tmp_path: Path):
    from bookforge.layout.pdf import PDFLayoutEngine

    with pytest.raises(RuntimeError, match="Font embed failed"):
        PDFLayoutEngine(tmp_path / "missing.ttf")


def test_cover_bleed_background_fills(tmp_path: Path, monkeypatch):
    import bookforge.layout.pdf as pdf_mod

    def fake_engine_init(self, font_path):
        self.font_name = "Helvetica"
        self.font_path = font_path

    monkeypatch.setattr(pdf_mod.PDFLayoutEngine, "__init__", fake_engine_init)
    from bookforge.layout.pdf import PDFLayoutEngine
    from PIL import Image

    eng = PDFLayoutEngine(Path("assets/fonts/NotoSans-Regular.ttf"))
    eng.font_name = "Helvetica"
    cov = tmp_path / "cover.pdf"
    guides = tmp_path / "guides.pdf"
    art = tmp_path / "art.png"
    style = tmp_path / "style.png"
    Image.new("RGB", (1000, 1000), (255, 0, 0)).save(art)
    Image.new("RGB", (1000, 1000), (0, 0, 255)).save(style)

    out = eng.render_cover_wrap(
        cov, guides, 8.5, 8.5, 0.125, 0.375, 24, 0.1, "T", "A", art, style,
        {"title_placement": "front_top", "author_placement": "front_bottom", "back_background_mode": "solid", "barcode_box_in": [0.6, 0.6, 2.0, 1.2]},
        {"spine_text_min_in": 0.1},
    )
    assert out["back_background_rect_pt"] == pytest.approx([0, 0, out["cover_w_in"] * 72, out["cover_h_in"] * 72])
    front_x, _, front_w, front_h = out["front_art_rect_pt"]
    spine_x, _, spine_w, _ = out["spine_rect_pt"]
    assert front_x + 1e-6 >= spine_x + spine_w
    assert front_w == pytest.approx((8.5 + 0.125) * 72)
    assert front_h == pytest.approx(out["cover_h_in"] * 72)
