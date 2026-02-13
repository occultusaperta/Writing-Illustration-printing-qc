from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image
from pypdf import PdfReader

from bookforge.knowledge.loader import KnowledgeLoader
from bookforge.layout.pdf import parse_trim_size


class KDPPreflight:
    def __init__(self) -> None:
        self.loader = KnowledgeLoader()

    def run(self, interior_pdf: Path, cover_pdf: Path, image_paths: List[str], trim_size: str, bleed_in: float, safe_margin_in: float, include_page_numbers: bool) -> Dict[str, Any]:
        loaded = self.loader.load()
        checks: List[Dict[str, Any]] = []
        errors: List[str] = []
        warnings: List[str] = []

        trim_w, trim_h = parse_trim_size(trim_size)
        expected_w = (trim_w + 2 * bleed_in) * 72
        expected_h = (trim_h + 2 * bleed_in) * 72

        if not interior_pdf.exists():
            errors.append("Missing interior PDF.")
            return {"status": "FAIL", "checks": [], "errors": errors, "warnings": warnings}

        reader = PdfReader(str(interior_pdf))
        page_count = len(reader.pages)
        media = reader.pages[0].mediabox
        pw, ph = float(media.width), float(media.height)
        checks.append({"check": "trim+bleed page size", "status": "PASS" if abs(pw - expected_w) < 1 and abs(ph - expected_h) < 1 else "FAIL"})
        checks.append({"check": "safe margin >= 0.375in", "status": "PASS" if safe_margin_in >= 0.375 else "FAIL"})

        if page_count % 2 != 0:
            checks.append({"check": "page count parity even", "status": "WARN"})
            warnings.append("Interior page count is odd; print parity should usually be even.")
        else:
            checks.append({"check": "page count parity even", "status": "PASS"})

        embedded_font = False
        for p in reader.pages:
            fonts = p.get("/Resources", {}).get("/Font")
            if not fonts:
                continue
            for font_ref in fonts.values():
                obj = font_ref.get_object()
                if obj.get("/FontDescriptor") and obj["/FontDescriptor"].get_object().get("/FontFile2"):
                    embedded_font = True
        checks.append({"check": "embedded TrueType font present", "status": "PASS" if embedded_font else "FAIL"})

        min_w = int((trim_w + 2 * bleed_in) * 300)
        min_h = int((trim_h + 2 * bleed_in) * 300)
        all_images_ok = True
        for ip in image_paths:
            if not Path(ip).exists():
                errors.append(f"Missing image: {ip}")
                all_images_ok = False
                continue
            with Image.open(ip) as im:
                if im.width < min_w or im.height < min_h:
                    errors.append(f"Image too small for 300DPI-equivalent: {ip}")
                    all_images_ok = False
        checks.append({"check": "image resolution >= 300DPI-equivalent", "status": "PASS" if all_images_ok else "FAIL"})

        checks.append({"check": "cover wrap exists", "status": "PASS" if cover_pdf.exists() and os.path.getsize(cover_pdf) > 0 else "FAIL"})

        if any(c["status"] == "FAIL" for c in checks) or errors:
            status = "FAIL"
        elif warnings:
            status = "WARN"
        else:
            status = "PASS"

        return {
            "status": status,
            "checks": checks,
            "errors": errors,
            "warnings": warnings,
            "knowledge_sources": loaded["knowledge_sources"],
            "knowledge_docs_used": loaded["knowledge_docs_used"],
            "pdf_sources_used": loaded["pdf_sources_used"],
            "style_refs_used": loaded["style_refs_used"],
            "knowledge_keys_used": {"kdp.trim_size": trim_size, "kdp.page_numbers": include_page_numbers},
        }
