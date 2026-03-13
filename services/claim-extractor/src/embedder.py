"""Sentence embedding using all-MiniLM-L6-v2."""

import logging

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_model = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading sentence-transformers model...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Sentence-transformers model loaded")
    return _model


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Generate 384-dim embeddings for a list of texts."""
    model = get_model()
    embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=False)
    return embeddings.tolist()


def embed_single(text: str) -> list[float]:
    """Generate embedding for a single text."""
    model = get_model()
    embedding = model.encode(text)
    return embedding.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embeddings."""
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
