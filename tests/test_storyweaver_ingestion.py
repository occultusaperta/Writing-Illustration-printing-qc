import json
from pathlib import Path

from PIL import Image

from bookforge.layout.pdf import extract_typography_directives
from bookforge.pipeline import BookforgePipeline
from bookforge.story.story_spec import parse_story
from bookforge.ui.utils import detect_storyweaver_summary


def _sample_storyweaver() -> str:
    return """[Pages 1–2] FULL DOUBLE-PAGE SPREAD
# GRRRRROWL
The cave shakes.
[ILLUSTRATION NOTE: Must include a tiny gold key hidden in moss.]
[PAGE TURN — The sound grows louder.]

[Pages 3–4]
The Grumblebeast stomps in.&nbsp;&nbsp;Sleep drifts away.
*sleep*
[ILLUSTRATION NOTE: Required hidden detail: moon charm on backpack.]

[Read-Aloud Notes]
Beat 1: whisper then roar.

[Parent's Companion]
THE LINE THAT SELLS THE BOOK: "A roar-sized tale about feelings."
One-sentence pitch: A grumpy creature learns to breathe and belong.
"""


def test_storyweaver_parser_extracts_pages_spreads_and_extras(tmp_path: Path):
    story = tmp_path / "story.md"
    story.write_text(_sample_storyweaver(), encoding="utf-8")

    parsed = parse_story(story, pages=24)

    assert parsed["declared_pages"] == 4
    assert [1, 2] in parsed["spread_pairs"]
    assert parsed["metadata"]["storyweaver_detected"] is True
    assert "ILLUSTRATION NOTE" not in parsed["pages"][0]["printed_markdown"]
    assert parsed["pages"][0]["illustration_notes"]
    extra_names = {x["section"] for x in parsed["extras"]}
    assert "Read-Aloud Notes" in extra_names
    assert "Parent's Companion" in extra_names


def test_typography_directive_detection():
    directives = extract_typography_directives("# GRRRRROWL\nS L E E P\n*tiny*")
    kinds = {d["kind"] for d in directives}
    assert "headline" in kinds
    assert "spaced" in kinds
    assert "tiny" in kinds


def test_lock_uses_declared_pages_over_cli_override(tmp_path: Path):
    out = tmp_path / "out"
    preprod = out / "preprod"
    (preprod / "bible_variants" / "v1").mkdir(parents=True, exist_ok=True)
    (preprod / "character_options").mkdir(parents=True, exist_ok=True)
    (preprod / "style_options").mkdir(parents=True, exist_ok=True)
    (preprod / "cover_options").mkdir(parents=True, exist_ok=True)

    for rel in [
        preprod / "bible_variants" / "v1" / "character_bible.json",
        preprod / "bible_variants" / "v1" / "style_bible.json",
    ]:
        rel.write_text("{}", encoding="utf-8")
    (preprod / "bible_variants" / "v1" / "prompt_prefix.txt").write_text("prefix", encoding="utf-8")
    (preprod / "bible_variants" / "v1" / "negative_prompt.txt").write_text("neg", encoding="utf-8")

    for folder, name in [
        (preprod / "character_options", "character_turnaround_v1.png"),
        (preprod / "style_options", "style_frame_v1.png"),
        (preprod / "cover_options", "cover_concept_v1.png"),
    ]:
        Image.new("RGB", (20, 20), (10, 10, 10)).save(folder / name)

    (preprod / "storyboard.json").write_text(json.dumps({"pages": []}), encoding="utf-8")
    (preprod / "story_parsed.json").write_text(
        json.dumps({"title": "T", "author": "A", "metadata": {"declared_pages": 32}, "spread_pairs": [[1, 2]]}),
        encoding="utf-8",
    )
    approval = {
        "approved": True,
        "approved_variant": 1,
        "approved_character": "character_turnaround_v1.png",
        "approved_style": "style_frame_v1.png",
        "approved_cover": "cover_concept_v1.png",
        "interior_layout_preset": "cinematic_panel_bottom",
        "typography_preset": "storybook_large",
        "cover_layout_preset": "front_title_top_back_blurb",
        "paper_thickness_in": 0.002252,
        "spine_min_in": 0.06,
        "image_steps": 6,
        "page_variants": 2,
        "spread_mode": "none",
        "spread_pairs": [],
    }
    approval.update(
        {
            "qa_profile": "platinum",
            "max_regen_rounds": 2,
            "min_sharpness": 120.0,
            "min_entropy": 3.5,
            "min_contrast": 25.0,
            "max_border_bar_score": 0.25,
            "min_style_hist_similarity": 0.65,
            "max_page_to_page_hist_drift": 0.45,
            "max_text_likelihood": 0.15,
            "max_watermark_likelihood": 0.15,
            "max_logo_likelihood": 0.20,
            "max_border_artifact_score": 0.25,
            "max_face_like_regions": 3,
            "max_focus_bleed_overlap": 0.15,
            "min_brightness_p05": 15,
            "max_brightness_p95": 245,
            "max_out_of_gamut_risk": 0.35,
            "max_book_palette_drift": 0.45,
        }
    )
    (preprod / "APPROVAL.json").write_text(json.dumps(approval), encoding="utf-8")

    result = BookforgePipeline().lock(str(out), size="8.5x8.5", page_count=24)
    assert result["status"] == "PASS"
    lock = json.loads((out / "LOCK.json").read_text(encoding="utf-8"))
    assert lock["print"]["page_count"] == 32


def test_ui_storyweaver_helper_non_streamlit_runtime():
    summary = detect_storyweaver_summary({"metadata": {"storyweaver_detected": True, "declared_pages": 32, "storyweaver_spread_pairs": [[1, 2], [23, 24]]}})
    assert summary["detected"] is True
    assert summary["declared_pages"] == 32
    assert [23, 24] in summary["spreads"]


def test_companion_extraction(tmp_path: Path):
    story = tmp_path / "story.md"
    story.write_text(_sample_storyweaver(), encoding="utf-8")
    parsed = parse_story(story, pages=12)
    companion = parsed["companion"]
    assert "Read-Aloud Notes" in companion
    assert "Parent's Companion" in companion
    assert parsed["metadata"]["cover_copy"]["line_that_sells_the_book"]
