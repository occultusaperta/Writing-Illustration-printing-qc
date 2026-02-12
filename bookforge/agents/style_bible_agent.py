"""Style Bible agent for defining visual style"""
from typing import Dict, Any
from .base_agent import BaseAgent


class StyleBibleAgent(BaseAgent):
    """Creates and validates the visual style guide for the book"""
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate style bible and get approval"""
        self.log("Creating style bible...")
        
        story = context.get("story", {})
        themes = story.get("themes", [])
        
        # Select appropriate visual mode and director style
        style_bible = self._create_style_bible(themes)
        
        self.log("Style bible created. Waiting for approval...")
        
        # Approval gate - in a real implementation, this would prompt the user
        # For now, we'll auto-approve with a note
        approval = self._get_approval(style_bible)
        
        if approval["approved"]:
            self.log("Style bible approved!")
        else:
            self.log("Style bible needs revision")
        
        return {
            "style_bible": style_bible,
            "approved": approval["approved"],
            "notes": approval.get("notes", "")
        }
    
    def _create_style_bible(self, themes: list) -> Dict[str, Any]:
        """Create a style bible based on themes"""
        # Select visual mode based on themes
        visual_modes = self.knowledge.visual_modes.get("visual_modes", {})
        directors = self.knowledge.directors.get("directors", {})
        
        # Simple selection logic (in real implementation, this would be more sophisticated)
        if "nature" in themes or "magic in everyday life" in themes:
            selected_mode = "watercolor"
            selected_director = "hayao_miyazaki"
        elif "friendship" in themes or "adventure" in themes:
            selected_mode = "digital_illustration"
            selected_director = "pixar"
        else:
            selected_mode = "digital_illustration"
            selected_director = "wes_anderson"
        
        mode_data = visual_modes.get(selected_mode, {})
        director_data = directors.get(selected_director, {})
        
        return {
            "visual_mode": selected_mode,
            "mode_details": mode_data,
            "director_style": selected_director,
            "director_details": director_data,
            "color_palette": director_data.get("color_palette", []),
            "visual_motifs": director_data.get("visual_motifs", []),
            "style_description": f"{mode_data.get('description', '')} with {director_data.get('style', '')} influences"
        }
    
    def _get_approval(self, style_bible: Dict[str, Any]) -> Dict[str, Any]:
        """Get approval for style bible (approval gate)"""
        # In a real implementation, this would prompt the user for approval
        # For now, auto-approve for pipeline flow
        print("\n" + "="*60)
        print("STYLE BIBLE APPROVAL GATE")
        print("="*60)
        print(f"Visual Mode: {style_bible['visual_mode']}")
        print(f"Director Style: {style_bible['director_style']}")
        print(f"Description: {style_bible['style_description']}")
        print(f"Color Palette: {', '.join(style_bible['color_palette'])}")
        print("="*60)
        print("Auto-approving for automated pipeline...")
        print("="*60 + "\n")
        
        return {
            "approved": True,
            "notes": "Auto-approved in automated mode"
        }
