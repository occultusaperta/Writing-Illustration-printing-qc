from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from PIL import Image
from pypdf import PdfReader


class KDPPreflight:
    def run(self, interior_pdf: Path, cover_pdf: Path, image_paths: List[str], trim_w: float, trim_h: float, bleed_in: float, page_count: int, spine_w: float, upscaled_pages: List[int], cover_config: Dict[str, Any], safe_in: float, max_interior_mb: float = 300.0) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        errors: List[str] = []
        warnings: List[str] = []
        if not interior_pdf.exists() or not cover_pdf.exists():
            return {"status": "FAIL", "checks": [], "errors": ["Missing PDFs. Remediation: run studio again and ensure render completed."], "warnings": []}

        interior = PdfReader(str(interior_pdf))
        expected_w = (trim_w + 2 * bleed_in) * 72
        expected_h = (trim_h + 2 * bleed_in) * 72
        size_ok = True
        for idx, page in enumerate(interior.pages, start=1):
            if abs(float(page.mediabox.width) - expected_w) > 0.1 or abs(float(page.mediabox.height) - expected_h) > 0.1:
                size_ok = False
                errors.append(f"Interior page {idx} has incorrect size. Remediation: regenerate interior with matching --size and bleed settings.")
        checks.append({"check": "interior pages exact trim+bleed", "status": "PASS" if size_ok else "FAIL"})

        embedded_font = False
        for page in interior.pages:
            fonts = page.get("/Resources", {}).get("/Font")
            if not fonts:
                continue
            for ref in fonts.values():
                descriptor = ref.get_object().get("/FontDescriptor")
                if descriptor and descriptor.get_object().get("/FontFile2"):
                    embedded_font = True
        if not embedded_font:
            errors.append("Missing embedded TrueType font. Remediation: use a valid TTF in assets/fonts and rerender interior.")
        checks.append({"check": "embedded font", "status": "PASS" if embedded_font else "FAIL"})

        min_w = int((trim_w + 2 * bleed_in) * 300)
        min_h = int((trim_h + 2 * bleed_in) * 300)
        img_ok = True
        for path in image_paths:
            with Image.open(path) as im:
                if im.width < min_w or im.height < min_h:
                    img_ok = False
                    errors.append(f"Image under 300DPI-equivalent: {path}. Remediation: regenerate page image at required dimensions.")
        checks.append({"check": "selected images >= 300DPI-equivalent", "status": "PASS" if img_ok else "FAIL"})

        cover = PdfReader(str(cover_pdf))
        cw = float(cover.pages[0].mediabox.width) / 72
        ch = float(cover.pages[0].mediabox.height) / 72
        c_ok = abs(cw - (2 * trim_w + spine_w + 2 * bleed_in)) < 0.01 and abs(ch - (trim_h + 2 * bleed_in)) < 0.01
        if not c_ok:
            errors.append("Cover dimensions do not match formula. Remediation: rerender cover with lock-derived spine and trim.")
        checks.append({"check": "cover dimensions formula", "status": "PASS" if c_ok else "FAIL"})

        bx, by, bw, bh = cover_config["barcode_box_in"]
        inside_safe = bx >= safe_in and by >= safe_in and (bx + bw) <= (trim_w - safe_in) and (by + bh) <= (trim_h - safe_in)
        if not inside_safe:
            errors.append("Barcode box outside back safe area. Remediation: choose a cover preset with barcode inside safe zone.")
        checks.append({"check": "barcode box in safe area", "status": "PASS" if inside_safe else "FAIL"})

        if page_count % 2 != 0:
            warnings.append("Odd page count. KDP may insert blanks; prefer even page counts.")
        interior_mb = interior_pdf.stat().st_size / (1024 * 1024)
        if interior_mb > max_interior_mb:
            warnings.append(f"Interior PDF size {interior_mb:.1f}MB exceeds configured threshold {max_interior_mb:.1f}MB.")
        if upscaled_pages:
            warnings.append(f"Heavy upscaling occurred on pages {upscaled_pages}. Consider increasing Fal output fidelity.")

        status = "FAIL" if errors else ("WARN" if warnings else "PASS")
        return {"status": status, "checks": checks, "errors": errors, "warnings": warnings}
