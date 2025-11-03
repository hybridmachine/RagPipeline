#!/bin/bash
# Demo script for RAG Pipeline CLI

set -e  # Exit on error

echo "========================================="
echo "RAG Pipeline CLI Demo"
echo "========================================="
echo

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Clean slate
echo "Cleaning previous data..."
rm -rf .rag/
echo

# Show help
echo "1. Showing CLI help:"
echo "----------------------------------------"
rag --help
echo

# Check initial status
echo "2. Checking initial status:"
echo "----------------------------------------"
rag status
echo

# Scan a small subset of files
echo "3. Scanning rag_core directory (limited to 5 files):"
echo "----------------------------------------"
rag scan --root rag_core --include "*.py" --limit 5
echo

# Check status after scan
echo "4. Status after scan:"
echo "----------------------------------------"
rag status
echo

# Show scan command help
echo "5. Scan command details:"
echo "----------------------------------------"
rag scan --help
echo

# Show embed command help
echo "6. Embed command details:"
echo "----------------------------------------"
rag embed --help
echo

echo "========================================="
echo "Demo Complete!"
echo "========================================="
echo
echo "To generate embeddings, you need to:"
echo "1. Set HF_API_TOKEN environment variable"
echo "2. Run: rag embed"
echo
echo "To query the system (after embedding), you need to:"
echo "1. Implement rag_core/retrieval/query_engine.py"
echo "2. Implement rag_core/llm/openai_client.py"
echo "3. Set OPENAI_API_KEY environment variable"
echo "4. Run: rag query -q 'your question'"
echo
