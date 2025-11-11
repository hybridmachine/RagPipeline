"""Database initialization and connection management for multi-project system."""

import sqlite3
from pathlib import Path
from typing import Optional

from rag_core.projects.schema import METADATA_SCHEMA, PROJECT_SCHEMA


class MetadataDB:
    """Handle metadata database for users, projects, and shared files."""

    def __init__(self, db_path: Path = Path(".rag/metadata.db")):
        """Initialize metadata database.

        Args:
            db_path: Path to metadata database file.
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        """Initialize database schema if needed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(METADATA_SCHEMA)
            conn.commit()

    def get_connection(self) -> sqlite3.Connection:
        """Get database connection.

        Returns:
            SQLite connection with row factory set.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


class ProjectDB:
    """Handle project-specific database for chunks and vectors."""

    def __init__(self, db_path: Path):
        """Initialize project database.

        Args:
            db_path: Path to project's vector database file.
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        """Initialize database schema if needed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(PROJECT_SCHEMA)
            conn.commit()

    def get_connection(self) -> sqlite3.Connection:
        """Get database connection.

        Returns:
            SQLite connection with row factory set.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
