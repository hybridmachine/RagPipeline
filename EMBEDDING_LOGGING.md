# Embedding Logging Guide

**Added**: Commit 7384f6f
**Purpose**: Debug and trace embedding operations with detailed logging
**Log Location**: `.rag/projects/{project_id}/embed.log`

## Overview

Comprehensive JSON logging has been added to the embedding pipeline to help trace what happens during document processing. Each embedding session, file, and batch operation is logged with timing metrics.

## Log File Location

```
.rag/
└── projects/
    └── {project_id}/
        └── embed.log  ← Embedding logs for this project
```

## Log Structure

Each log entry is a JSON object on a single line:

```json
{
  "timestamp": 1731339240.5,
  "span_id": "a1b2c3d4",
  "event": "batch_complete",
  "level": "INFO",
  "file_path": "docs/auth.md",
  "batch_num": 1,
  "batch_size": 32,
  "batch_status": "success",
  "embedding_time_ms": 245.5,
  "storage_time_ms": 12.3,
  "project_id": "my-project"
}
```

## Log Events

### Session-Level Events

#### `embed_start`
Logged when embedding begins for a project.

```json
{
  "timestamp": 1731339240.0,
  "span_id": "a1b2c3d4",
  "event": "embed_start",
  "level": "INFO",
  "project_id": "my-project",
  "user_id": "user123"
}
```

**Meaning**: User has clicked "embed" button or uploaded a file

**Use Cases**:
- Track when embedding sessions begin
- Correlate with frontend timestamp
- Attribute to user

#### `embed_complete`
Logged when embedding completes for the entire project.

```json
{
  "timestamp": 1731339250.5,
  "span_id": "a1b2c3d4",
  "event": "embed_complete",
  "level": "INFO",
  "batch_status": "success",
  "chunk_count": 150,
  "embedding_time_ms": 10500.0,
  "total_files": 2,
  "project_id": "my-project"
}
```

**Meaning**: All files processed, all chunks embedded

**Metrics**:
- `total_files`: Number of files that were embedded
- `chunk_count`: Total chunks embedded across all files
- `embedding_time_ms`: Total time for entire embedding session
- `total_files`: How many files were successfully processed

### File-Level Events

#### `file_start`
Logged when processing of a file begins.

```json
{
  "timestamp": 1731339240.2,
  "span_id": "a1b2c3d4",
  "event": "file_start",
  "level": "INFO",
  "file_path": "docs/auth.md",
  "file_size_bytes": 4096,
  "chunk_count": 8,
  "project_id": "my-project"
}
```

**Meaning**: A file has been read and split into chunks

**Metrics**:
- `file_path`: Relative path to file in project
- `file_size_bytes`: File size in bytes
- `chunk_count`: Number of chunks this file was split into

#### `file_complete`
Logged when all chunks from a file have been embedded.

```json
{
  "timestamp": 1731339245.1,
  "span_id": "a1b2c3d4",
  "event": "file_complete",
  "level": "INFO",
  "file_path": "docs/auth.md",
  "chunk_count": 8,
  "batch_status": "success",
  "embedding_time_ms": 4900.0,
  "project_id": "my-project"
}
```

**Meaning**: All chunks from this file have been embedded and stored

**Metrics**:
- `file_path`: Path to the file
- `chunk_count`: Number of chunks (for reference)
- `embedding_time_ms`: Total time to process this file

#### `file_error`
Logged if a file fails to read or encode.

```json
{
  "timestamp": 1731339242.0,
  "span_id": "a1b2c3d4",
  "event": "file_error",
  "level": "ERROR",
  "file_path": "docs/binary.pdf",
  "batch_status": "failed",
  "error": "Failed to read file: 'utf-8' codec can't decode byte 0xff in position 0",
  "project_id": "my-project"
}
```

**Meaning**: File could not be processed

**Common Errors**:
- `UnicodeDecodeError`: Binary file or wrong encoding
- `IsADirectoryError`: Path is a directory, not a file

### Batch-Level Events

#### `batch_complete`
Logged when a batch of chunks has been embedded and stored.

```json
{
  "timestamp": 1731339242.5,
  "span_id": "a1b2c3d4",
  "event": "batch_complete",
  "level": "INFO",
  "file_path": "docs/auth.md",
  "batch_num": 1,
  "batch_size": 32,
  "batch_status": "success",
  "embedding_time_ms": 245.5,
  "storage_time_ms": 12.3,
  "project_id": "my-project"
}
```

**Meaning**: Batch successfully embedded and stored

**Metrics**:
- `batch_num`: Batch number (1-indexed) within the file
- `batch_size`: Number of chunks in this batch
- `embedding_time_ms`: Time for HuggingFace embedding call
- `storage_time_ms`: Time to store vectors in SQLite
- **Total**: embedding_time_ms + storage_time_ms = batch time

**Performance Analysis**:
- If `embedding_time_ms` is high: HuggingFace API is slow
- If `storage_time_ms` is high: SQLite insert is slow
- Typical: embedding ~100ms for 32 chunks, storage ~5-20ms

#### `batch_error`
Logged if a batch fails during embedding.

```json
{
  "timestamp": 1731339243.0,
  "span_id": "a1b2c3d4",
  "event": "batch_error",
  "level": "ERROR",
  "file_path": "docs/auth.md",
  "batch_num": 2,
  "batch_status": "failed",
  "error": "Embedding failed: API timeout after 30s",
  "project_id": "my-project"
}
```

**Meaning**: A batch of chunks failed to embed

**Note**: Other files continue processing (graceful degradation)

## How to Read Logs

### View All Logs for a Project
```bash
cat .rag/projects/{project_id}/embed.log | jq .
```

### View Logs with Pretty-Printing
```bash
cat .rag/projects/{project_id}/embed.log | jq -r '[.timestamp, .span_id, .event, .file_path, .batch_status] | @csv'
```

### Follow Logs in Real-Time
```bash
tail -f .rag/projects/{project_id}/embed.log | jq .
```

### Find All Errors
```bash
cat .rag/projects/{project_id}/embed.log | jq 'select(.batch_status == "failed")'
```

### Analyze Session Timing
```bash
cat .rag/projects/{project_id}/embed.log | jq 'select(.event == "embed_complete")'
```

### Track a Specific File
```bash
cat .rag/projects/{project_id}/embed.log | jq 'select(.file_path == "docs/auth.md")'
```

## Example: Tracing a Complete Embedding Session

```bash
# Project ID from URL: abc123def456
# User uploads "docs/auth.md"

# 1. Session starts
{"timestamp": 1731339240.0, "span_id": "a1b2c3d4", "event": "embed_start", ...}

# 2. File is read (56KB, 8 chunks)
{"timestamp": 1731339240.2, "span_id": "a1b2c3d4", "event": "file_start",
 "file_path": "docs/auth.md", "file_size_bytes": 56000, "chunk_count": 8, ...}

# 3. Batch 1 (chunks 1-8) embedded
{"timestamp": 1731339242.5, "span_id": "a1b2c3d4", "event": "batch_complete",
 "file_path": "docs/auth.md", "batch_num": 1, "batch_size": 8,
 "embedding_time_ms": 245.5, "storage_time_ms": 12.3, ...}

# 4. File complete
{"timestamp": 1731339245.1, "span_id": "a1b2c3d4", "event": "file_complete",
 "file_path": "docs/auth.md", "chunk_count": 8, "embedding_time_ms": 4900.0, ...}

# 5. Session complete
{"timestamp": 1731339245.2, "span_id": "a1b2c3d4", "event": "embed_complete",
 "chunk_count": 8, "embedding_time_ms": 5100.0, "total_files": 1, ...}
```

## Debugging: Common Issues

### Issue: 500 Error on Embed

**Solution**: Check the embed log for detailed error

```bash
tail -20 .rag/projects/{project_id}/embed.log | jq .
```

Look for:
- `file_error`: File couldn't be read → wrong encoding/binary file
- `batch_error`: Batch failed → embedding API issue
- Last event should be an error, not `embed_complete`

### Issue: Embedding Takes Too Long

**Solution**: Check batch timing in logs

```bash
cat .rag/projects/{project_id}/embed.log | \
  jq 'select(.event == "batch_complete") | {file: .file_path, batch: .batch_num, embed_ms: .embedding_time_ms, storage_ms: .storage_time_ms}'
```

If `embedding_time_ms` is high (>500ms per batch):
- HuggingFace API is slow
- Check network connection
- Check HuggingFace endpoint

If `storage_time_ms` is high (>100ms per batch):
- SQLite insert is slow
- Database might be locked
- Try smaller batch size

### Issue: Only Some Files Embedded

**Solution**: Check for file errors

```bash
cat .rag/projects/{project_id}/embed.log | jq 'select(.level == "ERROR")'
```

Look at `file_error` events to see which files failed and why.

**Note**: Embedding continues for other files even if one fails.

## Performance Baselines

### Expected Timings

| Operation | Time |
|-----------|------|
| Read file | ~1-10ms |
| Chunk file | ~5-50ms |
| Embedding 32 chunks | ~200-400ms |
| Storage 32 chunks | ~10-50ms |
| **Total per batch** | ~250-500ms |

### Scaling

- **10 chunks total**: ~50-100ms total
- **100 chunks total**: ~500-1000ms total
- **1000 chunks total**: ~5-10 seconds total

### Bottleneck Analysis

1. **High embedding_time_ms** → Network/API is slow
2. **High storage_time_ms** → SQLite is slow or locked
3. **Many file_errors** → Encoding issues or binary files

## Metrics for Monitoring

### Embed Success Rate
```bash
cat .rag/projects/{project_id}/embed.log | \
  jq -s '
    {
      total_files: [.[] | select(.event == "file_start")] | length,
      successful: [.[] | select(.event == "file_complete")] | length,
      failed: [.[] | select(.event == "file_error")] | length
    }'
```

### Average File Embedding Time
```bash
cat .rag/projects/{project_id}/embed.log | \
  jq -s '[.[] | select(.event == "file_complete") | .embedding_time_ms] |
          add / length'
```

### Batch Efficiency
```bash
cat .rag/projects/{project_id}/embed.log | \
  jq 'select(.event == "batch_complete") |
      {batch_size, embedding_time_ms, per_chunk: (.embedding_time_ms / .batch_size)}'
```

## Configuration

### Batch Size

Control batch size in embed request:

```python
# Default: 64 chunks per batch
await apiClient.embed(projectId)

# Custom: 32 chunks per batch (slower but less memory)
await apiClient.embed(projectId, { batch_size: 32 })

# Custom: 128 chunks per batch (faster but more memory)
await apiClient.embed(projectId, { batch_size: 128 })
```

Adjust batch size to optimize:
- **Smaller** (32): Use if getting memory errors or timeouts
- **Larger** (128): Use if network is limiting factor

## Summary

The embedding logs provide complete visibility into:
1. **When** embedding started and completed
2. **Which** files were processed
3. **How many** chunks were created per file
4. **How long** each batch took (embedding + storage separately)
5. **Any** errors that occurred

Use these logs to:
- Debug 500 errors during embedding
- Monitor embedding performance
- Optimize batch sizes
- Track which files failed
- Measure improvement over time

For detailed tracing, include the `span_id` in bug reports or support requests.

---

**Log Format**: JSON (one entry per line)
**Automatic**: All logging is automatic, no configuration needed
**Performance**: Negligible impact (microseconds per log entry)
