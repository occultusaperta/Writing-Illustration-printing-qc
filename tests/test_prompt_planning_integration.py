import json
from pathlib import Path

from bookforge.color_script.prompting import build_color_negative_lines, build_color_prompt_lines, build_color_script_guidance
from bookforge.illustration.prompt_contract import build_prompt_contract
from bookforge.page_architecture.prompting import (
    build_architecture_negative_lines,
    build_architecture_prompt_lines,
    build_page_architecture_guidance,
)
from bookforge.pipeline import _build_planning_prompt_guidance


def _minimal_lock() -> dict:
    return {
        "approved_variant": 1,
        "approved_character": "char.png",
        "approved_style": "style.png",
        "locked_prompt_prefix": "storybook premium",
        "locked_negative_prompt": "no text",
        "print": {"required_pixels": [1024, 1024]},
        "seeds": {"per_page_seed": {"1": 11, "2": 22}},
        "premium_visual_contract": {
            "character_reference_pack": {"primary": "char.png"},
            "style_reference_pack": {"primary": "style.png"},
            "composition_guidance": {},
            "character_proportions": {},
            "negative_prompt_rules": ["no watermark"],
            "trim_typography_safe_rules": {},
            "manuscript_art_bible": {"parallel_visual_motifs": []},
        },
    }


def test_prompt_contract_backward_compatible_without_planning():
    parsed = {"title": "T", "pages": [{"page_number": 1, "text": "hello"}]}
    contract = build_prompt_contract(parsed, _minimal_lock())
    obj = contract["objects"][0]
    assert contract["version"] == "premium_prompt_contract_v1"
    assert "color_script_guidance" in obj["metadata"]
    assert "page_architecture_guidance" in obj["metadata"]
    assert obj["metadata"]["color_script_guidance"] == {}
    assert obj["metadata"]["page_architecture_guidance"] == {}


def test_color_prompt_metadata_generation():
    guidance = build_color_script_guidance(
        {
            "emotion": "mystery",
            "narrative_function": "climax",
            "dominant_colors_lab": [[48, 8, -20]],
            "accent_color_lab": [62, 44, 38],
            "forbidden_colors_lab": [[12, 0, 0]],
            "background_key_lab": [30, -3, -8],
            "target_lightness": 44,
            "target_chroma": 20,
            "target_temperature": -0.4,
        },
        {"intensity": 0.8, "emotion": "mystery", "narrative_function": "climax"},
    )
    lines = build_color_prompt_lines(guidance)
    negatives = build_color_negative_lines(guidance)
    assert guidance["palette_direction"]
    assert any("Dominant palette" in line for line in lines)
    assert any("forbidden palette contamination" in line for line in negatives)


def test_architecture_prompt_metadata_generation_spread_vs_single():
    spread = build_page_architecture_guidance(
        {"selected_architecture_type": "full_bleed_spread", "selected_variant_id": "full_bleed_spread_main", "target_energy": 0.9, "narrative_function": "climax"},
        {"zones": [{"zone_id": "caption", "zone_type": "caption"}]},
    )
    single = build_page_architecture_guidance(
        {"selected_architecture_type": "vignette", "selected_variant_id": "vignette_centered", "target_energy": 0.3, "narrative_function": "resolution"},
        {"zones": [{"zone_id": "text", "zone_type": "text"}]},
    )
    assert spread["spread_mode"] == "spread"
    assert spread["gutter_safety_required"] is True
    assert single["spread_mode"] == "single"
    assert any("single-page oriented" in l for l in build_architecture_prompt_lines(single))
    assert "avoid busy text zones" in build_architecture_negative_lines(spread)


def test_pipeline_prompt_guidance_loading_with_and_without_planning(tmp_path: Path):
    out = tmp_path / "out"
    planning = out / "preprod" / "planning"
    planning.mkdir(parents=True)
    (planning / "emotion_analysis.json").write_text(json.dumps([{"page_number": 1, "emotion": "calm", "intensity": 0.3, "narrative_function": "opening"}]), encoding="utf-8")
    (planning / "color_script.json").write_text(
        json.dumps({"pages": [{"page_number": 1, "emotion": "calm", "narrative_function": "opening", "dominant_colors_lab": [[70, -2, 6]], "accent_color_lab": [58, 14, 18], "forbidden_colors_lab": [[10, 0, 0]], "background_key_lab": [76, 0, 0], "target_lightness": 66, "target_chroma": 14, "target_temperature": 0.2}]}),
        encoding="utf-8",
    )
    (planning / "architecture_plan.json").write_text(
        json.dumps([{"page_number": 1, "narrative_function": "opening", "target_energy": 0.4, "selected_variant_id": "vignette_centered", "selected_architecture_type": "vignette", "score": 0.8}]),
        encoding="utf-8",
    )

    guidance = _build_planning_prompt_guidance(out)
    assert 1 in guidance
    assert guidance[1]["color_script_guidance"]["emotion"] == "calm"
    assert guidance[1]["page_architecture_guidance"]["architecture_type"] == "vignette"

    empty = _build_planning_prompt_guidance(tmp_path / "missing")
    assert empty == {}


def test_prompt_contract_includes_planning_guidance_and_negatives():
    parsed = {"title": "T", "pages": [{"page_number": 1, "text": "scene one"}]}
    planning_guidance = {
        1: {
            "color_script_guidance": {"emotion": "joy"},
            "page_architecture_guidance": {"architecture_type": "panel_sequence"},
            "prompt_lines": ["Color script: predominantly warm amber, honey, and golden tones."],
            "negative_lines": ["avoid composition that conflicts with architecture intent"],
        }
    }
    contract = build_prompt_contract(parsed, _minimal_lock(), planning_guidance=planning_guidance)
    obj = contract["objects"][0]
    assert "predominantly warm amber" in obj["prompt_text"]
    assert "avoid composition that conflicts with architecture intent" in obj["negative_prompt"]
    assert obj["metadata"]["page_architecture_guidance"]["architecture_type"] == "panel_sequence"
