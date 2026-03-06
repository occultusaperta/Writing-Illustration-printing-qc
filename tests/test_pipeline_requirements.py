import json
from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.colors import black, white

from bookforge.layout.pdf import PDFLayoutEngine
from bookforge.layout.presets import COVER_LAYOUT_PRESETS, INTERIOR_LAYOUT_PRESETS, TYPOGRAPHY_PRESETS
from bookforge.pipeline import BookforgePipeline
from bookforge.qc.image_qc import choose_best_variant
from bookforge.story.story_spec import parse_story
from bookforge.story.storyboard import generate_storyboard
from bookforge.pipeline import _apply_checkpoint_overrides, _parse_spread_pairs


def test_storyboard_schema_has_required_fields(tmp_path: Path):
    story = tmp_path / "story.md"
    story.write_text("## Page 1\nMira smiles in the forest.\n## Page 2\nMira explores town.", encoding="utf-8")
    parsed = parse_story(story, 2)
    sb = generate_storyboard(parsed, variants=2, use_openai_if_available=False)
    assert isinstance(sb["pages"], list) and len(sb["pages"]) == 2
    required = {"page_number", "summary", "characters_present", "emotion", "props", "setting", "camera", "composition", "continuity_tokens"}
    assert required.issubset(set(sb["pages"][0].keys()))


def test_image_qc_prefers_sharper_image(tmp_path: Path):
    from bookforge.qc.image_qc import sharpness

    blurry = tmp_path / "blurry.png"
    sharp = tmp_path / "sharp.png"
    Image.new("RGB", (120, 120), (120, 120, 120)).save(blurry)
    img = Image.new("RGB", (120, 120), (120, 120, 120))
    for x in range(20, 100):
        img.putpixel((x, 60), (0, 0, 0))
        img.putpixel((60, x), (0, 0, 0))
    img.save(sharp)
    assert sharpness(sharp) > sharpness(blurry)



def test_composite_reference_outputs_png(tmp_path: Path):
    char = tmp_path / "char.png"
    style = tmp_path / "style.png"
    out = tmp_path / "composite.png"
    Image.new("RGB", (100, 120), (200, 100, 50)).save(char)
    Image.new("RGB", (140, 120), (20, 20, 200)).save(style)

    from bookforge.illustration.fal_flux import FalFluxIllustrator

    FalFluxIllustrator().build_composite_reference(char, style, out)
    assert out.exists() and out.suffix == ".png"


def test_spread_split_dimensions(tmp_path: Path):
    spread = tmp_path / "spread.png"
    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    Image.new("RGB", (800, 400), (10, 20, 30)).save(spread)
    BookforgePipeline()._split_spread(spread, left, right)
    with Image.open(left) as l, Image.open(right) as r:
        assert l.size == (400, 400)
        assert r.size == (400, 400)


def test_spread_validation_rejects_overlaps_and_nonconsecutive_pairs():
    with pytest.raises(RuntimeError):
        _parse_spread_pairs({"mode": "custom_pairs", "pairs": [[2, 4]]}, 10)
    with pytest.raises(RuntimeError):
        _parse_spread_pairs({"mode": "custom_pairs", "pairs": [[2, 3], [3, 4]]}, 10)


def test_checkpoint_flow_template_written(tmp_path: Path):
    out = tmp_path / "out"
    (out / "images").mkdir(parents=True)
    lock = {
        "checkpoint": {"pages": 2},
        "fal": {"endpoint": "x", "steps": 1, "page_variants": 1},
        "approved_character": str(tmp_path / "char.png"),
        "approved_style": str(tmp_path / "style.png"),
        "locked_prompt_prefix": "p",
        "locked_negative_prompt": "n",
        "storyboard": {"pages": []},
        "print": {"required_pixels": [128, 128]},
        "approved_variant": 1,
        "qa": {"max_regen_rounds": 0, "max_focus_bleed_overlap": 1.0},
        "seeds": {"per_page_seed": {"1": 1, "2": 2}},
    }
    Image.new("RGB", (64, 64), (1, 1, 1)).save(tmp_path / "char.png")
    Image.new("RGB", (64, 64), (2, 2, 2)).save(tmp_path / "style.png")
    (out / "LOCK.json").write_text(json.dumps(lock), encoding="utf-8")

    story = tmp_path / "story.md"
    story.write_text("Hello world.", encoding="utf-8")

    from bookforge.illustration.fal_flux import FalFluxIllustrator

    def fake_generate(*args, **kwargs):
        variants_dir = args[2]
        variants_dir.mkdir(parents=True, exist_ok=True)
        p = variants_dir / "page_001_v1.png"
        Image.new("RGB", (128, 128), (3, 3, 3)).save(p)
        return {"variants": {1: [str(p)], 2: [str(p)]}}

    FalFluxIllustrator.generate_page_variants = fake_generate
    res = BookforgePipeline().studio(str(story), str(out), "8.5x8.5", 2, "fal", True)
    assert res["status"] == "STOPPED_CHECKPOINT"
    assert (out / "CHECKPOINT.json").exists()


def test_checkpoint_overrides_apply_to_prompt_building():
    prompts = [{"page_number": 3, "prompt": "base"}, {"page_number": 7, "prompt": "scene"}]
    merged, summary = _apply_checkpoint_overrides(
        prompts,
        {
            "approved": True,
            "notes": "ok",
            "overrides": {"page_prompt_addendum": {"3": "make it brighter"}, "force_regen": [7], "variant_preference": {"7": 2}},
        },
    )
    assert merged[0]["prompt"].endswith("make it brighter")
    assert summary["force_regen"] == [7]
    assert summary["variant_preference"] == {"7": 2}


def test_cover_title_color_choice(tmp_path: Path):
    engine = PDFLayoutEngine.__new__(PDFLayoutEngine)
    bright = tmp_path / "bright.png"
    dark = tmp_path / "dark.png"
    Image.new("RGB", (200, 120), (240, 240, 240)).save(bright)
    Image.new("RGB", (200, 120), (20, 20, 20)).save(dark)
    bright_main, _ = engine._choose_text_colors(bright, (0, 0, 200, 120))
    dark_main, _ = engine._choose_text_colors(dark, (0, 0, 200, 120))
    assert bright_main == black
    assert dark_main == white


def test_paragraph_layout_no_alpha():
    src = Path("bookforge/layout/pdf.py").read_text(encoding="utf-8")
    assert "Paragraph(" in src
    assert "alpha=" not in src


def test_package_includes_ultimate_imprint_artifacts(tmp_path: Path):
    out = tmp_path / "out"
    (out / "review" / "thumbs").mkdir(parents=True, exist_ok=True)

    required_files = [
        "interior.pdf",
        "cover_wrap.pdf",
        "cover_guides.pdf",
        "preflight_report.json",
        "LOCK.json",
        "prompts.json",
        "review/contact_sheet.pdf",
        "review/qa_report.json",
        "review/proof_pack.pdf",
        "review/production_report.json",
        "review/quality_summary.md",
        "review/report.html",
        "review/thumbs/cover.jpg",
        "review/thumbs/page_001.jpg",
    ]
    for rel in required_files:
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")

    zip_path = out / "bookforge_package.zip"
    BookforgePipeline()._create_package(zip_path, out)

    import zipfile

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())

    expected = {
        "interior.pdf",
        "cover_wrap.pdf",
        "cover_guides.pdf",
        "preflight_report.json",
        "LOCK.json",
        "prompts.json",
        "review/contact_sheet.pdf",
        "review/qa_report.json",
        "review/proof_pack.pdf",
        "review/production_report.json",
        "review/quality_summary.md",
        "review/report.html",
        "review/thumbs/cover.jpg",
        "review/thumbs/page_001.jpg",
    }
    assert expected.issubset(names)
