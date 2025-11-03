"""File scanning and change detection.

Walks directory trees, computes hashes, and identifies changed files.
"""

import asyncio
import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

from rag_core.config import Config
from rag_core.database.file_tracker import FileRecord, FileTracker


class ScannerError(Exception):
    """Base exception for scanner errors."""

    pass


@dataclass
class ScannedFile:
    """Represents a scanned file with metadata."""

    path: Path
    absolute_path: Path
    relative_path: str
    sha256: str
    size_bytes: int
    mtime_ns: int
    mime_type: Optional[str]
    is_changed: bool


class FileScanner:
    """Scans directories and detects file changes."""

    # Supported file extensions
    SUPPORTED_TEXT_EXTENSIONS = {
        ".txt", ".md", ".rst", ".html", ".htm",
    }

    SUPPORTED_CODE_EXTENSIONS = {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp",
        ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift",
        ".kt", ".scala", ".sh", ".bash", ".sql",
    }

    SUPPORTED_CONFIG_EXTENSIONS = {
        ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml",
    }

    SUPPORTED_DOC_EXTENSIONS = {
        ".pdf",
    }

    # Default exclude patterns
    DEFAULT_EXCLUDES = {
        "node_modules", ".git", ".svn", ".hg", "__pycache__",
        ".pytest_cache", ".mypy_cache", ".ruff_cache",
        "venv", ".venv", "env", ".env",
        "dist", "build", ".eggs", "*.egg-info",
        ".DS_Store", "Thumbs.db",
    }

    def __init__(
        self,
        config: Config,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> None:
        """Initialize file scanner.

        Args:
            config: Configuration instance
            include_patterns: Glob patterns to include (default: all supported)
            exclude_patterns: Glob patterns to exclude (default: common ignores)
        """
        self.config = config
        self.include_patterns = include_patterns or ["**/*"]
        self.exclude_patterns = exclude_patterns or []

        # Build exclude set
        self.exclude_dirs = self.DEFAULT_EXCLUDES.copy()
        for pattern in self.exclude_patterns:
            # Simple pattern matching - just check if directory name matches
            self.exclude_dirs.add(pattern.strip("*/"))

        # Build supported extensions set
        self.supported_extensions = (
            self.SUPPORTED_TEXT_EXTENSIONS
            | self.SUPPORTED_CODE_EXTENSIONS
            | self.SUPPORTED_CONFIG_EXTENSIONS
            | self.SUPPORTED_DOC_EXTENSIONS
        )

    def should_exclude_path(self, path: Path) -> bool:
        """Check if path should be excluded.

        Args:
            path: Path to check

        Returns:
            True if path should be excluded
        """
        # Check if any parent directory is in exclude set
        for part in path.parts:
            if part in self.exclude_dirs:
                return True

        # Check against exclude patterns (simple matching)
        for pattern in self.exclude_patterns:
            if pattern.startswith("*."):
                # Extension pattern
                if path.suffix == pattern[1:]:
                    return True
            elif pattern in str(path):
                return True

        return False

    def is_supported_file(self, path: Path) -> bool:
        """Check if file type is supported.

        Args:
            path: File path to check

        Returns:
            True if file is supported
        """
        return path.suffix.lower() in self.supported_extensions

    def is_binary_file(self, path: Path) -> bool:
        """Check if file is binary (heuristic check).

        Args:
            path: File path to check

        Returns:
            True if file appears to be binary
        """
        # PDF is explicitly supported but is binary
        if path.suffix.lower() == ".pdf":
            return False

        # Check MIME type
        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type:
            if mime_type.startswith("text/"):
                return False
            if mime_type in ("application/json", "application/xml", "application/javascript"):
                return False

        # Read first few bytes to check for binary content
        try:
            with open(path, "rb") as f:
                chunk = f.read(8192)
                # Check for null bytes
                if b"\x00" in chunk:
                    return True
        except Exception:
            return True

        return False

    async def compute_sha256(self, path: Path) -> str:
        """Compute SHA-256 hash of file.

        Args:
            path: File path

        Returns:
            Hex string of SHA-256 hash

        Raises:
            ScannerError: If file cannot be read
        """
        try:
            sha256_hash = hashlib.sha256()

            # Read file in chunks
            with open(path, "rb") as f:
                while chunk := f.read(8192):
                    sha256_hash.update(chunk)

            return sha256_hash.hexdigest()

        except OSError as e:
            raise ScannerError(f"Failed to hash {path}: {e}") from e

    async def scan_file(
        self,
        path: Path,
        root: Path,
        tracker: FileTracker,
    ) -> Optional[ScannedFile]:
        """Scan a single file and check if it changed.

        Args:
            path: File path to scan
            root: Root directory for relative path calculation
            tracker: File tracker for change detection

        Returns:
            ScannedFile if file should be processed, None otherwise
        """
        try:
            # Get file stats
            stat = path.stat()
            size_bytes = stat.st_size
            mtime_ns = stat.st_mtime_ns

            # Skip very large files
            if size_bytes > self.config.max_chunk_bytes * 10:
                return None

            # Get MIME type
            mime_type, _ = mimetypes.guess_type(str(path))

            # Compute hash
            sha256 = await self.compute_sha256(path)

            # Check if file changed
            relative_path = str(path.relative_to(root))
            existing = tracker.get_by_path(relative_path)

            is_changed = (
                existing is None
                or existing.sha256 != sha256
                or existing.size_bytes != size_bytes
            )

            return ScannedFile(
                path=path,
                absolute_path=path.resolve(),
                relative_path=relative_path,
                sha256=sha256,
                size_bytes=size_bytes,
                mtime_ns=mtime_ns,
                mime_type=mime_type,
                is_changed=is_changed,
            )

        except Exception as e:
            # Log error but continue scanning
            print(f"Error scanning {path}: {e}")
            return None

    async def scan_directory(
        self,
        root: Path,
        tracker: FileTracker,
        limit: Optional[int] = None,
    ) -> List[ScannedFile]:
        """Scan directory recursively and identify changed files.

        Args:
            root: Root directory to scan
            tracker: File tracker instance
            limit: Optional limit on number of files to scan

        Returns:
            List of changed files

        Raises:
            ScannerError: If scanning fails
        """
        try:
            all_files: List[Path] = []
            scanned_count = 0

            # Walk directory tree
            for path in root.rglob("*"):
                # Check limits
                if limit and scanned_count >= limit:
                    break

                # Skip directories
                if path.is_dir():
                    continue

                # Check exclusions
                if self.should_exclude_path(path):
                    continue

                # Check if supported
                if not self.is_supported_file(path):
                    continue

                # Check if binary (except PDFs)
                if self.is_binary_file(path):
                    continue

                all_files.append(path)
                scanned_count += 1

            # Scan files concurrently
            changed_files: List[ScannedFile] = []
            semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)

            async def scan_with_semaphore(path: Path) -> None:
                async with semaphore:
                    result = await self.scan_file(path, root, tracker)
                    if result and result.is_changed:
                        changed_files.append(result)

                        # Update tracker immediately for changed files
                        record = FileRecord(
                            path=result.relative_path,
                            sha256=result.sha256,
                            scanned_at=datetime.now(),
                            size_bytes=result.size_bytes,
                            mtime_ns=result.mtime_ns,
                        )
                        tracker.upsert(record)

            # Create tasks for all files
            tasks = [scan_with_semaphore(path) for path in all_files]

            # Wait for all scans to complete
            await asyncio.gather(*tasks)

            return changed_files

        except Exception as e:
            raise ScannerError(f"Failed to scan directory: {e}") from e

    def get_supported_extensions(self) -> Set[str]:
        """Get set of all supported file extensions.

        Returns:
            Set of supported extensions including leading dot
        """
        return self.supported_extensions.copy()
