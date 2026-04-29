from typing import Dict, Any, Optional
from .base import PromptElement

class TextElement(PromptElement):
    def __init__(self, text: str, priority: int = 100):
        super().__init__(priority)
        self.text = text

    def render(self) -> str:
        return self.text

class MessageElement(PromptElement):
    def __init__(self, role: str, content: str, priority: int = 500):
        super().__init__(priority)
        self.role = role
        self.content = content

    def render(self) -> str:
        # This render is for text-based prompt assembly. 
        # For chat APIs, we might extract the dict directly.
        return f"{self.role}: {self.content}"
    
    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}

class ContextBlock(PromptElement):
    def __init__(self, title: str, content: str, priority: int = 400):
        super().__init__(priority)
        self.title = title
        self.content = content

    def render(self) -> str:
        return f"<{self.title}>\n{self.content}\n</{self.title}>"

class SystemInstruction(TextElement):
    def __init__(self, text: str, priority: int = 1000):
        super().__init__(text, priority)
