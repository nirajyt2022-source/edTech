import logging
import os
from functools import lru_cache
from supabase import create_client, Client
from openai import OpenAI
from app.core.config import get_settings

_prompt_logger = logging.getLogger("practicecraft.gemini_prompts")


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)


@lru_cache
def get_openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.openai_api_key)


# ── Gemini adapter — mimics the OpenAI client interface ──────────────────────
# slot_engine.py calls client.chat.completions.create(...) — this adapter
# intercepts those calls and routes to Gemini, so slot_engine.py is untouched.

class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, text: str):
        self.choices = [_FakeChoice(text)]


class _FakeCompletions:
    def create(
        self,
        model=None,
        messages=None,
        temperature=0.7,
        max_tokens=None,
        **kwargs,
    ):
        from google import genai
        from google.genai import types

        system_parts = [
            m["content"] for m in (messages or []) if m.get("role") == "system"
        ]
        user_parts = [
            m["content"] for m in (messages or []) if m.get("role") != "system"
        ]

        system_instruction = "\n\n".join(system_parts) or None
        user_prompt = "\n\n".join(user_parts)

        if os.environ.get("DEBUG_LLM_PROMPTS", "").lower() in ("1", "true"):
            _prompt_logger.warning(
                "\n\n%s\n"
                "── SYSTEM ──────────────────────────────────────────────\n%s\n"
                "── USER ────────────────────────────────────────────────\n%s\n"
                "── CONFIG ──────────────────────────────────────────────\n"
                "  model=gemini-2.5-flash  temp=%s  max_tokens=%s\n"
                "%s",
                "=" * 60,
                system_instruction or "(none)",
                user_prompt,
                temperature,
                max_tokens or 2048,
                "=" * 60,
            )

        client = genai.Client(api_key=_gemini_api_key)

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_tokens or 2048,
            response_mime_type="application/json",
            # Disable thinking — prevents preamble text before JSON output
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=config,
        )
        return _FakeResponse(response.text or "")


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class GeminiClientAdapter:
    def __init__(self, api_key: str):
        global _gemini_api_key
        _gemini_api_key = api_key
        self.chat = _FakeChat()


# Module-level key storage (set once when GeminiClientAdapter is constructed)
_gemini_api_key: str = ""


def get_llm_client(settings=None):
    """Return the active LLM client based on llm_provider setting."""
    if settings is None:
        settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAI(api_key=settings.openai_api_key)
    return GeminiClientAdapter(api_key=settings.gemini_api_key)
