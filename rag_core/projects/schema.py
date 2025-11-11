"""Database schema for multi-project RAG system.

Provides SQL schema creation and migrations for the metadata database
that tracks users, projects, and shared files.
"""

# SQL Schema for metadata database
METADATA_SCHEMA = """
-- Users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Projects table for project management
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    config_json TEXT NOT NULL,
    data_dir TEXT NOT NULL,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, name)
);

-- Shared files table for content-addressable storage
CREATE TABLE IF NOT EXISTS shared_files (
    sha256 TEXT PRIMARY KEY,
    physical_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mime_type TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reference_count INTEGER NOT NULL DEFAULT 0
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);
CREATE INDEX IF NOT EXISTS idx_shared_files_accessed ON shared_files(last_accessed);
"""

# SQL Schema for project-specific databases
PROJECT_SCHEMA = """
-- File tracking for project files
CREATE TABLE IF NOT EXISTS file_scan_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    scanned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,

    UNIQUE(path)
);

-- Chunks metadata table
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_path TEXT NOT NULL,
    chunk_id INTEGER NOT NULL,
    start_char INTEGER,
    end_char INTEGER,
    text TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    section TEXT,
    mime TEXT,
    token_count INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    embedding_status TEXT DEFAULT 'pending',

    UNIQUE(doc_path, chunk_id)
);

-- Create indexes for chunks
CREATE INDEX IF NOT EXISTS idx_chunks_sha ON chunks(file_sha256);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_path);
CREATE INDEX IF NOT EXISTS idx_chunks_status ON chunks(embedding_status);

-- Vector table will be created dynamically by sqlite-vec
-- based on the embedding dimension of the embedding model
"""
