"""Layout agent for creating PDF files using ReportLab"""
from typing import Dict, Any
from pathlib import Path
from .base_agent import BaseAgent


class LayoutAgent(BaseAgent):
    """Creates interior and cover PDFs using ReportLab"""
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate interior and cover PDFs"""
        self.log("Creating PDF layouts...")
        
        story = context.get("story", {})
        illustrations = context.get("illustrations", [])
        output_dir = context.get("output_dir", "bookforge/output")
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Create interior PDF
        interior_pdf = self._create_interior_pdf(story, illustrations, output_path)
        
        # Create cover PDF
        cover_pdf = self._create_cover_pdf(story, output_path)
        
        self.log("PDF layouts completed")
        
        return {
            "interior_pdf": interior_pdf,
            "cover_pdf": cover_pdf,
            "output_dir": str(output_path)
        }
    
    def _create_interior_pdf(self, story: Dict[str, Any], illustrations: list, 
                            output_dir: Path) -> str:
        """Create the interior PDF"""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.units import inch
            from reportlab.pdfgen import canvas
            from reportlab.lib.utils import simpleSplit
            
            pdf_path = output_dir / "interior.pdf"
            c = canvas.Canvas(str(pdf_path), pagesize=letter)
            width, height = letter
            
            # Title page
            title = story.get("title", "Untitled")
            c.setFont("Helvetica-Bold", 24)
            c.drawCentredString(width / 2, height - 2*inch, title)
            c.showPage()
            
            # Story pages
            pages = story.get("pages", [])
            c.setFont("Helvetica", 12)
            
            for i, page in enumerate(pages):
                # Draw page number
                c.setFont("Helvetica", 10)
                c.drawString(width - inch, inch/2, f"Page {i+1}")
                
                # Draw illustration placeholder
                c.setFont("Helvetica-Oblique", 10)
                c.drawCentredString(width / 2, height - 3*inch, 
                                   f"[Illustration {i+1}]")
                
                # Draw text
                c.setFont("Helvetica", 14)
                text = page.get("text", "")
                
                # Simple text wrapping
                lines = simpleSplit(text, "Helvetica", 14, width - 2*inch)
                y = height - 5*inch
                for line in lines:
                    c.drawString(inch, y, line)
                    y -= 20
                
                c.showPage()
            
            c.save()
            self.log(f"Interior PDF created: {pdf_path}")
            return str(pdf_path)
            
        except ImportError:
            self.log("ReportLab not installed. Creating placeholder PDF info.")
            pdf_path = output_dir / "interior.pdf.txt"
            with open(pdf_path, 'w') as f:
                f.write(f"Interior PDF Placeholder\n")
                f.write(f"Title: {story.get('title', 'Untitled')}\n")
                f.write(f"Pages: {len(story.get('pages', []))}\n")
            return str(pdf_path)
    
    def _create_cover_pdf(self, story: Dict[str, Any], output_dir: Path) -> str:
        """Create the cover PDF"""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.units import inch
            from reportlab.pdfgen import canvas
            
            pdf_path = output_dir / "cover.pdf"
            c = canvas.Canvas(str(pdf_path), pagesize=letter)
            width, height = letter
            
            # Front cover
            title = story.get("title", "Untitled")
            c.setFont("Helvetica-Bold", 36)
            c.drawCentredString(width / 2, height - 3*inch, title)
            
            c.setFont("Helvetica-Oblique", 14)
            c.drawCentredString(width / 2, height - 4*inch, "[Cover Illustration]")
            
            c.setFont("Helvetica", 18)
            c.drawCentredString(width / 2, 2*inch, "By BookForge")
            
            c.save()
            self.log(f"Cover PDF created: {pdf_path}")
            return str(pdf_path)
            
        except ImportError:
            self.log("ReportLab not installed. Creating placeholder cover info.")
            pdf_path = output_dir / "cover.pdf.txt"
            with open(pdf_path, 'w') as f:
                f.write(f"Cover PDF Placeholder\n")
                f.write(f"Title: {story.get('title', 'Untitled')}\n")
            return str(pdf_path)
