from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def generate_proof_pack(output_pdf: Path, cover_path: Path, interior_pages: List[Path], metadata: Dict[str, Any], qa_attempts: List[Dict[str, Any]]) -> None:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_pdf))

    c.setFont("Helvetica-Bold", 16)
    c.drawString(36, 800, "Publisher Proof Pack")
    if cover_path.exists():
        c.drawImage(ImageReader(str(cover_path)), 36, 540, 220, 240, preserveAspectRatio=True, anchor="sw")
    c.setFont("Helvetica", 10)
    y = 780
    for k, v in metadata.items():
        c.drawString(280, y, f"{k}: {v}")
        y -= 14
    c.showPage()

    per_page = 9
    for i in range(0, len(interior_pages), per_page):
        chunk = interior_pages[i : i + per_page]
        c.setFont("Helvetica-Bold", 12)
        c.drawString(36, 810, f"Interior Contact Sheet {i+1}-{i+len(chunk)}")
        for idx, image_path in enumerate(chunk):
            row, col = divmod(idx, 3)
            x = 36 + col * 180
            y = 560 - row * 250
            if image_path.exists():
                c.drawImage(ImageReader(str(image_path)), x, y, 160, 220, preserveAspectRatio=True, anchor="sw")
                c.setFont("Helvetica", 8)
                c.drawString(x, y - 10, image_path.name)
        c.showPage()

    fails = sum(1 for a in qa_attempts if not a.get("passes", False))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(36, 800, "QA Summary")
    c.setFont("Helvetica", 10)
    c.drawString(36, 776, f"Total QA attempts: {len(qa_attempts)}")
    c.drawString(36, 760, f"Fail attempts: {fails}")
    worst = [a for a in qa_attempts if not a.get("passes", False)][:8]
    y = 736
    for item in worst:
        c.drawString(36, y, f"- page {item.get('page')} attempt {item.get('attempt')} fail")
        y -= 14
    c.save()


def write_production_report(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
