"""Shared file storage management with content-addressable storage.

Files are stored by content hash (SHA-256) in a shared store,
and projects link to them via symlinks. This enables deduplication
across projects while maintaining directory structure.
"""

import hashlib
import sqlite3
from pathlib import Path
from typing import Optional, Tuple


class FileStore:
    """Manage shared file storage and file references."""

    # Depth of hash subdirectories (2 levels for ~65k initial split)
    HASH_DEPTH = 2

    def __init__(self, base_dir: Path = Path(".rag")):
        """Initialize file store.

        Args:
            base_dir: Base directory for all RAG data (.rag)
        """
        self.base_dir = base_dir
        self.files_dir = base_dir / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)

    def get_file_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of file content.

        Args:
            file_path: Path to the file.

        Returns:
            Hex-encoded SHA-256 hash.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def get_content_hash(self, content: bytes) -> str:
        """Compute SHA-256 hash of content.

        Args:
            content: File content as bytes.

        Returns:
            Hex-encoded SHA-256 hash.
        """
        return hashlib.sha256(content).hexdigest()

    def get_storage_path(self, file_hash: str) -> Path:
        """Get storage path for a file hash.

        Uses nested directories based on hash prefix for distribution:
        .rag/files/{hash[:2]}/{hash[2:4]}/{hash}

        Args:
            file_hash: SHA-256 hash of file content.

        Returns:
            Path where file should be stored.
        """
        parts = [file_hash[i : i + 2] for i in range(self.HASH_DEPTH * 2)]
        return self.files_dir / Path(*parts) / file_hash

    def store_file(
        self,
        file_path: Optional[Path] = None,
        file_hash: Optional[str] = None,
        content: Optional[bytes] = None,
    ) -> Tuple[str, Path]:
        """Store file in shared store.

        Args:
            file_path: Path to file to store (ignored if content provided).
            file_hash: Pre-computed hash, or None to compute.
            content: File content as bytes (used instead of file_path if provided).

        Returns:
            Tuple of (file_hash, storage_path)

        Raises:
            FileNotFoundError: If file_path doesn't exist and content not provided.
            ValueError: If neither file_path nor content provided.
        """
        if content is None:
            if file_path is None:
                raise ValueError("Either file_path or content must be provided")
            content = file_path.read_bytes()

        if file_hash is None:
            file_hash = self.get_content_hash(content)

        storage_path = self.get_storage_path(file_hash)

        # If file already exists, skip writing
        if not storage_path.exists():
            # Create parent directory and write file
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            storage_path.write_bytes(content)

        return file_hash, storage_path

    def create_symlink(
        self,
        source_hash: str,
        link_path: Path,
        relative: bool = True,
    ) -> None:
        """Create symlink from project directory to shared file.

        Creates a symlink if it doesn't exist. If a symlink already exists
        pointing to the same file, it's left as-is. If it points to a different
        file, it's replaced.

        Args:
            source_hash: SHA-256 hash of file in shared store.
            link_path: Path where symlink should be created.
            relative: If True, use relative path in symlink.
        """
        link_path.parent.mkdir(parents=True, exist_ok=True)

        source_path = self.get_storage_path(source_hash)

        if relative:
            # Calculate relative path from link_path's parent to source_path
            # Both paths are relative to self.base_dir
            link_rel = link_path.relative_to(self.base_dir)
            source_rel = source_path.relative_to(self.base_dir)
            # Count how many levels up from link_path.parent to reach base_dir
            levels_up = len(link_rel.parent.parts)
            rel_path = Path(*[".."] * levels_up) / source_rel
            source_path = rel_path

        # If symlink already exists, remove it first
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()

        link_path.symlink_to(source_path)

    def remove_symlink(self, link_path: Path) -> None:
        """Remove symlink safely.

        Args:
            link_path: Path to the symlink.
        """
        if link_path.is_symlink():
            link_path.unlink()

    def get_file_references(
        self,
        conn: sqlite3.Connection,
        file_hash: str,
    ) -> int:
        """Get number of projects referencing a file.

        Args:
            conn: Connection to metadata database.
            file_hash: SHA-256 hash of file.

        Returns:
            Number of references.
        """
        cursor = conn.execute(
            "SELECT reference_count FROM shared_files WHERE sha256 = ?",
            (file_hash,),
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def increment_reference(
        self,
        conn: sqlite3.Connection,
        file_hash: str,
        size_bytes: int,
        mime_type: Optional[str] = None,
    ) -> None:
        """Increment reference count for a file.

        Args:
            conn: Connection to metadata database.
            file_hash: SHA-256 hash of file.
            size_bytes: File size in bytes.
            mime_type: MIME type of file.
        """
        cursor = conn.execute(
            """
            INSERT INTO shared_files (sha256, physical_path, size_bytes, mime_type, reference_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(sha256) DO UPDATE SET
                reference_count = reference_count + 1,
                last_accessed = CURRENT_TIMESTAMP
            """,
            (file_hash, str(self.get_storage_path(file_hash)), size_bytes, mime_type),
        )
        conn.commit()

    def decrement_reference(
        self,
        conn: sqlite3.Connection,
        file_hash: str,
    ) -> int:
        """Decrement reference count for a file.

        Args:
            conn: Connection to metadata database.
            file_hash: SHA-256 hash of file.

        Returns:
            New reference count.
        """
        cursor = conn.execute(
            """
            UPDATE shared_files SET reference_count = reference_count - 1
            WHERE sha256 = ?
            """,
            (file_hash,),
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT reference_count FROM shared_files WHERE sha256 = ?",
            (file_hash,),
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def cleanup_unused_files(self, conn: sqlite3.Connection) -> int:
        """Remove files with zero references.

        Args:
            conn: Connection to metadata database.

        Returns:
            Number of files deleted.
        """
        cursor = conn.execute(
            "SELECT sha256, physical_path FROM shared_files WHERE reference_count <= 0"
        )
        rows = cursor.fetchall()

        deleted = 0
        for row in rows:
            file_hash, physical_path = row
            path = Path(physical_path)
            if path.exists():
                path.unlink()
                deleted += 1
            conn.execute(
                "DELETE FROM shared_files WHERE sha256 = ?",
                (file_hash,),
            )

        conn.commit()
        return deleted
