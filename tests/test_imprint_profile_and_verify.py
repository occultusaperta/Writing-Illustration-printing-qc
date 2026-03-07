import json
import zipfile
from pathlib import Path

from PIL import Image

from bookforge.illustration.fal_flux import FalFluxIllustrator
from bookforge.layout import pdf as pdf_mod
from bookforge.pipeline import BookforgePipeline
from bookforge.profiles import apply_profile, load_profile
from bookforge.story.story_spec import parse_story


def test_profile_load_apply_merges_into_approval():
    profile = load_profile("ultimate_imprint_8p5x8p5_image_heavy")
    approval = {"image_steps": 6, "qa_profile": "platinum", "nested": {"a": 1}}
    merged = apply_profile(approval, profile)
    assert merged["image_steps"] == 10
    assert merged["qa_profile"] == "diamond"
    assert merged["nested"]["a"] == 1


def test_preprod_profile_writes_overrides(tmp_path: Path, monkeypatch):
    story = tmp_path / "story.md"
    story.write_text("A tiny story for children with simple words.", encoding="utf-8")

    def fake_option_image(self, prompt, out_path, image_size_px, steps):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 64), (120, 100, 80)).save(out_path)

    def fake_contact_sheet(images, out_path, columns=3):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"pdf")

    monkeypatch.setattr(FalFluxIllustrator, "generate_option_image", fake_option_image)
    monkeypatch.setattr("bookforge.pipeline.generate_contact_sheet", fake_contact_sheet)
    monkeypatch.setattr(pdf_mod.PDFLayoutEngine, "__init__", lambda self, font_path: None)
    monkeypatch.setattr(pdf_mod.PDFLayoutEngine, "render_interior_preview", lambda *a, **k: Path(a[1]).parent.mkdir(parents=True, exist_ok=True) or Path(a[1]).write_bytes(b"pdf"))
    monkeypatch.setattr(pdf_mod.PDFLayoutEngine, "render_cover_preview", lambda *a, **k: Path(a[1]).parent.mkdir(parents=True, exist_ok=True) or Path(a[1]).write_bytes(b"pdf"))

    out = tmp_path / "out"
    BookforgePipeline().preprod(str(story), str(out), "8.5x8.5", 6, 2, "ultimate_imprint_8p5x8p5_image_heavy")
    approval = json.loads((out / "preprod" / "APPROVAL.json").read_text(encoding="utf-8"))
    assert approval["interior_layout_preset"] == "imprint_image_heavy_bottom_strip"
    assert approval["typography_preset"] == "imprint_caption_lux"
    assert approval["cover_layout_preset"] == "imprint_auto_title_safe"


def test_fal_key_alias_used_when_primary_absent(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setenv("Fal_key", "alias-key")
    monkeypatch.delenv("fal_key", raising=False)
    captured = {}

    def fake_call(self, prompt, width, height, **kwargs):
        captured["fal_key"] = kwargs["fal_key"]
        from io import BytesIO
        buf = BytesIO()
        Image.new("RGB", (16, 16), (1, 2, 3)).save(buf, format="PNG")
        return buf.getvalue()

    monkeypatch.setattr(FalFluxIllustrator, "_call_fal_flux", fake_call)
    # Use generate_option_image path to exercise env lookup.
    out = Path("/tmp/fal_alias_test.png")
    FalFluxIllustrator().generate_option_image("prompt", out, (16, 16), 1)
    assert captured["fal_key"] == "alias-key"


def test_layout_aware_split_respects_max_words_and_no_empty(tmp_path: Path):
    story = tmp_path / "story.md"
    text = " ".join([f"word{i}" for i in range(1, 61)])
    story.write_text(text, encoding="utf-8")
    parsed = parse_story(story, 4, max_words_per_page_override=15)
    for page in parsed["pages"]:
        words = page["text"].split()
        assert 1 <= len(words) <= 15


def test_verify_command_missing_and_pass(tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    failed = BookforgePipeline().verify(str(out))
    assert failed["status"] == "FAIL"

    required = BookforgePipeline()._expected_package_artifacts()
    for rel in required:
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            if path.name == "preflight_report.json":
                payload = {"status": "PASS"}
            elif path.name == "production_report.json":
                payload = {"post": {"crop_mode": "smart", "director_grade_enabled": True, "tone_curve_preset": "storybook_lux"}, "qa_thresholds": {}, "cache_hit_rate": 1.0, "editorial": {"age_band": "6-8", "artifact_intensity": "light", "readaloud_script_enabled": True}, "dual_audience": {"enabled": False}, "page_turn_tension": {"enabled": False}}
            elif path.name == "book_sequence_report.json":
                payload = {"overall_sequence_score": 0.9, "color_flow_summary_score": 0.9, "architecture_flow_summary_score": 0.9, "energy_curve_summary_score": 0.9, "weak_clusters": [], "saliency_flow_sequence": {}, "dual_audience_summary": {}}
            elif path.name == "reselection_report.json":
                payload = {"config": {}, "considered_pages": [], "eligible_pages": [], "replaced_pages": [], "decisions": [], "sequence_improvement": {}}
            elif path.name == "targeted_regeneration_report.json":
                payload = {"enabled": False, "config": {}, "eligible_targets": [], "decisions": [], "sequence_improvement": {}}
            elif path.name == "storefront_optimization_report.json":
                payload = {"enabled": True, "look_inside": {}, "first_pages_strength_score": 0.5, "summary_score": 0.5, "limitations": []}
            elif path.name == "hidden_world_report.json":
                payload = {"summary_score": 0.5, "warnings": []}
            elif path.name == "character_commercial_report.json":
                payload = {"enabled": True, "summary_score": 0.5, "lead_character_strength_summary": "Moderate", "weakest_pages": [], "strongest_pages": [], "limitations": []}
            elif path.name == "layout_search_report.json":
                payload = {"summary": {}, "pages": []}
            elif path.name == "sequence_optimization_report.json":
                payload = {"enabled": False, "config": {}, "pages_considered": [], "candidate_moves_considered": 0, "accepted_moves": [], "rejected_moves": [], "cap_hit": False, "before_summary": {}, "after_summary": {}, "net_improvement": {}}
            elif path.name == "dual_audience_report.json":
                payload = {"enabled": False, "summary_score": 0.0, "child_channel_summary_score": 0.0, "adult_channel_summary_score": 0.0, "balance_summary_score": 0.0, "strongest_pages": [], "weakest_pages": [], "child_confusion_risk_pages": [], "adult_flatness_risk_pages": [], "imbalance_pages": [], "positive_notes": [], "warnings": [], "limitations": []}
            elif path.name == "page_turn_tension_report.json":
                payload = {"enabled": False, "summary_score": 0.0, "weak_turn_runs": [], "leftward_resistance_runs": [], "over_resolved_turns": [], "strong_turn_pages": [], "warnings": [], "positive_notes": [], "limitations": [], "findings": []}
            else:
                payload = {}
            path.write_text(json.dumps(payload), encoding="utf-8")
        else:
            path.write_bytes(b"x")
    thumbs = out / "review" / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    (thumbs / "cover.jpg").write_bytes(b"x")

    (out / "review" / "editorial_report.md").write_text("x", encoding="utf-8")
    (out / "review" / "readaloud_script.md").write_text("x", encoding="utf-8")

    with zipfile.ZipFile(out / "bookforge_package.zip", "w") as zf:
        for rel in required:
            zf.write(out / rel, arcname=rel)

    passed = BookforgePipeline().verify(str(out))
    assert passed["status"] == "PASS"


def test_new_imprint_presets_present_in_payload():
    from bookforge.layout.presets import presets_payload

    payload = presets_payload()
    assert any(p["id"] == "imprint_image_heavy_bottom_strip" for p in payload["interior_layout_presets"])
    assert any(p["id"] == "imprint_caption_lux" for p in payload["typography_presets"])
    assert any(p["id"] == "imprint_auto_title_safe" for p in payload["cover_layout_presets"])
