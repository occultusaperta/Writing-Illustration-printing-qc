from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image
from pypdf import PdfReader

from bookforge.knowledge.loader import KnowledgeLoader
from bookforge.layout.pdf import parse_trim_size


class KDPPreflight:
    def __init__(self) -> None:
        self.loader = KnowledgeLoader()

    def run(
        self,
        interior_pdf: Path,
        cover_pdf: Path,
        image_paths: List[str],
        trim_size: str,
        bleed_in: float,
        safe_margin_in: float,
        include_page_numbers: bool,
    ) -> Dict[str, Any]:
        loaded = self.loader.load()
        checks: List[Dict[str, Any]] = []
        errors: List[str] = []
        warnings: List[str] = []

        trim_w, trim_h = parse_trim_size(trim_size)
        expected_w = (trim_w + 2 * bleed_in) * 72
        expected_h = (trim_h + 2 * bleed_in) * 72

        reader = PdfReader(str(interior_pdf))
        page_count = len(reader.pages)
        media = reader.pages[0].mediabox
        pw = float(media.width)
        ph = float(media.height)

        checks.append({"check": "trim+bleed page size", "ok": abs(pw - expected_w) < 1 and abs(ph - expected_h) < 1})
        checks.append({"check": "safe margin >= 0.25in", "ok": safe_margin_in >= 0.25})
        checks.append({"check": "page count parity even", "ok": page_count % 2 == 0})
        if page_count % 2 != 0:
            warnings.append("Interior page count is odd; KDP print books generally require even page counts.")

        fonts = set()
        for p in reader.pages:
            resources = p.get("/Resources")
            if resources and "/Font" in resources:
                fonts.update(resources["/Font"].keys())
        checks.append({"check": "fonts present in PDF resources", "ok": bool(fonts)})
        if not fonts:
            errors.append("No fonts found in interior PDF resources.")

        min_w = int((trim_w + 2 * bleed_in) * 300)
        min_h = int((trim_h + 2 * bleed_in) * 300)
        image_ok = True
        for ip in image_paths:
            with Image.open(ip) as im:
                if im.width < min_w or im.height < min_h:
                    image_ok = False
                    errors.append(f"Image too small for 300DPI-equivalent: {ip}")
        checks.append({"check": "placed image dimensions >= 300DPI-equivalent", "ok": image_ok})

        if not cover_pdf.exists() or os.path.getsize(cover_pdf) == 0:
            errors.append("Missing or empty cover wrap PDF.")
            checks.append({"check": "cover wrap exists", "ok": False})
        else:
            checks.append({"check": "cover wrap exists", "ok": True})

        status = "PASS" if not errors else "FAIL"
        return {
            "status": status,
            "checks": checks,
            "errors": errors,
            "warnings": warnings,
            "knowledge_sources": loaded["knowledge_sources"],
            "knowledge_keys_used": {"kdp.trim_size": trim_size, "kdp.page_numbers": include_page_numbers},
            "pdf_sources_used": loaded["pdf_sources_used"],
        }
