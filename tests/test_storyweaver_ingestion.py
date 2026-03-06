from pathlib import Path

from bookforge.story.story_spec import parse_story
from bookforge.story.storyweaver_parser import parse_storyweaver_markdown
from bookforge.pipeline import _build_prompt_addendum
from bookforge.ui.utils import detect_storyweaver_story_file, should_disable_pages_input


def _sample_path() -> Path:
    return Path("examples/grumblebeast_storyweaver.md")


def test_storyweaver_parser_page_count_32():
    bundle = parse_storyweaver_markdown(_sample_path())
    assert bundle.declared_pages == 32
    assert len(bundle.pages) == 32


def test_storyweaver_parser_detects_spread_23_24():
    bundle = parse_storyweaver_markdown(_sample_path())
    assert (23, 24) in bundle.spreads


def test_illustration_notes_extracted_not_in_printed_text():
    bundle = parse_storyweaver_markdown(_sample_path())
    p = bundle.pages[22]
    assert "typography spaced across the page" in p.illustration_notes
    assert "ILLUSTRATION NOTE" not in p.printed_markdown


def test_companion_sections_extracted_not_interior():
    bundle = parse_storyweaver_markdown(_sample_path())
    assert "Pause on ellipses" in bundle.extras["readaloud_notes"]
    interior = "\n".join(page.printed_markdown for page in bundle.pages)
    assert "Pause on ellipses" not in interior


def test_back_cover_tagline_extracted_from_blockquote():
    bundle = parse_storyweaver_markdown(_sample_path())
    assert bundle.tagline_quote == "Even monsters can learn the sound of sleep."


def test_typography_directives_detect_sleep_and_grrrrrowl():
    bundle = parse_storyweaver_markdown(_sample_path())
    p20 = bundle.pages[18]
    p24 = bundle.pages[22]
    assert any(x.get("type") == "display_word" and x.get("text") == "GRRRRROWL" for x in p20.typography_directives)
    assert any(x.get("type") == "micro_word" and x.get("text") == "sleep" for x in p24.typography_directives)


def test_pipeline_honors_declared_pages_even_if_pages_arg_differs():
    parsed = parse_story(_sample_path(), pages=24)
    assert len(parsed["pages"]) == 32
    assert parsed["metadata"]["declared_pages"] == 32


def test_ui_detects_declared_pages_and_disables_pages_input():
    info = detect_storyweaver_story_file(_sample_path())
    assert info["is_storyweaver"] is True
    assert info["declared_pages"] == 32
    assert should_disable_pages_input(info) is True


def test_prompt_addendum_includes_required_hidden_details_first():
    page = {"required_hidden_details": ["a tiny brass key"], "illustration_notes": "Hidden detail: a tiny brass key."}
    text = _build_prompt_addendum(page, {}, {"artifact_type": "micro", "instruction": "add a firefly"}, editorial_mode=False)
    assert text.index("Required hidden details") < text.index("Hidden artifact")
