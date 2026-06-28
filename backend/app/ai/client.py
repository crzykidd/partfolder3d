"""AI client layer — provider dispatch for Claude, OpenAI, and Ollama.

Design
------
* All network calls are routed through injectable callables (_anthropic_caller,
  _openai_caller) that default to None → the real SDK is used. Tests monkeypatch
  them to avoid hitting real endpoints.
* Every public function is **best-effort**: on any error (network, timeout,
  malformed JSON, bad key) it returns a sentinel "no suggestion" result.
  AI failure **never** raises to the caller and never blocks the manual path.
* API keys are decrypted from Fernet ciphertext only at call time; never logged.

Provider dispatch
-----------------
* Claude  → ``anthropic`` SDK (``client.messages.create``).
            Default model: ``claude-opus-4-8`` (exact string, no date suffix).
            Do NOT send temperature/top_p/top_k or thinking block — they 400 on
            claude-opus-4-8.  Thinking is off by default.
* OpenAI  → ``openai`` SDK (``chat.completions.create``).
* Ollama  → ``openai`` SDK with ``base_url`` = the configured endpoint (Ollama
            exposes an OpenAI-compatible REST API).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..crypto import decrypt
from ..models.ai_provider import AiProvider, AiProviderType

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mockable callers (set to None → use real SDK; monkeypatch in tests)
# ---------------------------------------------------------------------------

# Signature: (api_key, model, system, user_msg, max_tokens) -> str | None
_anthropic_caller = None

# Signature: (api_key, base_url, model, system, user_msg, max_tokens) -> str | None
_openai_caller = None

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

MAX_NEW_SUGGESTIONS = 5  # hard cap on genuinely new tag suggestions


@dataclass
class AiTagResult:
    """Result of an AI tag-suggestion call.

    canonical       — matched names from the existing canonical tag list
    new_suggestions — genuinely new tags (≤ MAX_NEW_SUGGESTIONS); go to pending
    error           — non-None when the call failed (never re-raised to caller)
    """

    canonical: list[str] = field(default_factory=list)
    new_suggestions: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class AiTextResult:
    """Result of a description-cleanup or scrape-summarization call."""

    text: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Provider lookup
# ---------------------------------------------------------------------------


async def get_enabled_provider(db: AsyncSession) -> AiProvider | None:
    """Return the first enabled AiProvider row, or None if none configured."""
    result = await db.execute(
        select(AiProvider).where(AiProvider.enabled.is_(True)).limit(1)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "canonical": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Tags from the provided existing_tags list that match the content "
                "(exact names only)."
            ),
        },
        "new_suggestions": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                f"Genuinely new tags NOT in existing_tags. "
                f"Limit to {MAX_NEW_SUGGESTIONS} or fewer."
            ),
        },
    },
    "required": ["canonical", "new_suggestions"],
    "additionalProperties": False,
}


def _build_tag_prompt(
    title: str,
    description: str | None,
    scraped_text: str | None,
    filenames: list[str],
    existing_tags: list[str],
) -> tuple[str, str]:
    rule1 = "1. 'canonical' must only contain tags verbatim from existing_tags list."
    rule2 = (
        f"2. 'new_suggestions' must be genuinely new tags NOT in existing_tags "
        f"(≤{MAX_NEW_SUGGESTIONS})."
    )
    system = (
        "You are a 3D printing asset librarian. Given a design's metadata, suggest relevant tags.\n"
        "Return ONLY a single valid JSON object matching this schema:\n"
        f"{json.dumps(_TAG_SCHEMA, indent=2)}\n\n"
        "Rules:\n"
        f"{rule1}\n"
        f"{rule2}\n"
        "3. Prefer existing canonical tags over suggesting new ones.\n"
        "4. Output only the JSON object — no markdown fences, no prose."
    )
    parts = [f"Title: {title}"]
    if description:
        parts.append(f"Description: {description[:500]}")
    if scraped_text:
        parts.append(f"Scraped content: {scraped_text[:1000]}")
    if filenames:
        parts.append(f"Files: {', '.join(filenames[:20])}")
    parts.append(f"existing_tags: {json.dumps(existing_tags[:200])}")
    return system, "\n".join(parts)


def _build_cleanup_prompt(description: str, title: str) -> tuple[str, str]:
    system = (
        "You are a 3D printing asset librarian. Clean up the description below for a 3D design. "
        "Fix grammar, spelling, and formatting. Keep it concise (2–6 sentences). "
        "Return ONLY the cleaned description text — no JSON, no explanation."
    )
    user = f"Design title: {title}\n\nDescription to clean up:\n{description}"
    return system, user


def _build_summarize_prompt(scraped_text: str, title: str) -> tuple[str, str]:
    system = (
        "You are a 3D printing asset librarian. Summarize the following scraped web content "
        "into a concise description (2–5 sentences) suitable for a 3D design library. "
        "Focus on what the design is, its purpose, and key features. "
        "Return ONLY the summary text — no JSON, no explanation."
    )
    user = f"Design title: {title}\n\nScraped content:\n{scraped_text[:3000]}"
    return system, user


# ---------------------------------------------------------------------------
# Real SDK callers (used when injectable caller is None)
# ---------------------------------------------------------------------------


def _call_anthropic_real(
    api_key: str,
    model: str,
    system: str,
    user_msg: str,
    max_tokens: int,
) -> str | None:
    """Invoke the Anthropic SDK.  Returns response text or None on error."""
    try:
        import anthropic  # noqa: PLC0415

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        if response.content and hasattr(response.content[0], "text"):
            return str(response.content[0].text)
        return None
    except Exception:
        log.exception("Anthropic API call failed")
        return None


def _call_openai_real(
    api_key: str,
    base_url: str | None,
    model: str,
    system: str,
    user_msg: str,
    max_tokens: int,
) -> str | None:
    """Invoke the OpenAI SDK (also used for Ollama via base_url).  Returns text or None."""
    try:
        import openai  # noqa: PLC0415

        kwargs: dict[str, object] = {"api_key": api_key or "ollama"}
        if base_url:
            kwargs["base_url"] = base_url
        client = openai.OpenAI(**kwargs)
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
        )
        if response.choices:
            return response.choices[0].message.content
        return None
    except Exception:
        log.exception("OpenAI/Ollama API call failed")
        return None


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_DEFAULT_CLAUDE_MODEL = "claude-opus-4-8"
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def _dispatch(
    provider: AiProvider,
    system: str,
    user_msg: str,
    max_tokens: int = 1024,
) -> str | None:
    """Dispatch a call to the configured provider. Returns text or None."""
    # Decrypt key at call time only; never stored in cleartext.
    api_key = ""
    if provider.api_key_encrypted:
        try:
            api_key = decrypt(provider.api_key_encrypted)
        except Exception:
            log.exception("Failed to decrypt AI provider key; aborting AI call")
            return None

    model = provider.model

    if provider.provider == AiProviderType.claude:
        if not model:
            model = _DEFAULT_CLAUDE_MODEL
        caller = _anthropic_caller
        if caller is not None:
            return caller(api_key, model, system, user_msg, max_tokens)  # type: ignore[operator]
        return _call_anthropic_real(api_key, model, system, user_msg, max_tokens)

    # OpenAI or Ollama — both use the openai SDK; Ollama sets base_url.
    if not model:
        model = _DEFAULT_OPENAI_MODEL
    base_url = provider.endpoint  # None for OpenAI; endpoint for Ollama
    caller = _openai_caller
    if caller is not None:
        return caller(api_key, base_url, model, system, user_msg, max_tokens)  # type: ignore[operator]
    return _call_openai_real(api_key, base_url, model, system, user_msg, max_tokens)


# ---------------------------------------------------------------------------
# Public AI feature functions
# ---------------------------------------------------------------------------


def suggest_tags(
    provider: AiProvider,
    title: str,
    description: str | None,
    scraped_text: str | None,
    filenames: list[str],
    existing_tags: list[str],
) -> AiTagResult:
    """Suggest tags for an item using AI.

    Returns canonical matches (from *existing_tags*) and a small number of
    genuinely new suggestions (≤ MAX_NEW_SUGGESTIONS).

    On any error this returns an AiTagResult with empty lists and an error
    message — it **never** raises.  AI failure does not block the manual path.
    """
    system, user_msg = _build_tag_prompt(
        title, description, scraped_text, filenames, existing_tags
    )
    try:
        raw = _dispatch(provider, system, user_msg, max_tokens=512)
        if raw is None:
            return AiTagResult(error="No response from AI provider")

        # Strip markdown code fences if the model wraps its output.
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            # Drop first line (```json / ```) and last line (```)
            inner = lines[1:-1] if len(lines) > 2 else lines
            text = "\n".join(inner)

        data: dict = json.loads(text)
        canonical: list[str] = [
            t for t in (data.get("canonical") or []) if isinstance(t, str)
        ]
        new_suggestions: list[str] = [
            t for t in (data.get("new_suggestions") or []) if isinstance(t, str)
        ]

        # Enforce hard caps and safety filters.
        new_suggestions = new_suggestions[:MAX_NEW_SUGGESTIONS]
        existing_set = set(existing_tags)
        canonical = [t for t in canonical if t in existing_set]

        return AiTagResult(canonical=canonical, new_suggestions=new_suggestions)

    except Exception as exc:
        log.warning("AI tag suggestion failed: %s", exc)
        return AiTagResult(error=str(exc))


def cleanup_description(
    provider: AiProvider,
    description: str,
    title: str,
) -> AiTextResult:
    """Return an AI-cleaned version of *description*.

    The result is a **suggestion only** — the caller must present it to the user
    for review before applying it. Never auto-overwrites silently.

    Returns AiTextResult with ``text=None`` and an error message on failure.
    """
    if not description or not description.strip():
        return AiTextResult(error="Empty description provided")

    system, user_msg = _build_cleanup_prompt(description, title)
    try:
        raw = _dispatch(provider, system, user_msg, max_tokens=1024)
        if raw is None:
            return AiTextResult(error="No response from AI provider")
        return AiTextResult(text=raw.strip())
    except Exception as exc:
        log.warning("AI description cleanup failed: %s", exc)
        return AiTextResult(error=str(exc))


def summarize_scrape(
    provider: AiProvider,
    scraped_text: str,
    title: str,
) -> AiTextResult:
    """Summarize *scraped_text* into a short description draft.

    The result is a **draft** — the caller must present it to the user.
    Never auto-applies. Returns AiTextResult with error on failure.
    """
    if not scraped_text or not scraped_text.strip():
        return AiTextResult(error="No scraped content to summarize")

    system, user_msg = _build_summarize_prompt(scraped_text, title)
    try:
        raw = _dispatch(provider, system, user_msg, max_tokens=512)
        if raw is None:
            return AiTextResult(error="No response from AI provider")
        return AiTextResult(text=raw.strip())
    except Exception as exc:
        log.warning("AI scrape summarization failed: %s", exc)
        return AiTextResult(error=str(exc))
