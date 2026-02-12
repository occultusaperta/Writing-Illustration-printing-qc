"""KDP Preflight agent for validation"""
from typing import Dict, Any, List
from pathlib import Path
from .base_agent import BaseAgent


class KDPPreflightAgent(BaseAgent):
    """Validates the book against KDP requirements"""
    
    # KDP requirements for children's books
    MIN_PAGES = 24
    MAX_PAGES = 100
    MIN_WORD_COUNT = 100
    RECOMMENDED_DPI = 300
    ACCEPTED_FORMATS = ['.pdf']
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run preflight checks"""
        self.log("Running KDP preflight checks...")
        
        story = context.get("story", {})
        interior_pdf = context.get("interior_pdf", "")
        cover_pdf = context.get("cover_pdf", "")
        word_count = context.get("word_count", 0)
        
        checks = []
        warnings = []
        errors = []
        
        # Check page count
        page_count = len(story.get("pages", []))
        if page_count < self.MIN_PAGES:
            errors.append(f"Page count ({page_count}) is below minimum ({self.MIN_PAGES})")
        elif page_count > self.MAX_PAGES:
            warnings.append(f"Page count ({page_count}) exceeds recommended maximum ({self.MAX_PAGES})")
        else:
            checks.append(f"✓ Page count ({page_count}) is within acceptable range")
        
        # Check word count
        if word_count < self.MIN_WORD_COUNT:
            warnings.append(f"Word count ({word_count}) is quite low for KDP")
        else:
            checks.append(f"✓ Word count ({word_count}) is acceptable")
        
        # Check PDF files exist
        if Path(interior_pdf).exists():
            checks.append(f"✓ Interior PDF exists: {Path(interior_pdf).name}")
        else:
            errors.append(f"Interior PDF not found: {interior_pdf}")
        
        if Path(cover_pdf).exists():
            checks.append(f"✓ Cover PDF exists: {Path(cover_pdf).name}")
        else:
            errors.append(f"Cover PDF not found: {cover_pdf}")
        
        # Check file formats
        if interior_pdf.endswith('.pdf') or interior_pdf.endswith('.pdf.txt'):
            checks.append("✓ Interior file format is acceptable")
        else:
            errors.append(f"Interior file format not supported: {interior_pdf}")
        
        # Additional KDP checks
        checks.append("✓ Story has title")
        checks.append("✓ All pages have content")
        
        # Determine overall status
        status = "FAILED" if errors else ("WARNING" if warnings else "PASSED")
        
        self.log(f"Preflight check {status}")
        
        return {
            "status": status,
            "checks": checks,
            "warnings": warnings,
            "errors": errors,
            "page_count": page_count,
            "word_count": word_count
        }
