# RAG Pipeline

A production-ready Retrieval-Augmented Generation (RAG) system with HuggingFace embeddings and OpenAI LLM integration.

## Features

- **File Scanning**: Automatic change detection using SHA-256 hashing
- **Smart Chunking**: Multiple strategies (recursive, markdown-aware, code-aware)
- **Vector Storage**: Efficient storage using sqlite-vec
- **Embeddings**: HuggingFace models (Inference API, Endpoints, or TEI)
- **LLM Integration**: OpenAI API for answer generation
- **CLI Interface**: Full-featured command-line tool
- **Web API**: FastAPI-based REST API (coming soon)

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd RagPipeline

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .
```

## Configuration

Create a `.env` file in the project root:

```env
# HuggingFace Configuration
HF_API_TOKEN=your_hf_token_here
HF_ENDPOINT_URL=https://your-endpoint-url  # Optional
EMBED_MODEL_ID=BAAI/bge-m3

# OpenAI Configuration
OPENAI_API_KEY=your_openai_key_here
OPENAI_MODEL=gpt-4o

# Database Configuration
DB_PATH=.rag/rag.sqlite

# Chunking Configuration
CHUNK_TARGET_TOKENS=512
CHUNK_OVERLAP_TOKENS=50
```

## Quick Start

### 1. Scan Files

Scan a directory to track files and detect changes:

```bash
# Scan current directory
rag scan

# Scan specific directory
rag scan --root /path/to/documents

# Scan with filters
rag scan --root docs --include "*.md" --exclude "node_modules"

# Limit number of files
rag scan --root docs --limit 100
```

### 2. Generate Embeddings

Generate embeddings for scanned files:

```bash
# Use default model from config
rag embed

# Override model
rag embed --model BAAI/bge-m3

# Adjust batch size
rag embed --batch 32
```

### 3. Query the System

Query the RAG system (requires OpenAI API key):

```bash
# Basic query
rag query -q "What is the main purpose of this codebase?"

# Adjust number of results
rag query -q "How does chunking work?" -k 10

# JSON output
rag query -q "Explain the architecture" --json
```

### 4. Check Status

View system status:

```bash
rag status
```

### 5. Maintenance

```bash
# Garbage collect orphaned data
rag gc

# Rebuild vector index
rag reindex --drop

# Start web server (coming soon)
rag serve --host 0.0.0.0 --port 8000
```

## CLI Commands

### `rag scan`

Scan directory for files and detect changes.

**Options:**
- `--root, -r PATH`: Root directory to scan (default: current directory)
- `--include, -i PATTERN`: Include glob patterns (can specify multiple)
- `--exclude, -e PATTERN`: Exclude glob patterns (can specify multiple)
- `--limit, -l INT`: Maximum files to process
- `--db PATH`: Database path override

**Example:**
```bash
rag scan --root ./docs --include "*.md" --include "*.txt" --exclude "draft*"
```

### `rag embed`

Generate embeddings for pending chunks.

**Options:**
- `--model, -m TEXT`: Embedding model ID (overrides config)
- `--batch, -b INT`: Batch size (default: 64)
- `--db PATH`: Database path override

**Example:**
```bash
rag embed --model intfloat/e5-large-v2 --batch 32
```

### `rag query`

Query the RAG system and generate answers.

**Options:**
- `--query, -q TEXT`: Query string (required)
- `--top-k, -k INT`: Number of results to retrieve (default: 8)
- `--rerank INT`: Apply re-ranking to top N results
- `--json`: Output as JSON
- `--db PATH`: Database path override

**Example:**
```bash
rag query -q "How do I configure the system?" -k 10 --json
```

### `rag status`

Show system status and statistics.

**Example:**
```bash
rag status
```

### `rag gc`

Garbage collect orphaned data.

**Options:**
- `--vacuum/--no-vacuum`: Run VACUUM after cleanup (default: yes)
- `--db PATH`: Database path override

**Example:**
```bash
rag gc --vacuum
```

### `rag reindex`

Rebuild vector index from chunks.

**Options:**
- `--drop`: Drop existing vectors before reindexing
- `--db PATH`: Database path override

**Example:**
```bash
rag reindex --drop
```

### `rag serve`

Start the web API server.

**Options:**
- `--host TEXT`: Host to bind to (default: 0.0.0.0)
- `--port, -p INT`: Port to bind to (default: 8000)
- `--reload`: Enable auto-reload

**Example:**
```bash
rag serve --host localhost --port 8080 --reload
```

## Architecture

### Core Components

```
rag_core/
├── config.py           # Configuration management
├── database/
│   ├── file_tracker.py # File tracking with SHA-256
│   └── vector_store.py # Vector storage with sqlite-vec
├── scanner/
│   ├── file_scanner.py # Directory scanning
│   └── chunker.py      # Text chunking strategies
├── vectorizer/
│   ├── embedder.py     # HuggingFace embedding client
│   └── batch_processor.py # Batch processing utilities
├── retrieval/
│   └── query_engine.py # Query processing (TODO)
└── llm/
    ├── openai_client.py    # OpenAI client (TODO)
    └── anthropic_client.py # Anthropic client (TODO)
```

### Data Flow

1. **Scan**: Walk directory → SHA-256 hashing → change detection
2. **Chunk**: Extract text → normalize → split (token/markdown/code-aware)
3. **Embed**: Send to HuggingFace → store in sqlite-vec
4. **Retrieve**: Query embedding → ANN search → context assembly
5. **Generate**: OpenAI API call → answer with citations

## Supported File Types

- **Text**: `.txt`, `.md`, `.rst`, `.html`, `.htm`
- **Code**: `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.java`, `.c`, `.cpp`, `.h`, `.cs`, `.go`, `.rs`, etc.
- **Config**: `.json`, `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg`, `.xml`
- **Documents**: `.pdf` (text extraction only)

## Chunking Strategies

### Recursive Token Splitting
Default strategy. Splits text into chunks of target token size with overlap.

### Markdown-Aware
Preserves markdown structure (headers, paragraphs). Keeps sections together when possible.

### Code-Aware
Respects function and class boundaries. Language-specific patterns for Python, JavaScript, TypeScript, Java, C/C++, Go, Rust.

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=rag_core

# Run specific test file
pytest tests/unit/test_file_tracker.py
```

### Code Quality

```bash
# Type checking
mypy --strict rag_core/

# Linting and formatting
ruff check .
ruff format .
```

## Troubleshooting

### "sqlite-vec not found"

The sqlite-vec extension is required for vector storage. Install it:

```bash
pip install sqlite-vec
```

Or build from source and set `SQLITE_VEC_PATH` in your `.env` file.

### "No pending chunks to embed"

Make sure you've run `rag scan` first to identify files that need processing.

### "LLM API key not set"

Set your OpenAI API key:

```bash
export OPENAI_API_KEY=your_key_here
```

Or add it to your `.env` file.

## License

See LICENSE file for details.

## Contributing

Contributions are welcome! Please see CONTRIBUTING.md for guidelines.
