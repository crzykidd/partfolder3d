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

Token usage
-----------
* Real callers return ``AiCallResult`` (text + token counts).
* The injectable test callers may return a plain ``str`` (backward-compatible):
  ``_dispatch`` normalises ``str`` → ``AiCallResult(text=…, 0, 0)`` so existing
  tests that patch ``_anthropic_caller`` / ``_openai_caller`` to return a string
  do not need to change.
* ``AiTagResult`` and ``AiTextResult`` carry ``input_tokens`` / ``output_tokens``
  so callers (action endpoints) can record usage without touching the client layer.
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

# Signature: (api_key, model, system, user_msg, max_tokens) -> str | AiCallResult | None
_anthropic_caller = None

# Signature: (api_key, base_url, model, system, user_msg, max_tokens) -> str | AiCallResult | None
_openai_caller = None

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

MAX_NEW_SUGGESTIONS = 5  # hard cap on genuinely new tag suggestions


@dataclass
class AiCallResult:
    """Raw result from a single AI provider call.

    text         — the response text (None on error/empty response)
    input_tokens — tokens consumed by the prompt (0 when using mocked callers)
    output_tokens — tokens in the completion (0 when using mocked callers)
    """

    text: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class AiTagResult:
    """Result of an AI tag-suggestion call.

    canonical       — matched names from the existing canonical tag list
    new_suggestions — genuinely new tags (≤ MAX_NEW_SUGGESTIONS); go to pending
    error           — non-None when the call failed (never re-raised to caller)
    input_tokens    — prompt tokens (0 when mocked / provider error)
    output_tokens   — completion tokens (0 when mocked / provider error)
    """

    canonical: list[str] = field(default_factory=list)
    new_suggestions: list[str] = field(default_factory=list)
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class AiTextResult:
    """Result of a description-cleanup or scrape-summarization call."""

    text: str | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


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
    timeout: float = 60.0,
) -> AiCallResult | None:
    """Invoke the Anthropic SDK.  Returns AiCallResult (with token counts) or None on error."""
    if not api_key:
        # No key → the SDK raises a cryptic "could not resolve authentication"
        # TypeError. Return cleanly instead (callers treat None as "no result").
        log.warning("Anthropic call skipped: no API key configured")
        return None
    try:
        import anthropic  # noqa: PLC0415

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            timeout=timeout,
        )
        text: str | None = None
        if response.content and hasattr(response.content[0], "text"):
            text = str(response.content[0].text)
        input_tokens = getattr(response.usage, "input_tokens", 0) or 0
        output_tokens = getattr(response.usage, "output_tokens", 0) or 0
        return AiCallResult(text=text, input_tokens=input_tokens, output_tokens=output_tokens)
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
    timeout: float = 60.0,
) -> AiCallResult | None:
    """Invoke the OpenAI SDK (also used for Ollama via base_url).  Returns AiCallResult or None."""
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
            timeout=timeout,
        )
        text: str | None = None
        if response.choices:
            text = response.choices[0].message.content
        usage = response.usage
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        return AiCallResult(text=text, input_tokens=input_tokens, output_tokens=output_tokens)
    except Exception:
        log.exception("OpenAI/Ollama API call failed")
        return None


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_DEFAULT_CLAUDE_MODEL = "claude-opus-4-8"
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def _normalize_caller_result(raw: object) -> AiCallResult | None:
    """Normalise an injectable-caller return value to AiCallResult or None.

    Real callers now return AiCallResult.  Test callers that return a plain
    ``str`` are normalised here so they still work without any test changes.
    """
    if raw is None:
        return None
    if isinstance(raw, AiCallResult):
        return raw
    if isinstance(raw, str):
        return AiCallResult(text=raw, input_tokens=0, output_tokens=0)
    # Unexpected type — treat as no result
    log.warning("Unexpected AI caller return type: %s", type(raw))
    return None


def _dispatch(
    provider: AiProvider,
    system: str,
    user_msg: str,
    max_tokens: int = 1024,
    timeout: float = 60.0,
) -> AiCallResult | None:
    """Dispatch a call to the configured provider. Returns AiCallResult or None.

    ``timeout`` is passed to the real SDK caller so a slow provider fails fast
    rather than hanging indefinitely.  Injectable test callers do NOT receive the
    timeout argument — their signatures stay unchanged and they never make real
    network calls.

    Call sites MUST run this via ``asyncio.to_thread`` so a slow provider only
    blocks the thread that asked for it and never stalls the event loop.
    """
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
            # Injectable caller — no timeout (it never makes real network calls).
            raw = caller(api_key, model, system, user_msg, max_tokens)  # type: ignore[operator]
            return _normalize_caller_result(raw)
        return _call_anthropic_real(api_key, model, system, user_msg, max_tokens, timeout=timeout)

    # OpenAI or Ollama — both use the openai SDK; Ollama sets base_url.
    if not model:
        model = _DEFAULT_OPENAI_MODEL
    base_url = provider.endpoint  # None for OpenAI; endpoint for Ollama
    caller = _openai_caller
    if caller is not None:
        # Injectable caller — no timeout (it never makes real network calls).
        raw = caller(api_key, base_url, model, system, user_msg, max_tokens)  # type: ignore[operator]
        return _normalize_caller_result(raw)
    return _call_openai_real(
        api_key, base_url, model, system, user_msg, max_tokens, timeout=timeout
    )


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

    Token counts are populated in the returned AiTagResult so callers can
    record usage without touching this layer.
    """
    system, user_msg = _build_tag_prompt(
        title, description, scraped_text, filenames, existing_tags
    )
    try:
        call_result = _dispatch(provider, system, user_msg, max_tokens=512)
        if call_result is None or call_result.text is None:
            return AiTagResult(error="No response from AI provider")

        # Strip markdown code fences if the model wraps its output.
        text = call_result.text.strip()
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

        return AiTagResult(
            canonical=canonical,
            new_suggestions=new_suggestions,
            input_tokens=call_result.input_tokens,
            output_tokens=call_result.output_tokens,
        )

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
    Token counts in the result allow callers to record usage.
    """
    if not description or not description.strip():
        return AiTextResult(error="Empty description provided")

    system, user_msg = _build_cleanup_prompt(description, title)
    try:
        call_result = _dispatch(provider, system, user_msg, max_tokens=1024)
        if call_result is None or call_result.text is None:
            return AiTextResult(error="No response from AI provider")
        return AiTextResult(
            text=call_result.text.strip(),
            input_tokens=call_result.input_tokens,
            output_tokens=call_result.output_tokens,
        )
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
    Token counts in the result allow callers to record usage.
    """
    if not scraped_text or not scraped_text.strip():
        return AiTextResult(error="No scraped content to summarize")

    system, user_msg = _build_summarize_prompt(scraped_text, title)
    try:
        call_result = _dispatch(provider, system, user_msg, max_tokens=512)
        if call_result is None or call_result.text is None:
            return AiTextResult(error="No response from AI provider")
        return AiTextResult(
            text=call_result.text.strip(),
            input_tokens=call_result.input_tokens,
            output_tokens=call_result.output_tokens,
        )
    except Exception as exc:
        log.warning("AI scrape summarization failed: %s", exc)
        return AiTextResult(error=str(exc))
