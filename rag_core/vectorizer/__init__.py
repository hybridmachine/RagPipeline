"""Embedding generation and batch processing modules."""

from rag_core.vectorizer.batch_processor import BatchProcessor, embed_texts_batch
from rag_core.vectorizer.embedder import Embedder, EmbedderError

__all__ = [
    "Embedder",
    "EmbedderError",
    "BatchProcessor",
    "embed_texts_batch",
]
