# Debugging Guide - Embedding 500 Errors

**Added**: Commit 7384f6f and 222815d
**Problem**: Getting 500 error when embedding files
**Solution**: Use comprehensive embedding logs to trace the issue

## Quick Start

### 1. Upload a file and get the 500 error
The file will be uploaded and symlink created, but embedding fails.

### 2. Check the logs
```bash
# View embedding logs for your project
cat .rag/projects/{project_id}/embed.log | jq .

# Find errors
cat .rag/projects/{project_id}/embed.log | jq 'select(.level == "ERROR")'

# Follow in real-time (tail -f style)
tail -f .rag/projects/{project_id}/embed.log | jq .
```

### 3. Identify the issue
Look for error messages and determine the cause:

- `file_error`: File couldn't be read → Encoding issue?
- `batch_error`: Embedding failed → API issue?
- `embed_complete` missing: Process crashed → Check exception

## Common Issues and Solutions

### Issue 1: UnicodeDecodeError

**Log shows**:
```json
{"event": "file_error", "error": "'utf-8' codec can't decode byte 0xff"}
```

**Meaning**: File is binary (PDF, Excel, image) or has wrong encoding

**Solution**:
- Upload only text files (.txt, .md, .py, .java, .js)
- Avoid binary files (PDF, images, executables)
- Use UTF-8 encoded files

### Issue 2: HuggingFace API Timeout

**Log shows**:
```json
{"event": "batch_error", "error": "API timeout after 30s"}
```

**Meaning**: HuggingFace embedding endpoint is slow or unreachable

**Solution**:
- Check HF_API_TOKEN is set and valid
- Verify HF_ENDPOINT_URL is correct (if using custom endpoint)
- Try smaller batch size: `batch_size: 32` instead of 64
- Check network connectivity
- Check HuggingFace service status

### Issue 3: SQLite Database Error

**Log shows**:
```json
{"event": "batch_error", "error": "database is locked"}
```

**Meaning**: Vector database is locked (concurrent access?)

**Solution**:
- Don't start embedding twice simultaneously
- Close other database connections
- Try again after a few seconds
- Check `.rag/projects/{project_id}/rag.sqlite` permissions

### Issue 4: Out of Memory

**Log shows**:
```json
{"event": "batch_error", "error": "MemoryError"}
```

**Meaning**: Batch size is too large for available RAM

**Solution**:
- Reduce batch size: `batch_size: 32`
- Close other applications
- Reduce file size being embedded

### Issue 5: File Not Found

**Log shows**:
```json
{"event": "file_error", "error": "No such file or directory"}
```

**Meaning**: File was deleted after upload but before embedding

**Solution**:
- Don't delete files from project during embedding
- Upload again and embed immediately

## Log Anatomy

### Complete Successful Embedding

```bash
# 1. Session starts
$ cat .rag/projects/{project_id}/embed.log | jq 'select(.event == "embed_start")'
{
  "timestamp": 1731339240.0,
  "span_id": "a1b2c3d4",
  "event": "embed_start",
  "level": "INFO",
  "project_id": "my-project",
  "user_id": "user123"
}

# 2. File processing starts
$ cat .rag/projects/{project_id}/embed.log | jq 'select(.event == "file_start")'
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

# 3. Batches complete (one or more)
$ cat .rag/projects/{project_id}/embed.log | jq 'select(.event == "batch_complete")'
{
  "timestamp": 1731339242.5,
  "span_id": "a1b2c3d4",
  "event": "batch_complete",
  "level": "INFO",
  "file_path": "docs/auth.md",
  "batch_num": 1,
  "batch_size": 8,
  "batch_status": "success",
  "embedding_time_ms": 245.5,
  "storage_time_ms": 12.3,
  "project_id": "my-project"
}

# 4. File processing completes
$ cat .rag/projects/{project_id}/embed.log | jq 'select(.event == "file_complete")'
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

# 5. Session completes
$ cat .rag/projects/{project_id}/embed.log | jq 'select(.event == "embed_complete")'
{
  "timestamp": 1731339245.2,
  "span_id": "a1b2c3d4",
  "event": "embed_complete",
  "level": "INFO",
  "total_files": 1,
  "chunk_count": 8,
  "batch_status": "success",
  "embedding_time_ms": 5100.0,
  "project_id": "my-project"
}
```

## Performance Analysis

### Check Batch Timing

```bash
# Show all batches with timing
cat .rag/projects/{project_id}/embed.log | \
  jq 'select(.event == "batch_complete") |
      {file: .file_path, batch: .batch_num,
       embedding_ms: .embedding_time_ms,
       storage_ms: .storage_time_ms,
       total_ms: (.embedding_time_ms + .storage_time_ms)}'
```

**Interpretation**:
- `embedding_time_ms`: Time for HuggingFace API call
  - Normal: 100-300ms per 32 chunks
  - High: Network slow, API busy, or endpoint down
  - Very high (>1000ms): Likely timeout incoming

- `storage_time_ms`: Time for SQLite insert
  - Normal: 5-20ms per 32 chunks
  - High: Database slow or locked

### Check File Chunking

```bash
# Show chunk count per file
cat .rag/projects/{project_id}/embed.log | \
  jq 'select(.event == "file_start") |
      {file: .file_path, size_kb: (.file_size_bytes / 1024), chunks: .chunk_count}'
```

**Interpretation**:
- If chunks seem too high: File very large, may timeout
- If chunks seem too low: File very small, should be fast
- Typical: ~100-200 tokens per chunk with overlap

## Step-by-Step Debugging

### Step 1: Verify logs exist

```bash
ls -la .rag/projects/{project_id}/
# Should show: embed.log, queries.log, rag.sqlite
```

If no `embed.log`:
- Embedding endpoint wasn't called
- Check frontend is calling the right API

### Step 2: Check for errors

```bash
cat .rag/projects/{project_id}/embed.log | jq '.level' | sort | uniq -c
# Should show mostly "INFO" with possibly some "ERROR"
```

If no entries at all:
- Endpoint not being called
- Logging not working

### Step 3: Find the error

```bash
cat .rag/projects/{project_id}/embed.log | jq 'select(.level == "ERROR")'
# Look at first error entry
```

### Step 4: Check the span_id

```bash
# Get span_id from error
SPAN_ID=$(cat .rag/projects/{project_id}/embed.log | \
  jq -r 'select(.level == "ERROR") | .span_id' | head -1)

# Trace all entries with this span_id
cat .rag/projects/{project_id}/embed.log | jq "select(.span_id == \"$SPAN_ID\")"
```

This shows complete timeline of the failed embedding.

### Step 5: Correlate with frontend

- Check browser console for error message
- Compare error with backend log
- Share both for debugging

## Useful Commands

### Pretty-print latest error
```bash
cat .rag/projects/{project_id}/embed.log | \
  jq 'select(.level == "ERROR")' | \
  tail -1 | \
  jq .
```

### Count events by type
```bash
cat .rag/projects/{project_id}/embed.log | \
  jq -r '.event' | sort | uniq -c
```

### Find slowest batch
```bash
cat .rag/projects/{project_id}/embed.log | \
  jq 'select(.event == "batch_complete") |
      {file: .file_path, batch: .batch_num,
       total_ms: (.embedding_time_ms + .storage_time_ms)}' | \
  sort_by(.total_ms) | \
  last
```

### Export logs for analysis
```bash
# Convert to CSV for spreadsheet analysis
cat .rag/projects/{project_id}/embed.log | \
  jq -r '[.timestamp, .event, .file_path, .batch_num,
          .embedding_time_ms, .storage_time_ms] | @csv' > embed_analysis.csv
```

## What to Share When Reporting a Bug

When reporting a 500 embedding error:

1. **The error message** from frontend
2. **The embed.log** (entire file)
   ```bash
   cat .rag/projects/{project_id}/embed.log
   ```
3. **Span ID** (if identifiable)
4. **Browser console** (Ctrl+Shift+K)
5. **File information**
   - File name and size
   - File type (text, code, etc.)
   - Approximate line count

This will provide complete debugging context.

## Prevention

### Upload Only Text Files

✅ Good:
- `.txt`, `.md`, `.rst`
- `.py`, `.js`, `.ts`, `.java`, `.cpp`
- `.json`, `.yaml`, `.toml`
- `.html`, `.xml`

❌ Avoid:
- `.pdf`, `.docx`, `.xlsx`
- `.jpg`, `.png`, `.gif`
- `.exe`, `.bin`, `.so`
- Any binary format

### Monitor Logs Proactively

```bash
# Watch logs in real-time while uploading
tail -f .rag/projects/{project_id}/embed.log | jq .
# In another terminal, upload a file
# Watch the logs appear in real-time
```

### Test with Small Files

Start with a small (< 10KB) text file:
- If it works: large files likely caused issues
- If it fails: environmental issue, not file-specific

## Still Having Issues?

1. ✅ Check embedding logs: `.rag/projects/{project_id}/embed.log`
2. ✅ Look for `file_error` or `batch_error` entries
3. ✅ Verify file is text (not binary)
4. ✅ Check HF_API_TOKEN is set
5. ✅ Try with smaller batch size
6. ✅ Check network connectivity
7. ✅ Share logs with span_id for support

The logs contain everything needed to identify the exact issue.

---

**Log Format**: JSON (one entry per line)
**Location**: `.rag/projects/{project_id}/embed.log`
**Tools**: `jq` for filtering and analysis
**Real-time**: `tail -f ... | jq .` to watch in real-time
