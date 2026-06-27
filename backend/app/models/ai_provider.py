"""AiProvider model — Phase 1 stores config only; no AI calls until Phase 8.

api_key is stored Fernet-encrypted (via crypto.encrypt).
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AiProviderType(str, enum.Enum):
    claude = "claude"
    openai = "openai"
    ollama = "ollama"


class AiProvider(Base):
    __tablename__ = "ai_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[AiProviderType] = mapped_column(
        Enum(AiProviderType, name="aiprovidertype"), nullable=False
    )
    # Optional custom endpoint (for Ollama or OpenAI-compatible endpoints).
    endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Fernet-encrypted API key.  Never stored in cleartext.
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
