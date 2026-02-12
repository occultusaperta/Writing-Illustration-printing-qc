"""Knowledge loader for bookforge agents"""
import json
import os
from pathlib import Path
from typing import Dict, Any


class KnowledgeLoader:
    """Loads and provides access to knowledge base files"""
    
    def __init__(self):
        self.knowledge_dir = Path(__file__).parent / "knowledge"
        self.directors = self._load_json("directors.json")
        self.visual_modes = self._load_json("visual_modes.json")
        self.psychology = self._load_json("psychology.json")
    
    def _load_json(self, filename: str) -> Dict[str, Any]:
        """Load a JSON file from the knowledge directory"""
        file_path = self.knowledge_dir / filename
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Knowledge file {filename} not found at {file_path}")
            return {}
        except json.JSONDecodeError as e:
            print(f"Warning: Error parsing {filename}: {e}")
            return {}
    
    def get_all_knowledge(self) -> Dict[str, Any]:
        """Get all knowledge as a dictionary"""
        return {
            "directors": self.directors,
            "visual_modes": self.visual_modes,
            "psychology": self.psychology
        }
