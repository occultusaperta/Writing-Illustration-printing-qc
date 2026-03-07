import json
from pathlib import Path

from bookforge.page_architecture.constants import DPI, FULL_HEIGHT_PX, FULL_WIDTH_PX
from bookforge.page_architecture.energy import target_energy_curve
from bookforge.page_architecture.sequencing import plan_architecture_sequence
from bookforge.page_architecture.templates import architecture_templates
from bookforge.pipeline import BookforgePipeline


def test_constants_and_templates_present():
    assert DPI == 300
    assert FULL_WIDTH_PX > 0 and FULL_HEIGHT_PX > 0
    variants = architecture_templates()
    kinds = {v.architecture_type.value for v in variants}
    for needed in {
        "full_bleed_spread",
        "full_bleed_single",
        "vignette",
        "spot_illustration",
        "panel_sequence",
        "wordless_spread",
        "text_dominant",
        "inset_composite",
    }:
        assert needed in kinds


def test_energy_curve_and_sequence_constraints():
    pages = [
        {"page_number": 1, "narrative_function": "opening"},
        {"page_number": 2, "narrative_function": "rising_action"},
        {"page_number": 3, "narrative_function": "climax"},
        {"page_number": 4, "narrative_function": "resolution"},
    ]
    curve = target_energy_curve([p["narrative_function"] for p in pages], genre="fantasy")
    assert len(curve) == 4 and curve[2] > curve[0]
    sequence, report = plan_architecture_sequence(pages, beam_width=4)
    assert len(sequence) == 4
    assert report["sequence_length"] == 4
    for a, b in zip(sequence, sequence[1:]):
        assert not (a.selected_architecture_type.value == "wordless_spread" and b.selected_architecture_type.value == "wordless_spread")


def test_preprod_architecture_artifacts_and_backward_compat(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BOOKFORGE_COLOR_SCRIPT", "false")
    monkeypatch.setenv("BOOKFORGE_PAGE_ARCHITECTURE", "true")
    monkeypatch.setenv("FAL_KEY", "x")
    story = tmp_path / "story.md"
    out = tmp_path / "out"
    story.write_text("## Page 1\nintro\n## Page 2\naction\n## Page 3\nfinally", encoding="utf-8")

    import bookforge.pipeline as bp

    class FakeIll:
        def generate_option_image(self, *args, **kwargs):
            from PIL import Image

            p = args[1]
            p.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (64, 64), (10, 20, 30)).save(p)

    monkeypatch.setattr(bp, "resolve_image_provider", lambda *_args, **_kwargs: (FakeIll(), "fake"))
    monkeypatch.setattr(bp, "generate_contact_sheet", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bp.PDFLayoutEngine, "render_interior_preview", lambda *a, **k: None)
    monkeypatch.setattr(bp.PDFLayoutEngine, "render_cover_preview", lambda *a, **k: None)

    res = BookforgePipeline().preprod(str(story), str(out), "8.5x8.5", 3, 1)
    assert res["status"] == "PASS"

    planning = out / "preprod" / "planning"
    assert (planning / "architecture_plan.json").exists()
    assert (planning / "architecture_sequence_report.json").exists()
    plan = json.loads((planning / "architecture_plan.json").read_text(encoding="utf-8"))
    assert len(plan) == 3
    assert not (planning / "emotion_analysis.json").exists()
