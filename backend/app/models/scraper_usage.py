"""ScraperUsage model — records each external scraper API call (Phase 18).

Tracks calls to premium scrapers (e.g. AgentQL) for local budget enforcement.
AgentQL's API exposes no usage/quota endpoint, so we count our own calls.

The created_at column is indexed for efficient windowed queries.
One row per API call made; the admin dashboard uses this for the usage summary.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ScraperUsage(Base):
    __tablename__ = "scraper_usage"
    __table_args__ = (Index("ix_scraper_usage_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Provider string (e.g. 'agentql')
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    # The URL that was scraped
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Whether the scrape succeeded (returned non-blocked result)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Estimated cost in USD (per-call rate at time of call)
    est_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
