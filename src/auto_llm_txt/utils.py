"""Shared helpers for LLM-backed nodes."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from auto_llm_txt.config import settings


def get_llm() -> BaseChatModel:
    """Return a provider-agnostic chat model via OpenRouter.

    Uses langchain-openrouter. Requires OPENROUTER_API_KEY env var for real calls.
    Tests should mock this function (or inject a FakeListChatModel) instead.
    """
    try:
        from langchain_openrouter import ChatOpenRouter
    except ImportError as e:
        raise ImportError(
            "langchain-openrouter is required. Install with `uv sync`."
        ) from e

    if not settings.openrouter_api_key:
        # Still construct — langchain will raise on invoke if key missing,
        # but this lets graph compilation succeed without a key.
        pass

    return ChatOpenRouter(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=settings.openrouter_api_key or None,
    )


def get_structured_llm(schema, llm: BaseChatModel | None = None) -> BaseChatModel:
    """Return llm with structured output bound to `schema` (pydantic model)."""
    llm = llm or get_llm()
    return llm.with_structured_output(schema)
