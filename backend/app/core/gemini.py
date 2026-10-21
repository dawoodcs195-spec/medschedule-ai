"""Gemini client factory (google-genai SDK, Interactions API)."""
from __future__ import annotations

from functools import lru_cache

from google import genai

from app.core.config import settings


def gemini_enabled() -> bool:
    return bool(settings.GEMINI_API_KEY)


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    if not gemini_enabled():
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    return genai.Client(api_key=settings.GEMINI_API_KEY)
