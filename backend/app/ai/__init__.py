"""AI assist layer for PartFolder 3D — Phase 8.

Provides optional AI-powered tag suggestions, description cleanup, and
web-scrape summarization. All features are additive and best-effort:
- Manual-only must always work with zero AI configured.
- AI errors/timeouts/malformed output never block item creation or import commit.
- Keys are decrypted only at call time and never logged.
- Network calls are mockable via module-level callables in client.py.

Supported providers: Claude (anthropic SDK), OpenAI + Ollama (openai SDK).
"""

from .client import (
    AiTagResult,
    AiTextResult,
    cleanup_description,
    get_enabled_provider,
    suggest_tags,
    summarize_scrape,
)

__all__ = [
    "get_enabled_provider",
    "suggest_tags",
    "cleanup_description",
    "summarize_scrape",
    "AiTagResult",
    "AiTextResult",
]
