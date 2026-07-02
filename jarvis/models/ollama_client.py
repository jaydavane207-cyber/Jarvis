import httpx
import json
import logging
from ..config import settings
from typing import List, Dict, AsyncGenerator

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.model = settings.local_model

    async def chat_stream(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        """Multi-turn chat using conversation history, streaming response asynchronously.
        
        Args:
            messages: List of dicts with 'role' and 'content' keys.
                      Roles: 'system', 'user', 'assistant'
        
        Yields:
            The assistant's generated tokens as strings.
        """
        logger.info(f"Calling Ollama chat_stream with model {self.model} ({len(messages)} messages)")
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True
                    }
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                data = json.loads(line)
                                if "message" in data and "content" in data["message"]:
                                    yield data["message"]["content"]
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            logger.error(f"Failed to call Ollama chat_stream: {e}")
            raise RuntimeError(f"I'm sorry, I'm having trouble connecting to my local AI model right now. Please make sure Ollama is running. Details: {str(e)}")

    def chat(self, messages: List[Dict[str, str]]) -> str:
        """Legacy synchronous multi-turn chat using conversation history.
        Kept for backward compatibility if needed."""
        import requests
        logger.info(f"Calling Ollama chat with model {self.model} ({len(messages)} messages)")
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False
                },
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.error(f"Failed to call Ollama chat: {e}")
            raise RuntimeError(f"I'm sorry, I'm having trouble connecting to my local AI model right now. Please make sure Ollama is running. Details: {str(e)}")
