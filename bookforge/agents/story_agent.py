"""Story agent for generating children's book stories"""
import random
from typing import Dict, Any
from .base_agent import BaseAgent


class StoryAgent(BaseAgent):
    """Generates story content for children's books"""
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a story based on the idea"""
        self.log("Generating story...")
        
        idea = context.get("idea", "a magical adventure")
        age_group = context.get("age_group", "ages_3_5")
        
        # Get psychology knowledge for the age group
        psych_data = self.knowledge.psychology.get("age_groups", {}).get(age_group, {})
        themes = psych_data.get("themes", ["friendship", "adventure"])
        
        # Generate story structure
        story = self._generate_story(idea, themes, psych_data)
        
        self.log(f"Story generated with {len(story['pages'])} pages")
        
        return {
            "story": story,
            "age_group": age_group,
            "word_count": sum(len(page["text"].split()) for page in story["pages"])
        }
    
    def _generate_story(self, idea: str, themes: list, psych_data: Dict) -> Dict[str, Any]:
        """Generate story structure"""
        # Simple story generation (in a real implementation, this would use an LLM)
        language_level = psych_data.get("language", "Simple sentences")
        
        # Create a simple story structure
        pages = []
        
        # Title page
        title = self._generate_title(idea)
        
        # Generate 24-28 pages to meet KDP minimum requirements
        story_beats = [
            f"Once upon a time, there was {idea}.",
            "Every day was a new adventure.",
            "They loved to play and explore the world.",
            "They had many friends who cared about them.",
            "Together, they shared wonderful times.",
            "But one day, something unexpected happened.",
            "A challenge appeared that seemed too big.",
            "At first, they didn't know what to do.",
            "They felt worried and unsure.",
            "But then, they remembered their friends.",
            "They decided to be brave and try.",
            "Step by step, they worked on the problem.",
            "Sometimes it was hard, but they kept going.",
            "They tried different ways to solve it.",
            "They learned new things along the way.",
            "They helped each other when things got tough.",
            "Slowly, they started to see progress.",
            "They were getting closer to the answer!",
            "With one final effort, they succeeded!",
            "Everyone was amazed at what they had done.",
            "They felt so proud of themselves.",
            "They celebrated their achievement together.",
            "And from that day on, they knew they could do anything.",
            "They lived happily, ready for new adventures.",
            "The End."
        ]
        
        for i, beat in enumerate(story_beats):
            pages.append({
                "page_number": i + 1,
                "text": beat,
                "scene_description": f"Scene {i+1}: {beat[:50]}..."
            })
        
        return {
            "title": title,
            "pages": pages,
            "themes": themes,
            "age_group": psych_data.get("name", "Children")
        }
    
    def _generate_title(self, idea: str) -> str:
        """Generate a story title"""
        # Simple title generation
        prefixes = ["The Amazing", "The Wonderful", "The Magical", "The Adventures of"]
        return f"{random.choice(prefixes)} {idea.title()}"
