# Embedding and LLM Query Implementation

**Status**: ✅ Complete
**Commit**: 7489b48
**Date**: November 10, 2025

## Overview

Implemented the complete RAG (Retrieval-Augmented Generation) pipeline via web interface, enabling:
1. **File embedding** via `/embed` endpoint
2. **LLM-powered querying** via `/query` endpoint

## Implementation Details

### POST `/{project_id}/embed` - Embedding Generation

**Purpose**: Process uploaded files, chunk them, generate embeddings, and store vectors.

**Flow**:
```
1. FileScanner.scan() → detect changed files
2. For each file:
   a. Chunker.chunk() → split into overlapping tokens
   b. Embedder.embed_batch() → generate vectors
   c. VectorStore.insert_chunks() → store in database
   d. FileTracker.record_file() → mark as processed
3. Return: count of embedded chunks + elapsed time
```

**Request**:
```json
{
  "batch_size": 64  // Optional, default 64
}
```

**Response**:
```json
{
  "embedded_chunks": 150,
  "total_chunks": 150,
  "elapsed_seconds": 23.45
}
```

**Features**:
- ✅ Automatic change detection (only processes new/modified files)
- ✅ Graceful error handling (continues on file encode errors)
- ✅ Batch processing for efficiency
- ✅ Token-based chunking with overlap for context preservation
- ✅ Time tracking for performance monitoring

### POST `/{project_id}/query` - RAG Query

**Purpose**: Execute a full RAG query including embedding, search, and LLM generation.

**Flow**:
```
1. QueryEngine.query()
   a. Embedder.embed() → embed query text
   b. VectorStore.search() → find k nearest neighbors
   c. Assemble context with citations
2. OpenAIClient.generate_answer()
   a. Call LLM with context
   b. Extract citations from response
3. Log metrics and return answer
```

**Request**:
```json
{
  "query": "How do I implement authentication?",
  "k": 8,           // Optional, number of chunks to retrieve (default 8)
  "rerank": null    // Optional, top-n results to rerank (not yet implemented)
}
```

**Response**:
```json
{
  "answer": "Based on the codebase, authentication is implemented using...",
  "citations": [
    {
      "path": "rag_core/auth/jwt_utils.py",
      "chunk_id": 0,
      "text": "JWT token generation and validation..."
    }
  ],
  "num_retrieved": 8,
  "elapsed_seconds": 5.32
}
```

**Features**:
- ✅ Full RAG pipeline (embed → search → generate)
- ✅ Query parameters: k (num chunks), rerank (future)
- ✅ Citation preservation from LLM response
- ✅ Comprehensive logging with span IDs for tracing
- ✅ Performance metrics (search time, LLM time, total time)
- ✅ Per-project and per-user logging

## Architecture Integration

### Component Usage

| Component | Endpoint | Purpose |
|-----------|----------|---------|
| FileScanner | embed | Detect file changes |
| Chunker | embed | Split files into chunks |
| Embedder | both | Generate embeddings (HF/OpenAI-compatible) |
| VectorStore | both | Store/search vectors (sqlite-vec) |
| QueryEngine | query | Embed query + vector search |
| OpenAIClient | query | Generate answer via LLM |
| FileTracker | embed | Track processed files |
| QueryLogger | query | Log queries with project/user context |

### Config Conversion

Both endpoints convert `ProjectConfig` → core `Config` using:
```python
config = project.to_core_config()
```

This enables:
- ✅ Per-project embeddings
- ✅ Per-project LLM models
- ✅ Per-project API keys
- ✅ Isolated vector databases

### Logging Integration

Queries are logged with:
- `project_id` - Project context
- `user_id` - User attribution
- `span_id` - Request tracing
- Timing metrics (search_ms, llm_ms)
- Retrieved chunks
- Generated answer

Logs written to: `.rag/projects/{project_id}/queries.log`

## Configuration

### Project Settings Used

From `ProjectConfig`:
- `embed_model_id` - Model for embeddings (default: sentence-transformers/all-MiniLM-L6-v2)
- `hf_endpoint_url` - Custom embedding endpoint
- `hf_api_token` - HuggingFace API token
- `llm_model_id` - LLM model (default: HuggingFaceTB/SmolLM3-3B)
- `llm_endpoint_url` - Custom LLM endpoint
- `llm_api_token` - LLM API token
- `chunk_target_tokens` - Token target for chunks (default: 512)
- `chunk_overlap_tokens` - Overlap between chunks (default: 50)

### Environment Variables

Required for queries:
- `HF_API_TOKEN` - HuggingFace Inference API
- `OPENAI_API_KEY` - OpenAI API (if using OpenAI LLM)

## Error Handling

### Embed Endpoint
- ✅ Catches file encoding errors, continues processing
- ✅ Handles embedding API timeouts
- ✅ Graceful fallback for individual file failures
- ✅ Returns partial results (embedded_chunks < total_chunks)

### Query Endpoint
- ✅ Validates query length (1-1000 chars)
- ✅ Handles empty vector store
- ✅ Catches embedding API errors
- ✅ Catches LLM API errors
- ✅ Logs errors with span ID for tracing

## API Contract

### Embed Endpoint
```
POST /api/projects/{project_id}/embed

Authentication: Bearer {token}

Response: 200 OK
{
  "embedded_chunks": integer,
  "total_chunks": integer,
  "elapsed_seconds": float
}

Errors:
- 401 Unauthorized (invalid token)
- 404 Not Found (project not found)
- 500 Internal Server Error (embedding failed)
```

### Query Endpoint
```
POST /api/projects/{project_id}/query

Authentication: Bearer {token}

Body:
{
  "query": string (1-1000 chars),
  "k": integer? (1-50, default 8),
  "rerank": integer? (future)
}

Response: 200 OK
{
  "answer": string,
  "citations": [
    {
      "path": string,
      "chunk_id": integer,
      "text": string?
    }
  ],
  "num_retrieved": integer,
  "elapsed_seconds": float
}

Errors:
- 401 Unauthorized (invalid token)
- 404 Not Found (project not found)
- 500 Internal Server Error (query failed)
```

## Frontend Integration

The React frontend should:

1. **Call `/embed` after uploading files**:
   ```typescript
   const response = await apiClient.embed(projectId, {
     batch_size: 64
   });
   // response: { embedded_chunks: N, total_chunks: N, elapsed_seconds: X }
   ```

2. **Call `/query` when user submits question**:
   ```typescript
   const response = await apiClient.query(projectId, {
     query: "What is X?",
     k: 8
   });
   // response: { answer: "...", citations: [...], num_retrieved: N }
   ```

3. **Display results**:
   - Answer text in main area
   - Citations as expandable references
   - Performance metrics (elapsed time)

## Testing Checklist

- [ ] Test `/embed` with various file types
- [ ] Test `/embed` with large files (>10MB)
- [ ] Test `/embed` with non-UTF8 files (should skip gracefully)
- [ ] Test `/embed` with duplicate files (should mark as non-changed)
- [ ] Test `/query` with valid tokens
- [ ] Test `/query` with invalid/expired tokens
- [ ] Test `/query` with empty project (no embeddings)
- [ ] Test `/query` with large k values
- [ ] Test logging (check `.rag/projects/{project_id}/queries.log`)
- [ ] Verify citations are preserved in answers
- [ ] Check performance metrics accuracy

## Known Limitations

1. **Reranking** - Placeholder for cross-encoder reranking (not yet implemented)
2. **PDF Processing** - Requires PDF extraction setup
3. **LLM Streaming** - Returns complete answer only (not streamed)
4. **Rate Limiting** - No rate limiting on API endpoints
5. **Caching** - No query result caching

## Future Enhancements

1. **Reranking**: Implement cross-encoder reranking via Hugging Face
2. **Streaming**: Stream LLM response chunks to client
3. **Rate Limiting**: Add per-user rate limiting
4. **Query Caching**: Cache similar queries
5. **Batch Queries**: Support multiple queries in single request
6. **Incremental Embedding**: Resume interrupted embedding jobs

## Dependencies

Uses existing core components:
- ✅ `rag_core.scanner.FileScanner` - File change detection
- ✅ `rag_core.scanner.Chunker` - Text chunking
- ✅ `rag_core.vectorizer.Embedder` - Vector generation
- ✅ `rag_core.database.VectorStore` - Vector storage
- ✅ `rag_core.retrieval.QueryEngine` - Query execution
- ✅ `rag_core.llm.OpenAIClient` - LLM integration
- ✅ `rag_core.database.FileTracker` - File tracking
- ✅ `rag_core.logging_config` - Structured logging

## Security Considerations

- ✅ All endpoints require authentication (Bearer token)
- ✅ File access isolated to project directory
- ✅ User ID tracked in logs for audit trail
- ✅ Input validation on query length
- ✅ API key isolation (per-project keys supported)

---

**Commit**: 7489b48
**Files Modified**: web/api/routes/query.py
**Lines Added**: 159
