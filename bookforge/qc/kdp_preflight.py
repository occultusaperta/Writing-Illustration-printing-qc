from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from PIL import Image
from pypdf import PdfReader


class KDPPreflight:
    def run(
        self,
        interior_pdf: Path,
        cover_pdf: Path,
        image_paths: List[str],
        trim_w: float,
        trim_h: float,
        bleed_in: float,
        page_count: int,
        spine_w: float,
        upscaled_pages: List[int],
    ) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        errors: List[str] = []
        warnings: List[str] = []

        if not interior_pdf.exists() or not cover_pdf.exists():
            return {"status": "FAIL", "checks": [], "errors": ["Missing PDFs."], "warnings": []}

        interior = PdfReader(str(interior_pdf))
        expected_w = (trim_w + 2 * bleed_in) * 72
        expected_h = (trim_h + 2 * bleed_in) * 72

        all_pages_size_ok = True
        for idx, page in enumerate(interior.pages, start=1):
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
            if abs(w - expected_w) > 0.1 or abs(h - expected_h) > 0.1:
                all_pages_size_ok = False
                errors.append(f"Interior page {idx} has incorrect size.")
        checks.append({"check": "interior pages exact trim+bleed", "status": "PASS" if all_pages_size_ok else "FAIL"})

        embedded_font = False
        for page in interior.pages:
            fonts = page.get("/Resources", {}).get("/Font")
            if not fonts:
                continue
            for ref in fonts.values():
                obj = ref.get_object()
                descriptor = obj.get("/FontDescriptor")
                if descriptor and descriptor.get_object().get("/FontFile2"):
                    embedded_font = True
        if not embedded_font:
            errors.append("Missing embedded TrueType font.")
        checks.append({"check": "embedded font", "status": "PASS" if embedded_font else "FAIL"})

        min_w = int((trim_w + 2 * bleed_in) * 300)
        min_h = int((trim_h + 2 * bleed_in) * 300)
        img_ok = True
        for path in image_paths:
            with Image.open(path) as im:
                if im.width < min_w or im.height < min_h:
                    img_ok = False
                    errors.append(f"Image under 300DPI-equivalent: {path}")
        checks.append({"check": "selected images >= 300DPI-equivalent", "status": "PASS" if img_ok else "FAIL"})

        cover = PdfReader(str(cover_pdf))
        cw = float(cover.pages[0].mediabox.width) / 72
        ch = float(cover.pages[0].mediabox.height) / 72
        expected_cw = 2 * trim_w + spine_w + 2 * bleed_in
        expected_ch = trim_h + 2 * bleed_in
        cover_ok = abs(cw - expected_cw) < 0.01 and abs(ch - expected_ch) < 0.01
        if not cover_ok:
            errors.append("Cover dimensions do not match formula.")
        checks.append({"check": "cover dimensions formula", "status": "PASS" if cover_ok else "FAIL"})

        if page_count % 2 != 0:
            warnings.append("Odd page count.")
        if upscaled_pages:
            warnings.append(f"Heavy upscaling on pages: {upscaled_pages}")

        status = "FAIL" if errors else ("WARN" if warnings else "PASS")
        return {"status": status, "checks": checks, "errors": errors, "warnings": warnings}
