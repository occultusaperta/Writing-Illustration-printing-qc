import json
from pathlib import Path

from PIL import Image, ImageDraw

from bookforge.layout.presets import get_preset
from bookforge.qc.visual_integrity import border_artifact_score, text_likelihood
from bookforge.review.proof_pack import generate_proof_pack
from bookforge.story.back_matter import generate_blurb_options
from bookforge.story.prompt_compiler import compile_prompt
from bookforge.pipeline import _seed_from_lock


def test_visual_integrity_flags_text(tmp_path: Path):
    p = tmp_path / "t.png"
    img = Image.new("RGB", (320, 220), "white")
    d = ImageDraw.Draw(img)
    d.text((10, 180), "HELLO WATERMARK", fill="black")
    img.save(p)
    assert text_likelihood(p) > 0.15


def test_visual_integrity_border_artifact(tmp_path: Path):
    p = tmp_path / "b.png"
    img = Image.new("RGB", (320, 220), (120, 120, 120))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 319, 25), fill=(0, 0, 0))
    img.save(p)
    assert border_artifact_score(p) > 0.25


def test_prompt_compiler_camera_templates():
    lock = {"locked_prompt_prefix": "LOCK", "locked_negative_prompt": "NEG"}
    wide = compile_prompt(lock, "Mira runs.", {"camera": "wide"})
    close = compile_prompt(lock, "Mira smiles.", {"camera": "close"})
    assert "Environment-first composition" in wide
    assert "Expression clarity" in close


def test_back_matter_blurb_options_fallback_nonempty(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = generate_blurb_options({"title": "A", "pages": [{"page_number": 1, "text": "A short tale."}]})
    assert out["blurbs"] and out["subtitles"]


def test_cover_blurb_box_does_not_overlap_barcode():
    preset = get_preset("front_title_top_back_blurb", "cover")
    bx, by, bw, bh = preset["barcode_box_in"]
    x, y, w, h = preset["blurb_box_in"]
    no_overlap = (x + w <= bx) or (x >= bx + bw) or (y + h <= by) or (y >= by + bh)
    assert no_overlap


def test_proof_pack_generation(tmp_path: Path):
    cover = tmp_path / "cover.png"
    Image.new("RGB", (300, 400), "blue").save(cover)
    pages = []
    for i in range(3):
        p = tmp_path / f"p{i}.png"
        Image.new("RGB", (300, 400), (100 + i, 120, 130)).save(p)
        pages.append(p)
    out = tmp_path / "proof_pack.pdf"
    generate_proof_pack(out, cover, pages, {"trim": "8.5x8.5", "dpi": 300}, [{"page": 1, "attempt": 1, "passes": True}])
    assert out.exists() and out.stat().st_size > 0


def test_seed_plan_deterministic():
    a = _seed_from_lock("T", "A", 1)
    b = _seed_from_lock("T", "A", 1)
    c = _seed_from_lock("T", "A", 2)
    assert a == b and a != c
