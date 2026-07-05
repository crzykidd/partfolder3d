"""Import session task — scrape URL, read sidecar, reconcile tags."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

log = logging.getLogger(__name__)

# Type alias hint (avoids importing ScrapeResult at module level in the worker)
ScrapeResultT = object


async def _try_agentql_fallback(
    url: str,
    db: object,
    scrape_max_images: int = 20,
) -> ScrapeResultT | None:
    """Try AgentQL fallback scraping for a blocked URL.

    Checks enabled/key/budget, calls agentql_scrape (in an executor),
    records a scraper_usage row, and returns a ScrapeResult.

    Returns None on unexpected error (caller treats as graceful failure).
    Returns a ScrapeResult with blocked=True when agentql is disabled/no-key/budget.
    Best-effort: never raises.
    """
    import asyncio as _asyncio  # noqa: PLC0415
    import json as _json  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from app.crypto import InvalidToken, decrypt  # noqa: PLC0415
    from app.models.scraper_usage import ScraperUsage  # noqa: PLC0415
    from app.models.setting import Setting  # noqa: PLC0415
    from app.storage.agentql_client import agentql_scrape  # noqa: PLC0415
    from app.storage.scraper import ScrapeResult  # noqa: PLC0415
    from app.storage.ssrf_guard import sanitize_for_log  # noqa: PLC0415

    _su = sanitize_for_log(url)

    RESET_DAY = 1  # matches AGENTQL_RESET_DAY in agentql router

    async def _setting(key: str) -> object:
        r = await db.execute(sa.select(Setting).where(Setting.key == key))  # type: ignore[union-attr]
        row = r.scalar_one_or_none()
        return _json.loads(row.value) if row else None

    try:
        enabled = bool(await _setting("agentql.enabled") or False)
        if not enabled:
            return ScrapeResult(
                url=url, domain="",
                blocked=True,
                note=(
                    "Automated fetch blocked; AgentQL fallback is not enabled — "
                    "enter details manually."
                ),
            )

        api_key_enc = await _setting("agentql.api_key_enc")
        if not api_key_enc:
            return ScrapeResult(
                url=url, domain="",
                blocked=True,
                note=(
                    "Automated fetch blocked; AgentQL API key not configured — "
                    "enter details manually."
                ),
            )

        try:
            api_key = decrypt(str(api_key_enc))
        except InvalidToken:
            log.warning("_try_agentql_fallback: key decryption failed for %s", _su)
            return ScrapeResult(
                url=url, domain="",
                blocked=True,
                note="AgentQL key decryption failed — re-enter the key in settings.",
            )

        free_allowance = int(await _setting("agentql.free_allowance") or 50)
        budget_mode = str(await _setting("agentql.budget_mode") or "free_only")
        monthly_cap_usd_val = await _setting("agentql.monthly_cap_usd")
        monthly_cap_usd = float(monthly_cap_usd_val) if monthly_cap_usd_val is not None else None
        per_call_usd = float(await _setting("agentql.per_call_usd") or 0.02)

        # Compute budget window start (most recent RESET_DAY at/before now)
        from datetime import UTC, datetime  # noqa: PLC0415
        now = datetime.now(UTC)
        if now.day >= RESET_DAY:
            window_start = now.replace(
                day=RESET_DAY, hour=0, minute=0, second=0, microsecond=0
            )
        elif now.month == 1:
            window_start = now.replace(
                year=now.year - 1, month=12, day=RESET_DAY,
                hour=0, minute=0, second=0, microsecond=0,
            )
        else:
            window_start = now.replace(
                month=now.month - 1, day=RESET_DAY,
                hour=0, minute=0, second=0, microsecond=0,
            )

        # Query current window usage
        usage_result = await db.execute(  # type: ignore[union-attr]
            sa.select(
                sa.func.count(ScraperUsage.id),
                sa.func.coalesce(sa.func.sum(ScraperUsage.est_cost_usd), 0.0),
            ).where(
                ScraperUsage.created_at >= window_start,
                ScraperUsage.provider == "agentql",
            )
        )
        window_calls_raw, window_cost_raw = usage_result.one()
        window_calls = int(window_calls_raw)
        window_cost = float(window_cost_raw)

        # Budget enforcement
        if budget_mode == "free_only":
            if window_calls >= free_allowance:
                return ScrapeResult(
                    url=url, domain="",
                    blocked=True,
                    note=(
                        f"Automated fetch blocked; AgentQL free allowance "
                        f"({free_allowance} calls/month) reached — enter details manually."
                    ),
                )
        elif budget_mode == "cap":
            if monthly_cap_usd is not None and window_cost + per_call_usd > monthly_cap_usd:
                return ScrapeResult(
                    url=url, domain="",
                    blocked=True,
                    note=(
                        f"Automated fetch blocked; AgentQL monthly $ cap "
                        f"(${monthly_cap_usd:.2f}) would be exceeded — enter details manually."
                    ),
                )

        # Call AgentQL (sync HTTP → run in thread executor)
        sr = await _asyncio.get_event_loop().run_in_executor(
            None, lambda: agentql_scrape(url, api_key)
        )

        # Record usage (best-effort: never crash the import)
        try:
            usage_row = ScraperUsage(
                provider="agentql",
                source_url=url,
                success=not sr.blocked,
                est_cost_usd=per_call_usd,
            )
            db.add(usage_row)  # type: ignore[union-attr]
            await db.flush()  # type: ignore[union-attr]
        except Exception:
            log.warning(
                "_try_agentql_fallback: could not record usage row for %s", _su
            )

        return sr

    except Exception as exc:
        log.warning(
            "_try_agentql_fallback: unexpected error for %s: %s", _su, exc
        )
        return None


async def process_import_session(ctx: dict, session_id: str) -> None:
    """Pre-fill an ImportSession: scrape URL, read sidecar, reconcile tags.

    Flow:
      1. Load the session.
      2. If source_url: scrape metadata/images/tags/creator.
      3. If inbox_folder: walk for model files; read sidecar if present.
      4. Reconcile raw tags (alias map → confirmed; unknown → pending suggestions).
      5. Set session status to 'pending_wizard' (or 'failed' on error).

    The wizard does NOT auto-finalize — the user must confirm and call /commit.
    A failure marks the session 'failed' with an error message; the wizard can
    still be used manually (manual path always works).
    """
    import asyncio  # noqa: PLC0415
    import uuid as _uuid  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.import_session import (  # noqa: PLC0415
        ImportSession,
        ImportSessionImage,
        ImportSessionStatus,
        ImportSourceType,
    )
    from app.models.site_capability import SiteCapability  # noqa: PLC0415
    from app.storage.link_url import normalize_link_url  # noqa: PLC0415
    from app.storage.scraper import extract_domain, scrape_url  # noqa: PLC0415
    from app.storage.ssrf_guard import sanitize_for_log  # noqa: PLC0415

    try:
        sid = _uuid.UUID(session_id)
    except ValueError:
        log.error("process_import_session: invalid session_id %r", session_id)
        return

    # Reload session
    async with SessionLocal() as db:
        result = await db.execute(
            sa.select(ImportSession).where(ImportSession.id == sid)
        )
        session = result.scalar_one_or_none()
        if session is None:
            log.warning("process_import_session: session %s not found", session_id)
            return
        if session.status not in (
            ImportSessionStatus.processing, ImportSessionStatus.draft
        ):
            log.info(
                "process_import_session: session %s is %s, skipping",
                session_id, session.status,
            )
            return

    raw_tags: list[str] = []
    scraped_title: str | None = None
    scraped_description: str | None = None
    scraped_creator: str | None = None
    scraped_creator_url: str | None = None
    scraped_license: str | None = None
    scraped_source_site: str | None = None
    image_urls: list[str] = []
    error: str | None = None

    try:
        async with SessionLocal() as db:
            session_result = await db.execute(
                sa.select(ImportSession).where(ImportSession.id == sid)
            )
            session = session_result.scalar_one()

            # ---- URL scrape ----
            if session.source_url:
                from app.config import settings as _settings  # noqa: PLC0415

                domain = extract_domain(session.source_url)

                # Check site capability
                cap_result = await db.execute(
                    sa.select(SiteCapability).where(SiteCapability.domain == domain)
                )
                cap = cap_result.scalar_one_or_none()

                should_scrape = True
                if cap and cap.is_manual_only:
                    should_scrape = False
                    log.info(
                        "process_import_session: %s is manual-only, skip scrape",
                        domain,
                    )

                if should_scrape:
                    # Run blocking scrape in a thread
                    sr = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: scrape_url(
                            session.source_url,
                            timeout=_settings.SCRAPE_TIMEOUT,
                            max_images=_settings.SCRAPE_MAX_IMAGES,
                            html_max_bytes=_settings.SCRAPE_HTML_MAX_MB * 1024 * 1024,
                        ),
                    )

                    # Record/update site capability
                    if cap is None:
                        cap = SiteCapability(
                            domain=domain,
                            can_scrape_metadata=not sr.blocked,
                            can_scrape_images=bool(sr.image_urls),
                            requires_token=False,
                            is_manual_only=False,
                        )
                        db.add(cap)
                    else:
                        if not sr.blocked:
                            cap.can_scrape_metadata = True
                        if sr.image_urls:
                            cap.can_scrape_images = True
                    cap.last_probed_at = datetime.now(UTC)
                    await db.flush()

                    if not sr.blocked:
                        scraped_title = sr.title
                        scraped_description = sr.description
                        scraped_creator = sr.creator_name
                        scraped_creator_url = sr.creator_profile_url
                        scraped_license = sr.license
                        scraped_source_site = sr.source_site
                        raw_tags = sr.raw_tags
                        image_urls = sr.image_urls
                    else:
                        # Static scraper was blocked — try AgentQL fallback
                        fallback_sr = await _try_agentql_fallback(
                            session.source_url,
                            db,
                            scrape_max_images=_settings.SCRAPE_MAX_IMAGES,
                        )
                        if fallback_sr is not None and not fallback_sr.blocked:
                            scraped_title = fallback_sr.title
                            scraped_description = fallback_sr.description
                            scraped_creator = getattr(fallback_sr, "creator_name", None)
                            scraped_creator_url = getattr(fallback_sr, "creator_profile_url", None)
                            scraped_license = getattr(fallback_sr, "license", None)
                            scraped_source_site = getattr(fallback_sr, "source_site", None)
                            raw_tags = getattr(fallback_sr, "raw_tags", []) or []
                            image_urls = fallback_sr.image_urls
                            session.scrape_note = "Fetched via AgentQL"
                            log.info(
                                "process_import_session: AgentQL fallback succeeded for %s "
                                "(title=%r images=%d)",
                                sanitize_for_log(session.source_url),
                                scraped_title,
                                len(image_urls),
                            )
                        else:
                            # Both blocked — set a helpful note
                            note_msg = (
                                getattr(fallback_sr, "note", None)
                                if fallback_sr is not None
                                else None
                            )
                            if not note_msg:
                                note_msg = (
                                    "Automated fetch was blocked; enter details manually."
                                )
                            session.scrape_note = note_msg
                            log.info(
                                "process_import_session: static + AgentQL both blocked for %s: %s",
                                sanitize_for_log(session.source_url), note_msg,
                            )

            # ---- Inbox folder sidecar read ----
            if session.source_type == ImportSourceType.inbox and session.inbox_folder:
                from pathlib import Path  # noqa: PLC0415

                from app.storage.sidecar import read_sidecar  # noqa: PLC0415

                inbox_path = Path(session.inbox_folder)
                # Try to find a sidecar in the folder
                # Look for .yml files that match the sidecar pattern
                yml_files = list(inbox_path.glob("*.yml"))
                for yf in yml_files:
                    sc = read_sidecar(inbox_path, yf.stem, yf.stem)
                    if sc is None:
                        # Try the generic sidecar reader with the file directly
                        try:
                            import yaml  # noqa: PLC0415
                            raw = yaml.safe_load(yf.read_text(encoding="utf-8"))
                            if isinstance(raw, dict) and "schema_version" in raw:
                                # It's a sidecar; extract fields
                                if not scraped_title and raw.get("title"):
                                    scraped_title = str(raw["title"])
                                if not scraped_description and raw.get("description"):
                                    scraped_description = str(raw["description"])
                                src = raw.get("source") or {}
                                if isinstance(src, dict):
                                    if not session.source_url and src.get("url"):
                                        # Update session source URL (drop non-http(s)
                                        # schemes so a hostile sidecar can't plant a
                                        # javascript: href — see storage.link_url).
                                        session.source_url = normalize_link_url(str(src["url"]))
                                    if not scraped_license and src.get("license"):
                                        scraped_license = str(src["license"])
                                    if not scraped_source_site and src.get("site"):
                                        scraped_source_site = str(src["site"])
                                creator_d = raw.get("creator")
                                if isinstance(creator_d, dict) and not scraped_creator:
                                    scraped_creator = creator_d.get("name")
                                    scraped_creator_url = creator_d.get("profile_url")
                                sidecar_tags = [
                                    str(t) for t in (raw.get("tags") or [])
                                ]
                                if sidecar_tags:
                                    raw_tags = sidecar_tags + raw_tags
                        except Exception:
                            log.debug("process_import_session: sidecar parse failed for %s", yf)
                    else:
                        # read_sidecar succeeded
                        if not scraped_title:
                            scraped_title = sc.title
                        if not scraped_description:
                            scraped_description = sc.description
                        if not scraped_license:
                            scraped_license = sc.license
                        if not scraped_source_site:
                            scraped_source_site = sc.source_site
                        if sc.creator:
                            scraped_creator = sc.creator.name
                            scraped_creator_url = sc.creator.profile_url
                        raw_tags = list(sc.tags) + raw_tags
                    break  # Use first sidecar found

            # ---- Tag reconciliation ----
            from app.routers.import_sessions import reconcile_tags  # noqa: PLC0415

            tag_state = (
                await reconcile_tags(db, raw_tags)
                if raw_tags
                else {"confirmed": [], "pending": []}
            )

            # ---- Update session ----
            if not session.suggested_title:
                session.suggested_title = scraped_title
            if not session.confirmed_title:
                session.confirmed_title = scraped_title
            if not session.description:
                session.description = scraped_description
            if not session.license:
                session.license = scraped_license
            if not session.source_site:
                session.source_site = scraped_source_site
            if not session.creator_name:
                session.creator_name = scraped_creator
            if not session.creator_profile_url:
                # Drop non-http(s) schemes from scraped creator URLs (XSS-safe href).
                session.creator_profile_url = normalize_link_url(scraped_creator_url)
            if not session.creator_source_site and scraped_source_site:
                session.creator_source_site = scraped_source_site

            session.tag_state = tag_state
            session.status = ImportSessionStatus.pending_wizard
            session.updated_at = datetime.now(UTC)

            # Add scraped image URLs to session images
            existing_orders = {img.order for img in await _load_session_images(db, sid)}
            for i, img_url in enumerate(image_urls):
                order = i + len(existing_orders)
                img = ImportSessionImage(
                    session_id=session.id,
                    path=img_url,
                    is_url=True,
                    source="scrape",
                    order=order,
                    is_default=(order == 0 and not existing_orders),
                )
                db.add(img)

            await db.commit()
            log.info(
                "process_import_session: session %s → pending_wizard "
                "(tags confirmed=%d pending=%d images=%d)",
                session_id,
                len(tag_state.get("confirmed", [])),
                len(tag_state.get("pending", [])),
                len(image_urls),
            )

    except Exception as exc:
        error = str(exc)
        log.exception("process_import_session: failed for session %s", session_id)
        async with SessionLocal() as db:
            try:
                res = await db.execute(
                    sa.select(ImportSession).where(ImportSession.id == sid)
                )
                session = res.scalar_one_or_none()
                if session:
                    session.status = ImportSessionStatus.failed
                    session.error = error
                    session.updated_at = datetime.now(UTC)
                    await db.commit()
            except Exception:
                log.exception(
                    "process_import_session: could not mark session %s failed",
                    session_id,
                )


async def _load_session_images(db: object, sid: object) -> list:
    """Helper: load existing ImportSessionImage rows for a session."""
    import sqlalchemy as sa  # noqa: PLC0415

    from app.models.import_session import ImportSessionImage  # noqa: PLC0415

    result = await db.execute(  # type: ignore[union-attr]
        sa.select(ImportSessionImage).where(ImportSessionImage.session_id == sid)
    )
    return list(result.scalars().all())
