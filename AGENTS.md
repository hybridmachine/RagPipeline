# AGENTS.md — RAG Pipeline (Hugging Face embeddings + OpenAI LLM)

**Goal**: Implement a production‑ready Retrieval‑Augmented Generation (RAG) system with a shared Python core library (`rag_core`) that powers both a CLI and a web service. Embeddings run on Hugging Face (Inference Endpoints or TEI). LLM calls use the OpenAI API (Anthropic optional later).

---

## 1) Scope & Non‑Goals

### In scope

* File scanning, SHA‑256 tracking, and change detection in SQLite.
* Text extraction & chunking for common textual formats (txt, md, html, pdf*), code files optional.
* Batch embedding using HF models. Persist vectors in `sqlite-vec`.
* Query engine: vector search, optional re‑ranking, and LLM synthesis.
* Interfaces: CLI (Typer or Click) and web (FastAPI) that both call the same core.

*PDF extraction initially via `pypdf`/`pdfminer.six` (best‑effort text only).

### Non‑goals (v1)

* Fine‑tuning / continued pretraining of embedding models.
* Online learning or auto‑ingestion of remote sources.
* Multi‑tenant auth/ACL. (Single‑tenant dev/admin secret only.)

---

## 2) High‑Level Architecture

```
rag_core/
  scanner/ → file_scanner.py, chunker.py
  database/ → file_tracker.py (SQLite), vector_store.py (sqlite‑vec)
  vectorizer/ → embedder.py (HF), batch_processor.py
  retrieval/ → query_engine.py
  llm/ → openai_client.py, anthropic_client.py (stub)
CLI/ → main.py   Web/ → FastAPI app.py + api/routes.py
```

**Data flow**

1. **Scan**: Walk directory → calc SHA‑256 → compare with `file_scan_history` → build worklist.
2. **Chunk**: Extract text → normalize → split to chunks (by tokens/markdown/code heuristics).
3. **Embed**: Send chunks to Hugging Face (Inference Endpoint or TEI) → store vectors in SQLite via `sqlite‑vec` + chunk metadata in side table.
4. **Retrieve**: Given a query → embed query → ANN search in `sqlite‑vec` → (optional) re‑rank → compose context.
5. **Generate**: Call OpenAI Responses API with system/user/context → return answer + citations.

---

## 3) Configuration (rag_core/config.py)

* Source directories, include/exclude globs.
* Chunking strategy & token target (e.g., 512–1,024 tokens) and overlap.
* Embedding model + endpoint URL + auth.
* Vector index config: distance (cosine), dims, batch size, shards (if any), `k`.
* LLM model + API key/base URL + request defaults (temperature, max_tokens, JSON mode optional).
* Limits: max files per run, max chunk bytes, concurrency.
* Logging level, file path; `stderr` friendly JSON logs.

Expose via: env → `config.yaml` → CLI flags (highest precedence).

---

## 4) Storage Schemas

### 4.1 SQLite — file scan history (database/file_tracker.py)

```sql
CREATE TABLE IF NOT EXISTS file_scan_history (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  scanned_at TIMESTAMP NOT NULL,
  size_bytes INTEGER NOT NULL,
  mtime_ns INTEGER NOT NULL,
  UNIQUE(path)
);
CREATE INDEX IF NOT EXISTS idx_fsh_sha ON file_scan_history(sha256);
```

### 4.2 SQLite + sqlite‑vec — vector store (database/vector_store.py)

Metadata table (one row per chunk):

```sql
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY,
  doc_path TEXT NOT NULL,
  chunk_id INTEGER NOT NULL,
  start_char INTEGER,
  end_char INTEGER,
  text TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  section TEXT,
  mime TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(doc_path, chunk_id)
);
```

Vector table (virtual):

```sql
-- Dimension set at runtime (e.g., 1024). Name kept stable via PRAGMA/user_version.
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(
  embedding FLOAT[?],           -- replace ? with actual dims
  id INTEGER                    -- FK to chunks.id
);
CREATE INDEX IF NOT EXISTS idx_chunks_sha ON chunks(sha256);
```

**Invariants**

* `chunk_vectors.id` ⇄ `chunks.id` is 1:1.
* `sha256` equals file content hash at scan time; changing file content creates new chunk rows and new vectors; old rows remain until `vacuum_orphaned()` maintenance.

---

## 5) Scanning & Change Detection

### 5.1 SHA‑256 & worklist

* Walk directory with include/exclude filters.
* For each file: compute `(size, mtime_ns, sha256)`.
* If path not in `file_scan_history` **or** stored `sha256` differs → enqueue for chunking/embedding.
* Upserts `file_scan_history` after successful embed of all chunks.

### 5.2 Supported file types (v1)

* `.txt`, `.md`, `.rst`, `.html`, `.py`, `.js`, `.ts`, `.java`, `.c`, `.cpp`, `.h`, `.json`, `.yaml`, `.ini`, `.toml`.
* `.pdf` best‑effort; skip images/binaries by default.

---

## 6) Chunking (scanner/chunker.py)

Provide pluggable strategies:

* **Recursive token splitter**: aims for `target_tokens` with `overlap_tokens`. Tokenizer: `tiktoken` or HF `tokenizers` depending on LLM context length.
* **Markdown‑aware**: keep headings/paragraphs together; hard limit by tokens.
* **Code‑aware**: prefer function/class boundaries; backstop by lines/tokens.

Normalization: strip control chars, collapse whitespace, preserve minimal markdown.

Return: list of `Chunk(text, path, chunk_id, offsets, section)`.

---

## 7) Embedding (vectorizer/embedder.py, batch_processor.py)

### 7.1 Interface

```python
class Embedder:
    def __init__(self, model_id: str, endpoint_url: str, auth_token: str, timeout_s: float = 30.0):
        ...
    def embed_texts(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        ...
    @property
    def dims(self) -> int: ...
```

* Supports **Hugging Face Inference Endpoints** or **TEI** (HTTP). Autodetect dims from first response or model‑card hints cache.
* Retries with exponential backoff; per‑request timeout; streaming disabled.

### 7.2 Recommended models (initial presets)

* `BAAI/bge-m3` (English/multilingual, high quality).
* `intfloat/e5-large-v2` (English, strong retrieval baseline).
* `sentence-transformers/all-MiniLM-L6-v2` (fast, low‑dim baseline).
* `gte-base-en-v1.5` (balanced, performant at 768d).

Expose presets and allow override via config/CLI.

---

## 8) Vector Store (database/vector_store.py)

### 8.1 Insert API

```python
def upsert_vectors(chunks: list[Chunk], vectors: list[list[float]]):
    # Inserts rows to chunks, then vectors to vec0 table, in a TXN.
```

### 8.2 Query API

```python
@dataclass
class Hit:
    chunk_id: int
    score: float

class VectorStore:
    def search(self, query_vec: list[float], k: int, prefilter: dict | None = None) -> list[Hit]:
        ...  # cosine distance, return ids and scores
```

Maintenance: `vacuum_orphaned()` to delete vectors whose `chunks` rows were GC’d; `analyze()` after large ingests.

---

## 9) Retrieval & Re‑ranking (retrieval/query_engine.py)

* **Query embedding** → top‑`k` ANN via `vec0` (cosine).
* (Optional) **cross‑encoder re‑ranker** on top‑N, e.g., BGE reranker; pluggable.
* **Context assembly**: concatenate deduped chunks under token budget with source headers: `[#] path:line_start-line_end`.
* **Prompt template** (system): "Use only provided context. If unknown, say you don’t know. Cite chunk ids."

Return: `Answer(text, citations=[(doc_path, chunk_id, score)])`.

---

## 10) LLM Integration (llm/openai_client.py)

Abstractions align to a Responses‑style API; JSON‑mode optional.

```python
class LLMClient(Protocol):
    def complete(self, system: str, user: str, context: str, *, model: str, temperature: float = 0.2,
                 max_tokens: int = 800, tools: list | None = None) -> dict: ...
```

OpenAI implementation:

* Reads `OPENAI_API_KEY`, optional `OPENAI_BASE_URL`.
* Default model configurable (e.g., `gpt‑4o` family or a reasoning variant).
* Retries with jitter; 429/backoff; structured error types.

Anthropic (stub):

* Same interface; enable via config when ready.

---

## 11) CLI (cli/main.py)

Use **Typer**.

```
rag scan   [--root <dir>] [--include *.md --exclude node_modules] [--limit N]
rag embed  [--model <hf_id>] [--batch 64]
rag query  --q "question" [--k 8] [--rerank topN] [--json]
rag serve  [--host 0.0.0.0 --port 8000]
rag reindex [--drop]  # rebuild vectors from chunks
rag gc     # prune orphaned chunks/vectors; VACUUM
```

**Exit codes**: 0 success; 2 invalid args; 3 endpoint/auth failure; 4 db error.

---

## 12) Web API (web/app.py, web/api/routes.py)

Framework: **FastAPI**.

**Endpoints**

* `POST /api/query` → `{ query: str, k?: int }` ⇒ `{ answer, citations: [{path, chunk_id, score}] }`
* `POST /api/scan`  → `{ root?: str }` ⇒ `{ enqueued: int }`
* `POST /api/embed` → `{ model?: str, batch?: int }` ⇒ `{ embedded: int, dims }`
* `GET  /api/health` ⇒ `{ ok: true, dims, counts: { files, chunks } }`

CORS: disabled by default; enable for UI during dev.

Static UI: `web/static/` (simple query form).

---

## 13) Error Handling & Observability

* Structured errors: `ScannerError`, `EmbedderError`, `VectorStoreError`, `LLMError`.
* Logging: JSON (level, ts, span_id, event, fields…); quiet by default; `--verbose` for INFO/DEBUG.
* Basic timing metrics per stage; expose `/api/health` with counts and last‑run timestamps.

---

## 14) Security

* Secrets from env or OS keyring; never commit.
* Input size limits; refuse binary by default.
* Prompt injection mitigation: prepend strict system prompt; show citations.

---

## 15) Testing Strategy (tests/)

* **Unit**: chunk boundaries, hash stability, TEI client pagination, sqlite‑vec inserts/queries.
* **Integration**: end‑to‑end ingest + query with a small fixture corpus.
* **Golden tests**: retrieval determinism on a frozen corpus.
* **Contract tests**: FastAPI routes schemas and error codes.

Use `pytest`, `pytest‑tmpdir`, and `httpx` test client.

---

## 16) Implementation Tasks & Acceptance Criteria

### Milestone A — Scanning + Tracking

* [ ] Implement `file_scanner.py`: walk, hash, worklist.
* [ ] Implement `file_tracker.py`: schema + upsert + lookup.
* **Done when**: `rag scan` prints counts and persists `file_scan_history` rows.

### Milestone B — Chunking

* [ ] Implement `chunker.py` with token/markdown strategies.
* **Done when**: `rag scan` can display chunk stats per file.

### Milestone C — Embedding + Vector Store

* [ ] Implement `embedder.py` with HF endpoint/TEI client.
* [ ] Implement `vector_store.py` with `vec0` tables and search.
* **Done when**: `rag embed` ingests chunks, creates vectors, returns dims.

### Milestone D — Retrieval + LLM

* [ ] Implement `query_engine.py` with `top_k` and (optional) re‑ranker.
* [ ] Implement `openai_client.py` and answer synthesis with citations.
* **Done when**: `rag query -q "…"` returns an answer with source attributions.

### Milestone E — Web API

* [ ] Implement `FastAPI` app + endpoints + static UI.
* **Done when**: `/api/query` works from a browser.

---

## 17) Configuration & Environment

Environment variables (read by `config.py`):

```
HF_ENDPOINT_URL=...        # e.g., TEI or Inference Endpoint URL
HF_API_TOKEN=...
EMBED_MODEL_ID=BAAI/bge-m3
VECTOR_DISTANCE=cosine
OPENAI_API_KEY=...
OPENAI_BASE_URL=...        # optional self‑hosted gateway
OPENAI_MODEL=gpt-4o        # override per env
DB_PATH=.rag/rag.sqlite    # holds both tables; sqlite‑vec loaded via extension
SQLITE_VEC_PATH=./sqlite-vec*.so  # or bundled wheel
```

`requirements.txt` (baseline):

```
fastapi
uvicorn
typer
pydantic
httpx
pydantic-settings
python-dotenv
pypdf
pdfminer.six
markdown-it-py
beautifulsoup4
sqlite-vec    # Python bindings
sqlalchemy    # optional convenience
tiktoken
orjson
pytest
```

---

## 18) Example Pseudocode

```python
# cli/main.py
@app.command()
def scan(root: Path = Option(".")):
    files = scanner.walk(root)
    work = tracker.plan(files)
    console.print({"new_or_changed": len(work)})

@app.command()
def embed(model: str = Option(None), batch: int = 64):
    chunks = chunker.load_pending()
    vecs = embedder.embed_texts([c.text for c in chunks], batch_size=batch)
    store.upsert_vectors(chunks, vecs)

@app.command()
def query(q: str, k: int = 8):
    qv = embedder.embed_texts([q])[0]
    hits = store.search(qv, k=k)
    ctx = retrieval.assemble(hits)
    answer = llm.complete(system=SYSTEM, user=q, context=ctx, model=config.openai_model)
    print(json.dumps(answer))
```

---

## 19) Coding Guidelines

* Type‑hint everything; `mypy --strict` clean.
* `ruff` for lint/format; `black` if needed.
* No global state in core; pass `Config`/`Session` explicitly.
* All I/O cancelable with timeouts; retries with capped exponential backoff.
* Deterministic tests; seed randomness; freeze time where relevant.

---

## 20) Future Enhancements

* Anthropic client (same interface) and model selection at runtime.
* Background job runner for ingestion.
* Hybrid retrieval (BM25 + dense) and query‑aware fusion.
* Tool‑augmented prompts (structured schema/JSON output modes).
* UI: highlight spans from chunks; per‑chunk feedback loop for re‑ranking.
