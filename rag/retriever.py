"""
IntentFlow — Persistent ChromaDB vector store for RAG retrieval.
Compatible with ChromaDB 1.x API.
"""

import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

import chromadb

from config import get_settings
from rag.embeddings import embed

logger = logging.getLogger(__name__)

_client = None
_collection = None

COLLECTION_NAME = "intentflow_kb"


def _reset_persistent_store() -> None:
    """Clear the local ChromaDB persistence directory so it can be rebuilt."""
    global _client, _collection

    settings = get_settings()
    persist_dir = Path(settings.CHROMA_PERSIST_DIR)

    _client = None
    _collection = None

    if persist_dir.exists():
        shutil.rmtree(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)


def _get_collection():
    global _client, _collection
    if _collection is None:
        settings = get_settings()
        try:
            _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
            _collection = _client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "collections.topic" not in message and "no such column" not in message:
                raise

            logger.warning(
                "ChromaDB schema mismatch detected; rebuilding local persistence store"
            )
            _reset_persistent_store()
            _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
            _collection = _client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )

        logger.info(f"ChromaDB collection '{COLLECTION_NAME}' ready ({_collection.count()} docs)")
    return _collection


def index(doc_id: str, text: str, metadata: Optional[Dict] = None) -> None:
    """Index a document into the vector store."""
    col = _get_collection()
    vec = embed(text)
    col.upsert(
        ids=[doc_id],
        embeddings=[vec],
        documents=[text],
        metadatas=[metadata or {}],
    )


def index_batch(docs: List[Dict]) -> None:
    """
    Batch index documents.
    Each doc: {"id": str, "text": str, "metadata": dict}
    """
    if not docs:
        return
    col = _get_collection()
    from rag.embeddings import embed_batch
    texts = [d["text"] for d in docs]
    vecs = embed_batch(texts)
    col.upsert(
        ids=[d["id"] for d in docs],
        embeddings=vecs,
        documents=texts,
        metadatas=[d.get("metadata", {}) for d in docs],
    )
    logger.info(f"Indexed {len(docs)} documents")


def search(query: str, top_k: int = 5) -> List[Dict]:
    """Search the knowledge base. Returns list of {id, text, score, metadata}."""
    col = _get_collection()
    if col.count() == 0:
        return []

    vec = embed(query)
    results = col.query(
        query_embeddings=[vec],
        n_results=min(top_k, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for i in range(len(results["ids"][0])):
        distance = results["distances"][0][i]
        # ChromaDB cosine distance → similarity: 1 - distance
        score = round(1.0 - distance, 4) if distance is not None else 0.0
        hits.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "score": score,
            "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
        })

    return hits


def count() -> int:
    """Return number of documents in the collection."""
    col = _get_collection()
    return col.count()
