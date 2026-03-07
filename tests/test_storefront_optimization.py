import json
from pathlib import Path

from PIL import Image, ImageDraw

from bookforge.pipeline import BookforgePipeline
from bookforge.storefront.scoring import build_storefront_optimization_report, write_storefront_optimization_report
from bookforge.storefront.thumbnail import score_cover_thumbnail


def _cover(path: Path) -> None:
    img = Image.new("RGB", (900, 1400), (35, 50, 95))
    d = ImageDraw.Draw(img)
    d.rectangle((120, 220, 780, 1180), outline=(255, 210, 100), width=16)
    d.ellipse((280, 500, 620, 980), fill=(225, 140, 120))
    d.text((150, 80), "THE STARRY DOOR", fill=(250, 250, 245))
    img.save(path)


def _page(path: Path, color: int) -> None:
    img = Image.new("RGB", (900, 900), (color, color, min(255, color + 20)))
    d = ImageDraw.Draw(img)
    d.rectangle((170, 200, 730, 760), outline=(255 - color, 180, 120), width=12)
    img.save(path)


def test_thumbnail_scoring_bounds_and_schema(tmp_path: Path):
    c = tmp_path / "cover.png"
    _cover(c)
    diag = score_cover_thumbnail(c, thumbnail_heights=[100, 140], title_text_available=False)
    agg = diag.aggregate
    assert len(diag.per_size_scores) == 2
    assert 0.0 <= agg.title_readability_score <= 1.0
    assert 0.0 <= agg.composite_score <= 1.0
    assert "title_layer_unavailable_readability_is_proxy_only" in agg.warnings


def test_storefront_report_noop_when_disabled(tmp_path: Path):
    p1 = tmp_path / "p1.png"
    _page(p1, 80)
    report = build_storefront_optimization_report(
        selected=[str(p1)],
        cover_path=None,
        qa_attempts=[],
        color_script={},
        architecture_plan=[],
        camera_sequence_plan={},
        hidden_world_plan={},
        enabled=False,
    )
    assert report.enabled is False
    assert report.summary_score == 0.0


def test_look_inside_window_and_artifact_generation(tmp_path: Path):
    cover = tmp_path / "cover.png"
    _cover(cover)
    pages = []
    for i, c in enumerate([70, 95, 120, 140], start=1):
        p = tmp_path / f"p{i}.png"
        _page(p, c)
        pages.append(str(p))

    qa_attempts = [
        {
            "page": idx,
            "best": {
                "path": pages[idx - 1],
                "contrast": 32.0,
                "text_likelihood": 0.08,
                "metadata": {
                    "saliency_flow_score": {"composite_score": 0.65},
                    "color_score": {"composite_score": 0.72},
                    "hidden_world_score": {"composite_score": 0.55},
                    "page_architecture_score": {"composite_score": 0.66},
                },
            },
        }
        for idx in range(1, 5)
    ]

    report = build_storefront_optimization_report(
        selected=pages,
        cover_path=str(cover),
        qa_attempts=qa_attempts,
        color_script={"pages": [{"page_number": 1}]},
        architecture_plan=[{"page_number": 1}],
        camera_sequence_plan={1: {"shot_type": "closeup_emotion"}},
        hidden_world_plan={"pages": [{"page_number": 1}]},
        enabled=True,
    )
    assert report.look_inside.priority_pages[:4] == [1, 2, 3, 4]
    assert report.look_inside.strongest_page is not None
    assert 0.0 <= report.first_pages_strength_score <= 1.0

    out = tmp_path / "review" / "storefront_optimization_report.json"
    write_storefront_optimization_report(out, report)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "cover_thumbnail" in payload
    assert "look_inside" in payload


def test_pipeline_expected_artifacts_include_storefront_report():
    required = BookforgePipeline()._expected_package_artifacts()
    assert "review/book_quality_report.json" in required
