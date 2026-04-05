"""
IntentFlow — Local embeddings using sentence-transformers.
No API key needed — runs entirely on CPU.
"""

import logging
from functools import lru_cache
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        from config import get_settings
        settings = get_settings()
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")
    return _model


def embed(text: str) -> List[float]:
    """Embed a single text string → vector."""
    model = _get_model()
    vec = model.encode(text, show_progress_bar=False)
    return vec.tolist()


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed multiple texts at once (more efficient)."""
    model = _get_model()
    vecs = model.encode(texts, show_progress_bar=False, batch_size=32)
    return [v.tolist() for v in vecs]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))
