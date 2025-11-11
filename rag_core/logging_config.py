"""
Structured logging configuration for RAG pipeline.

Provides JSON-formatted logging per CLAUDE.md specification with support
for query logging including questions, retrieved chunks, and answers.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, asdict
import uuid


@dataclass
class QueryLogEntry:
    """Structured log entry for a RAG query."""

    timestamp: float
    span_id: str
    event: str
    level: str
    query_text: Optional[str] = None
    retrieved_chunks: Optional[list[dict[str, Any]]] = None
    context_length: Optional[int] = None
    answer: Optional[str] = None
    model: Optional[str] = None
    total_tokens: Optional[int] = None
    search_time_ms: Optional[float] = None
    llm_time_ms: Optional[float] = None
    error: Optional[str] = None
    project_id: Optional[str] = None
    user_id: Optional[str] = None

    def to_json(self) -> str:
        """Convert to JSON string."""
        data = asdict(self)
        # Remove None values for cleaner logs
        data = {k: v for k, v in data.items() if v is not None}
        return json.dumps(data, ensure_ascii=False)


class QueryLogger:
    """Logger for RAG queries with structured JSON output."""

    def __init__(
        self,
        log_file: Optional[Path] = None,
        log_level: str = "INFO",
        project_id: Optional[str] = None,
    ):
        """
        Initialize query logger.

        Args:
            log_file: Path to log file (default: .rag/queries.log or .rag/projects/{project_id}/queries.log)
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            project_id: Optional project ID for per-project logging
        """
        # If project_id provided, use project-specific log path
        if project_id and not log_file:
            log_file = Path(".rag") / "projects" / project_id / "queries.log"
        else:
            log_file = log_file or Path(".rag/queries.log")

        self.log_file = log_file
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.project_id = project_id

        # Ensure log directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Use project ID in logger name if available
        logger_name = f"rag.query.{project_id}" if project_id else "rag.query"

        # Configure logger
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(self.log_level)
        self.logger.handlers.clear()  # Remove any existing handlers

        # File handler with JSON formatting
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(logging.Formatter("%(message)s"))  # Raw JSON
        self.logger.addHandler(file_handler)

        # Don't propagate to root logger
        self.logger.propagate = False

    def _generate_span_id(self) -> str:
        """Generate unique span ID for tracking related log entries."""
        return str(uuid.uuid4())[:8]

    def _truncate_text(self, text: str, max_length: int = 200) -> str:
        """Truncate text to max_length characters with ellipsis."""
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."

    def log_query_start(
        self,
        query_text: str,
        span_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """
        Log the start of a query.

        Args:
            query_text: The user's query
            span_id: Optional span ID (will generate if not provided)
            user_id: Optional user ID for the query

        Returns:
            span_id for tracking this query
        """
        span_id = span_id or self._generate_span_id()

        entry = QueryLogEntry(
            timestamp=time.time(),
            span_id=span_id,
            event="query_start",
            level="INFO",
            query_text=query_text,
            project_id=self.project_id,
            user_id=user_id,
        )

        self.logger.info(entry.to_json())
        return span_id

    def log_retrieved_chunks(
        self,
        span_id: str,
        chunks: list[dict[str, Any]],
        search_time_ms: Optional[float] = None,
    ) -> None:
        """
        Log retrieved document chunks with excerpts.

        Args:
            span_id: Query span ID
            chunks: List of chunk dicts with keys: doc_path, chunk_id, score, text
            search_time_ms: Time taken for vector search
        """
        # Create excerpts (first 200 chars of each chunk)
        chunk_excerpts = []
        for chunk in chunks:
            chunk_excerpts.append(
                {
                    "doc_path": chunk.get("doc_path"),
                    "chunk_id": chunk.get("chunk_id"),
                    "score": chunk.get("score"),
                    "text_excerpt": self._truncate_text(
                        chunk.get("text", ""), 200
                    ),
                }
            )

        entry = QueryLogEntry(
            timestamp=time.time(),
            span_id=span_id,
            event="chunks_retrieved",
            level="INFO",
            retrieved_chunks=chunk_excerpts,
            search_time_ms=search_time_ms,
            project_id=self.project_id,
        )

        self.logger.info(entry.to_json())

    def log_answer(
        self,
        span_id: str,
        answer: str,
        model: Optional[str] = None,
        total_tokens: Optional[int] = None,
        llm_time_ms: Optional[float] = None,
    ) -> None:
        """
        Log the LLM's answer.

        Args:
            span_id: Query span ID
            answer: The generated answer
            model: Model used for generation
            total_tokens: Total tokens used
            llm_time_ms: Time taken for LLM generation
        """
        entry = QueryLogEntry(
            timestamp=time.time(),
            span_id=span_id,
            event="answer_generated",
            level="INFO",
            answer=answer,
            model=model,
            total_tokens=total_tokens,
            llm_time_ms=llm_time_ms,
            project_id=self.project_id,
        )

        self.logger.info(entry.to_json())

    def log_error(self, span_id: str, error: str) -> None:
        """
        Log an error during query processing.

        Args:
            span_id: Query span ID
            error: Error message
        """
        entry = QueryLogEntry(
            timestamp=time.time(),
            span_id=span_id,
            event="query_error",
            level="ERROR",
            error=error,
            project_id=self.project_id,
        )

        self.logger.error(entry.to_json())


# Global logger instances: one per project + global
_query_loggers: dict[Optional[str], QueryLogger] = {}


def get_query_logger(
    log_file: Optional[Path] = None,
    log_level: str = "INFO",
    project_id: Optional[str] = None,
) -> QueryLogger:
    """
    Get or create a query logger instance (per-project or global).

    Args:
        log_file: Path to log file (default: .rag/queries.log or .rag/projects/{project_id}/queries.log)
        log_level: Logging level
        project_id: Optional project ID for per-project logging

    Returns:
        QueryLogger instance
    """
    # Use project_id as cache key (None for global logger)
    cache_key = project_id

    if cache_key not in _query_loggers:
        _query_loggers[cache_key] = QueryLogger(log_file, log_level, project_id)

    return _query_loggers[cache_key]
