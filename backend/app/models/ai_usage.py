"""AiUsage model — records token usage from every real AI call (Phase 13).

Captures provider, model, action, token counts, and the user who triggered the call.
The created_at column is indexed for efficient windowed queries (24h / 7d / 30d).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AiUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Provider string (claude / openai / ollama)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    # Model name (may be None when the caller relies on the provider default)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Action: suggest_tags | cleanup_description | summarize | test
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Who triggered the call (nullable; deleted users → SET NULL)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
