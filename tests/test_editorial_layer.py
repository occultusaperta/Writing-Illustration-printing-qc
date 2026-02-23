import json
from pathlib import Path

from PIL import Image

from bookforge.editorial.dual_address import analyze_dual_address
from bookforge.editorial.eye_flow import verify_focus_not_covered_by_panel
from bookforge.editorial.hidden_artifacts import apply_artifact_plan_to_pages, propose_artifact_options
from bookforge.editorial.hook_packaging import generate_hook_pack
from bookforge.editorial.page_turns import build_page_turn_map
from bookforge.editorial.readaloud_script import generate_readaloud_script
from bookforge.editorial.rhythm_audit import audit_rhythm_and_rhyme
from bookforge.pipeline import BookforgePipeline


def test_dual_address_outputs_keys():
    out = analyze_dual_address("Can you find the moon? They laugh and then feel safe at home.", "6-8")
    assert "child_engagement_signals" in out
    assert "adult_gatekeeper_signals" in out
    assert "read_aloud_fatigue_risk" in out


def test_rhythm_audit_scores_and_flags():
    txt = "I run to the sun.\nI jump and I bump and I thump.\nA very very very long line that may become somewhat tiring to read aloud in one breath."
    out = audit_rhythm_and_rhyme(txt)
    assert 0 <= out["read_aloud_smoothness_score"] <= 100
    assert isinstance(out["flagged_lines"], list)


def test_hook_pack_nonempty_fallback(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = generate_hook_pack("Milo loses a map but finds courage.", "6-8")
    assert out["one_sentence_premise"]
    assert len(out["title_candidates"]) == 10


def test_page_turn_map_has_hooks_and_payoffs():
    pages = [{"page_number": 1, "text": "A"}, {"page_number": 2, "text": "B"}]
    out = build_page_turn_map(pages, "6-8")
    assert out[0]["recto_hook"]
    assert out[0]["verso_payoff"]


def test_hidden_artifacts_produces_multiple_types_not_just_one():
    options = propose_artifact_options("6-8", {"motif": "star"})
    plan = options["plans"][1]
    pages = [{"page_number": i, "text": f"p{i}"} for i in range(1, 9)]
    mapped = apply_artifact_plan_to_pages(plan, pages)
    types = {m["artifact_type"] for m in mapped}
    assert len(types) > 1


def test_eye_flow_warns_when_focus_in_panel():
    out = verify_focus_not_covered_by_panel((0.5, 0.9), (0.0, 0.8, 1.0, 1.0))
    assert out["status"] == "warn"


def test_readaloud_script_contains_pauses():
    pages = [{"page_number": 1, "text": "Hello there."}]
    script = generate_readaloud_script(pages, {"flagged_lines": []}, [{"page_number": 1, "page_turn_phrase": "...until"}])
    assert "pause" in script.lower()


def test_lock_persists_editorial_fields(tmp_path: Path):
    out = tmp_path / "out"
    preprod = out / "preprod"
    (preprod / "bible_variants" / "v1").mkdir(parents=True)
    (preprod / "character_options").mkdir(parents=True)
    (preprod / "style_options").mkdir(parents=True)
    (preprod / "cover_options").mkdir(parents=True)
    (preprod / "editorial").mkdir(parents=True)
    (preprod / "storyboard.json").write_text(json.dumps({"pages": []}), encoding="utf-8")
    (preprod / "story_parsed.json").write_text(json.dumps({"title": "T", "author": "A", "pages": [{"page_number": 1, "text": "x"}]}), encoding="utf-8")
    (preprod / "bible_variants" / "v1" / "character_bible.json").write_text("{}", encoding="utf-8")
    (preprod / "bible_variants" / "v1" / "style_bible.json").write_text('{"palette":["#111"]}', encoding="utf-8")
    (preprod / "bible_variants" / "v1" / "prompt_prefix.txt").write_text("x", encoding="utf-8")
    (preprod / "bible_variants" / "v1" / "negative_prompt.txt").write_text("x", encoding="utf-8")
    for folder, name in [("character_options", "character_turnaround_v1.png"), ("style_options", "style_frame_v1.png"), ("cover_options", "cover_concept_v1.png")]:
        Image.new("RGB", (10, 10), (1, 2, 3)).save(preprod / folder / name)
    (preprod / "editorial" / "artifact_plan_options.json").write_text(json.dumps({"plans": [{"plan_id": "plan_1_light", "artifact_sequence": ["hidden_motif"]}]}), encoding="utf-8")
    (preprod / "editorial" / "hook_pack.json").write_text(json.dumps({"one_sentence_premise": "P"}), encoding="utf-8")
    (preprod / "editorial" / "page_turn_map.json").write_text(json.dumps([]), encoding="utf-8")

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
        "qa_profile": "platinum",
        "max_regen_rounds": 1,
        "min_sharpness": 1,
        "min_entropy": 1,
        "min_contrast": 1,
        "max_border_bar_score": 1,
        "min_style_hist_similarity": 0,
        "max_page_to_page_hist_drift": 1,
        "max_text_likelihood": 1,
        "max_watermark_likelihood": 1,
        "max_logo_likelihood": 1,
        "max_border_artifact_score": 1,
        "max_face_like_regions": 99,
        "max_focus_bleed_overlap": 1,
        "min_brightness_p05": 0,
        "max_brightness_p95": 255,
        "max_out_of_gamut_risk": 1,
        "max_book_palette_drift": 1,
        "fal_endpoint": "x",
        "checkpoint_pages": 0,
        "spread_mode": "none",
        "spread_pairs": [],
        "pdf_image_embed": "jpeg",
        "pdf_jpeg_quality": 90,
        "preflight_max_interior_mb": 300,
        "artifact_plan_id": "plan_1_light",
        "artifact_intensity": "light",
        "readaloud_script_enabled": True,
        "trade_dress_lock_enabled": True,
        "age_band": "6-8",
        "editorial_mode": True,
    }
    (preprod / "APPROVAL.json").write_text(json.dumps(approval), encoding="utf-8")
    BookforgePipeline().lock(str(out), "8.5x8.5", 1)
    lock = json.loads((out / "LOCK.json").read_text(encoding="utf-8"))
    assert "editorial" in lock
    assert lock["editorial"]["artifact_intensity"] == "light"


def test_verify_warns_not_fails_when_editorial_missing(tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir(parents=True)
    required = BookforgePipeline()._expected_package_artifacts()
    for rel in required:
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            payload = {"status": "PASS"} if path.name == "preflight_report.json" else {"post": {"crop_mode": "smart", "director_grade_enabled": True, "tone_curve_preset": "storybook_lux"}, "qa_thresholds": {}, "cache_hit_rate": 1.0}
            path.write_text(json.dumps(payload), encoding="utf-8")
        else:
            path.write_bytes(b"x")
    (out / "review" / "thumbs").mkdir(parents=True, exist_ok=True)
    (out / "review" / "thumbs" / "cover.jpg").write_bytes(b"x")
    result = BookforgePipeline().verify(str(out))
    assert result["status"] == "WARN"
    assert any("editorial_report" in w for w in result["warnings"])
