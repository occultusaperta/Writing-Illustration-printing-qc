from __future__ import annotations

import json

from PIL import Image, ImageDraw

from bookforge.character_scoring import score_character_commercial
from bookforge.character_scoring.baby_schema import score_baby_schema
from bookforge.character_scoring.sequence import build_character_commercial_report
from bookforge.character_scoring.silhouette import score_character_silhouette
from bookforge.character_scoring.toyetic import score_toyetic
from bookforge.pipeline import BookforgePipeline
from bookforge.qc.image_qc import choose_best_variant


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


def _make_character_image(path):
    img = Image.new("RGB", (256, 256), (242, 236, 228))
    d = ImageDraw.Draw(img)
    d.ellipse((70, 28, 190, 150), fill=(253, 216, 188), outline=(80, 60, 60), width=2)
    d.ellipse((94, 70, 122, 98), fill=(24, 24, 24))
    d.ellipse((138, 70, 166, 98), fill=(24, 24, 24))
    d.rounded_rectangle((104, 107, 154, 120), radius=4, fill=(240, 118, 124))
    d.rounded_rectangle((92, 146, 168, 232), radius=20, fill=(95, 146, 224), outline=(25, 45, 95), width=2)
    img.save(path)


def test_baby_schema_scores_bounded(tmp_path):
    p = tmp_path / "char.png"
    _make_character_image(p)
    res = score_baby_schema(p)
    assert 0.0 <= res.composite_score <= 1.0
    assert 0.0 <= res.confidence <= 1.0
    assert "biometric" in " ".join(res.notes).lower()


def test_silhouette_and_toyetic_scores_bounded(tmp_path):
    p = tmp_path / "char.png"
    _make_character_image(p)
    sil = score_character_silhouette(p)
    toy = score_toyetic(p, sil)
    assert 0.0 <= sil.composite_score <= 1.0
    assert 0.0 <= toy.composite_score <= 1.0
    assert "proxy" in " ".join(sil.notes).lower()


def test_choose_best_variant_attaches_character_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKFORGE_CHARACTER_COMMERCIAL_SCORING", "true")
    style = tmp_path / "style.png"
    p = tmp_path / "v1.png"
    Image.new("RGB", (256, 256), (200, 180, 160)).save(style)
    _make_character_image(p)
    _best, qa = choose_best_variant([p], _qa_cfg(), style_ref=style, prev_ref=None, page_number=1)
    meta = qa["best"].get("metadata", {})
    assert "baby_schema_score" in meta
    assert "toyetic_score" in meta
    assert "silhouette_score" in meta
    assert "character_commercial_score" in meta


def test_feature_flag_disable_safe_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKFORGE_CHARACTER_COMMERCIAL_SCORING", "false")
    style = tmp_path / "style.png"
    p = tmp_path / "v1.png"
    Image.new("RGB", (256, 256), (200, 180, 160)).save(style)
    _make_character_image(p)
    _best, qa = choose_best_variant([p], _qa_cfg(), style_ref=style, prev_ref=None, page_number=1)
    meta = qa["best"].get("metadata", {})
    assert "character_commercial_score" not in meta


def test_character_report_generation_and_disable_behavior(tmp_path):
    p = tmp_path / "v1.png"
    _make_character_image(p)
    score = score_character_commercial(p).to_dict()
    qa_attempts = [{"page": 1, "best": {"metadata": {"character_commercial_score": score, "baby_schema_score": score["baby_schema"], "toyetic_score": score["toyetic"], "silhouette_score": score["silhouette"]}}}]

    rep = build_character_commercial_report(page_count=1, qa_attempts=qa_attempts, enabled=True)
    assert rep.enabled is True
    assert rep.strongest_pages

    rep_off = build_character_commercial_report(page_count=1, qa_attempts=qa_attempts, enabled=False)
    assert rep_off.enabled is False
    assert rep_off.summary_score == 0.0


def test_verify_checks_character_commercial_artifact(tmp_path):
    out = tmp_path / "out"
    required = BookforgePipeline()._expected_package_artifacts()
    for rel in required:
        f = out / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.suffix == ".json":
            if f.name == "preflight_report.json":
                payload = {"status": "PASS"}
            elif f.name == "production_report.json":
                payload = {"post": {"crop_mode": "smart", "director_grade_enabled": True, "tone_curve_preset": "storybook_lux"}, "qa_thresholds": {}, "cache_hit_rate": 1.0, "editorial": {"readaloud_script_enabled": False, "age_band": "6-8", "artifact_intensity": "light"}}
            elif f.name == "book_sequence_report.json":
                payload = {"overall_sequence_score": 0.8, "color_flow_summary_score": 0.8, "architecture_flow_summary_score": 0.8, "energy_curve_summary_score": 0.8, "weak_clusters": [], "saliency_flow_sequence": {}}
            elif f.name == "reselection_report.json":
                payload = {"config": {}, "considered_pages": [], "eligible_pages": [], "replaced_pages": [], "decisions": [], "sequence_improvement": {}}
            elif f.name == "targeted_regeneration_report.json":
                payload = {"enabled": False, "config": {}, "eligible_targets": [], "decisions": [], "sequence_improvement": {}}
            elif f.name == "storefront_optimization_report.json":
                payload = {"enabled": True, "look_inside": {}, "first_pages_strength_score": 0.5, "summary_score": 0.5, "limitations": []}
            elif f.name == "hidden_world_report.json":
                payload = {"summary_score": 0.5, "warnings": []}
            elif f.name == "character_commercial_report.json":
                payload = {"enabled": True, "summary_score": 0.5, "lead_character_strength_summary": "Moderate", "weakest_pages": [], "strongest_pages": [], "limitations": []}
            elif f.name == "layout_search_report.json":
                payload = {"summary": {}, "pages": []}
            elif f.name == "sequence_optimization_report.json":
                payload = {"enabled": False, "config": {}, "pages_considered": [], "candidate_moves_considered": 0, "accepted_moves": [], "rejected_moves": [], "cap_hit": False, "before_summary": {}, "after_summary": {}, "net_improvement": {}}
            else:
                payload = {}
            f.write_text(json.dumps(payload), encoding="utf-8")
        else:
            f.write_bytes(b"x")
    thumbs = out / "review" / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    (thumbs / "cover.jpg").write_bytes(b"x")

    import zipfile

    with zipfile.ZipFile(out / "bookforge_package.zip", "w") as zf:
        for rel in required:
            zf.write(out / rel, arcname=rel)

    res = BookforgePipeline().verify(str(out))
    assert res["status"] in {"PASS", "WARN"}
