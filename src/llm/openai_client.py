"""Shared OpenAI client factory.

Single source of truth for OpenAI API key resolution so we don't sprinkle
`AsyncOpenAI(api_key=settings.openai_api_key)` across every call site.
"""
from functools import lru_cache

from openai import AsyncOpenAI

from src.config import get_settings


@lru_cache
def get_openai_client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required (set in .env)")
    return AsyncOpenAI(api_key=settings.openai_api_key)
