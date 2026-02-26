"""
Centralized AI client for all Gemini calls.

ALL AI interactions go through this module. This gives us one place for:
- LLMOps metrics (latency, tokens, cost, cache hit rate, retry/error rates)
- Retry logic
- Structured logging
- Model swapping
- Prompt versioning (via caller-supplied prompt_version tag)

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

import hashlib
import json
import time
from collections import defaultdict
from typing import Any

import sentry_sdk
import structlog

from app.core.config import get_settings

logger = structlog.get_logger("skolar.ai")

# Default model
DEFAULT_MODEL = "gemini-2.5-flash"

# In-memory cache for Gemini CachedContent objects (keyed by system prompt hash)
_cached_contents: dict[str, Any] = {}
_CACHE_TTL_MINUTES = 60

# ── Token estimation ──────────────────────────────────────────────────────────
# Gemini uses ~4 chars per token (similar to GPT). This is an approximation
# used for budget guarding and cost estimation — not billing-grade.
_CHARS_PER_TOKEN = 4

# Gemini 2.5 Flash pricing (per 1M tokens, as of 2026-02)
_INPUT_COST_PER_M = 0.15  # $0.15 per 1M input tokens
_OUTPUT_COST_PER_M = 0.60  # $0.60 per 1M output tokens
_CACHED_INPUT_COST_PER_M = 0.04  # $0.04 per 1M cached input tokens

# Context window limit (Gemini 2.5 Flash)
_MAX_CONTEXT_TOKENS = 1_000_000


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length. ~4 chars per token for Gemini."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def estimate_cost(input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    """Estimate cost in USD for a single LLM call."""
    uncached_input = max(0, input_tokens - cached_tokens)
    return (
        uncached_input * _INPUT_COST_PER_M / 1_000_000
        + cached_tokens * _CACHED_INPUT_COST_PER_M / 1_000_000
        + output_tokens * _OUTPUT_COST_PER_M / 1_000_000
    )


class LLMMetrics:
    """Thread-safe LLMOps metrics collector.

    Tracks per-method and aggregate stats: calls, latency, tokens, cost,
    cache hits, retries, errors.
    """

    def __init__(self):
        self._calls: dict[str, int] = defaultdict(int)
        self._errors: dict[str, int] = defaultdict(int)
        self._retries: dict[str, int] = defaultdict(int)
        self._latency_ms: dict[str, int] = defaultdict(int)
        self._input_tokens: dict[str, int] = defaultdict(int)
        self._output_tokens: dict[str, int] = defaultdict(int)
        self._cached_tokens: dict[str, int] = defaultdict(int)
        self._cost_usd: dict[str, float] = defaultdict(float)
        self._cache_hits = 0
        self._cache_misses = 0

    def record_call(
        self,
        method: str,
        latency_ms: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        is_error: bool = False,
        is_retry: bool = False,
    ) -> None:
        self._calls[method] += 1
        self._latency_ms[method] += latency_ms
        self._input_tokens[method] += input_tokens
        self._output_tokens[method] += output_tokens
        self._cached_tokens[method] += cached_tokens
        self._cost_usd[method] += estimate_cost(input_tokens, output_tokens, cached_tokens)
        if is_error:
            self._errors[method] += 1
        if is_retry:
            self._retries[method] += 1

    def record_cache_hit(self, hit: bool) -> None:
        if hit:
            self._cache_hits += 1
        else:
            self._cache_misses += 1

    def snapshot(self) -> dict[str, Any]:
        """Return a point-in-time snapshot of all metrics."""
        total_calls = sum(self._calls.values())
        total_latency = sum(self._latency_ms.values())
        total_errors = sum(self._errors.values())
        total_retries = sum(self._retries.values())
        total_input = sum(self._input_tokens.values())
        total_output = sum(self._output_tokens.values())
        total_cached = sum(self._cached_tokens.values())
        total_cost = sum(self._cost_usd.values())
        cache_total = self._cache_hits + self._cache_misses

        return {
            "total_calls": total_calls,
            "total_errors": total_errors,
            "total_retries": total_retries,
            "error_rate": round(total_errors / total_calls, 4) if total_calls else 0,
            "retry_rate": round(total_retries / total_calls, 4) if total_calls else 0,
            "avg_latency_ms": total_latency // total_calls if total_calls else 0,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cached_tokens": total_cached,
            "estimated_cost_usd": round(total_cost, 4),
            "cache_hit_rate": round(self._cache_hits / cache_total, 4) if cache_total else 0,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "by_method": {
                method: {
                    "calls": self._calls[method],
                    "errors": self._errors[method],
                    "retries": self._retries[method],
                    "avg_latency_ms": self._latency_ms[method] // self._calls[method] if self._calls[method] else 0,
                    "input_tokens": self._input_tokens[method],
                    "output_tokens": self._output_tokens[method],
                    "cost_usd": round(self._cost_usd[method], 4),
                }
                for method in sorted(self._calls.keys())
            },
        }


# Global metrics instance — shared across all AIClient instances
_metrics = LLMMetrics()


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
        self.metrics = _metrics
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
        input_tokens = estimate_tokens(prompt + (system or ""))

        last_error: Exception | None = None
        for attempt in range(1 + retries):
            is_retry = attempt > 0
            start = time.perf_counter()
            try:
                with sentry_sdk.start_span(op="ai.generate", description="generate_json") as span:
                    span.set_data("temperature", temperature)
                    span.set_data("max_tokens", max_tokens)
                    span.set_data("thinking_budget", thinking_budget)
                    span.set_data("attempt", attempt + 1)
                    span.set_data("input_tokens_est", input_tokens)

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

                    raw = response.text or ""
                    output_tokens = estimate_tokens(raw)
                    parsed = self._parse_json(raw)

                    self.metrics.record_call(
                        "generate_json",
                        elapsed_ms,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        is_retry=is_retry,
                    )
                    span.set_data("latency_ms", elapsed_ms)
                    span.set_data("response_len", len(raw))
                    span.set_data("output_tokens_est", output_tokens)

                    logger.info(
                        "generate_json OK",
                        attempt=attempt + 1,
                        latency_ms=elapsed_ms,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )
                    return parsed

            except json.JSONDecodeError as e:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                self.metrics.record_call(
                    "generate_json",
                    elapsed_ms,
                    input_tokens=input_tokens,
                    is_error=True,
                    is_retry=is_retry,
                )
                last_error = e
                logger.warning(
                    "generate_json parse failed, retrying",
                    attempt=attempt + 1,
                    error=str(e),
                )
            except Exception as e:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                self.metrics.record_call(
                    "generate_json",
                    elapsed_ms,
                    input_tokens=input_tokens,
                    is_error=True,
                    is_retry=is_retry,
                )
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
        input_tokens = estimate_tokens(prompt + (system or ""))
        start = time.perf_counter()
        try:
            with sentry_sdk.start_span(op="ai.generate", description="generate_text") as span:
                span.set_data("temperature", temperature)
                span.set_data("max_tokens", max_tokens)
                span.set_data("input_tokens_est", input_tokens)
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
                text = response.text or ""
                output_tokens = estimate_tokens(text)
                self.metrics.record_call(
                    "generate_text",
                    elapsed_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                span.set_data("latency_ms", elapsed_ms)
                span.set_data("response_len", len(text))
                logger.info(
                    "generate_text OK", latency_ms=elapsed_ms, input_tokens=input_tokens, output_tokens=output_tokens
                )
                return text

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self.metrics.record_call(
                "generate_text",
                elapsed_ms,
                input_tokens=input_tokens,
                is_error=True,
            )
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
        all_text = (system or "") + " ".join(m.get("content", "") for m in messages)
        input_tokens = estimate_tokens(all_text)

        # Guard context window — warn if approaching limit
        if input_tokens > _MAX_CONTEXT_TOKENS * 0.8:
            logger.warning(
                "context_window_warning",
                input_tokens=input_tokens,
                limit=_MAX_CONTEXT_TOKENS,
                turns=len(messages),
            )

        start = time.perf_counter()
        try:
            with sentry_sdk.start_span(op="ai.generate", description="generate_chat") as span:
                span.set_data("temperature", temperature)
                span.set_data("max_tokens", max_tokens)
                span.set_data("turns", len(messages))
                span.set_data("input_tokens_est", input_tokens)
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
                text = response.text or ""
                output_tokens = estimate_tokens(text)
                self.metrics.record_call(
                    "generate_chat",
                    elapsed_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                span.set_data("latency_ms", elapsed_ms)
                logger.info("generate_chat OK", latency_ms=elapsed_ms, turns=len(messages), input_tokens=input_tokens)
                return text

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self.metrics.record_call(
                "generate_chat",
                elapsed_ms,
                input_tokens=input_tokens,
                is_error=True,
            )
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
        # Estimate tokens: text + ~258 tokens per image (Gemini standard)
        text_tokens = estimate_tokens(prompt + (system or ""))
        image_tokens = len(image_parts) * 258
        input_tokens = text_tokens + image_tokens

        start = time.perf_counter()
        try:
            with sentry_sdk.start_span(op="ai.generate", description="generate_with_images") as span:
                span.set_data("temperature", temperature)
                span.set_data("max_tokens", max_tokens)
                span.set_data("num_images", len(image_parts))
                span.set_data("input_tokens_est", input_tokens)
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
                raw = response.text or ""
                output_tokens = estimate_tokens(raw)
                self.metrics.record_call(
                    "generate_with_images",
                    elapsed_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                span.set_data("latency_ms", elapsed_ms)
                span.set_data("response_len", len(raw))
                logger.info(
                    "generate_with_images OK",
                    latency_ms=elapsed_ms,
                    num_images=len(image_parts),
                    input_tokens=input_tokens,
                )
                if response_json:
                    return self._parse_json(raw)
                return raw

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self.metrics.record_call(
                "generate_with_images",
                elapsed_ms,
                input_tokens=input_tokens,
                is_error=True,
            )
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
                text = response.text or ""
                output_tokens = estimate_tokens(text)
                self.metrics.record_call(
                    "generate_with_typed_parts",
                    elapsed_ms,
                    output_tokens=output_tokens,
                )
                span.set_data("latency_ms", elapsed_ms)
                span.set_data("response_len", len(text))
                logger.info("generate_with_typed_parts OK", latency_ms=elapsed_ms, output_tokens=output_tokens)
                return text

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self.metrics.record_call(
                "generate_with_typed_parts",
                elapsed_ms,
                is_error=True,
            )
            sentry_sdk.set_context("ai_call", {"method": "generate_with_typed_parts", "model": self.model})
            sentry_sdk.capture_exception(e)
            logger.error("generate_with_typed_parts failed", error=str(e))
            raise ValueError(f"AI typed parts generation failed: {e}")

    # -- Gemini Context Caching -----------------------------------------------

    def _get_or_create_cache(self, system_instruction: str) -> Any:
        """Get or create a Gemini CachedContent for the given system prompt.

        Caches the system prompt server-side so repeated worksheet generations
        with the same system prompt (same problem_style + subject combo) reuse
        cached tokens instead of re-processing them. Saves 50-90% on input tokens.

        Falls back to None (no caching) on any error — the call proceeds normally.
        """
        cache_key = hashlib.sha256(system_instruction.encode()).hexdigest()

        # Check in-memory cache first
        cached = _cached_contents.get(cache_key)
        if cached:
            logger.debug("gemini_cache_hit", cache_key=cache_key[:8])
            return cached

        # Create server-side cached content
        try:
            from datetime import timedelta

            t = _types()
            cached_content = self.client.caches.create(
                model=self.model,
                config=t.CreateCachedContentConfig(
                    system_instruction=system_instruction,
                    ttl=timedelta(minutes=_CACHE_TTL_MINUTES),
                    display_name=f"skolar-sys-{cache_key[:8]}",
                ),
            )
            _cached_contents[cache_key] = cached_content
            logger.info("gemini_cache_created", cache_key=cache_key[:8])
            return cached_content
        except Exception as exc:
            # Caching is optional — fall back to uncached call
            logger.warning("gemini_cache_create_failed", error=str(exc))
            return None

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

        Uses Gemini context caching for the system prompt when available,
        reducing input token costs by 50-90% across repeated generations.
        """
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        user_parts = [m["content"] for m in messages if m.get("role") != "system"]

        system_instruction = "\n\n".join(system_parts) or None
        user_prompt = "\n\n".join(user_parts)

        system_tokens = estimate_tokens(system_instruction) if system_instruction else 0
        user_tokens = estimate_tokens(user_prompt)
        input_tokens = system_tokens + user_tokens

        start = time.perf_counter()
        try:
            with sentry_sdk.start_span(op="ai.generate", description="generate_openai_style") as span:
                span.set_data("temperature", temperature)
                span.set_data("max_tokens", max_tokens)
                span.set_data("thinking_budget", thinking_budget)
                span.set_data("input_tokens_est", input_tokens)
                t = _types()

                # Try to use cached system prompt
                cached_content = None
                cached_tokens = 0
                if system_instruction:
                    cached_content = self._get_or_create_cache(system_instruction)

                cache_hit = cached_content is not None
                self.metrics.record_cache_hit(cache_hit)

                if cached_content:
                    # Use cached content — system prompt is already server-side
                    span.set_data("cache_hit", True)
                    cached_tokens = system_tokens
                    config = t.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                        response_mime_type="application/json",
                        thinking_config=t.ThinkingConfig(thinking_budget=thinking_budget),
                    )
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=user_prompt,
                        config=config,
                        cached_content=cached_content.name,
                    )
                else:
                    # Fallback: uncached call with inline system instruction
                    span.set_data("cache_hit", False)
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
                text = response.text or ""
                output_tokens = estimate_tokens(text)
                self.metrics.record_call(
                    "generate_openai_style",
                    elapsed_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=cached_tokens,
                )
                span.set_data("latency_ms", elapsed_ms)
                span.set_data("response_len", len(text))
                span.set_data("cached_tokens", cached_tokens)
                logger.info(
                    "generate_openai_style OK",
                    latency_ms=elapsed_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_hit=cache_hit,
                )
                return text

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self.metrics.record_call(
                "generate_openai_style",
                elapsed_ms,
                input_tokens=input_tokens,
                is_error=True,
            )
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

    @property
    def stats(self) -> dict:
        """Get usage stats (backward-compatible + new metrics)."""
        snapshot = self.metrics.snapshot()
        return {
            "total_calls": snapshot["total_calls"],
            "total_latency_ms": sum(self.metrics._latency_ms.values()),
            "avg_latency_ms": snapshot["avg_latency_ms"],
            "total_input_tokens": snapshot["total_input_tokens"],
            "total_output_tokens": snapshot["total_output_tokens"],
            "estimated_cost_usd": snapshot["estimated_cost_usd"],
            "cache_hit_rate": snapshot["cache_hit_rate"],
            "error_rate": snapshot["error_rate"],
            "retry_rate": snapshot["retry_rate"],
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


def get_llm_metrics() -> dict[str, Any]:
    """Get the global LLM metrics snapshot. Used by /health/ai-metrics."""
    return _metrics.snapshot()
