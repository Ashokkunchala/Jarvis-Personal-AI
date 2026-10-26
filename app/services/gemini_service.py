import logging
import asyncio
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types

from app.core.config import get_settings

logger = logging.getLogger("jarvis.gemini")


class GeminiService:
    def __init__(self):
        self.settings = get_settings()
        self.client = None
        self._init_client()
    
    def _init_client(self):
        if self.settings.gemini_api_key and self.settings.gemini_api_key != "replace_me":
            try:
                self.client = genai.Client(api_key=self.settings.gemini_api_key)
                logger.info("Gemini client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                self.client = None
        else:
            self.client = None
    
    def is_configured(self) -> bool:
        return self.client is not None
    
    async def generate_content(
        self,
        contents: List[Dict[str, Any]],
        system_instruction: str = "",
        temperature: float = 0.8,
        max_retries: int = 3,
        timeout: int = 60,
    ) -> Optional[str]:
        if not self.client:
            raise RuntimeError("Gemini client not configured")
        
        model = self.settings.gemini_model
        for attempt in range(max_retries):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=model,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=temperature,
                        ),
                    ),
                    timeout=timeout,
                )
                text = (response.text or "").strip()
                if text:
                    return text
                logger.warning(f"Empty response from Gemini (attempt {attempt + 1})")
            except asyncio.TimeoutError:
                logger.warning(f"Gemini timeout (attempt {attempt + 1})")
                if attempt == max_retries - 1:
                    raise
            except Exception as e:
                logger.error(f"Gemini error (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    # Try fallback model
                    if model != self.settings.gemini_model_fallback:
                        try:
                            model = self.settings.gemini_model_fallback
                            response = await asyncio.wait_for(
                                asyncio.to_thread(
                                    self.client.models.generate_content,
                                    model=model,
                                    contents=contents,
                                    config=types.GenerateContentConfig(
                                        system_instruction=system_instruction,
                                        temperature=temperature,
                                    ),
                                ),
                                timeout=timeout,
                            )
                            return (response.text or "").strip()
                        except Exception as e2:
                            logger.error(f"Fallback model also failed: {e2}")
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return None
    
    def generate_content_stream(self, *args, **kwargs):
        if not self.client:
            raise RuntimeError("Gemini client not configured")
        return self.client.models.generate_content_stream(*args, **kwargs)


gemini_service = GeminiService()
