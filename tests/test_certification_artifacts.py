from pathlib import Path

from PIL import Image

from bookforge.pipeline import BookforgePipeline
from bookforge.review.contact_sheet import generate_contact_sheet
from bookforge.review.html_report import generate_report
from bookforge.review.proof_pack import generate_proof_pack


def test_certification_artifacts_generation_without_fal_key(tmp_path: Path):
    out = tmp_path / "run"
    images = out / "images"
    images.mkdir(parents=True, exist_ok=True)

    pages = []
    for i in range(3):
        p = images / f"page_{i+1:03d}.png"
        Image.new("RGB", (320, 320), (100 + 10 * i, 120, 140)).save(p)
        pages.append(p)

    cover = out / "cover.png"
    Image.new("RGB", (320, 400), (80, 90, 110)).save(cover)

    contact_sheet = out / "review" / "contact_sheet.pdf"
    proof_pack = out / "review" / "proof_pack.pdf"

    qa_attempts = [
        {
            "page": 1,
            "attempt": 1,
            "passes": True,
            "best": {
                "path": str(pages[0]),
                "sharpness": 10.0,
                "contrast": 20.0,
                "entropy": 3.0,
                "text_likelihood": 0.01,
                "watermark_likelihood": 0.01,
                "logo_likelihood": 0.01,
                "style_hist_similarity": 0.8,
                "page_to_page_hist_drift": 0.1,
                "brightness_mean": 120,
                "color_drift_vs_style": 0.2,
            },
        }
    ]

    generate_contact_sheet(pages, contact_sheet)
    generate_proof_pack(proof_pack, cover, pages, {"trim": "8.5x8.5", "dpi": 300}, qa_attempts)

    production_report = {
        "drift": {"top_pages": [{"page": 1, "drift": 0.2}]},
        "regen_counts": {"1": 1, "2": 1, "3": 1},
        "cache_hit_rate": 0.33,
    }
    qa_report = {"attempts": qa_attempts}
    html_report = generate_report(out, pages, qa_report, production_report, cover)

    quality_summary = BookforgePipeline()._write_quality_summary(
        out,
        qa_attempts,
        {1: [True], 2: [False], 3: [True]},
        {"qa": {"max_text_likelihood": 0.15, "max_watermark_likelihood": 0.15, "max_logo_likelihood": 0.20}},
    )

    assert contact_sheet.exists() and contact_sheet.stat().st_size > 0
    assert proof_pack.exists() and proof_pack.stat().st_size > 0
    assert html_report.exists()
    assert quality_summary.exists()

    html_text = html_report.read_text(encoding="utf-8")
    assert "BookForge Static Proof Dashboard" in html_text
    assert "QA Table" in html_text

    summary_text = quality_summary.read_text(encoding="utf-8")
    assert "Top 5 Worst Pages by QA Score" in summary_text
    assert "Cache Hit Rate" in summary_text
