#!/usr/bin/env python3
"""Integration test for the RAG pipeline."""

import tempfile
from pathlib import Path
from rag_core.projects.file_store import FileStore


def test_file_store_reupload():
    """Test that re-uploading a file doesn't cause FileExistsError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        store = FileStore(base_dir)

        # Create a test file
        test_content = b"Test content for embedding"

        # First upload
        file_hash, storage_path = store.store_file(content=test_content)
        print(f"✓ First upload: {file_hash[:8]}... stored at {storage_path}")

        # Create a project and symlink
        project_dir = base_dir / "projects" / "test-project" / "files"
        link_path = project_dir / "test_file.txt"

        # First symlink creation
        store.create_symlink(file_hash, link_path, relative=True)
        print(f"✓ First symlink created: {link_path}")
        assert link_path.is_symlink(), "Symlink should exist"

        # Re-upload same content (simulating user re-uploading same file)
        file_hash2, storage_path2 = store.store_file(content=test_content)
        assert file_hash == file_hash2, "Hash should be the same for same content"
        print(f"✓ Second upload: {file_hash2[:8]}... (same hash)")

        # Second symlink creation (this would previously cause FileExistsError)
        try:
            store.create_symlink(file_hash2, link_path, relative=True)
            print(f"✓ Second symlink created successfully (no FileExistsError)")
            assert link_path.is_symlink(), "Symlink should still exist"
        except FileExistsError as e:
            print(f"✗ FAILED: FileExistsError on re-upload: {e}")
            return False

        # Verify symlink points to correct location
        target = link_path.resolve()
        assert target.exists(), "Symlink target should exist"
        print(f"✓ Symlink resolves correctly to {target}")

        return True


def test_file_store_different_file():
    """Test uploading a different file with same name."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        store = FileStore(base_dir)

        # First file
        content1 = b"First file content"
        file_hash1, _ = store.store_file(content=content1)
        print(f"✓ First file: {file_hash1[:8]}...")

        # Create symlink
        project_dir = base_dir / "projects" / "test-project" / "files"
        link_path = project_dir / "file.txt"
        store.create_symlink(file_hash1, link_path, relative=True)
        print(f"✓ Symlink created for first file")

        # Second file with different content
        content2 = b"Second file content - different"
        file_hash2, _ = store.store_file(content=content2)
        print(f"✓ Second file: {file_hash2[:8]}...")

        # Update symlink to point to second file
        try:
            store.create_symlink(file_hash2, link_path, relative=True)
            print(f"✓ Symlink updated to second file (no FileExistsError)")

            # Verify it points to second file
            target = link_path.resolve()
            content_read = target.read_bytes()
            assert content_read == content2, "Symlink should point to second file"
            print(f"✓ Symlink correctly updated to second file")
        except FileExistsError as e:
            print(f"✗ FAILED: FileExistsError when updating symlink: {e}")
            return False

        return True


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Testing File Store Re-upload (Same Content)")
    print("="*60)
    test1_passed = test_file_store_reupload()

    print("\n" + "="*60)
    print("Testing File Store Update (Different Content)")
    print("="*60)
    test2_passed = test_file_store_different_file()

    print("\n" + "="*60)
    if test1_passed and test2_passed:
        print("✓ All integration tests PASSED")
        print("="*60)
    else:
        print("✗ Some tests FAILED")
        print("="*60)
