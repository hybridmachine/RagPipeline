"""RAG Pipeline CLI interface.

Command-line interface for the RAG Pipeline system using Typer.
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from rag_core.config import Config, get_config, set_config
from rag_core.database.file_tracker import FileTracker

app = typer.Typer(
    name="rag",
    help="RAG Pipeline - Retrieval-Augmented Generation system",
    add_completion=False,
)
console = Console()


def get_or_create_config(
    db_path: Optional[Path] = None,
) -> Config:
    """Get or create configuration with optional overrides."""
    config = get_config()
    if db_path:
        config.db_path = db_path
    config.ensure_db_directory()
    return config


@app.command()
def scan(
    root: Path = typer.Option(
        Path("."),
        "--root",
        "-r",
        help="Root directory to scan",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    include: Optional[List[str]] = typer.Option(
        None,
        "--include",
        "-i",
        help="Include patterns (glob)",
    ),
    exclude: Optional[List[str]] = typer.Option(
        None,
        "--exclude",
        "-e",
        help="Exclude patterns (glob)",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum files to process",
    ),
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        help="Database path",
    ),
) -> None:
    """Scan directory for files and detect changes.

    Walks the directory tree, computes SHA-256 hashes, and identifies
    new or changed files that need to be processed.
    """
    try:
        config = get_or_create_config(db_path)

        console.print(f"[bold blue]Scanning directory:[/bold blue] {root}")

        # Import scanner
        try:
            from rag_core.scanner.file_scanner import FileScanner
            from rag_core.scanner.chunker import Chunker
            from rag_core.database.vector_store import VectorStore
        except ImportError as e:
            console.print(f"[red]Error: Required module not implemented: {e}[/red]")
            raise typer.Exit(code=3)

        scanner = FileScanner(
            config=config,
            include_patterns=include or ["**/*"],
            exclude_patterns=exclude or [],
        )

        chunker = Chunker(config=config)

        with FileTracker(config.db_path) as tracker:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                # Scan files
                task = progress.add_task("Scanning files...", total=None)
                changed_files = asyncio.run(
                    scanner.scan_directory(root, tracker, limit=limit)
                )
                progress.update(task, completed=True)

                # Chunk changed files
                if changed_files:
                    task = progress.add_task(f"Chunking {len(changed_files)} files...", total=None)

                    vector_store = VectorStore(config)
                    vector_store.connect()

                    total_chunks = 0
                    for scanned_file in changed_files:
                        try:
                            # Read and chunk file
                            with open(scanned_file.path, "r", encoding="utf-8", errors="ignore") as f:
                                text = f.read()

                            chunks = chunker.chunk_text(text, scanned_file.relative_path)

                            if chunks:
                                vector_store.insert_chunks(chunks, scanned_file.sha256)
                                total_chunks += len(chunks)

                        except Exception as e:
                            console.print(f"[yellow]Warning: Failed to chunk {scanned_file.path}: {e}[/yellow]")

                    vector_store.close()
                    progress.update(task, completed=True)

            # Display results
            table = Table(title="Scan Results")
            table.add_column("Metric", style="cyan")
            table.add_column("Count", style="green", justify="right")

            table.add_row("Total files tracked", str(tracker.count()))
            table.add_row("New or changed files", str(len(changed_files)))
            if changed_files:
                table.add_row("Chunks created", str(total_chunks))

            console.print(table)

            if changed_files and total_chunks > 0:
                console.print("\n[yellow]Run 'rag embed' to generate embeddings for chunks[/yellow]")

        sys.exit(0)

    except Exception as e:
        console.print(f"[red]Error during scan:[/red] {e}")
        sys.exit(4)


@app.command()
def embed(
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Embedding model ID (overrides config)",
    ),
    batch: int = typer.Option(
        64,
        "--batch",
        "-b",
        help="Batch size for embedding",
    ),
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        help="Database path",
    ),
) -> None:
    """Generate embeddings for pending chunks.

    Processes chunks that haven't been embedded yet and stores
    vectors in the vector database.
    """
    try:
        config = get_or_create_config(db_path)
        if model:
            config.embed_model_id = model
        config.embedding_batch_size = batch

        console.print(f"[bold blue]Generating embeddings[/bold blue]")
        console.print(f"Model: {config.embed_model_id}")
        console.print(f"Batch size: {batch}")

        # Import required modules
        try:
            from rag_core.vectorizer.embedder import Embedder
            from rag_core.vectorizer.batch_processor import BatchProcessor
            from rag_core.database.vector_store import VectorStore
        except ImportError as e:
            console.print(f"[red]Error: Required module not implemented: {e}[/red]")
            console.print("[yellow]Please implement rag_core/database/vector_store.py[/yellow]")
            raise typer.Exit(code=3)

        async def run_embedding() -> None:
            async with Embedder(config=config, model_id=model) as embedder:
                # Initialize vector store
                vector_store = VectorStore(config)
                vector_store.connect()

                # Get pending chunks
                pending_chunks = vector_store.get_pending_chunks()

                if not pending_chunks:
                    console.print("[green]No pending chunks to embed[/green]")
                    return

                console.print(f"Found {len(pending_chunks)} chunks to embed")

                # Create batch processor
                processor = BatchProcessor(
                    embedder=embedder,
                    config=config,
                    batch_size=batch,
                )

                # Process with progress bar
                texts = [chunk.text for chunk in pending_chunks]
                completed = [0]

                def progress_callback(done: int, total: int) -> None:
                    completed[0] = done
                    console.print(f"Progress: {done}/{total} batches")

                embeddings = await processor.process_batches(
                    texts=texts,
                    normalize=True,
                    progress_callback=progress_callback,
                )

                # Store embeddings
                vector_store.upsert_vectors(pending_chunks, embeddings)

                console.print(f"[green]Successfully embedded {len(embeddings)} chunks[/green]")
                console.print(f"Embedding dimension: {embedder.embedding_dim}")

                vector_store.close()

        asyncio.run(run_embedding())
        sys.exit(0)

    except Exception as e:
        console.print(f"[red]Error during embedding:[/red] {e}")
        sys.exit(4)


@app.command()
def query(
    q: str = typer.Option(
        ...,
        "--query",
        "-q",
        help="Query string",
    ),
    k: int = typer.Option(
        8,
        "--top-k",
        "-k",
        help="Number of results to retrieve",
    ),
    rerank: Optional[int] = typer.Option(
        None,
        "--rerank",
        help="Apply re-ranking to top N results",
    ),
    json: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON",
    ),
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        help="Database path",
    ),
) -> None:
    """Query the RAG system.

    Embeds the query, retrieves relevant chunks, and generates
    an answer using the LLM.
    """
    try:
        config = get_or_create_config(db_path)

        if not json:
            console.print(f"[bold blue]Query:[/bold blue] {q}")

        # Import required modules
        try:
            from rag_core.retrieval.query_engine import QueryEngine
            from rag_core.llm.openai_client import OpenAIClient
        except ImportError as e:
            console.print(f"[red]Error: Required module not implemented: {e}[/red]")
            console.print("[yellow]Please implement query_engine.py and openai_client.py[/yellow]")
            raise typer.Exit(code=3)

        async def run_query() -> None:
            # Use async context managers to ensure proper connection/cleanup
            async with QueryEngine(config) as query_engine:
                async with OpenAIClient(config) as llm_client:
                    # Get query results
                    result = await query_engine.query(
                        query_text=q,
                        k=k,
                        rerank_top_n=rerank,
                    )

                    # Generate answer
                    answer = await llm_client.generate_answer(
                        query=q,
                        context=result.context,
                        citations=result.citations,
                    )

                    if json:
                        import orjson
                        output = orjson.dumps({
                            "query": q,
                            "answer": answer.text,
                            "citations": [
                                {
                                    "path": c.doc_path,
                                    "chunk_id": c.chunk_id,
                                    "score": c.score,
                                }
                                for c in answer.citations
                            ],
                        }).decode()
                        console.print(output)
                    else:
                        console.print(f"\n[bold green]Answer:[/bold green]\n{answer.text}\n")

                        if answer.citations:
                            console.print("[bold]Sources:[/bold]")
                            for i, citation in enumerate(answer.citations, 1):
                                console.print(f"{i}. {citation.doc_path} (chunk {citation.chunk_id}, score: {citation.score:.3f})")

        asyncio.run(run_query())
        sys.exit(0)

    except Exception as e:
        console.print(f"[red]Error during query:[/red] {e}")
        sys.exit(4)


@app.command()
def serve(
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        help="Host to bind to",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="Port to bind to",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        help="Enable auto-reload",
    ),
) -> None:
    """Start the web API server.

    Launches a FastAPI server with the RAG endpoints.
    """
    try:
        console.print(f"[bold blue]Starting RAG API server[/bold blue]")
        console.print(f"Host: {host}")
        console.print(f"Port: {port}")

        try:
            import uvicorn
            from web.app import app as web_app
        except ImportError as e:
            console.print(f"[red]Error: Web module not implemented: {e}[/red]")
            console.print("[yellow]Please implement web/app.py[/yellow]")
            raise typer.Exit(code=3)

        uvicorn.run(
            "web.app:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info",
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error starting server:[/red] {e}")
        sys.exit(4)


@app.command()
def reindex(
    drop: bool = typer.Option(
        False,
        "--drop",
        help="Drop existing vectors before reindexing",
    ),
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        help="Database path",
    ),
) -> None:
    """Rebuild vector index from chunks.

    Useful for changing embedding models or fixing corrupted indexes.
    """
    try:
        config = get_or_create_config(db_path)

        console.print("[bold blue]Reindexing vectors[/bold blue]")

        try:
            from rag_core.database.vector_store import VectorStore
        except ImportError:
            console.print("[red]Error: vector_store module not implemented[/red]")
            raise typer.Exit(code=3)

        vector_store = VectorStore(config)
        vector_store.connect()

        if drop:
            console.print("[yellow]Dropping existing vectors...[/yellow]")
            vector_store.drop_vectors()

        # Get all chunks
        chunks = vector_store.get_all_chunks()
        console.print(f"Found {len(chunks)} chunks to reindex")

        # Mark them as pending
        vector_store.mark_pending(chunks)

        vector_store.close()

        console.print("[green]Chunks marked for reindexing[/green]")
        console.print("[yellow]Run 'rag embed' to generate embeddings[/yellow]")

        sys.exit(0)

    except Exception as e:
        console.print(f"[red]Error during reindex:[/red] {e}")
        sys.exit(4)


@app.command()
def gc(
    vacuum: bool = typer.Option(
        True,
        "--vacuum/--no-vacuum",
        help="Run VACUUM after cleanup",
    ),
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        help="Database path",
    ),
) -> None:
    """Garbage collect orphaned data.

    Removes orphaned chunks and vectors whose source files no longer exist
    or have been updated.
    """
    try:
        config = get_or_create_config(db_path)

        console.print("[bold blue]Running garbage collection[/bold blue]")

        try:
            from rag_core.database.vector_store import VectorStore
        except ImportError:
            console.print("[red]Error: vector_store module not implemented[/red]")
            raise typer.Exit(code=3)

        with FileTracker(config.db_path) as tracker:
            vector_store = VectorStore(config)
            vector_store.connect()

            # Clean up orphaned chunks/vectors
            deleted_chunks = vector_store.cleanup_orphaned(tracker)

            console.print(f"Deleted {deleted_chunks} orphaned chunks")

            if vacuum:
                console.print("Running VACUUM...")
                tracker.vacuum()
                vector_store.vacuum()

            vector_store.close()

        console.print("[green]Garbage collection complete[/green]")
        sys.exit(0)

    except Exception as e:
        console.print(f"[red]Error during GC:[/red] {e}")
        sys.exit(4)


@app.command()
def status(
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        help="Database path",
    ),
) -> None:
    """Show system status and statistics."""
    try:
        config = get_or_create_config(db_path)

        table = Table(title="RAG Pipeline Status")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details", style="yellow")

        # Check database
        if config.db_path.exists():
            with FileTracker(config.db_path) as tracker:
                file_count = tracker.count()
                table.add_row("Database", "✓ Connected", f"{file_count} files tracked")
        else:
            table.add_row("Database", "✗ Not found", str(config.db_path))

        # Check vector store
        try:
            from rag_core.database.vector_store import VectorStore
            vector_store = VectorStore(config)
            vector_store.connect()
            chunk_count = vector_store.count_chunks()
            vector_count = vector_store.count_vectors()
            table.add_row("Vector Store", "✓ Available", f"{chunk_count} chunks, {vector_count} vectors")
            vector_store.close()
        except ImportError:
            table.add_row("Vector Store", "✗ Not implemented", "")
        except Exception as e:
            table.add_row("Vector Store", "✗ Error", str(e))

        # Check embedder
        try:
            from rag_core.vectorizer.embedder import Embedder
            table.add_row("Embedder", "✓ Available", config.embed_model_id)
        except ImportError:
            table.add_row("Embedder", "✗ Not available", "")

        # Check LLM
        if config.openai_api_key:
            table.add_row("LLM", "✓ Configured", config.openai_model)
        else:
            table.add_row("LLM", "⚠ No API key", "Set OPENAI_API_KEY")

        console.print(table)
        sys.exit(0)

    except Exception as e:
        console.print(f"[red]Error getting status:[/red] {e}")
        sys.exit(4)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
