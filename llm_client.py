"""
IntentFlow — LLM Client (Groq primary, Ollama fallback).
Provides a unified interface for JSON and text completions.
"""

import json
import logging
import re
from functools import lru_cache
from typing import Any, Dict, Optional

import httpx

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMClient:
    """
    Unified LLM client:
      - Primary: Groq API (free tier — Llama 3.3 70B, Gemma 2 9B)
      - Fallback: Ollama local
    """

    def __init__(self):
        self._groq_key = settings.GROQ_API_KEY
        self._ollama_url = settings.OLLAMA_URL
        self._timeout = settings.GROQ_TIMEOUT
        self._max_tokens = settings.GROQ_MAX_TOKENS

    def _groq_model(self, tier: str) -> str:
        return settings.GROQ_MODEL_SMART if tier == "smart" else settings.GROQ_MODEL_FAST

    # ── Groq API ──────────────────────────────────────────────────────────────

    def _call_groq(self, prompt: str, model: str) -> str:
        if not self._groq_key:
            raise RuntimeError("GROQ_API_KEY not set")

        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self._groq_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": self._max_tokens,
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    # ── Ollama Fallback ───────────────────────────────────────────────────────

    def _call_ollama(self, prompt: str) -> str:
        if not self._ollama_url:
            raise RuntimeError("Neither GROQ_API_KEY nor OLLAMA_URL configured")

        url = f"{self._ollama_url.rstrip('/')}/api/generate"
        resp = httpx.post(
            url,
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3},
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

    # ── Unified Methods ───────────────────────────────────────────────────────

    def complete_text(self, prompt: str, model: str = "fast") -> str:
        """Get raw text completion."""
        groq_model = self._groq_model(model)
        try:
            return self._call_groq(prompt, groq_model)
        except Exception as e:
            logger.warning(f"Groq failed ({e}), trying Ollama fallback")
            return self._call_ollama(prompt)

    def complete_json(self, prompt: str, model: str = "fast") -> Dict[str, Any]:
        """Get a JSON completion — extracts JSON from the response."""
        raw = self.complete_text(prompt, model)
        return _extract_json(raw)


def _extract_json(text: str) -> Dict[str, Any]:
    """
    Robustly extract JSON from LLM output.
    Handles markdown code blocks, extra text before/after JSON, etc.
    """
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code blocks
    patterns = [
        r"```json\s*(.*?)\s*```",
        r"```\s*(.*?)\s*```",
        r"\{.*\}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1) if match.lastindex else match.group(0)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    # Last resort: find the first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.error(f"Failed to extract JSON from LLM output: {text[:300]}")
    return {}


@lru_cache()
def get_llm() -> LLMClient:
    return LLMClient()