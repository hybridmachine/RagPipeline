"""OpenAI client for LLM answer generation.

Handles answer generation using OpenAI's chat completion API with RAG context.
"""

import asyncio
from dataclasses import dataclass
from typing import List, Optional

import httpx

from rag_core.config import Config
from rag_core.retrieval.query_engine import Citation


class OpenAIError(Exception):
    """Base exception for OpenAI client errors."""

    pass


@dataclass
class Answer:
    """Represents an LLM-generated answer with citations."""

    text: str
    citations: List[Citation]
    model: str
    total_tokens: Optional[int] = None


class OpenAIClient:
    """Client for OpenAI chat completion API.

    Handles:
    - Answer generation from query + context
    - Citation preservation
    - Retry logic and error handling
    """

    def __init__(self, config: Config) -> None:
        """Initialize OpenAI client.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.api_key = config.openai_api_key
        self.base_url = config.openai_base_url or "https://api.openai.com/v1"
        self.model = config.openai_model
        self._client: Optional[httpx.AsyncClient] = None

        if not self.api_key:
            raise OpenAIError(
                "OpenAI API key not configured. Set OPENAI_API_KEY environment variable."
            )

    async def __aenter__(self) -> "OpenAIClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Initialize HTTP client."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.request_timeout_seconds),
            headers=headers,
            base_url=self.base_url,
        )

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get active client or raise error."""
        if self._client is None:
            raise OpenAIError(
                "Client not connected. Use async context manager or call connect()."
            )
        return self._client

    def _build_system_prompt(self) -> str:
        """Build system prompt for RAG answer generation."""
        return """You are a helpful AI assistant that answers questions based on provided context.

IMPORTANT INSTRUCTIONS:
1. Answer the question using ONLY the information provided in the context below
2. If the context doesn't contain enough information to answer the question, say so clearly
3. Include citation numbers [1], [2], etc. when referencing information from the context
4. Be concise but thorough in your answers
5. Do not make up information or use knowledge outside the provided context"""

    def _build_user_prompt(self, query: str, context: str) -> str:
        """Build user prompt with query and context.

        Args:
            query: User's question
            context: Retrieved context with citation markers

        Returns:
            Formatted user prompt
        """
        return f"""Context:
{context}

Question: {query}

Please answer the question based on the context above. Include citation numbers [1], [2], etc. when referencing specific information."""

    async def generate_answer(
        self,
        query: str,
        context: str,
        citations: List[Citation],
        max_retries: int = 3,
    ) -> Answer:
        """Generate an answer using OpenAI chat completion.

        Args:
            query: The user's question
            context: Retrieved context with citation markers
            citations: List of citations for the context
            max_retries: Maximum number of retry attempts

        Returns:
            Answer object with generated text and citations

        Raises:
            OpenAIError: If answer generation fails
        """
        client = self._get_client()

        # Build messages
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": self._build_user_prompt(query, context)},
        ]

        # Prepare request
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1000,
        }

        # Retry loop with exponential backoff
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    "/chat/completions",
                    json=payload,
                )
                response.raise_for_status()

                result = response.json()

                # Extract answer text
                if (
                    "choices" not in result
                    or len(result["choices"]) == 0
                    or "message" not in result["choices"][0]
                ):
                    raise OpenAIError(f"Unexpected response format: {result}")

                answer_text = result["choices"][0]["message"]["content"]

                # Extract token usage if available
                total_tokens = None
                if "usage" in result:
                    total_tokens = result["usage"].get("total_tokens")

                return Answer(
                    text=answer_text,
                    citations=citations,
                    model=self.model,
                    total_tokens=total_tokens,
                )

            except httpx.HTTPStatusError as e:
                last_error = e
                # Check if it's a rate limit or server error (retryable)
                if e.response.status_code in (429, 500, 502, 503, 504):
                    if attempt < max_retries - 1:
                        # Exponential backoff: 1s, 2s, 4s
                        wait_time = 2**attempt
                        await asyncio.sleep(wait_time)
                        continue
                # Client errors (4xx except 429) are not retryable
                raise OpenAIError(
                    f"HTTP {e.response.status_code}: {e.response.text}"
                ) from e

            except httpx.RequestError as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
                    continue
                raise OpenAIError(f"Request failed: {e}") from e

            except Exception as e:
                raise OpenAIError(f"Unexpected error: {e}") from e

        # If we exhausted all retries
        raise OpenAIError(
            f"Failed after {max_retries} attempts. Last error: {last_error}"
        )
