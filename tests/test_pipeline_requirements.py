import json
from pathlib import Path

import pytest
from PIL import Image

from bookforge.layout.pdf import PDFLayoutEngine
from bookforge.layout.presets import COVER_LAYOUT_PRESETS, INTERIOR_LAYOUT_PRESETS, TYPOGRAPHY_PRESETS
from bookforge.pipeline import BookforgePipeline
from bookforge.qc.image_qc import choose_best_variant, style_hist_similarity
from bookforge.story.story_spec import parse_story
from bookforge.story.storyboard import generate_storyboard


def test_storyboard_schema(tmp_path: Path):
    story = tmp_path / "story.md"
    story.write_text("## Page 1\nMira smiles in the forest.\n## Page 2\nMira explores town.", encoding="utf-8")
    parsed = parse_story(story, 2)
    sb = generate_storyboard(parsed, variants=2, use_openai_if_available=False)
    assert isinstance(sb["pages"], list) and len(sb["pages"]) == 2
    required = {"page_number", "summary", "characters_present", "emotion", "props", "setting", "camera", "composition", "continuity_tokens"}
    assert required.issubset(set(sb["pages"][0].keys()))


def test_image_qc_prefers_sharp(tmp_path: Path):
    blurry = tmp_path / "blurry.png"
    sharp = tmp_path / "sharp.png"
    Image.new("RGB", (120, 120), (120, 120, 120)).save(blurry)
    img = Image.new("RGB", (120, 120), (0, 0, 0))
    for x in range(0, 120, 4):
        for y in range(120):
            img.putpixel((x, y), (255, 255, 255))
    img.save(sharp)
    cfg = {
        "min_sharpness": 0,
        "min_entropy": 0,
        "min_contrast": 0,
        "max_border_bar_score": 1,
        "min_style_hist_similarity": 0,
        "max_page_to_page_hist_drift": 1,
    }
    best, _ = choose_best_variant([blurry, sharp], cfg, None, None)
    assert best == sharp


def test_style_hist_similarity(tmp_path: Path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    c = tmp_path / "c.png"
    Image.new("RGB", (80, 80), (200, 100, 50)).save(a)
    Image.new("RGB", (80, 80), (200, 100, 50)).save(b)
    Image.new("RGB", (80, 80), (20, 20, 200)).save(c)
    assert style_hist_similarity(a, b) > style_hist_similarity(a, c)


def test_spread_split_dimensions(tmp_path: Path):
    spread = tmp_path / "spread.png"
    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    Image.new("RGB", (800, 400), (10, 20, 30)).save(spread)
    BookforgePipeline()._split_spread(spread, left, right)
    with Image.open(left) as l, Image.open(right) as r:
        assert l.size == (400, 400)
        assert r.size == (400, 400)


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


def test_paragraph_layout_no_alpha():
    src = Path("bookforge/layout/pdf.py").read_text(encoding="utf-8")
    assert "Paragraph(" in src
    assert "alpha=" not in src
