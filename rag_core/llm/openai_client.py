"""LLM client for answer generation.

Supports:
- OpenAI Chat Completion API
- HuggingFace Inference API (Text Generation Inference)
- OpenAI-compatible endpoints (LocalAI, vLLM, etc.)

Auto-detects endpoint format and handles RAG context with citations.
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
    """Client for LLM answer generation (OpenAI, HuggingFace, or compatible).

    Handles:
    - Answer generation from query + context
    - Citation preservation
    - Retry logic and error handling
    - Auto-detects OpenAI vs HuggingFace format

    Supports:
    - OpenAI API (/v1/chat/completions)
    - HuggingFace Inference API (serverless and Inference Endpoints)
    - OpenAI-compatible servers (LocalAI, vLLM, etc.)
    """

    def __init__(self, config: Config) -> None:
        """Initialize LLM client.

        Args:
            config: Configuration instance
        """
        self.config = config

        # Use new config variables with fallback to legacy ones
        self.api_token = config.llm_api_token or config.openai_api_key
        self.endpoint_url = config.llm_endpoint_url or config.openai_base_url
        self.model_id = config.llm_model_id or config.openai_model

        # Default to OpenAI if no endpoint specified
        if not self.endpoint_url:
            self.endpoint_url = "https://api.openai.com/v1"

        # Determine endpoint type
        # HuggingFace Inference Endpoints often use OpenAI-compatible format
        self.is_huggingface = self._is_huggingface_endpoint(self.endpoint_url)
        # Use OpenAI format if: explicit /v1/ in URL, or Inference Endpoints (which support OpenAI format)
        self.is_openai_compatible = (
            "/v1/" in self.endpoint_url
            or ".endpoints.huggingface.cloud" in self.endpoint_url
            or not self.is_huggingface
        )

        self._client: Optional[httpx.AsyncClient] = None

        if not self.api_token:
            raise OpenAIError(
                "LLM API token not configured. Set LLM_API_TOKEN, HF_API_TOKEN, or OPENAI_API_KEY environment variable."
            )

    def _is_huggingface_endpoint(self, url: str) -> bool:
        """Check if endpoint is HuggingFace Inference API.

        Args:
            url: Endpoint URL

        Returns:
            True if HuggingFace endpoint
        """
        hf_indicators = [
            "huggingface.co",
            "api-inference.huggingface.co",
            ".endpoints.huggingface.cloud",
        ]
        return any(indicator in url for indicator in hf_indicators)

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
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        # Determine base URL
        if self.is_openai_compatible:
            # For OpenAI-compatible endpoints, ensure we have /v1 in the base URL
            if ".endpoints.huggingface.cloud" in self.endpoint_url and not self.endpoint_url.endswith("/v1"):
                base_url = f"{self.endpoint_url}/v1"
            else:
                base_url = self.endpoint_url

            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.request_timeout_seconds),
                headers=headers,
                base_url=base_url,
            )
        else:
            # For pure HuggingFace Inference API, no base_url
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.request_timeout_seconds),
                headers=headers,
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
        """Generate an answer using LLM chat completion.

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

        # Build request based on endpoint type
        if self.is_openai_compatible:
            # OpenAI-compatible format: messages array
            messages = [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": self._build_user_prompt(query, context)},
            ]

            payload = {
                "model": self.model_id,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1000,
            }
            url = "/chat/completions"
        else:
            # HuggingFace Inference API format: single prompt string
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(query, context)
            full_prompt = f"{system_prompt}\n\n{user_prompt}"

            payload = {
                "inputs": full_prompt,
                "parameters": {
                    "temperature": 0.7,
                    "max_new_tokens": 1000,
                    "return_full_text": False,
                },
            }
            url = self.endpoint_url

        # Retry loop with exponential backoff
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()

                result = response.json()

                # Parse response based on endpoint type
                if self.is_openai_compatible:
                    # OpenAI format: {"choices": [{"message": {"content": "..."}}]}
                    if (
                        "choices" not in result
                        or len(result["choices"]) == 0
                        or "message" not in result["choices"][0]
                    ):
                        raise OpenAIError(f"Unexpected OpenAI response format: {result}")

                    answer_text = result["choices"][0]["message"]["content"]
                else:
                    # HuggingFace Inference API format: [{"generated_text": "..."}] or {"generated_text": "..."}
                    if isinstance(result, list) and len(result) > 0:
                        answer_text = result[0].get("generated_text", "")
                    elif isinstance(result, dict):
                        answer_text = result.get("generated_text", "")
                    else:
                        raise OpenAIError(f"Unexpected HuggingFace response format: {result}")

                # Extract token usage if available
                total_tokens = None
                if "usage" in result:
                    total_tokens = result["usage"].get("total_tokens")

                return Answer(
                    text=answer_text,
                    citations=citations,
                    model=self.model_id,
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
