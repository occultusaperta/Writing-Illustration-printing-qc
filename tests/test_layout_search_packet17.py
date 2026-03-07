from __future__ import annotations

import json

from PIL import Image, ImageDraw

from bookforge.layout_search import LayoutSearchConfig, build_layout_search_report, select_best_layout
from bookforge.layout_search.sampler import generate_layout_permutations
from bookforge.layout_search.scoring import score_layout_permutation
from bookforge.pipeline import BookforgePipeline


def _base_layout() -> dict:
    return {
        "page_number": 1,
        "architecture_type": "full_bleed_spread",
        "variant_id": "fb_1",
        "text_zone": {"x": 0.08, "y": 0.74, "w": 0.84, "h": 0.2},
        "art_zone": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        "panel_zones": [],
        "inset_zones": [],
        "reserve_whitespace": [],
        "gutter_sensitive": True,
        "compositor_hints": {"mode": "full_bleed_spread"},
    }


def _img(path):
    img = Image.new("RGB", (512, 512), (220, 224, 229))
    d = ImageDraw.Draw(img)
    d.ellipse((145, 120, 330, 290), fill=(85, 122, 185))
    d.rectangle((0, 380, 512, 512), fill=(244, 244, 244))
    img.save(path)


def test_permutation_generation_bounded_and_seeded(tmp_path):
    cfg = LayoutSearchConfig(max_permutations_per_page=5, random_seed=11)
    rows1 = generate_layout_permutations(page_numbers=[1], base_layout=_base_layout(), config=cfg, seed=123, is_spread=False)
    rows2 = generate_layout_permutations(page_numbers=[1], base_layout=_base_layout(), config=cfg, seed=123, is_spread=False)
    assert len(rows1) <= 5
    assert [r.permutation_id for r in rows1] == [r.permutation_id for r in rows2]


def test_score_schema_bounds(tmp_path):
    image = tmp_path / "p.png"
    _img(image)
    cfg = LayoutSearchConfig(max_permutations_per_page=3)
    perm = generate_layout_permutations(page_numbers=[1], base_layout=_base_layout(), config=cfg, seed=8, is_spread=False)[0]
    score = score_layout_permutation(
        perm,
        image_path=image,
        page_text="A short line of text.",
        base_layout=_base_layout(),
        page_number=1,
        is_spread=False,
        gutter_sensitive=False,
    )
    assert 0.0 <= score.composite_score <= 1.0
    assert 0.0 <= score.confidence <= 1.0


def test_hard_rejection_for_invalid_layout(tmp_path):
    image = tmp_path / "p.png"
    _img(image)
    bad = _base_layout()
    bad["text_zone"] = {"x": 0.49, "y": 0.84, "w": 0.08, "h": 0.05}
    cfg = LayoutSearchConfig(max_permutations_per_page=1, enable_text_zone_variation=False, enable_crop_shift=False, enable_variant_swap_within_architecture=False)
    perm = generate_layout_permutations(page_numbers=[1], base_layout=bad, config=cfg, seed=4, is_spread=False)[0]
    score = score_layout_permutation(
        perm,
        image_path=image,
        page_text="This is intentionally long text that should not fit into tiny zone." * 8,
        base_layout=bad,
        page_number=1,
        is_spread=True,
        gutter_sensitive=True,
    )
    assert score.rejected is True


def test_selected_layout_affects_render_metadata_path(tmp_path):
    image = tmp_path / "p.png"
    _img(image)
    res = select_best_layout(
        page_numbers=[1],
        base_layout=_base_layout(),
        image_path=image,
        page_text="Hello there.",
        config=LayoutSearchConfig(max_permutations_per_page=6),
        seed=99,
        is_spread=False,
        architecture_variants={
            "fb_1": {
                "variant_id": "fb_1",
                "architecture_type": "full_bleed_spread",
                "zones": [
                    {"zone_id": "art", "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                    {"zone_id": "text", "x": 0.08, "y": 0.74, "w": 0.84, "h": 0.2},
                ],
            }
        },
    )
    assert res.selected_layout["layout_search"]["chosen_permutation_id"] == res.chosen_permutation_id


def test_disable_noop_and_verify_package_inclusion(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKFORGE_MONTE_CARLO_LAYOUT", "false")
    out = tmp_path / "out"
    out.mkdir(parents=True)
    required = BookforgePipeline()._expected_package_artifacts()
    assert "review/layout_search_report.json" in required

    for rel in required:
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            payload = {}
            if path.name == "preflight_report.json":
                payload = {"status": "PASS"}
            elif path.name == "production_report.json":
                payload = {"post": {"crop_mode": "smart", "director_grade_enabled": True, "tone_curve_preset": "storybook_lux"}, "qa_thresholds": {}, "cache_hit_rate": 1.0, "dual_audience": {"enabled": False}, "page_turn_tension": {"enabled": False}}
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
            path.write_text(json.dumps(payload), encoding="utf-8")
        else:
            path.write_bytes(b"x")

    (out / "review" / "thumbs").mkdir(parents=True, exist_ok=True)
    (out / "review" / "thumbs" / "cover.jpg").write_bytes(b"x")
    result = BookforgePipeline().verify(str(out))
    assert result["status"] in {"PASS", "WARN"}


def test_report_generation_schema():
    rep = build_layout_search_report([])
    assert "summary" in rep
    assert "pages" in rep
