"""AI pricing table — per-model USD rates for cost estimation.

Rates are expressed in USD per 1,000,000 tokens (per-MTok).

Design
------
- Claude models: seeded with current published rates.
- Ollama: always $0 (local / self-hosted).
- OpenAI: rates vary by model and change frequently — not hardcoded.
  An OpenAI model not in the table yields ``cost = None`` (shown as "—" in the UI).
  Add OpenAI entries here as needed.
- Unknown model (non-Ollama, not in table): cost = None / unknown.
- All returned costs are labelled as **estimates** (rates may drift; this table
  is the local source of truth and must be updated when pricing changes).

Usage
-----
    from app.ai.pricing import estimate_cost
    cost = estimate_cost("claude", "claude-opus-4-8", input_tokens=100, output_tokens=50)
    # Returns float USD or None if the model's rate is unknown.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRate:
    """USD per 1,000,000 tokens (per-MTok)."""

    input_per_mtok: float
    output_per_mtok: float


# ---------------------------------------------------------------------------
# Pricing table — keyed by (provider, model) pairs.
# provider is the AiProviderType string: "claude" | "openai" | "ollama"
# model is the exact model name string (or None key for provider-level defaults).
#
# To add OpenAI pricing, insert entries like:
#   ("openai", "gpt-4o"):       ModelRate(input_per_mtok=2.50, output_per_mtok=10.00),
#   ("openai", "gpt-4o-mini"):  ModelRate(input_per_mtok=0.15, output_per_mtok=0.60),
# ---------------------------------------------------------------------------

_RATES: dict[tuple[str, str | None], ModelRate] = {
    # --- Claude models ---
    ("claude", "claude-opus-4-8"):   ModelRate(input_per_mtok=5.0,  output_per_mtok=25.0),
    ("claude", "claude-opus-4-7"):   ModelRate(input_per_mtok=5.0,  output_per_mtok=25.0),
    ("claude", "claude-opus-4-6"):   ModelRate(input_per_mtok=5.0,  output_per_mtok=25.0),
    ("claude", "claude-sonnet-4-6"): ModelRate(input_per_mtok=3.0,  output_per_mtok=15.0),
    ("claude", "claude-haiku-4-5"):  ModelRate(input_per_mtok=1.0,  output_per_mtok=5.0),
    ("claude", "claude-fable-5"):    ModelRate(input_per_mtok=10.0, output_per_mtok=50.0),

    # --- Ollama (local / self-hosted — always free) ---
    # Represented by a zero-rate entry; looked up per provider, not per model.
    # estimate_cost handles ollama specially before hitting this table.
}

# Fall-through defaults: any "claude-opus-*" model not explicitly listed
_CLAUDE_OPUS_DEFAULT = ModelRate(input_per_mtok=5.0, output_per_mtok=25.0)


def _lookup_rate(provider: str, model: str | None) -> ModelRate | None:
    """Return the ModelRate for a provider+model pair, or None if unknown."""
    if provider == "ollama":
        return ModelRate(input_per_mtok=0.0, output_per_mtok=0.0)

    if model:
        rate = _RATES.get((provider, model))
        if rate is not None:
            return rate
        # Fall-through default for claude-opus-* models not explicitly listed
        if provider == "claude" and model.startswith("claude-opus-"):
            return _CLAUDE_OPUS_DEFAULT

    # No match → unknown rate
    return None


def estimate_cost(
    provider: str,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
) -> float | None:
    """Return estimated USD cost for a single call, or None if rate is unknown.

    The returned value is an **estimate** — rates are configured locally and
    may drift from actual billing. The caller should label the figure accordingly.
    """
    rate = _lookup_rate(provider, model)
    if rate is None:
        return None
    cost = (input_tokens / 1_000_000) * rate.input_per_mtok + (
        output_tokens / 1_000_000
    ) * rate.output_per_mtok
    return round(cost, 8)
