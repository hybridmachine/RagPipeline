"""Unit tests for file_tracker module."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rag_core.database.file_tracker import FileRecord, FileTracker, FileTrackerError


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def tracker(temp_db: Path) -> FileTracker:
    """Create a FileTracker instance with temporary database."""
    tracker = FileTracker(temp_db)
    tracker.connect()
    yield tracker
    tracker.close()


@pytest.fixture
def sample_record() -> FileRecord:
    """Create a sample FileRecord."""
    return FileRecord(
        path="/test/file.txt",
        sha256="a" * 64,
        scanned_at=datetime.now(),
        size_bytes=1024,
        mtime_ns=1234567890000000000,
    )


class TestFileRecord:
    """Tests for FileRecord dataclass."""

    def test_create_valid_record(self, sample_record: FileRecord) -> None:
        """Test creating a valid FileRecord."""
        assert sample_record.path == "/test/file.txt"
        assert sample_record.sha256 == "a" * 64
        assert sample_record.size_bytes == 1024
        assert sample_record.mtime_ns == 1234567890000000000
        assert sample_record.id is None

    def test_empty_path_raises_error(self) -> None:
        """Test that empty path raises ValueError."""
        with pytest.raises(ValueError, match="path cannot be empty"):
            FileRecord(
                path="",
                sha256="a" * 64,
                scanned_at=datetime.now(),
                size_bytes=1024,
                mtime_ns=1234567890000000000,
            )

    def test_invalid_sha256_raises_error(self) -> None:
        """Test that invalid SHA-256 raises ValueError."""
        with pytest.raises(ValueError, match="sha256 must be a 64-character"):
            FileRecord(
                path="/test/file.txt",
                sha256="invalid",
                scanned_at=datetime.now(),
                size_bytes=1024,
                mtime_ns=1234567890000000000,
            )

    def test_negative_size_raises_error(self) -> None:
        """Test that negative size raises ValueError."""
        with pytest.raises(ValueError, match="size_bytes must be non-negative"):
            FileRecord(
                path="/test/file.txt",
                sha256="a" * 64,
                scanned_at=datetime.now(),
                size_bytes=-1,
                mtime_ns=1234567890000000000,
            )

    def test_negative_mtime_raises_error(self) -> None:
        """Test that negative mtime raises ValueError."""
        with pytest.raises(ValueError, match="mtime_ns must be non-negative"):
            FileRecord(
                path="/test/file.txt",
                sha256="a" * 64,
                scanned_at=datetime.now(),
                size_bytes=1024,
                mtime_ns=-1,
            )


class TestFileTrackerConnection:
    """Tests for FileTracker connection management."""

    def test_connect_creates_database(self, temp_db: Path) -> None:
        """Test that connect() creates database file."""
        assert not temp_db.exists()
        tracker = FileTracker(temp_db)
        tracker.connect()
        assert temp_db.exists()
        tracker.close()

    def test_connect_creates_parent_directory(self, tmp_path: Path) -> None:
        """Test that connect() creates parent directories."""
        db_path = tmp_path / "subdir" / "test.db"
        assert not db_path.parent.exists()
        tracker = FileTracker(db_path)
        tracker.connect()
        assert db_path.parent.exists()
        assert db_path.exists()
        tracker.close()

    def test_schema_initialization(self, tracker: FileTracker) -> None:
        """Test that schema is properly initialized."""
        conn = tracker._get_conn()

        # Check that table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='file_scan_history'"
        )
        assert cursor.fetchone() is not None

        # Check that index exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_fsh_sha'"
        )
        assert cursor.fetchone() is not None

        # Check schema version
        cursor = conn.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        assert version == FileTracker.SCHEMA_VERSION

    def test_operations_without_connect_raise_error(self, temp_db: Path) -> None:
        """Test that operations without connect() raise error."""
        tracker = FileTracker(temp_db)
        with pytest.raises(FileTrackerError, match="Database not connected"):
            tracker.count()

    def test_context_manager(self, temp_db: Path, sample_record: FileRecord) -> None:
        """Test FileTracker as context manager."""
        with FileTracker(temp_db) as tracker:
            tracker.upsert(sample_record)
            assert tracker.count() == 1

        # Verify database was properly closed
        assert tracker._conn is None


class TestFileTrackerUpsert:
    """Tests for FileTracker upsert operation."""

    def test_insert_new_record(self, tracker: FileTracker, sample_record: FileRecord) -> None:
        """Test inserting a new record."""
        record_id = tracker.upsert(sample_record)
        assert record_id > 0
        assert tracker.count() == 1

    def test_update_existing_record(self, tracker: FileTracker, sample_record: FileRecord) -> None:
        """Test updating an existing record."""
        # Insert initial record
        tracker.upsert(sample_record)
        assert tracker.count() == 1

        # Update with new SHA-256
        updated_record = FileRecord(
            path=sample_record.path,
            sha256="b" * 64,
            scanned_at=datetime.now(),
            size_bytes=2048,
            mtime_ns=1987654321000000000,
        )
        tracker.upsert(updated_record)

        # Should still have only one record
        assert tracker.count() == 1

        # Verify record was updated
        retrieved = tracker.get_by_path(sample_record.path)
        assert retrieved is not None
        assert retrieved.sha256 == "b" * 64
        assert retrieved.size_bytes == 2048
        assert retrieved.mtime_ns == 1987654321000000000

    def test_insert_multiple_records(self, tracker: FileTracker) -> None:
        """Test inserting multiple records."""
        records = [
            FileRecord(
                path=f"/test/file{i}.txt",
                sha256=f"{i:064x}",
                scanned_at=datetime.now(),
                size_bytes=1024 * i,
                mtime_ns=1234567890000000000 + i,
            )
            for i in range(1, 6)
        ]

        for record in records:
            tracker.upsert(record)

        assert tracker.count() == 5


class TestFileTrackerRetrieval:
    """Tests for FileTracker retrieval operations."""

    def test_get_by_path_existing(self, tracker: FileTracker, sample_record: FileRecord) -> None:
        """Test getting an existing record by path."""
        tracker.upsert(sample_record)
        retrieved = tracker.get_by_path(sample_record.path)

        assert retrieved is not None
        assert retrieved.path == sample_record.path
        assert retrieved.sha256 == sample_record.sha256
        assert retrieved.size_bytes == sample_record.size_bytes
        assert retrieved.mtime_ns == sample_record.mtime_ns
        assert retrieved.id is not None

    def test_get_by_path_nonexistent(self, tracker: FileTracker) -> None:
        """Test getting a non-existent record returns None."""
        retrieved = tracker.get_by_path("/nonexistent/path.txt")
        assert retrieved is None

    def test_get_by_sha256_single(self, tracker: FileTracker, sample_record: FileRecord) -> None:
        """Test getting records by SHA-256 with single match."""
        tracker.upsert(sample_record)
        results = tracker.get_by_sha256(sample_record.sha256)

        assert len(results) == 1
        assert results[0].sha256 == sample_record.sha256
        assert results[0].path == sample_record.path

    def test_get_by_sha256_multiple(self, tracker: FileTracker) -> None:
        """Test getting records by SHA-256 with multiple matches."""
        sha = "a" * 64
        records = [
            FileRecord(
                path=f"/test/file{i}.txt",
                sha256=sha,
                scanned_at=datetime.now() + timedelta(seconds=i),
                size_bytes=1024,
                mtime_ns=1234567890000000000 + i,
            )
            for i in range(3)
        ]

        for record in records:
            tracker.upsert(record)

        results = tracker.get_by_sha256(sha)
        assert len(results) == 3
        # Should be ordered by scanned_at DESC
        assert results[0].path == "/test/file2.txt"
        assert results[1].path == "/test/file1.txt"
        assert results[2].path == "/test/file0.txt"

    def test_get_by_sha256_nonexistent(self, tracker: FileTracker) -> None:
        """Test getting records by non-existent SHA-256."""
        results = tracker.get_by_sha256("z" * 64)
        assert len(results) == 0

    def test_get_all(self, tracker: FileTracker) -> None:
        """Test getting all records."""
        records = [
            FileRecord(
                path=f"/test/file{i}.txt",
                sha256=f"{i:064x}",
                scanned_at=datetime.now() + timedelta(seconds=i),
                size_bytes=1024 * i,
                mtime_ns=1234567890000000000 + i,
            )
            for i in range(5)
        ]

        for record in records:
            tracker.upsert(record)

        all_records = tracker.get_all()
        assert len(all_records) == 5
        # Should be ordered by scanned_at DESC
        assert all_records[0].path == "/test/file4.txt"
        assert all_records[4].path == "/test/file0.txt"

    def test_get_all_with_limit(self, tracker: FileTracker) -> None:
        """Test getting all records with limit."""
        records = [
            FileRecord(
                path=f"/test/file{i}.txt",
                sha256=f"{i:064x}",
                scanned_at=datetime.now() + timedelta(seconds=i),
                size_bytes=1024 * i,
                mtime_ns=1234567890000000000 + i,
            )
            for i in range(10)
        ]

        for record in records:
            tracker.upsert(record)

        limited = tracker.get_all(limit=3)
        assert len(limited) == 3
        assert limited[0].path == "/test/file9.txt"

    def test_get_all_empty(self, tracker: FileTracker) -> None:
        """Test getting all records from empty database."""
        all_records = tracker.get_all()
        assert len(all_records) == 0


class TestFileTrackerDeletion:
    """Tests for FileTracker deletion operations."""

    def test_delete_existing_record(self, tracker: FileTracker, sample_record: FileRecord) -> None:
        """Test deleting an existing record."""
        tracker.upsert(sample_record)
        assert tracker.count() == 1

        result = tracker.delete_by_path(sample_record.path)
        assert result is True
        assert tracker.count() == 0

    def test_delete_nonexistent_record(self, tracker: FileTracker) -> None:
        """Test deleting a non-existent record."""
        result = tracker.delete_by_path("/nonexistent/path.txt")
        assert result is False

    def test_delete_one_of_many(self, tracker: FileTracker) -> None:
        """Test deleting one record among many."""
        records = [
            FileRecord(
                path=f"/test/file{i}.txt",
                sha256=f"{i:064x}",
                scanned_at=datetime.now(),
                size_bytes=1024 * i,
                mtime_ns=1234567890000000000 + i,
            )
            for i in range(5)
        ]

        for record in records:
            tracker.upsert(record)

        tracker.delete_by_path("/test/file2.txt")
        assert tracker.count() == 4
        assert tracker.get_by_path("/test/file2.txt") is None
        assert tracker.get_by_path("/test/file0.txt") is not None


class TestFileTrackerMaintenance:
    """Tests for FileTracker maintenance operations."""

    def test_count_empty(self, tracker: FileTracker) -> None:
        """Test counting records in empty database."""
        assert tracker.count() == 0

    def test_count_with_records(self, tracker: FileTracker) -> None:
        """Test counting records."""
        for i in range(7):
            record = FileRecord(
                path=f"/test/file{i}.txt",
                sha256=f"{i:064x}",
                scanned_at=datetime.now(),
                size_bytes=1024,
                mtime_ns=1234567890000000000,
            )
            tracker.upsert(record)

        assert tracker.count() == 7

    def test_vacuum(self, tracker: FileTracker, sample_record: FileRecord) -> None:
        """Test vacuum operation."""
        # Insert and delete records to create fragmentation
        for i in range(100):
            record = FileRecord(
                path=f"/test/file{i}.txt",
                sha256=f"{i:064x}",
                scanned_at=datetime.now(),
                size_bytes=1024,
                mtime_ns=1234567890000000000,
            )
            tracker.upsert(record)

        for i in range(50):
            tracker.delete_by_path(f"/test/file{i}.txt")

        # Get database size before vacuum
        db_size_before = tracker.db_path.stat().st_size

        # Vacuum should succeed
        tracker.vacuum()

        # Verify data is still intact
        assert tracker.count() == 50

        # Database size should be reduced (or at least not increased)
        db_size_after = tracker.db_path.stat().st_size
        assert db_size_after <= db_size_before


class TestFileTrackerEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_path_uniqueness_constraint(self, tracker: FileTracker, sample_record: FileRecord) -> None:
        """Test that path uniqueness is enforced via upsert."""
        tracker.upsert(sample_record)

        # Upserting same path should update, not create duplicate
        modified_record = FileRecord(
            path=sample_record.path,
            sha256="b" * 64,
            scanned_at=datetime.now(),
            size_bytes=2048,
            mtime_ns=8888888888888888888,
        )
        tracker.upsert(modified_record)

        assert tracker.count() == 1
        retrieved = tracker.get_by_path(sample_record.path)
        assert retrieved is not None
        assert retrieved.sha256 == "b" * 64

    def test_timestamp_preservation(self, tracker: FileTracker) -> None:
        """Test that timestamps are correctly preserved."""
        now = datetime.now()
        record = FileRecord(
            path="/test/file.txt",
            sha256="a" * 64,
            scanned_at=now,
            size_bytes=1024,
            mtime_ns=1234567890000000000,
        )
        tracker.upsert(record)

        retrieved = tracker.get_by_path("/test/file.txt")
        assert retrieved is not None
        # Compare timestamps (allow small difference due to serialization)
        assert abs((retrieved.scanned_at - now).total_seconds()) < 1

    def test_special_characters_in_path(self, tracker: FileTracker) -> None:
        """Test handling of special characters in file paths."""
        special_path = "/test/file with spaces & special!@#$%chars.txt"
        record = FileRecord(
            path=special_path,
            sha256="a" * 64,
            scanned_at=datetime.now(),
            size_bytes=1024,
            mtime_ns=1234567890000000000,
        )
        tracker.upsert(record)

        retrieved = tracker.get_by_path(special_path)
        assert retrieved is not None
        assert retrieved.path == special_path

    def test_very_long_path(self, tracker: FileTracker) -> None:
        """Test handling of very long file paths."""
        long_path = "/test/" + "a" * 1000 + ".txt"
        record = FileRecord(
            path=long_path,
            sha256="a" * 64,
            scanned_at=datetime.now(),
            size_bytes=1024,
            mtime_ns=1234567890000000000,
        )
        tracker.upsert(record)

        retrieved = tracker.get_by_path(long_path)
        assert retrieved is not None
        assert retrieved.path == long_path

    def test_zero_size_file(self, tracker: FileTracker) -> None:
        """Test handling of zero-size files."""
        record = FileRecord(
            path="/test/empty.txt",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # SHA256 of empty string
            scanned_at=datetime.now(),
            size_bytes=0,
            mtime_ns=1234567890000000000,
        )
        tracker.upsert(record)

        retrieved = tracker.get_by_path("/test/empty.txt")
        assert retrieved is not None
        assert retrieved.size_bytes == 0
