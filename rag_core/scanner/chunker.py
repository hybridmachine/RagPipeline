"""Text chunking with multiple strategies.

Provides recursive token splitting, markdown-aware, and code-aware chunking.
"""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

import tiktoken

from rag_core.config import Config


class ChunkStrategy(str, Enum):
    """Chunking strategy types."""

    RECURSIVE = "recursive"
    MARKDOWN = "markdown"
    CODE = "code"


@dataclass
class Chunk:
    """Represents a text chunk with metadata."""

    text: str
    doc_path: str
    chunk_id: int
    start_char: int
    end_char: int
    section: Optional[str] = None
    token_count: Optional[int] = None


class Chunker:
    """Text chunking with multiple strategies."""

    def __init__(
        self,
        config: Config,
        strategy: ChunkStrategy = ChunkStrategy.RECURSIVE,
        encoding_name: str = "cl100k_base",  # GPT-4 encoding
    ) -> None:
        """Initialize chunker.

        Args:
            config: Configuration instance
            strategy: Chunking strategy to use
            encoding_name: Tiktoken encoding name
        """
        self.config = config
        self.strategy = strategy
        self.target_tokens = config.chunk_target_tokens
        self.overlap_tokens = config.chunk_overlap_tokens

        # Initialize tokenizer
        try:
            self.encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            # Fallback to basic encoding
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        return len(self.encoding.encode(text))

    def normalize_text(self, text: str) -> str:
        """Normalize text for chunking.

        Args:
            text: Raw text

        Returns:
            Normalized text
        """
        # Remove null bytes
        text = text.replace("\x00", "")

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Remove excessive whitespace but preserve paragraph breaks
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Strip leading/trailing whitespace
        text = text.strip()

        return text

    def chunk_recursive(
        self,
        text: str,
        doc_path: str,
    ) -> List[Chunk]:
        """Split text recursively by tokens with overlap.

        Args:
            text: Text to chunk
            doc_path: Document path for metadata

        Returns:
            List of chunks
        """
        chunks: List[Chunk] = []

        # Tokenize entire text
        tokens = self.encoding.encode(text)
        total_tokens = len(tokens)

        if total_tokens <= self.target_tokens:
            # Text fits in one chunk
            return [
                Chunk(
                    text=text,
                    doc_path=doc_path,
                    chunk_id=0,
                    start_char=0,
                    end_char=len(text),
                    token_count=total_tokens,
                )
            ]

        # Calculate step size (target - overlap)
        step_size = self.target_tokens - self.overlap_tokens

        chunk_id = 0
        start_idx = 0

        while start_idx < total_tokens:
            # Get chunk tokens
            end_idx = min(start_idx + self.target_tokens, total_tokens)
            chunk_tokens = tokens[start_idx:end_idx]

            # Decode back to text
            chunk_text = self.encoding.decode(chunk_tokens)

            # Calculate character positions (approximate)
            # This is approximate because token boundaries don't align with char boundaries
            char_ratio = len(text) / total_tokens if total_tokens > 0 else 0
            start_char = int(start_idx * char_ratio)
            end_char = int(end_idx * char_ratio)

            chunks.append(
                Chunk(
                    text=chunk_text,
                    doc_path=doc_path,
                    chunk_id=chunk_id,
                    start_char=start_char,
                    end_char=min(end_char, len(text)),
                    token_count=len(chunk_tokens),
                )
            )

            chunk_id += 1
            start_idx += step_size

        return chunks

    def chunk_markdown(
        self,
        text: str,
        doc_path: str,
    ) -> List[Chunk]:
        """Split markdown text preserving structure.

        Args:
            text: Markdown text to chunk
            doc_path: Document path for metadata

        Returns:
            List of chunks
        """
        chunks: List[Chunk] = []
        chunk_id = 0

        # Split by headers first
        header_pattern = r"^(#{1,6})\s+(.+)$"
        lines = text.split("\n")

        current_section: Optional[str] = None
        current_text: List[str] = []
        current_start_char = 0

        def flush_section() -> None:
            """Flush current section as chunk(s)."""
            nonlocal chunk_id, current_text, current_start_char

            if not current_text:
                return

            section_text = "\n".join(current_text)
            token_count = self.count_tokens(section_text)

            if token_count <= self.target_tokens:
                # Section fits in one chunk
                chunks.append(
                    Chunk(
                        text=section_text,
                        doc_path=doc_path,
                        chunk_id=chunk_id,
                        start_char=current_start_char,
                        end_char=current_start_char + len(section_text),
                        section=current_section,
                        token_count=token_count,
                    )
                )
                chunk_id += 1
            else:
                # Section too large, split recursively
                sub_chunks = self.chunk_recursive(section_text, doc_path)
                for sub_chunk in sub_chunks:
                    chunks.append(
                        Chunk(
                            text=sub_chunk.text,
                            doc_path=doc_path,
                            chunk_id=chunk_id,
                            start_char=current_start_char + sub_chunk.start_char,
                            end_char=current_start_char + sub_chunk.end_char,
                            section=current_section,
                            token_count=sub_chunk.token_count,
                        )
                    )
                    chunk_id += 1

            current_text = []

        char_pos = 0
        for line in lines:
            match = re.match(header_pattern, line, re.MULTILINE)

            if match:
                # Found a header, flush previous section
                flush_section()
                current_section = match.group(2).strip()
                current_start_char = char_pos

            current_text.append(line)
            char_pos += len(line) + 1  # +1 for newline

        # Flush final section
        flush_section()

        # If no chunks created (no headers), fall back to recursive
        if not chunks:
            return self.chunk_recursive(text, doc_path)

        return chunks

    def chunk_code(
        self,
        text: str,
        doc_path: str,
        language: Optional[str] = None,
    ) -> List[Chunk]:
        """Split code preserving function/class boundaries.

        Args:
            text: Code text to chunk
            doc_path: Document path for metadata
            language: Programming language (detected from extension if None)

        Returns:
            List of chunks
        """
        chunks: List[Chunk] = []
        chunk_id = 0

        # Detect language from file extension
        if language is None:
            ext = Path(doc_path).suffix.lower()
            language = ext.lstrip(".")

        # Language-specific patterns
        if language in ("py", "python"):
            # Python: class and def
            boundary_pattern = r"^(class |def |async def )"
        elif language in ("js", "ts", "jsx", "tsx", "javascript", "typescript"):
            # JavaScript/TypeScript: function, class, const/let arrow functions
            boundary_pattern = r"^(function |class |const \w+ = |let \w+ = |export )"
        elif language in ("java", "c", "cpp", "cs", "go", "rs", "rust"):
            # C-family and similar: class, function, struct
            boundary_pattern = r"^(class |struct |public |private |protected |func |\w+ \w+\()"
        else:
            # Fallback to recursive splitting
            return self.chunk_recursive(text, doc_path)

        lines = text.split("\n")
        current_chunk: List[str] = []
        current_start_char = 0
        char_pos = 0

        def flush_chunk() -> None:
            """Flush current chunk."""
            nonlocal chunk_id, current_chunk, current_start_char

            if not current_chunk:
                return

            chunk_text = "\n".join(current_chunk)
            token_count = self.count_tokens(chunk_text)

            if token_count <= self.target_tokens:
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        doc_path=doc_path,
                        chunk_id=chunk_id,
                        start_char=current_start_char,
                        end_char=current_start_char + len(chunk_text),
                        token_count=token_count,
                    )
                )
                chunk_id += 1
            else:
                # Chunk too large, split recursively
                sub_chunks = self.chunk_recursive(chunk_text, doc_path)
                for sub_chunk in sub_chunks:
                    chunks.append(
                        Chunk(
                            text=sub_chunk.text,
                            doc_path=doc_path,
                            chunk_id=chunk_id,
                            start_char=current_start_char + sub_chunk.start_char,
                            end_char=current_start_char + sub_chunk.end_char,
                            token_count=sub_chunk.token_count,
                        )
                    )
                    chunk_id += 1

            current_chunk = []

        for line in lines:
            # Check if line is a boundary
            if re.match(boundary_pattern, line.lstrip()):
                # If we have content and this is a new boundary, flush
                if current_chunk:
                    flush_chunk()
                    current_start_char = char_pos

            current_chunk.append(line)
            char_pos += len(line) + 1

        # Flush final chunk
        flush_chunk()

        # If no chunks created, fall back to recursive
        if not chunks:
            return self.chunk_recursive(text, doc_path)

        return chunks

    def chunk_text(
        self,
        text: str,
        doc_path: str,
        strategy: Optional[ChunkStrategy] = None,
    ) -> List[Chunk]:
        """Chunk text using specified strategy.

        Args:
            text: Text to chunk
            doc_path: Document path for metadata
            strategy: Override chunking strategy

        Returns:
            List of chunks
        """
        # Normalize text first
        text = self.normalize_text(text)

        if not text:
            return []

        # Use override strategy or default
        chunk_strategy = strategy or self.strategy

        # Detect best strategy from file extension if recursive
        if chunk_strategy == ChunkStrategy.RECURSIVE:
            ext = Path(doc_path).suffix.lower()

            if ext in (".md", ".markdown"):
                chunk_strategy = ChunkStrategy.MARKDOWN
            elif ext in (
                ".py",
                ".js",
                ".ts",
                ".tsx",
                ".jsx",
                ".java",
                ".c",
                ".cpp",
                ".h",
                ".cs",
                ".go",
                ".rs",
            ):
                chunk_strategy = ChunkStrategy.CODE

        # Apply strategy
        if chunk_strategy == ChunkStrategy.MARKDOWN:
            return self.chunk_markdown(text, doc_path)
        elif chunk_strategy == ChunkStrategy.CODE:
            return self.chunk_code(text, doc_path)
        else:
            return self.chunk_recursive(text, doc_path)

    def chunk_file(
        self,
        file_path: Path,
        strategy: Optional[ChunkStrategy] = None,
    ) -> List[Chunk]:
        """Read and chunk a file.

        Args:
            file_path: Path to file
            strategy: Optional chunking strategy override

        Returns:
            List of chunks

        Raises:
            OSError: If file cannot be read
        """
        # Read file
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

        # Chunk with relative path as doc_path
        return self.chunk_text(text, str(file_path), strategy=strategy)
