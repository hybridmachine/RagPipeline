"""Batch processing utilities for efficient embedding generation.

Handles splitting large lists of texts into batches and processing them
concurrently with proper rate limiting and error handling.
"""

import asyncio
from typing import Any, Callable, Optional, TypeVar

from rag_core.config import Config
from rag_core.vectorizer.embedder import Embedder, EmbedderError

T = TypeVar("T")


class BatchProcessor:
    """Process items in batches with concurrency control."""

    def __init__(
        self,
        embedder: Embedder,
        config: Config,
        batch_size: Optional[int] = None,
        max_concurrent_batches: Optional[int] = None,
    ) -> None:
        """Initialize batch processor.

        Args:
            embedder: Embedder instance to use
            config: Configuration instance
            batch_size: Override batch size (from config if None)
            max_concurrent_batches: Override max concurrent batches (from config if None)
        """
        self.embedder = embedder
        self.config = config
        self.batch_size = batch_size or config.embedding_batch_size
        self.max_concurrent_batches = (
            max_concurrent_batches or config.max_concurrent_requests
        )

    def create_batches(self, items: list[T]) -> list[list[T]]:
        """Split items into batches.

        Args:
            items: List of items to batch

        Returns:
            List of batches
        """
        if not items:
            return []

        batches = []
        for i in range(0, len(items), self.batch_size):
            batch = items[i : i + self.batch_size]
            batches.append(batch)
        return batches

    async def process_batches(
        self,
        texts: list[str],
        normalize: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[list[float]]:
        """Process texts in batches with concurrency control.

        Args:
            texts: List of texts to embed
            normalize: Whether to normalize embeddings
            progress_callback: Optional callback(completed, total) for progress tracking

        Returns:
            List of embedding vectors in same order as input texts

        Raises:
            EmbedderError: If any batch fails after retries
        """
        if not texts:
            return []

        batches = self.create_batches(texts)
        total_batches = len(batches)

        # Semaphore to limit concurrent batches
        semaphore = asyncio.Semaphore(self.max_concurrent_batches)

        # Track results with their batch index to preserve order
        results: list[tuple[int, list[list[float]]]] = []
        completed = 0

        async def process_batch(batch_idx: int, batch: list[str]) -> None:
            """Process a single batch with semaphore."""
            nonlocal completed

            async with semaphore:
                embeddings = await self.embedder.embed_batch(
                    batch, normalize=normalize
                )
                results.append((batch_idx, embeddings))

                completed += 1
                if progress_callback:
                    progress_callback(completed, total_batches)

        # Create tasks for all batches
        tasks = [
            asyncio.create_task(process_batch(idx, batch))
            for idx, batch in enumerate(batches)
        ]

        # Wait for all tasks to complete
        await asyncio.gather(*tasks)

        # Sort results by batch index and flatten
        results.sort(key=lambda x: x[0])
        all_embeddings = []
        for _, batch_embeddings in results:
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def process_with_metadata(
        self,
        items: list[tuple[str, T]],
        normalize: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[tuple[list[float], T]]:
        """Process texts with associated metadata.

        Args:
            items: List of (text, metadata) tuples
            normalize: Whether to normalize embeddings
            progress_callback: Optional callback for progress tracking

        Returns:
            List of (embedding, metadata) tuples in same order as input

        Raises:
            EmbedderError: If any batch fails after retries
        """
        if not items:
            return []

        # Extract texts and metadata
        texts = [text for text, _ in items]
        metadata = [meta for _, meta in items]

        # Process all texts
        embeddings = await self.process_batches(
            texts, normalize=normalize, progress_callback=progress_callback
        )

        # Combine embeddings with metadata
        return list(zip(embeddings, metadata))


async def embed_texts_batch(
    texts: list[str],
    config: Config,
    endpoint_url: Optional[str] = None,
    api_token: Optional[str] = None,
    model_id: Optional[str] = None,
    batch_size: Optional[int] = None,
    normalize: bool = True,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> list[list[float]]:
    """Convenience function to embed texts in batches.

    Creates embedder and batch processor, processes texts, and cleans up.

    Args:
        texts: List of texts to embed
        config: Configuration instance
        endpoint_url: Override endpoint URL
        api_token: Override API token
        model_id: Override model ID
        batch_size: Override batch size
        normalize: Whether to normalize embeddings
        progress_callback: Optional callback for progress tracking

    Returns:
        List of embedding vectors

    Raises:
        EmbedderError: If embedding generation fails
    """
    async with Embedder(
        config=config,
        endpoint_url=endpoint_url,
        api_token=api_token,
        model_id=model_id,
    ) as embedder:
        processor = BatchProcessor(
            embedder=embedder,
            config=config,
            batch_size=batch_size,
        )
        return await processor.process_batches(
            texts=texts,
            normalize=normalize,
            progress_callback=progress_callback,
        )
