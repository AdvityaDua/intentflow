"""
IntentFlow — Configuration via environment variables.
All settings are loaded from .env or OS env vars. Nothing is hardcoded.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "IntentFlow"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./intentflow.db"

    # ── Auth ──────────────────────────────────────────────────────────────────
    JWT_SECRET: str = "change-me-in-production-use-a-random-256-bit-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24

    # ── LLM – Groq (primary) ─────────────────────────────────────────────────
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL_SMART: str = "llama-3.3-70b-versatile"
    GROQ_MODEL_FAST: str = "llama-3.1-8b-instant"
    GROQ_TIMEOUT: int = 30
    GROQ_MAX_TOKENS: int = 2048

    # ── LLM – Ollama (fallback) ───────────────────────────────────────────────
    OLLAMA_URL: Optional[str] = None
    OLLAMA_MODEL: str = "llama3.2"

    # ── RAG ───────────────────────────────────────────────────────────────────
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # ── Whisper STT ───────────────────────────────────────────────────────────
    WHISPER_MODEL: str = "tiny"

    # ── CRM / External System ─────────────────────────────────────────────────
    CRM_BASE_URL: Optional[str] = "http://localhost:8000/mock-crm"
    CRM_API_KEY: Optional[str] = None

    # ── Decision Thresholds ───────────────────────────────────────────────────
    AUTO_THRESHOLD: int = 75       # >= this → autonomous execution
    ASSISTED_THRESHOLD: int = 45   # >= this → human-assisted; < this → escalated

    # ── SLA ───────────────────────────────────────────────────────────────────
    SLA_CHECK_INTERVAL: int = 60   # seconds between SLA checks

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "*"

    # ── Deployment ────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()