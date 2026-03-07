import json
from pathlib import Path

from PIL import Image

from bookforge.camera_language.planning import plan_camera_sequence, write_planning_artifact
from bookforge.camera_language.prompting import build_camera_guidance, build_camera_negative_lines, build_camera_prompt_lines
from bookforge.qc.image_qc import choose_best_variant
from bookforge.review.book_sequence import build_book_sequence_report


def _qa_cfg() -> dict:
    return {
        "min_sharpness": 0.0,
        "min_entropy": 0.0,
        "min_contrast": 0.0,
        "max_border_bar_score": 1.0,
        "max_text_likelihood": 1.0,
        "max_watermark_likelihood": 1.0,
        "max_logo_likelihood": 1.0,
        "max_border_artifact_score": 1.0,
        "max_face_like_regions": 99,
        "min_style_hist_similarity": 0.0,
        "max_page_to_page_hist_drift": 1.0,
        "max_focus_bleed_overlap": 1.0,
    }


def test_camera_planning_constraints_and_artifact(tmp_path: Path):
    pages = [
        {"page_number": 1, "narrative_function": "opening", "text": "Mara arrives."},
        {"page_number": 2, "narrative_function": "rising_action", "text": "Mara and Patch look around."},
        {"page_number": 3, "narrative_function": "climax", "text": "A reveal in the hall."},
        {"page_number": 4, "narrative_function": "ending", "text": "Quiet return home."},
    ]
    plan = plan_camera_sequence(pages)
    assert plan.pages[0].shot_type.value == "establishing_wide"
    assert plan.pages[-1].shot_type.value in {"establishing_wide", "medium_interaction", "closeup_emotion"}
    assert all(plan.pages[i].shot_type != plan.pages[i - 1].shot_type for i in range(1, len(plan.pages)))

    out = tmp_path / "preprod" / "planning"
    write_planning_artifact(out, plan)
    payload = json.loads((out / "camera_sequence_plan.json").read_text(encoding="utf-8"))
    assert payload["pages"][0]["shot_type"] == "establishing_wide"


def test_camera_prompt_guidance_and_noop_behavior():
    assert build_camera_guidance(None) == {}
    assert build_camera_prompt_lines({}) == []
    assert build_camera_negative_lines({}) == []

    g = build_camera_guidance({"shot_type": "worms_eye", "target_angle_class": "low_angle", "target_subject_focus": "Mara"})
    lines = build_camera_prompt_lines(g)
    assert any("Camera shot plan" in x for x in lines)
    assert "avoid tight crop that breaks establishing composition" not in build_camera_negative_lines(g)


def test_candidate_metadata_attaches_shot_score(tmp_path: Path):
    img = tmp_path / "img.png"
    style = tmp_path / "style.png"
    Image.new("RGB", (96, 96), (120, 130, 140)).save(img)
    Image.new("RGB", (96, 96), (120, 130, 140)).save(style)

    _, qa = choose_best_variant(
        [img],
        _qa_cfg(),
        style,
        None,
        page_number=1,
        page_color_spec={},
        master_palette={},
        shot_plan_entry={
            "shot_type": "closeup_emotion",
            "target_distance_class": "close",
            "target_angle_class": "level",
        },
    )
    meta = qa["variants"][0]["metadata"]
    assert "shot_adherence_score" in meta
    assert 0.0 <= meta["shot_adherence_score"]["composite_score"] <= 1.0


def test_camera_sequence_diagnostics_warnings():
    camera_plan = {
        1: {"page_number": 1, "shot_type": "medium_interaction", "target_distance_class": "medium", "narrative_reason": "opening beat"},
        2: {"page_number": 2, "shot_type": "medium_interaction", "target_distance_class": "medium", "narrative_reason": "rising_action beat"},
        3: {"page_number": 3, "shot_type": "medium_interaction", "target_distance_class": "medium", "narrative_reason": "climax beat"},
        4: {"page_number": 4, "shot_type": "dutch_tilt", "target_distance_class": "medium", "narrative_reason": "ending beat"},
    }
    report = build_book_sequence_report(
        page_count=4,
        color_script={},
        architecture_plan=[],
        applied_arch_rows=[],
        qa_attempts=[],
        premium_qc={},
        camera_sequence_plan=camera_plan,
    )
    assert report.camera_sequence.medium_run_warnings
    assert report.camera_sequence.opening_warnings
    assert report.camera_sequence.ending_warnings


def test_preprod_writes_camera_sequence_artifact(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BOOKFORGE_COLOR_SCRIPT", "false")
    monkeypatch.setenv("BOOKFORGE_PAGE_ARCHITECTURE", "false")
    monkeypatch.setenv("BOOKFORGE_CAMERA_LANGUAGE", "true")
    monkeypatch.setenv("FAL_KEY", "x")

    out = tmp_path / "out"
    story = tmp_path / "story.md"
    story.write_text("## Page 1\nMara enters.\n## Page 2\nPatch points.", encoding="utf-8")

    import bookforge.pipeline as bp
    from bookforge.pipeline import BookforgePipeline

    class FakeIll:
        def generate_option_image(self, *args, **kwargs):
            path = args[1]
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (64, 64), (120, 120, 120)).save(path)

    monkeypatch.setattr(bp, "resolve_image_provider", lambda *_a, **_k: (FakeIll(), "fake"))
    monkeypatch.setattr(bp, "generate_contact_sheet", lambda *_a, **_k: None)
    monkeypatch.setattr(bp.PDFLayoutEngine, "render_interior_preview", lambda *a, **k: None)
    monkeypatch.setattr(bp.PDFLayoutEngine, "render_cover_preview", lambda *a, **k: None)

    res = BookforgePipeline().preprod(str(story), str(out), "8.5x8.5", 2, 1)
    assert res["status"] == "PASS"
    assert (out / "preprod" / "planning" / "camera_sequence_plan.json").exists()
