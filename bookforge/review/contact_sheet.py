from __future__ import annotations

from pathlib import Path
from typing import Iterable

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def generate_contact_sheet(image_paths: Iterable[Path], out_pdf: Path, columns: int = 4) -> None:
    paths = list(image_paths)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_pdf), pagesize=(11 * 72, 8.5 * 72))
    margin = 24
    gap = 12
    cell_w = (11 * 72 - 2 * margin - (columns - 1) * gap) / columns
    cell_h = 140
    rows = 4
    for idx, path in enumerate(paths):
        page = idx // (columns * rows)
        local = idx % (columns * rows)
        if local == 0 and idx > 0:
            c.showPage()
        row = local // columns
        col = local % columns
        x = margin + col * (cell_w + gap)
        y = 8.5 * 72 - margin - (row + 1) * cell_h - row * gap
        c.drawImage(ImageReader(str(path)), x, y + 20, cell_w, cell_h - 24, preserveAspectRatio=True, anchor="c")
        c.setFont("Helvetica", 9)
        c.drawString(x, y + 6, path.stem)
    c.save()
