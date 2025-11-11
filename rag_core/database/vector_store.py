"""Vector storage using sqlite-vec.

Manages chunk metadata and vector embeddings with ANN search capabilities.
"""

import sqlite3
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import sqlite_vec

from rag_core.config import Config
from rag_core.database.file_tracker import FileTracker
from rag_core.scanner.chunker import Chunk


class VectorStoreError(Exception):
    """Base exception for vector store errors."""

    pass


@dataclass
class Hit:
    """Represents a search result hit."""

    chunk_id: int
    doc_path: str
    text: str
    score: float
    section: Optional[str] = None


class VectorStore:
    """Manages vector storage and search using sqlite-vec."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        config: Config,
        embedding_dim: Optional[int] = None,
    ) -> None:
        """Initialize vector store.

        Args:
            config: Configuration instance
            embedding_dim: Embedding dimension (auto-detected if None)
        """
        self.config = config
        self.embedding_dim = embedding_dim
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Open database connection and initialize schema."""
        try:
            self.config.db_path.parent.mkdir(parents=True, exist_ok=True)

            self._conn = sqlite3.connect(
                str(self.config.db_path),
                isolation_level="DEFERRED",
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row

            # Load sqlite-vec extension
            # Try custom path first, then auto-detect from sqlite_vec package
            if self.config.sqlite_vec_path:
                self._conn.enable_load_extension(True)
                self._conn.load_extension(str(self.config.sqlite_vec_path))
                self._conn.enable_load_extension(False)
            else:
                # Use sqlite_vec.load() which handles the extension path automatically
                self._conn.enable_load_extension(True)
                sqlite_vec.load(self._conn)
                self._conn.enable_load_extension(False)

            # Verify vec0 module loaded successfully
            try:
                cursor = self._conn.execute("SELECT vec_version()")
                version = cursor.fetchone()
                if version:
                    print(f"sqlite-vec version: {version[0]}")
            except sqlite3.OperationalError as e:
                raise VectorStoreError(
                    f"Failed to load sqlite-vec extension. "
                    f"Ensure sqlite-vec package is installed: pip install sqlite-vec. Error: {e}"
                ) from e

            self._init_schema()

        except sqlite3.Error as e:
            raise VectorStoreError(f"Failed to connect to database: {e}") from e

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _get_conn(self) -> sqlite3.Connection:
        """Get active connection or raise error."""
        if self._conn is None:
            raise VectorStoreError("Database not connected. Call connect() first.")
        return self._conn

    def _init_schema(self) -> None:
        """Initialize database schema."""
        conn = self._get_conn()

        try:
            with conn:
                # Create chunks table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chunks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        doc_path TEXT NOT NULL,
                        chunk_id INTEGER NOT NULL,
                        start_char INTEGER,
                        end_char INTEGER,
                        text TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        section TEXT,
                        mime TEXT,
                        token_count INTEGER,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        embedding_status TEXT DEFAULT 'pending',
                        UNIQUE(doc_path, chunk_id)
                    )
                    """
                )

                # Create indexes
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chunks_sha
                    ON chunks(sha256)
                    """
                )

                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chunks_doc
                    ON chunks(doc_path)
                    """
                )

                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chunks_status
                    ON chunks(embedding_status)
                    """
                )

                # Note: chunk_vectors table will be created dynamically
                # when we know the embedding dimension

        except sqlite3.Error as e:
            raise VectorStoreError(f"Failed to initialize schema: {e}") from e

    def _ensure_vector_table(self, dims: int) -> None:
        """Ensure vector table exists with correct dimensions.

        Args:
            dims: Embedding dimension
        """
        conn = self._get_conn()

        try:
            # Check if table exists
            cursor = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='chunk_vectors'
                """
            )

            if cursor.fetchone() is None:
                # Create vec0 virtual table
                # Note: sqlite-vec syntax varies by version
                # This is a simple implementation - may need adjustment
                conn.execute(
                    f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors
                    USING vec0(
                        embedding FLOAT[{dims}]
                    )
                    """
                )

                self.embedding_dim = dims

        except sqlite3.Error as e:
            raise VectorStoreError(f"Failed to create vector table: {e}") from e

    def _serialize_vector(self, vector: List[float]) -> bytes:
        """Serialize vector to bytes for storage.

        Args:
            vector: Embedding vector

        Returns:
            Serialized bytes
        """
        # Pack as array of floats
        return struct.pack(f"{len(vector)}f", *vector)

    def _deserialize_vector(self, data: bytes) -> List[float]:
        """Deserialize vector from bytes.

        Args:
            data: Serialized vector bytes

        Returns:
            Embedding vector
        """
        count = len(data) // 4  # 4 bytes per float
        return list(struct.unpack(f"{count}f", data))

    def insert_chunks(self, chunks: List[Chunk], sha256: str) -> None:
        """Insert chunks into database.

        Args:
            chunks: List of chunks to insert
            sha256: SHA-256 hash of source file

        Raises:
            VectorStoreError: If insertion fails
        """
        conn = self._get_conn()

        try:
            with conn:
                for chunk in chunks:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO chunks
                            (doc_path, chunk_id, start_char, end_char, text,
                             sha256, section, token_count, embedding_status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                        """,
                        (
                            chunk.doc_path,
                            chunk.chunk_id,
                            chunk.start_char,
                            chunk.end_char,
                            chunk.text,
                            sha256,
                            chunk.section,
                            chunk.token_count,
                        ),
                    )

        except sqlite3.Error as e:
            raise VectorStoreError(f"Failed to insert chunks: {e}") from e

    def upsert_vectors(
        self,
        chunks: List[Chunk],
        vectors: List[List[float]],
    ) -> None:
        """Insert or update vectors for chunks.

        Args:
            chunks: List of chunks
            vectors: List of embedding vectors

        Raises:
            VectorStoreError: If upsert fails
        """
        if len(chunks) != len(vectors):
            raise VectorStoreError("Number of chunks and vectors must match")

        if not vectors:
            return

        conn = self._get_conn()

        # Ensure vector table exists with correct dimensions
        dims = len(vectors[0])
        self._ensure_vector_table(dims)

        try:
            with conn:
                for chunk, vector in zip(chunks, vectors):
                    # Get or create chunk record
                    cursor = conn.execute(
                        """
                        SELECT id FROM chunks
                        WHERE doc_path = ? AND chunk_id = ?
                        """,
                        (chunk.doc_path, chunk.chunk_id),
                    )

                    row = cursor.fetchone()

                    if row is None:
                        # Insert chunk first
                        cursor = conn.execute(
                            """
                            INSERT INTO chunks
                                (doc_path, chunk_id, start_char, end_char, text,
                                 sha256, section, token_count, embedding_status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'embedded')
                            """,
                            (
                                chunk.doc_path,
                                chunk.chunk_id,
                                chunk.start_char,
                                chunk.end_char,
                                chunk.text,
                                "",  # SHA will be updated separately
                                chunk.section,
                                chunk.token_count,
                            ),
                        )
                        chunk_id = cursor.lastrowid
                    else:
                        chunk_id = row[0]

                        # Update status
                        conn.execute(
                            """
                            UPDATE chunks
                            SET embedding_status = 'embedded'
                            WHERE id = ?
                            """,
                            (chunk_id,),
                        )

                    # Insert/update vector
                    # Note: Simplified version - actual sqlite-vec API may differ
                    vector_bytes = self._serialize_vector(vector)

                    conn.execute(
                        """
                        INSERT OR REPLACE INTO chunk_vectors (rowid, embedding)
                        VALUES (?, ?)
                        """,
                        (chunk_id, vector_bytes),
                    )

        except sqlite3.Error as e:
            raise VectorStoreError(f"Failed to upsert vectors: {e}") from e

    def search(
        self,
        query_vector: List[float],
        k: int = 10,
        distance_metric: str = "cosine",
    ) -> List[Hit]:
        """Search for similar vectors.

        Args:
            query_vector: Query embedding vector
            k: Number of results to return
            distance_metric: Distance metric ('cosine', 'l2', 'inner_product')

        Returns:
            List of hits sorted by similarity

        Raises:
            VectorStoreError: If search fails
        """
        conn = self._get_conn()

        try:
            # Check if chunk_vectors table exists
            cursor = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='chunk_vectors'
                """
            )
            if cursor.fetchone() is None:
                # Vector table doesn't exist yet (no embeddings added)
                return []

            # Check if there are any embedded chunks
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM chunks WHERE embedding_status = 'embedded'"
            )
            result = cursor.fetchone()
            if result and result["count"] == 0:
                # No embeddings have been added yet
                return []

            # Serialize query vector
            query_bytes = self._serialize_vector(query_vector)

            # Perform vector search
            # Note: Actual sqlite-vec syntax may vary
            cursor = conn.execute(
                f"""
                SELECT
                    c.id,
                    c.doc_path,
                    c.text,
                    c.section,
                    vec_distance_{distance_metric}(v.embedding, ?) as distance
                FROM chunk_vectors v
                JOIN chunks c ON c.id = v.rowid
                WHERE c.embedding_status = 'embedded'
                ORDER BY distance
                LIMIT ?
                """,
                (query_bytes, k),
            )

            hits = []
            for row in cursor:
                # Convert distance to similarity score (1 - distance for cosine)
                score = 1.0 - row["distance"] if distance_metric == "cosine" else row["distance"]

                hits.append(
                    Hit(
                        chunk_id=row["id"],
                        doc_path=row["doc_path"],
                        text=row["text"],
                        score=score,
                        section=row["section"],
                    )
                )

            return hits

        except sqlite3.Error as e:
            raise VectorStoreError(f"Search failed: {e}") from e

    def get_pending_chunks(self) -> List[Chunk]:
        """Get chunks that need embedding.

        Returns:
            List of chunks with pending status
        """
        conn = self._get_conn()

        try:
            cursor = conn.execute(
                """
                SELECT id, doc_path, chunk_id, start_char, end_char,
                       text, section, token_count
                FROM chunks
                WHERE embedding_status = 'pending'
                ORDER BY created_at
                """
            )

            chunks = []
            for row in cursor:
                chunks.append(
                    Chunk(
                        text=row["text"],
                        doc_path=row["doc_path"],
                        chunk_id=row["chunk_id"],
                        start_char=row["start_char"],
                        end_char=row["end_char"],
                        section=row["section"],
                        token_count=row["token_count"],
                    )
                )

            return chunks

        except sqlite3.Error as e:
            raise VectorStoreError(f"Failed to get pending chunks: {e}") from e

    def get_all_chunks(self) -> List[Chunk]:
        """Get all chunks.

        Returns:
            List of all chunks
        """
        conn = self._get_conn()

        try:
            cursor = conn.execute(
                """
                SELECT id, doc_path, chunk_id, start_char, end_char,
                       text, section, token_count
                FROM chunks
                ORDER BY doc_path, chunk_id
                """
            )

            chunks = []
            for row in cursor:
                chunks.append(
                    Chunk(
                        text=row["text"],
                        doc_path=row["doc_path"],
                        chunk_id=row["chunk_id"],
                        start_char=row["start_char"],
                        end_char=row["end_char"],
                        section=row["section"],
                        token_count=row["token_count"],
                    )
                )

            return chunks

        except sqlite3.Error as e:
            raise VectorStoreError(f"Failed to get all chunks: {e}") from e

    def mark_pending(self, chunks: List[Chunk]) -> None:
        """Mark chunks as pending for re-embedding.

        Args:
            chunks: Chunks to mark as pending
        """
        conn = self._get_conn()

        try:
            with conn:
                for chunk in chunks:
                    conn.execute(
                        """
                        UPDATE chunks
                        SET embedding_status = 'pending'
                        WHERE doc_path = ? AND chunk_id = ?
                        """,
                        (chunk.doc_path, chunk.chunk_id),
                    )

        except sqlite3.Error as e:
            raise VectorStoreError(f"Failed to mark chunks pending: {e}") from e

    def drop_vectors(self) -> None:
        """Drop all vectors (keeps chunks)."""
        conn = self._get_conn()

        try:
            with conn:
                conn.execute("DROP TABLE IF EXISTS chunk_vectors")
                conn.execute(
                    """
                    UPDATE chunks
                    SET embedding_status = 'pending'
                    """
                )

        except sqlite3.Error as e:
            raise VectorStoreError(f"Failed to drop vectors: {e}") from e

    def cleanup_orphaned(self, tracker: FileTracker) -> int:
        """Clean up chunks for deleted/changed files.

        Args:
            tracker: File tracker to check against

        Returns:
            Number of chunks deleted
        """
        conn = self._get_conn()

        try:
            # Get all unique doc paths
            cursor = conn.execute(
                """
                SELECT DISTINCT doc_path, sha256
                FROM chunks
                """
            )

            rows = cursor.fetchall()
            deleted = 0

            with conn:
                for row in rows:
                    doc_path = row["doc_path"]
                    sha256 = row["sha256"]

                    # Check if file still exists with same hash
                    file_record = tracker.get_by_path(doc_path)

                    if file_record is None or file_record.sha256 != sha256:
                        # File deleted or changed, remove chunks
                        conn.execute(
                            """
                            DELETE FROM chunks
                            WHERE doc_path = ? AND sha256 = ?
                            """,
                            (doc_path, sha256),
                        )
                        deleted += conn.total_changes

            return deleted

        except sqlite3.Error as e:
            raise VectorStoreError(f"Failed to cleanup orphaned chunks: {e}") from e

    def count_chunks(self) -> int:
        """Count total chunks.

        Returns:
            Number of chunks
        """
        conn = self._get_conn()

        try:
            cursor = conn.execute("SELECT COUNT(*) FROM chunks")
            result = cursor.fetchone()
            return result[0] if result else 0

        except sqlite3.Error as e:
            raise VectorStoreError(f"Failed to count chunks: {e}") from e

    def count_vectors(self) -> int:
        """Count total vectors.

        Returns:
            Number of vectors
        """
        conn = self._get_conn()

        try:
            # Check if vector table exists
            cursor = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='chunk_vectors'
                """
            )

            if cursor.fetchone() is None:
                return 0

            cursor = conn.execute("SELECT COUNT(*) FROM chunk_vectors")
            result = cursor.fetchone()
            return result[0] if result else 0

        except sqlite3.Error as e:
            # Table may not exist yet
            return 0

    def vacuum(self) -> None:
        """Run VACUUM to optimize database.

        Raises:
            VectorStoreError: If vacuum fails
        """
        conn = self._get_conn()

        try:
            conn.isolation_level = None
            conn.execute("VACUUM")
            conn.isolation_level = "DEFERRED"

        except sqlite3.Error as e:
            raise VectorStoreError(f"Failed to vacuum database: {e}") from e

    def __enter__(self) -> "VectorStore":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """Context manager exit."""
        self.close()
