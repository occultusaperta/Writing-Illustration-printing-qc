from pathlib import Path

from bookforge.ui.utils import apply_variant_selection_to_approval, resolve_variant_assets


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"png")


def test_resolve_variant_assets_returns_expected_files(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    preprod = out_dir / "preprod"
    for i in range(1, 5):
        _touch(preprod / "character_options" / f"char_v{i}.png")
        _touch(preprod / "style_options" / f"style_v{i}.png")
        _touch(preprod / "cover_options" / f"cover_v{i}.png")
        vdir = preprod / "bible_variants" / f"v{i}"
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "prompt_prefix.txt").write_text(f"prefix {i}", encoding="utf-8")
        (vdir / "negative_prompt.txt").write_text(f"negative {i}", encoding="utf-8")

    _touch(preprod / "anchor_pack" / "character_turnaround_v2.png")
    _touch(preprod / "anchor_pack" / "style_frame_v2.png")

    selection = resolve_variant_assets(out_dir, 2)

    assert selection["approved_variant"] == 2
    assert selection["approved_character"] == "char_v2.png"
    assert selection["approved_style"] == "style_v2.png"
    assert selection["approved_cover"] == "cover_v2.png"
    assert selection["anchors"] == {
        "character_turnaround": "character_turnaround_v2.png",
        "style_frame": "style_frame_v2.png",
    }


def test_apply_variant_selection_updates_without_auto_approve() -> None:
    approval = {
        "approved": False,
        "approved_variant": 1,
        "approved_character": "char_v1.png",
        "approved_style": "style_v1.png",
        "approved_cover": "cover_v1.png",
    }
    selection = {
        "approved_variant": 3,
        "approved_character": "char_v3.png",
        "approved_style": "style_v3.png",
        "approved_cover": "cover_v3.png",
        "anchors": {"palette_tile": "palette_tile_v3.png"},
    }

    updated = apply_variant_selection_to_approval(approval, selection)

    assert updated["approved_variant"] == 3
    assert updated["approved_character"] == "char_v3.png"
    assert updated["approved_style"] == "style_v3.png"
    assert updated["approved_cover"] == "cover_v3.png"
    assert updated["palette_tile"] == "palette_tile_v3.png"
    assert updated["approved"] is False
