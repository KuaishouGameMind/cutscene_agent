from typing import List, Dict, Any
from .base import PromptElement
from .elements import MessageElement, SystemInstruction, ContextBlock

class PromptManager:
    def __init__(self, model_name: str = "gpt-4"):
        self.model_name = model_name
        self.system_elements: List[PromptElement] = []
        self.context_elements: List[PromptElement] = []

    def add_system_instruction(self, text: str, priority: int = 1000):
        self.system_elements.append(SystemInstruction(text, priority))

    def add_context(self, title: str, content: str, priority: int = 400):
        self.context_elements.append(ContextBlock(title, content, priority))
        
    def clear_context(self):
        self.context_elements = []

    def render_system_prompt(self, max_tokens: int = 2000) -> str:
        """
        Renders the system prompt including instructions and context, respecting the token budget.
        """
        # 1. Collect all candidates
        candidates = self.system_elements + self.context_elements
        
        # 2. Sort by priority (descending) to decide what to KEEP
        # We create a copy to sort
        sorted_candidates = sorted(candidates, key=lambda x: x.priority, reverse=True)
        
        kept_elements = set()
        used_tokens = 0
        
        for el in sorted_candidates:
            t = el.get_token_count(self.model_name)
            if used_tokens + t <= max_tokens:
                kept_elements.add(el)
                used_tokens += t
        
        # 3. Render in a logical order: System Instructions first, then Context.
        final_render_list = []
        
        # We iterate through the original lists to preserve insertion order within categories
        for el in self.system_elements:
            if el in kept_elements:
                final_render_list.append(el)
        
        for el in self.context_elements:
            if el in kept_elements:
                final_render_list.append(el)
                
        return "\n\n".join([e.render() for e in final_render_list])

