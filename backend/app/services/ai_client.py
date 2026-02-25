"""
Centralized AI client for all Gemini calls.

ALL AI interactions go through this module. This gives us one place for:
- Rate limiting (future)
- Response caching (future)
- Cost tracking (future)
- Retry logic
- Structured logging
- Model swapping

Usage:
    from app.services.ai_client import get_ai_client
    ai = get_ai_client()

    # JSON response (worksheets, flashcards, revision, etc.)
    result = ai.generate_json(prompt, system=system_prompt, temperature=0.5)

    # Text response (Ask Skolar chat)
    text = ai.generate_text(prompt, system=system_prompt)

    # Vision response (grading, textbook scan)
    result = ai.generate_with_images(images, prompt, temperature=0.3)

    # Chat with history (Ask Skolar multi-turn)
    text = ai.generate_chat(messages, system=system_prompt)
"""

from __future__ import annotations

import json
import time
from typing import Any

import sentry_sdk
import structlog

from app.core.config import get_settings

logger = structlog.get_logger("skolar.ai")

# Default model
DEFAULT_MODEL = "gemini-2.5-flash"


def _types():
    """Lazy import google.genai.types to avoid import errors in environments without the SDK."""
    from google.genai import types as _t

    return _t


class AIClient:
    """Single Gemini client for the entire Skolar app."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        from google import genai as _genai

        self.client = _genai.Client(api_key=api_key)
        self.model = model
        self._call_count = 0
        self._total_latency_ms = 0
        logger.info("AIClient initialized", model=model)

    # -- JSON generation (worksheets, flashcards, revision, etc.) -----------

    def generate_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        retries: int = 1,
        thinking_budget: int = 0,
    ) -> dict[str, Any]:
        """Generate a JSON response from Gemini.

        Parses the response, strips markdown fences, retries on parse failure.
        """
        last_error: Exception | None = None
        for attempt in range(1 + retries):
            start = time.perf_counter()
            try:
                with sentry_sdk.start_span(op="ai.generate", description="generate_json") as span:
                    span.set_data("temperature", temperature)
                    span.set_data("max_tokens", max_tokens)
                    span.set_data("thinking_budget", thinking_budget)
                    span.set_data("attempt", attempt + 1)

                    t = _types()
                    config = t.GenerateContentConfig(
                        system_instruction=system,
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                        response_mime_type="application/json",
                        thinking_config=t.ThinkingConfig(thinking_budget=thinking_budget),
                    )
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=config,
                    )
                    elapsed_ms = int((time.perf_counter() - start) * 1000)
                    self._track_call(elapsed_ms)

                    raw = response.text or ""
                    parsed = self._parse_json(raw)

                    span.set_data("latency_ms", elapsed_ms)
                    span.set_data("response_len", len(raw))

                    logger.info(
                        "generate_json OK",
                        attempt=attempt + 1,
                        latency_ms=elapsed_ms,
                        response_len=len(raw),
                    )
                    return parsed

            except json.JSONDecodeError as e:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                self._track_call(elapsed_ms)
                last_error = e
                logger.warning(
                    "generate_json parse failed, retrying",
                    attempt=attempt + 1,
                    error=str(e),
                )
            except Exception as e:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                self._track_call(elapsed_ms)
                last_error = e
                sentry_sdk.set_context(
                    "ai_call", {"method": "generate_json", "model": self.model, "attempt": attempt + 1}
                )
                sentry_sdk.capture_exception(e)
                logger.error(
                    "generate_json API error",
                    attempt=attempt + 1,
                    error=str(e),
                )

        raise ValueError(f"AI generation failed after {1 + retries} attempts: {last_error}")

    # -- Text generation (Ask Skolar, general text) -------------------------

    def generate_text(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.5,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a plain text response."""
        start = time.perf_counter()
        try:
            with sentry_sdk.start_span(op="ai.generate", description="generate_text") as span:
                span.set_data("temperature", temperature)
                span.set_data("max_tokens", max_tokens)
                config = _types().GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                self._track_call(elapsed_ms)
                text = response.text or ""
                span.set_data("latency_ms", elapsed_ms)
                span.set_data("response_len", len(text))
                logger.info("generate_text OK", latency_ms=elapsed_ms, response_len=len(text))
                return text

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self._track_call(elapsed_ms)
            sentry_sdk.set_context("ai_call", {"method": "generate_text", "model": self.model})
            sentry_sdk.capture_exception(e)
            logger.error("generate_text failed", error=str(e))
            raise ValueError(f"AI text generation failed: {e}")

    # -- Chat with history (Ask Skolar multi-turn) --------------------------

    def generate_chat(
        self,
        messages: list[dict],
        system: str | None = None,
        temperature: float = 0.5,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a response from a multi-turn conversation."""
        start = time.perf_counter()
        try:
            with sentry_sdk.start_span(op="ai.generate", description="generate_chat") as span:
                span.set_data("temperature", temperature)
                span.set_data("max_tokens", max_tokens)
                span.set_data("turns", len(messages))
                gemini_messages = []
                for msg in messages:
                    gemini_messages.append(
                        {
                            "role": msg["role"],
                            "parts": [{"text": msg["content"]}],
                        }
                    )
                config = _types().GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=gemini_messages,
                    config=config,
                )
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                self._track_call(elapsed_ms)
                text = response.text or ""
                span.set_data("latency_ms", elapsed_ms)
                logger.info("generate_chat OK", latency_ms=elapsed_ms, turns=len(messages))
                return text

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self._track_call(elapsed_ms)
            sentry_sdk.set_context("ai_call", {"method": "generate_chat", "model": self.model})
            sentry_sdk.capture_exception(e)
            logger.error("generate_chat failed", error=str(e))
            raise ValueError(f"AI chat generation failed: {e}")

    # -- Vision (grading photos, textbook scan) -----------------------------

    def generate_with_images(
        self,
        image_parts: list[dict],
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_json: bool = True,
    ) -> dict[str, Any] | str:
        """Generate from image(s) + text prompt.

        image_parts: list of {"inline_data": {"mime_type": "image/jpeg", "data": base64_string}}
        """
        start = time.perf_counter()
        try:
            with sentry_sdk.start_span(op="ai.generate", description="generate_with_images") as span:
                span.set_data("temperature", temperature)
                span.set_data("max_tokens", max_tokens)
                span.set_data("num_images", len(image_parts))
                parts = image_parts + [{"text": prompt}]
                config_kwargs: dict[str, Any] = {
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                }
                if system:
                    config_kwargs["system_instruction"] = system
                t = _types()
                if response_json:
                    config_kwargs["response_mime_type"] = "application/json"
                    config_kwargs["thinking_config"] = t.ThinkingConfig(thinking_budget=0)
                config = t.GenerateContentConfig(**config_kwargs)
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[{"parts": parts}],
                    config=config,
                )
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                self._track_call(elapsed_ms)
                raw = response.text or ""
                span.set_data("latency_ms", elapsed_ms)
                span.set_data("response_len", len(raw))
                logger.info("generate_with_images OK", latency_ms=elapsed_ms, num_images=len(image_parts))
                if response_json:
                    return self._parse_json(raw)
                return raw

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self._track_call(elapsed_ms)
            sentry_sdk.set_context("ai_call", {"method": "generate_with_images", "model": self.model})
            sentry_sdk.capture_exception(e)
            logger.error("generate_with_images failed", error=str(e))
            raise ValueError(f"AI vision generation failed: {e}")

    # -- Vision with typed Parts (syllabus image OCR) -----------------------

    def generate_with_typed_parts(
        self,
        parts: list,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """Generate from a list of google.genai.types.Part objects.

        Used by syllabus image OCR which builds Part.from_text / Part.from_bytes.
        Returns raw text (not JSON-parsed).
        """
        start = time.perf_counter()
        try:
            with sentry_sdk.start_span(op="ai.generate", description="generate_with_typed_parts") as span:
                span.set_data("temperature", temperature)
                span.set_data("max_tokens", max_tokens)
                config = _types().GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=parts,
                    config=config,
                )
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                self._track_call(elapsed_ms)
                text = response.text or ""
                span.set_data("latency_ms", elapsed_ms)
                span.set_data("response_len", len(text))
                logger.info("generate_with_typed_parts OK", latency_ms=elapsed_ms)
                return text

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self._track_call(elapsed_ms)
            sentry_sdk.set_context("ai_call", {"method": "generate_with_typed_parts", "model": self.model})
            sentry_sdk.capture_exception(e)
            logger.error("generate_with_typed_parts failed", error=str(e))
            raise ValueError(f"AI typed parts generation failed: {e}")

    # -- Adapter for worksheet_generator (backward compat) ------------------

    def generate_openai_style(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        thinking_budget: int = 0,
    ) -> str:
        """Backward-compatible method that mimics the old OpenAI-style interface.

        Used by worksheet_generator.py's call_gemini() function.

        messages: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        Returns: raw text response
        """
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        user_parts = [m["content"] for m in messages if m.get("role") != "system"]

        system_instruction = "\n\n".join(system_parts) or None
        user_prompt = "\n\n".join(user_parts)

        start = time.perf_counter()
        try:
            with sentry_sdk.start_span(op="ai.generate", description="generate_openai_style") as span:
                span.set_data("temperature", temperature)
                span.set_data("max_tokens", max_tokens)
                span.set_data("thinking_budget", thinking_budget)
                t = _types()
                config = t.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                    thinking_config=t.ThinkingConfig(thinking_budget=thinking_budget),
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=config,
                )
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                self._track_call(elapsed_ms)
                text = response.text or ""
                span.set_data("latency_ms", elapsed_ms)
                span.set_data("response_len", len(text))
                logger.info("generate_openai_style OK", latency_ms=elapsed_ms, response_len=len(text))
                return text

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self._track_call(elapsed_ms)
            sentry_sdk.set_context("ai_call", {"method": "generate_openai_style", "model": self.model})
            sentry_sdk.capture_exception(e)
            logger.error("generate_openai_style failed", error=str(e))
            raise

    # -- Internal helpers ---------------------------------------------------

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """Parse JSON from AI response, stripping markdown fences."""
        text = raw.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())

    def _track_call(self, elapsed_ms: int) -> None:
        """Track call count and latency for monitoring."""
        self._call_count += 1
        self._total_latency_ms += elapsed_ms

    @property
    def stats(self) -> dict:
        """Get usage stats."""
        return {
            "total_calls": self._call_count,
            "total_latency_ms": self._total_latency_ms,
            "avg_latency_ms": (self._total_latency_ms // self._call_count if self._call_count else 0),
        }


# -- OpenAI-compat adapter for worksheet_generator -------------------------


class OpenAICompatAdapter:
    """Makes AIClient compatible with code that calls client.chat.completions.create().

    Drop-in replacement for the old GeminiClientAdapter in deps.py.
    """

    def __init__(self, ai_client: AIClient):
        self._ai = ai_client
        self.chat = self._Chat(ai_client)

    class _Chat:
        def __init__(self, ai_client: AIClient):
            self.completions = self._Completions(ai_client)

        class _Completions:
            def __init__(self, ai_client: AIClient):
                self._ai = ai_client

            def create(self, model=None, messages=None, temperature=0.7, max_tokens=None, thinking_budget=0, **kwargs):
                text = self._ai.generate_openai_style(
                    messages=messages or [],
                    temperature=temperature,
                    max_tokens=max_tokens or 4096,
                    thinking_budget=thinking_budget,
                )

                class _Msg:
                    def __init__(self, content):
                        self.content = content

                class _Choice:
                    def __init__(self, content):
                        self.message = _Msg(content)

                class _Resp:
                    def __init__(self, text):
                        self.choices = [_Choice(text)]

                return _Resp(text)


# -- Singletons ------------------------------------------------------------

_ai_client: AIClient | None = None


def get_ai_client() -> AIClient:
    """Get the singleton AI client instance."""
    global _ai_client
    if _ai_client is None:
        settings = get_settings()
        _ai_client = AIClient(api_key=settings.gemini_api_key)
    return _ai_client


def get_openai_compat_client() -> OpenAICompatAdapter:
    """Get an OpenAI-compatible adapter wrapping the centralized AI client."""
    return OpenAICompatAdapter(get_ai_client())
