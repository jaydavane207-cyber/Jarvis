import re
import logging
import urllib.parse
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

class ImageAgent:
    """
    Handles requests to generate images.
    Takes the user's prompt, enhances it slightly for better results,
    and returns a formatted Pollinations AI URL wrapped in an [IMAGE] tag.
    """
    
    def __init__(self):
        self.base_url = "https://image.pollinations.ai/prompt/"
    
    def _extract_query(self, message: str) -> str:
        """Strip common preambles to get the core image subject."""
        cleaned = re.sub(
            r"^(?:generate|create|make|draw|paint|show me|i want)\s+(?:an?\s+)?(?:image|picture|photo|drawing|illustration)\s+(?:of\s+)?",
            "",
            message.strip(),
            flags=re.IGNORECASE,
        ).strip(" ?.,")
        return cleaned if len(cleaned) > 2 else message.strip()
        
    def _enhance_prompt(self, raw_subject: str) -> str:
        """Add aesthetic keywords to make the generated image look better."""
        if "style" not in raw_subject.lower() and "realistic" not in raw_subject.lower():
            return f"{raw_subject}, highly detailed, 8k resolution, cinematic lighting, masterpiece"
        return raw_subject

    def handle(self, message: str, llm=None, history=None, semantic=None, voice_mode=False) -> str:
        """Synchronous handler."""
        raw_subject = self._extract_query(message)
        enhanced = self._enhance_prompt(raw_subject)
        encoded_prompt = urllib.parse.quote(enhanced)
        final_url = f"{self.base_url}{encoded_prompt}?nologo=true"
        
        response = (
            f"Here is the image you requested for '{raw_subject}':\n\n"
            f"[IMAGE]{final_url}[/IMAGE]\n"
        )
        return response

    async def handle_stream(self, message: str, llm=None, history=None, semantic=None, voice_mode=False) -> AsyncGenerator[str, None]:
        """Streaming handler."""
        response = self.handle(message, llm, history, semantic, voice_mode)
        # Yield in chunks just like the LLM
        chunk_size = 20
        for i in range(0, len(response), chunk_size):
            yield response[i:i+chunk_size]
