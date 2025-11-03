"""Configuration management for RAG Pipeline.

Handles environment variables, config files, and CLI flag precedence.
"""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Main configuration for RAG Pipeline.

    Configuration precedence: CLI flags > config.yaml > environment variables
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database configuration
    db_path: Path = Field(
        default=Path(".rag/rag.sqlite"),
        description="Path to SQLite database file",
    )
    sqlite_vec_path: Optional[Path] = Field(
        default=None,
        description="Path to sqlite-vec extension (.so file)",
    )

    # Hugging Face configuration
    hf_endpoint_url: Optional[str] = Field(
        default=None,
        description="Hugging Face Inference Endpoint or TEI URL",
    )
    hf_api_token: Optional[str] = Field(
        default=None,
        description="Hugging Face API token",
    )
    embed_model_id: str = Field(
        default="BAAI/bge-m3",
        description="Embedding model ID",
    )

    # Vector store configuration
    vector_distance: str = Field(
        default="cosine",
        description="Distance metric for vector similarity",
    )
    embedding_batch_size: int = Field(
        default=64,
        description="Batch size for embedding generation",
    )

    # OpenAI configuration
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key",
    )
    openai_base_url: Optional[str] = Field(
        default=None,
        description="Optional OpenAI base URL for self-hosted gateways",
    )
    openai_model: str = Field(
        default="gpt-4o",
        description="OpenAI model to use for generation",
    )

    # Chunking configuration
    chunk_target_tokens: int = Field(
        default=512,
        description="Target tokens per chunk",
    )
    chunk_overlap_tokens: int = Field(
        default=50,
        description="Token overlap between chunks",
    )

    # Scanning configuration
    max_files_per_run: Optional[int] = Field(
        default=None,
        description="Maximum files to process per scan run",
    )
    max_chunk_bytes: int = Field(
        default=1_000_000,
        description="Maximum bytes per chunk",
    )

    # Retrieval configuration
    retrieval_k: int = Field(
        default=8,
        description="Number of chunks to retrieve",
    )

    # Logging configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    log_file: Optional[Path] = Field(
        default=None,
        description="Optional log file path",
    )

    # Concurrency configuration
    max_concurrent_requests: int = Field(
        default=10,
        description="Maximum concurrent API requests",
    )
    request_timeout_seconds: float = Field(
        default=30.0,
        description="Timeout for API requests in seconds",
    )

    def ensure_db_directory(self) -> None:
        """Ensure database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


# Global config instance (can be overridden)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config) -> None:
    """Set global config instance."""
    global _config
    _config = config
