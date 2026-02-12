"""Pipeline orchestrator for bookforge"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from .agents import (
    StoryAgent,
    StyleBibleAgent,
    IllustratorAgent,
    LayoutAgent,
    KDPPreflightAgent
)


class Pipeline:
    """Orchestrates the book creation pipeline"""
    
    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or "bookforge/output"
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        
        # Initialize agents
        self.story_agent = StoryAgent()
        self.style_bible_agent = StyleBibleAgent()
        self.illustrator_agent = IllustratorAgent()
        self.layout_agent = LayoutAgent()
        self.kdp_preflight_agent = KDPPreflightAgent()
    
    def run(self, idea: str, age_group: str = "ages_3_5") -> Dict[str, Any]:
        """Run the complete pipeline"""
        print("\n" + "="*60)
        print("BOOKFORGE PIPELINE STARTING")
        print("="*60)
        print(f"Idea: {idea}")
        print(f"Age Group: {age_group}")
        print(f"Output Directory: {self.output_dir}")
        print("="*60 + "\n")
        
        context = {
            "idea": idea,
            "age_group": age_group,
            "output_dir": self.output_dir
        }
        
        # Step 1: Generate story
        story_result = self.story_agent.run(context)
        context.update(story_result)
        
        # Step 2: Create style bible (with approval gate)
        style_result = self.style_bible_agent.run(context)
        context.update(style_result)
        
        # Only proceed if style bible is approved
        if not style_result.get("approved", False):
            print("Pipeline stopped: Style bible not approved")
            return self._create_report(context, success=False)
        
        # Step 3: Generate illustrations
        illustration_result = self.illustrator_agent.run(context)
        context.update(illustration_result)
        
        # Step 4: Create layout PDFs
        layout_result = self.layout_agent.run(context)
        context.update(layout_result)
        
        # Step 5: Run KDP preflight checks
        preflight_result = self.kdp_preflight_agent.run(context)
        context.update(preflight_result)
        
        # Generate final report
        report = self._create_report(context, success=True)
        
        print("\n" + "="*60)
        print("PIPELINE COMPLETED")
        print("="*60)
        print(f"Status: {preflight_result.get('status', 'UNKNOWN')}")
        print(f"Report: {report['report_path']}")
        print("="*60 + "\n")
        
        return report
    
    def _create_report(self, context: Dict[str, Any], success: bool) -> Dict[str, Any]:
        """Create a final report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = Path(self.output_dir) / f"report_{timestamp}.json"
        
        report_data = {
            "timestamp": timestamp,
            "success": success,
            "idea": context.get("idea", ""),
            "age_group": context.get("age_group", ""),
            "story_title": context.get("story", {}).get("title", ""),
            "page_count": len(context.get("story", {}).get("pages", [])),
            "word_count": context.get("word_count", 0),
            "style_approved": context.get("approved", False),
            "interior_pdf": context.get("interior_pdf", ""),
            "cover_pdf": context.get("cover_pdf", ""),
            "preflight_status": context.get("status", "NOT RUN"),
            "preflight_checks": context.get("checks", []),
            "preflight_warnings": context.get("warnings", []),
            "preflight_errors": context.get("errors", [])
        }
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2)
        
        # Also create a human-readable report
        text_report_path = Path(self.output_dir) / f"report_{timestamp}.txt"
        with open(text_report_path, 'w', encoding='utf-8') as f:
            f.write("BOOKFORGE PIPELINE REPORT\n")
            f.write("="*60 + "\n\n")
            f.write(f"Generated: {timestamp}\n")
            f.write(f"Success: {success}\n\n")
            
            f.write("BOOK DETAILS\n")
            f.write("-"*60 + "\n")
            f.write(f"Idea: {report_data['idea']}\n")
            f.write(f"Title: {report_data['story_title']}\n")
            f.write(f"Age Group: {report_data['age_group']}\n")
            f.write(f"Pages: {report_data['page_count']}\n")
            f.write(f"Words: {report_data['word_count']}\n\n")
            
            f.write("OUTPUT FILES\n")
            f.write("-"*60 + "\n")
            f.write(f"Interior PDF: {report_data['interior_pdf']}\n")
            f.write(f"Cover PDF: {report_data['cover_pdf']}\n\n")
            
            f.write("KDP PREFLIGHT\n")
            f.write("-"*60 + "\n")
            f.write(f"Status: {report_data['preflight_status']}\n\n")
            
            if report_data['preflight_checks']:
                f.write("Checks Passed:\n")
                for check in report_data['preflight_checks']:
                    f.write(f"  {check}\n")
                f.write("\n")
            
            if report_data['preflight_warnings']:
                f.write("Warnings:\n")
                for warning in report_data['preflight_warnings']:
                    f.write(f"  ⚠ {warning}\n")
                f.write("\n")
            
            if report_data['preflight_errors']:
                f.write("Errors:\n")
                for error in report_data['preflight_errors']:
                    f.write(f"  ✗ {error}\n")
                f.write("\n")
        
        return {
            "report_path": str(report_path),
            "text_report_path": str(text_report_path),
            "report_data": report_data
        }
