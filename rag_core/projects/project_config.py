"""Project-specific configuration management.

Each project has its own configuration for embedding models, LLM models,
and API keys. This module handles loading, saving, and converting project
configurations.
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from rag_core.config import Config


@dataclass
class ProjectConfig:
    """Project-specific configuration.

    Each project can have its own embedding model, LLM model, API keys,
    and other settings. This allows different projects to use different
    AI models and services independently.
    """

    # Project identity
    id: str
    name: str
    description: Optional[str] = None

    # Storage paths (auto-generated)
    data_dir: Optional[Path] = None
    vector_db_path: Optional[Path] = None
    log_file: Optional[Path] = None

    # Embedding configuration
    embed_model_id: str = "BAAI/bge-m3"
    hf_endpoint_url: Optional[str] = None
    hf_api_token: Optional[str] = None
    embed_add_eos_token: Optional[str] = None

    # LLM configuration
    llm_model_id: str = "gpt-4o"
    llm_endpoint_url: Optional[str] = None
    llm_api_token: Optional[str] = None

    # Chunking configuration
    chunk_target_tokens: int = 512
    chunk_overlap_tokens: int = 50

    # Retrieval configuration
    retrieval_k: int = 8

    # Concurrency configuration
    max_concurrent_requests: int = 10
    request_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        """Initialize derived paths if not already set."""
        if self.data_dir is None:
            self.data_dir = Path(f".rag/projects/{self.id}")
        if self.vector_db_path is None:
            self.vector_db_path = self.data_dir / "vectors.db"
        if self.log_file is None:
            self.log_file = self.data_dir / "queries.log"

    def to_core_config(self, sqlite_vec_path: Optional[Path] = None) -> Config:
        """Convert to rag_core.Config instance for use with core modules.

        Args:
            sqlite_vec_path: Path to sqlite-vec extension, if needed.

        Returns:
            Config instance with project settings applied.

        Note:
            Falls back to environment variables for any unset project settings.
            Priority: project config > environment variables > hardcoded defaults
        """
        # Get global config to use as fallback for unset project settings
        from rag_core.config import get_config
        global_config = get_config()

        return Config(
            db_path=self.vector_db_path,
            sqlite_vec_path=sqlite_vec_path,
            hf_endpoint_url=self.hf_endpoint_url or global_config.hf_endpoint_url,
            hf_api_token=self.hf_api_token or global_config.hf_api_token,
            embed_model_id=self.embed_model_id or global_config.embed_model_id,
            embed_add_eos_token=self.embed_add_eos_token or global_config.embed_add_eos_token,
            llm_endpoint_url=self.llm_endpoint_url or global_config.llm_endpoint_url,
            llm_api_token=self.llm_api_token or global_config.llm_api_token,
            llm_model_id=self.llm_model_id or global_config.llm_model_id,
            chunk_target_tokens=self.chunk_target_tokens,
            chunk_overlap_tokens=self.chunk_overlap_tokens,
            retrieval_k=self.retrieval_k,
            log_file=self.log_file,
            max_concurrent_requests=self.max_concurrent_requests,
            request_timeout_seconds=self.request_timeout_seconds,
        )

    def to_dict(self, exclude_paths: bool = False) -> dict:
        """Convert to dictionary for JSON serialization.

        Args:
            exclude_paths: If True, exclude Path objects. Useful for JSON storage.

        Returns:
            Dictionary representation of the config.
        """
        data = asdict(self)
        if exclude_paths:
            # Remove Path objects, keep them as strings
            for key in ["data_dir", "vector_db_path", "log_file"]:
                if key in data and data[key] is not None:
                    data[key] = str(data[key])
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectConfig":
        """Create ProjectConfig from dictionary.

        Args:
            data: Dictionary with project configuration.

        Returns:
            ProjectConfig instance.
        """
        # Convert string paths back to Path objects
        if isinstance(data.get("data_dir"), str):
            data["data_dir"] = Path(data["data_dir"])
        if isinstance(data.get("vector_db_path"), str):
            data["vector_db_path"] = Path(data["vector_db_path"])
        if isinstance(data.get("log_file"), str):
            data["log_file"] = Path(data["log_file"])
        return cls(**data)

    def save_to_file(self, path: Path) -> None:
        """Save configuration to JSON file.

        Args:
            path: Path to save the configuration JSON.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(exclude_paths=True), f, indent=2)

    @classmethod
    def load_from_file(cls, path: Path) -> "ProjectConfig":
        """Load configuration from JSON file.

        Args:
            path: Path to the configuration JSON.

        Returns:
            ProjectConfig instance.

        Raises:
            FileNotFoundError: If the config file doesn't exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)
