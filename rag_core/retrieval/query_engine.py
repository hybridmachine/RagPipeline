"""Query engine for RAG retrieval.

Handles query embedding, vector search, re-ranking, and context assembly.
"""

import asyncio
from dataclasses import dataclass
from typing import List, Optional

from rag_core.config import Config
from rag_core.database.vector_store import Hit, VectorStore
from rag_core.vectorizer.embedder import Embedder
from rag_core.logging_config import get_query_logger


class QueryEngineError(Exception):
    """Base exception for query engine errors."""

    pass


@dataclass
class Citation:
    """Represents a source citation for a query result."""

    doc_path: str
    chunk_id: int
    score: float
    text: str
    section: Optional[str] = None


@dataclass
class QueryResult:
    """Represents the result of a query."""

    query_text: str
    context: str
    citations: List[Citation]
    total_chunks: int
    search_time_ms: float
    span_id: str  # For tracking query across logging


class QueryEngine:
    """Query engine for RAG retrieval.

    Handles:
    - Query embedding generation
    - Vector similarity search
    - Optional re-ranking
    - Context assembly with citations
    """

    def __init__(self, config: Config) -> None:
        """Initialize query engine.

        Args:
            config: Configuration instance
        """
        self.config = config
        self._embedder: Optional[Embedder] = None
        self._vector_store: Optional[VectorStore] = None

    async def query(
        self,
        query_text: str,
        k: int = 8,
        rerank_top_n: Optional[int] = None,
        distance_metric: str = "cosine",
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> QueryResult:
        """Execute a query against the RAG system.

        Args:
            query_text: The query string
            k: Number of chunks to retrieve
            rerank_top_n: If specified, re-rank top N results (not yet implemented)
            distance_metric: Distance metric for vector search
            project_id: Optional project ID for per-project logging
            user_id: Optional user ID for logging

        Returns:
            QueryResult with context and citations

        Raises:
            QueryEngineError: If query execution fails
        """
        import time

        start_time = time.perf_counter()

        # Initialize query logger with project context
        query_logger = get_query_logger(
            log_level=self.config.log_level, project_id=project_id
        )
        span_id = query_logger.log_query_start(query_text, user_id=user_id)

        try:
            # Initialize components
            if self._embedder is None:
                self._embedder = Embedder(self.config)
                await self._embedder.connect()

            if self._vector_store is None:
                self._vector_store = VectorStore(self.config)
                self._vector_store.connect()

            # Generate query embedding
            query_vector = await self._embedder.embed(query_text)

            # Perform vector search
            hits = self._vector_store.search(
                query_vector=query_vector,
                k=k,
                distance_metric=distance_metric,
            )

            # Check if no embeddings have been added yet
            if not hits:
                query_logger.log_warning(
                    span_id,
                    "No embeddings found in vector store. Please upload and embed documents first.",
                )

            # Log retrieved chunks with excerpts
            chunks_for_log = [
                {
                    "doc_path": hit.doc_path,
                    "chunk_id": hit.chunk_id,
                    "score": hit.score,
                    "text": hit.text,
                }
                for hit in hits
            ]
            search_time_ms = (time.perf_counter() - start_time) * 1000
            query_logger.log_retrieved_chunks(span_id, chunks_for_log, search_time_ms)

            # Optional re-ranking (placeholder for future implementation)
            if rerank_top_n and rerank_top_n < len(hits):
                # TODO: Implement cross-encoder re-ranking
                # For now, just take top N
                hits = hits[:rerank_top_n]

            # Build context and citations
            context_parts = []
            citations = []

            for i, hit in enumerate(hits):
                # Add to context with citation marker
                context_parts.append(f"[{i+1}] {hit.text}")

                # Create citation
                citations.append(
                    Citation(
                        doc_path=hit.doc_path,
                        chunk_id=hit.chunk_id,
                        score=hit.score,
                        text=hit.text,
                        section=hit.section,
                    )
                )

            # Assemble final context
            context = "\n\n".join(context_parts)

            # Calculate search time
            search_time_ms = (time.perf_counter() - start_time) * 1000

            return QueryResult(
                query_text=query_text,
                context=context,
                citations=citations,
                total_chunks=len(hits),
                search_time_ms=search_time_ms,
                span_id=span_id,
            )

        except Exception as e:
            query_logger.log_error(span_id, f"Query execution failed: {e}")
            raise QueryEngineError(f"Query execution failed: {e}") from e

    async def close(self) -> None:
        """Close query engine resources."""
        if self._embedder:
            await self._embedder.close()
        if self._vector_store:
            self._vector_store.close()

    async def __aenter__(self) -> "QueryEngine":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """Async context manager exit."""
        await self.close()
