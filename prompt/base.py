from abc import ABC, abstractmethod
from typing import List, Any
from .utils import count_tokens

class PromptElement(ABC):
    def __init__(self, priority: int = 100):
        """
        priority: Higher number means higher priority (less likely to be pruned).
        """
        self.priority = priority

    @abstractmethod
    def render(self) -> str:
        pass

    def get_token_count(self, model_name: str = "gpt-4") -> int:
        return count_tokens(self.render(), model_name)

class CompositePromptElement(PromptElement):
    def __init__(self, elements: List[PromptElement], priority: int = 100, separator: str = "\n"):
        super().__init__(priority)
        self.elements = elements
        self.separator = separator

    def render(self) -> str:
        return self.separator.join([e.render() for e in self.elements if e])

    def get_token_count(self, model_name: str = "gpt-4") -> int:
        return sum(e.get_token_count(model_name) for e in self.elements) + (len(self.elements) - 1) * count_tokens(self.separator, model_name)
