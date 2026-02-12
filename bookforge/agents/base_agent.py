"""Base agent class for bookforge"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from ..knowledge_loader import KnowledgeLoader


class BaseAgent(ABC):
    """Base class for all bookforge agents"""
    
    def __init__(self):
        self.knowledge = KnowledgeLoader()
    
    @abstractmethod
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the agent's task"""
        pass
    
    def log(self, message: str):
        """Log a message"""
        print(f"[{self.__class__.__name__}] {message}")
