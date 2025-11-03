"""File tracking database for managing scanned files and change detection.

Tracks files by path, SHA-256 hash, scan timestamp, size, and modification time.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


class FileTrackerError(Exception):
    """Base exception for file tracker errors."""

    pass


@dataclass
class FileRecord:
    """Represents a file record in the tracking database."""

    path: str
    sha256: str
    scanned_at: datetime
    size_bytes: int
    mtime_ns: int
    id: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate record fields."""
        if not self.path:
            raise ValueError("path cannot be empty")
        if not self.sha256 or len(self.sha256) != 64:
            raise ValueError("sha256 must be a 64-character hex string")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        if self.mtime_ns < 0:
            raise ValueError("mtime_ns must be non-negative")


class FileTracker:
    """Manages file scan history in SQLite database."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path) -> None:
        """Initialize file tracker with database path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Open database connection and initialize schema."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self.db_path),
                isolation_level="DEFERRED",
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
        except sqlite3.Error as e:
            raise FileTrackerError(f"Failed to connect to database: {e}") from e

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _get_conn(self) -> sqlite3.Connection:
        """Get active connection or raise error."""
        if self._conn is None:
            raise FileTrackerError("Database not connected. Call connect() first.")
        return self._conn

    def _init_schema(self) -> None:
        """Initialize database schema."""
        conn = self._get_conn()
        try:
            with conn:
                # Create file_scan_history table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS file_scan_history (
                        id INTEGER PRIMARY KEY,
                        path TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        scanned_at TIMESTAMP NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        mtime_ns INTEGER NOT NULL,
                        UNIQUE(path)
                    )
                    """
                )

                # Create index on sha256 for efficient lookups
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_fsh_sha
                    ON file_scan_history(sha256)
                    """
                )

                # Store schema version
                conn.execute(
                    f"PRAGMA user_version = {self.SCHEMA_VERSION}"
                )
        except sqlite3.Error as e:
            raise FileTrackerError(f"Failed to initialize schema: {e}") from e

    def upsert(self, record: FileRecord) -> int:
        """Insert or update a file record.

        Args:
            record: FileRecord to upsert

        Returns:
            The id of the inserted/updated record

        Raises:
            FileTrackerError: If database operation fails
        """
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO file_scan_history
                        (path, sha256, scanned_at, size_bytes, mtime_ns)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        sha256 = excluded.sha256,
                        scanned_at = excluded.scanned_at,
                        size_bytes = excluded.size_bytes,
                        mtime_ns = excluded.mtime_ns
                    """,
                    (
                        record.path,
                        record.sha256,
                        record.scanned_at.isoformat(),
                        record.size_bytes,
                        record.mtime_ns,
                    ),
                )
                return cursor.lastrowid or self.get_by_path(record.path).id  # type: ignore
        except sqlite3.Error as e:
            raise FileTrackerError(f"Failed to upsert record: {e}") from e

    def get_by_path(self, path: str) -> Optional[FileRecord]:
        """Retrieve a file record by path.

        Args:
            path: File path to look up

        Returns:
            FileRecord if found, None otherwise

        Raises:
            FileTrackerError: If database operation fails
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """
                SELECT id, path, sha256, scanned_at, size_bytes, mtime_ns
                FROM file_scan_history
                WHERE path = ?
                """,
                (path,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            return FileRecord(
                id=row["id"],
                path=row["path"],
                sha256=row["sha256"],
                scanned_at=datetime.fromisoformat(row["scanned_at"]),
                size_bytes=row["size_bytes"],
                mtime_ns=row["mtime_ns"],
            )
        except sqlite3.Error as e:
            raise FileTrackerError(f"Failed to get record by path: {e}") from e

    def get_by_sha256(self, sha256: str) -> list[FileRecord]:
        """Retrieve all file records with a given SHA-256 hash.

        Args:
            sha256: SHA-256 hash to look up

        Returns:
            List of FileRecords with matching hash

        Raises:
            FileTrackerError: If database operation fails
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """
                SELECT id, path, sha256, scanned_at, size_bytes, mtime_ns
                FROM file_scan_history
                WHERE sha256 = ?
                ORDER BY scanned_at DESC
                """,
                (sha256,),
            )
            return [
                FileRecord(
                    id=row["id"],
                    path=row["path"],
                    sha256=row["sha256"],
                    scanned_at=datetime.fromisoformat(row["scanned_at"]),
                    size_bytes=row["size_bytes"],
                    mtime_ns=row["mtime_ns"],
                )
                for row in cursor.fetchall()
            ]
        except sqlite3.Error as e:
            raise FileTrackerError(f"Failed to get records by sha256: {e}") from e

    def delete_by_path(self, path: str) -> bool:
        """Delete a file record by path.

        Args:
            path: File path to delete

        Returns:
            True if record was deleted, False if not found

        Raises:
            FileTrackerError: If database operation fails
        """
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    DELETE FROM file_scan_history
                    WHERE path = ?
                    """,
                    (path,),
                )
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            raise FileTrackerError(f"Failed to delete record: {e}") from e

    def get_all(self, limit: Optional[int] = None) -> list[FileRecord]:
        """Retrieve all file records.

        Args:
            limit: Optional limit on number of records to return

        Returns:
            List of all FileRecords

        Raises:
            FileTrackerError: If database operation fails
        """
        conn = self._get_conn()
        try:
            query = """
                SELECT id, path, sha256, scanned_at, size_bytes, mtime_ns
                FROM file_scan_history
                ORDER BY scanned_at DESC
            """
            if limit is not None:
                query += f" LIMIT {limit}"

            cursor = conn.execute(query)
            return [
                FileRecord(
                    id=row["id"],
                    path=row["path"],
                    sha256=row["sha256"],
                    scanned_at=datetime.fromisoformat(row["scanned_at"]),
                    size_bytes=row["size_bytes"],
                    mtime_ns=row["mtime_ns"],
                )
                for row in cursor.fetchall()
            ]
        except sqlite3.Error as e:
            raise FileTrackerError(f"Failed to get all records: {e}") from e

    def count(self) -> int:
        """Count total number of tracked files.

        Returns:
            Total number of records

        Raises:
            FileTrackerError: If database operation fails
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM file_scan_history")
            result = cursor.fetchone()
            return result[0] if result else 0
        except sqlite3.Error as e:
            raise FileTrackerError(f"Failed to count records: {e}") from e

    def vacuum(self) -> None:
        """Run VACUUM to reclaim space and optimize database.

        Raises:
            FileTrackerError: If database operation fails
        """
        conn = self._get_conn()
        try:
            # VACUUM cannot run in a transaction
            conn.isolation_level = None
            conn.execute("VACUUM")
            conn.isolation_level = "DEFERRED"
        except sqlite3.Error as e:
            raise FileTrackerError(f"Failed to vacuum database: {e}") from e

    def __enter__(self) -> "FileTracker":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """Context manager exit."""
        self.close()
