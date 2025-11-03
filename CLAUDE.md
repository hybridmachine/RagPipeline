# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a production-ready Retrieval-Augmented Generation (RAG) system with a shared Python core library (`rag_core`) that powers both a CLI and a web service. The system uses Hugging Face for embeddings and OpenAI for LLM calls.

## Architecture

### Core Components

```
rag_core/
  scanner/        # File scanning and chunking (file_scanner.py, chunker.py)
  database/       # SQLite storage (file_tracker.py, vector_store.py)
  vectorizer/     # Embedding generation (embedder.py, batch_processor.py)
  retrieval/      # Query processing (query_engine.py)
  llm/            # LLM clients (openai_client.py, anthropic_client.py)
  config.py       # Configuration management
```

### Interfaces

- **CLI**: `cli/main.py` using Typer
- **Web API**: `web/app.py` using FastAPI with routes in `web/api/routes.py`

### Data Flow

1. **Scan**: Walk directory → SHA-256 hashing → change detection via `file_scan_history`
2. **Chunk**: Extract text → normalize → split (token/markdown/code-aware strategies)
3. **Embed**: Send to Hugging Face (Inference Endpoint or TEI) → store in `sqlite-vec`
4. **Retrieve**: Query embedding → ANN search → optional re-ranking → context assembly
5. **Generate**: OpenAI API call with context → answer with citations

## Storage

### File Tracking (SQLite)

`file_scan_history` table tracks files by path, SHA-256, scan timestamp, size, and mtime.

### Vector Store (sqlite-vec)

- `chunks` table: metadata per chunk (doc_path, chunk_id, offsets, text, sha256)
- `chunk_vectors` virtual table: embeddings with FK to chunks.id
- 1:1 relationship between chunks and vectors via `id`

## Development Commands

### CLI Commands

```bash
# Scan files for changes
rag scan [--root <dir>] [--include *.md --exclude node_modules] [--limit N]

# Generate embeddings
rag embed [--model <hf_id>] [--batch 64]

# Query the system
rag query --q "question" [--k 8] [--rerank topN] [--json]

# Start web server
rag serve [--host 0.0.0.0 --port 8000]

# Rebuild vector index
rag reindex [--drop]

# Clean up orphaned data
rag gc
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=rag_core

# Run specific test file
pytest tests/test_chunker.py
```

### Code Quality

```bash
# Type checking (must pass with --strict)
mypy --strict rag_core/

# Linting and formatting
ruff check .
ruff format .
```

## Configuration

### Environment Variables

```
HF_ENDPOINT_URL          # Hugging Face TEI or Inference Endpoint URL
HF_API_TOKEN             # Hugging Face API token
EMBED_MODEL_ID           # e.g., BAAI/bge-m3
VECTOR_DISTANCE          # cosine (default)
OPENAI_API_KEY           # Required for LLM calls
OPENAI_BASE_URL          # Optional self-hosted gateway
OPENAI_MODEL             # e.g., gpt-4o
DB_PATH                  # Default: .rag/rag.sqlite
SQLITE_VEC_PATH          # Path to sqlite-vec extension
```

Configuration precedence: CLI flags > config.yaml > environment variables

## Key Implementation Details

### Chunking Strategies

- **Recursive token splitter**: targets `target_tokens` with overlap
- **Markdown-aware**: preserves headings/paragraphs, hard token limit
- **Code-aware**: respects function/class boundaries, backstops by lines/tokens
- Uses `tiktoken` or HF `tokenizers` for tokenization

### Embedding Models (Presets)

- `BAAI/bge-m3` - multilingual, high quality
- `intfloat/e5-large-v2` - English, strong baseline
- `sentence-transformers/all-MiniLM-L6-v2` - fast, low-dim
- `gte-base-en-v1.5` - balanced, 768d

### Supported File Types

Text: `.txt`, `.md`, `.rst`, `.html`
Code: `.py`, `.js`, `.ts`, `.java`, `.c`, `.cpp`, `.h`
Config: `.json`, `.yaml`, `.ini`, `.toml`
Documents: `.pdf` (best-effort text extraction via pypdf/pdfminer.six)

### Error Handling

Custom error types:
- `ScannerError` - file scanning/hashing issues
- `EmbedderError` - embedding generation failures
- `VectorStoreError` - database/vector operations
- `LLMError` - LLM API failures

All I/O operations use timeouts and exponential backoff retries.

### Web API Endpoints

```
POST /api/query   { query, k? } → { answer, citations }
POST /api/scan    { root? } → { enqueued }
POST /api/embed   { model?, batch? } → { embedded, dims }
GET  /api/health  → { ok, dims, counts }
```

## Coding Standards

- **Type hints**: Required on all functions; must pass `mypy --strict`
- **No global state**: Pass `Config`/`Session` explicitly to all core functions
- **Structured logging**: JSON format (level, ts, span_id, event, fields)
- **Testing**: All I/O must be cancelable; deterministic tests with seeded randomness
- **Exit codes**: 0 = success, 2 = invalid args, 3 = endpoint/auth failure, 4 = db error

## Implementation Milestones

**Milestone A**: Scanning + Tracking (file_scanner.py, file_tracker.py)
**Milestone B**: Chunking (chunker.py with multiple strategies)
**Milestone C**: Embedding + Vector Store (embedder.py, vector_store.py)
**Milestone D**: Retrieval + LLM (query_engine.py, openai_client.py)
**Milestone E**: Web API (FastAPI app + endpoints)

Refer to AGENTS.md for detailed acceptance criteria per milestone.

## Security Notes

- Never commit secrets; use environment variables or OS keyring
- Input size limits enforced; binary files refused by default
- Prompt injection mitigation via strict system prompts and citation requirements
- Chunk metadata includes SHA-256 for integrity verification
