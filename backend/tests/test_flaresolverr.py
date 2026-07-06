"""Issue #23 — FlareSolverr fallback scraper + pluggable scrapers framework tests.

Tests:
  1.  FlareSolverr client: mock seam works; maps solution.response HTML correctly.
  2.  extract_metadata_from_html: shared helper produces identical output to the
      inline scrape_url path (regression guard for the refactor).
  3.  Dispatcher order: FlareSolverr tried first (priority 1); falls through to
      AgentQL when FlareSolverr returns blocked.
  4.  Dispatcher respects scraper.<name>.priority settings rows.
  5.  FlareSolverr disabled / no base_url → blocked result; AgentQL still tried.
  6.  scraper_usage row with provider="flaresolverr" recorded on each call.
  7.  GET/PUT /api/admin/scrapers/flaresolverr endpoints (admin-only; round-trips).
  8.  POST test-connection endpoints (FlareSolverr health + AgentQL validation).
  9.  GET /api/admin/scrapers/usage — all-provider summary.
  10. DELETE /api/admin/scrapers/usage — clear all / per-provider.
  11. extract_metadata_from_html refactor doesn't regress scrape_url.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scraper_usage import ScraperUsage
from app.storage.scraper import ScrapeResult as ScrapeResultScraper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient) -> str:
    """Initialize instance and log in as admin; returns CSRF token."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@test.com",
            "admin_name": "Admin",
            "admin_password": "adminpassword1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "adminpassword1"},
    )
    assert resp.status_code == 200
    return client.cookies.get("pf3d_csrf", "")


async def _set_flaresolverr_settings(
    client: AsyncClient,
    csrf: str,
    *,
    enabled: bool = True,
    base_url: str = "http://localhost:8191",
    timeout_s: int = 60,
    priority: int = 1,
) -> None:
    resp = await client.put(
        "/api/admin/scrapers/flaresolverr",
        json={
            "enabled": enabled,
            "base_url": base_url,
            "timeout_s": timeout_s,
            "priority": priority,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, f"Failed to set FlareSolverr settings: {resp.text}"


async def _set_agentql_settings(
    client: AsyncClient,
    csrf: str,
    *,
    enabled: bool = True,
    api_key: str = "test-key",
    free_allowance: int = 50,
    budget_mode: str = "free_only",
    priority: int = 2,
) -> None:
    resp = await client.put(
        "/api/admin/agentql",
        json={
            "enabled": enabled,
            "api_key": api_key,
            "free_allowance": free_allowance,
            "budget_mode": budget_mode,
            "priority": priority,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, f"Failed to set AgentQL settings: {resp.text}"


# ---------------------------------------------------------------------------
# 1. FlareSolverr client: mock seam
# ---------------------------------------------------------------------------


def test_flaresolverr_client_mock_seam(monkeypatch: Any) -> None:
    """Injected mock seam is used instead of real HTTP."""
    import app.storage.flaresolverr_client as mod

    def fake_caller(url: str, base_url: str) -> ScrapeResultScraper:
        return ScrapeResultScraper(
            url=url,
            domain="makerworld.com",
            title="FlareSolverr Title",
            description="FlareSolverr Description",
            image_urls=["https://example.com/img.jpg"],
            blocked=False,
        )

    monkeypatch.setattr(mod, "_flaresolverr_caller", fake_caller)

    from app.storage.flaresolverr_client import flaresolverr_scrape
    result = flaresolverr_scrape(
        "https://makerworld.com/models/1",
        "http://localhost:8191",
    )

    assert result.blocked is False
    assert result.title == "FlareSolverr Title"
    assert result.description == "FlareSolverr Description"
    assert "https://example.com/img.jpg" in result.image_urls


# ---------------------------------------------------------------------------
# 2. extract_metadata_from_html: shared helper
# ---------------------------------------------------------------------------


def test_extract_metadata_from_html_basic() -> None:
    """extract_metadata_from_html parses HTML into ScrapeResult correctly."""
    from app.storage.scraper import extract_metadata_from_html

    html = """<html>
    <head>
      <meta property="og:title" content="My Model" />
      <meta property="og:description" content="A great model" />
      <meta property="og:image" content="https://example.com/img.png" />
      <meta property="og:site_name" content="Printables" />
    </head>
    <body><p>Content</p></body>
    </html>"""

    sr = extract_metadata_from_html(html, "https://printables.com/model/1", "printables.com", 20)
    assert sr.title == "My Model"
    assert sr.description == "A great model"
    assert sr.source_site == "Printables"
    assert "https://example.com/img.png" in sr.image_urls
    assert sr.blocked is False


def test_extract_metadata_from_html_parse_failure() -> None:
    """extract_metadata_from_html with invalid HTML sets a note (doesn't raise)."""
    from app.storage.scraper import extract_metadata_from_html

    # selectolax is lenient; test with a completely empty string which produces
    # an empty tree but doesn't crash.
    sr = extract_metadata_from_html("", "https://example.com", "example.com", 5)
    # Empty HTML → no title/images; should not crash
    assert sr.url == "https://example.com"
    assert sr.domain == "example.com"


def test_extract_metadata_regression_from_scrape_url(monkeypatch: Any) -> None:
    """Confirm scrape_url still calls extract_metadata_from_html and gets the same result."""
    import app.storage.scraper as mod

    html = """<html><head>
    <meta property="og:title" content="Test Item" />
    <meta property="og:description" content="Desc" />
    </head><body></body></html>"""

    # Patch guarded_fetch to return a fake 200 HTML response
    class FakeResp:
        status_code = 200
        content_type = "text/html"
        text = html

    monkeypatch.setattr(mod, "guarded_fetch", lambda *a, **kw: FakeResp())
    monkeypatch.setattr(mod, "_robots_allows", lambda domain, path: True)
    monkeypatch.setattr(mod, "assert_safe_url", lambda url: None)

    from app.storage.scraper import scrape_url
    sr = scrape_url("https://example.com/test", max_images=5)
    assert sr.title == "Test Item"
    assert sr.description == "Desc"
    assert sr.blocked is False


# ---------------------------------------------------------------------------
# 3 & 4. Dispatcher order tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatcher_flaresolverr_tried_first_by_default(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: Any
) -> None:
    """FlareSolverr (priority=1) is tried before AgentQL (priority=2) by default."""
    import app.storage.agentql_client as aql_mod
    import app.storage.flaresolverr_client as fs_mod

    csrf = await _setup_and_login(client)
    await _set_flaresolverr_settings(client, csrf, enabled=True, priority=1)
    await _set_agentql_settings(client, csrf, enabled=True, priority=2)

    tried_order: list[str] = []

    def mock_fs(url: str, base_url: str) -> ScrapeResultScraper:
        tried_order.append("flaresolverr")
        return ScrapeResultScraper(
            url=url, domain="makerworld.com",
            title="FS Title", description="FS Desc",
            image_urls=["https://cdn/img.jpg"],
            blocked=False,
        )

    def mock_aql(url: str, key: str) -> ScrapeResultScraper:
        tried_order.append("agentql")
        return ScrapeResultScraper(url=url, domain="makerworld.com", blocked=False)

    monkeypatch.setattr(fs_mod, "_flaresolverr_caller", mock_fs)
    monkeypatch.setattr(aql_mod, "_agentql_caller", mock_aql)

    from app.worker.tasks.import_session import _try_fallback_scrapers
    result, backend = await _try_fallback_scrapers(
        "https://makerworld.com/models/1", db_session
    )

    assert result is not None
    assert not result.blocked
    assert result.title == "FS Title"
    assert backend == "flaresolverr"
    assert tried_order == ["flaresolverr"]  # AgentQL never reached


@pytest.mark.asyncio
async def test_dispatcher_falls_through_to_agentql_when_fs_blocked(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: Any
) -> None:
    """When FlareSolverr returns blocked, AgentQL is tried next."""
    import app.storage.agentql_client as aql_mod
    import app.storage.flaresolverr_client as fs_mod

    csrf = await _setup_and_login(client)
    await _set_flaresolverr_settings(client, csrf, enabled=True, priority=1)
    await _set_agentql_settings(client, csrf, enabled=True, priority=2)

    def mock_fs_blocked(url: str, base_url: str) -> ScrapeResultScraper:
        return ScrapeResultScraper(
            url=url, domain="", blocked=True, note="FlareSolverr: blocked"
        )

    def mock_aql_success(url: str, key: str) -> ScrapeResultScraper:
        return ScrapeResultScraper(
            url=url, domain="makerworld.com",
            title="AgentQL Title", description="AgentQL Desc",
            image_urls=["https://cdn/img2.jpg"],
            blocked=False,
        )

    monkeypatch.setattr(fs_mod, "_flaresolverr_caller", mock_fs_blocked)
    monkeypatch.setattr(aql_mod, "_agentql_caller", mock_aql_success)

    from app.worker.tasks.import_session import _try_fallback_scrapers
    result, backend = await _try_fallback_scrapers(
        "https://makerworld.com/models/2", db_session
    )

    assert result is not None
    assert not result.blocked
    assert result.title == "AgentQL Title"
    assert backend == "agentql"


@pytest.mark.asyncio
async def test_dispatcher_respects_priority_setting(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: Any
) -> None:
    """Setting agentql.priority=1 makes AgentQL go first."""
    import app.storage.agentql_client as aql_mod
    import app.storage.flaresolverr_client as fs_mod

    csrf = await _setup_and_login(client)
    # AgentQL priority=1, FlareSolverr priority=2 (reversed from default)
    await _set_flaresolverr_settings(client, csrf, enabled=True, priority=2)
    await _set_agentql_settings(client, csrf, enabled=True, priority=1)

    tried_order: list[str] = []

    def mock_fs(url: str, base_url: str) -> ScrapeResultScraper:
        tried_order.append("flaresolverr")
        return ScrapeResultScraper(url=url, domain="", blocked=False, title="FS")

    def mock_aql(url: str, key: str) -> ScrapeResultScraper:
        tried_order.append("agentql")
        return ScrapeResultScraper(
            url=url, domain="makerworld.com",
            title="AgentQL First", blocked=False,
        )

    monkeypatch.setattr(fs_mod, "_flaresolverr_caller", mock_fs)
    monkeypatch.setattr(aql_mod, "_agentql_caller", mock_aql)

    from app.worker.tasks.import_session import _try_fallback_scrapers
    result, backend = await _try_fallback_scrapers(
        "https://makerworld.com/models/3", db_session
    )

    assert result is not None
    assert not result.blocked
    assert backend == "agentql"
    # AgentQL went first, FlareSolverr never reached
    assert tried_order == ["agentql"]


# ---------------------------------------------------------------------------
# 5. FlareSolverr disabled / no base_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flaresolverr_disabled_returns_blocked(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: Any
) -> None:
    """When FlareSolverr is disabled, it returns blocked immediately."""
    import app.storage.flaresolverr_client as fs_mod

    csrf = await _setup_and_login(client)
    # Explicitly disable FlareSolverr
    await client.put(
        "/api/admin/scrapers/flaresolverr",
        json={"enabled": False, "base_url": "http://localhost:8191"},
        headers={"X-CSRF-Token": csrf},
    )

    calls: list[str] = []

    def mock_fs(url: str, base_url: str) -> ScrapeResultScraper:
        calls.append(url)
        return ScrapeResultScraper(url=url, domain="", blocked=False)

    monkeypatch.setattr(fs_mod, "_flaresolverr_caller", mock_fs)

    from app.worker.tasks.import_session import _try_flaresolverr_fallback
    result = await _try_flaresolverr_fallback("https://makerworld.com/x", db_session)

    assert result is not None
    assert result.blocked is True
    assert "not enabled" in (result.note or "").lower()
    assert len(calls) == 0


@pytest.mark.asyncio
async def test_flaresolverr_no_base_url_returns_blocked(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: Any
) -> None:
    """When FlareSolverr base_url is empty, returns blocked with a note."""
    import app.storage.flaresolverr_client as fs_mod

    csrf = await _setup_and_login(client)
    await client.put(
        "/api/admin/scrapers/flaresolverr",
        json={"enabled": True, "base_url": ""},
        headers={"X-CSRF-Token": csrf},
    )

    monkeypatch.setattr(fs_mod, "_flaresolverr_caller", None)

    from app.worker.tasks.import_session import _try_flaresolverr_fallback
    result = await _try_flaresolverr_fallback("https://makerworld.com/y", db_session)

    assert result is not None
    assert result.blocked is True
    assert "base url" in (result.note or "").lower() or "url" in (result.note or "").lower()


# ---------------------------------------------------------------------------
# 6. scraper_usage row recorded for FlareSolverr
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flaresolverr_usage_row_recorded(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: Any
) -> None:
    """A scraper_usage row with provider='flaresolverr' is written per call."""
    import app.storage.flaresolverr_client as fs_mod

    csrf = await _setup_and_login(client)
    await _set_flaresolverr_settings(client, csrf, enabled=True)

    def mock_fs(url: str, base_url: str) -> ScrapeResultScraper:
        return ScrapeResultScraper(
            url=url, domain="makerworld.com",
            title="FS Test", description="Desc",
            image_urls=["https://cdn/img.jpg"],
            blocked=False,
        )

    monkeypatch.setattr(fs_mod, "_flaresolverr_caller", mock_fs)

    from app.worker.tasks.import_session import _try_flaresolverr_fallback
    result = await _try_flaresolverr_fallback(
        "https://makerworld.com/models/99", db_session
    )

    assert result is not None
    assert result.blocked is False
    assert result.title == "FS Test"

    usage_result = await db_session.execute(
        select(ScraperUsage).where(
            ScraperUsage.source_url == "https://makerworld.com/models/99",
            ScraperUsage.provider == "flaresolverr",
        )
    )
    row = usage_result.scalar_one_or_none()
    assert row is not None
    assert row.provider == "flaresolverr"
    assert row.success is True
    assert row.est_cost_usd == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 7. GET/PUT /api/admin/scrapers/flaresolverr endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_flaresolverr_settings_default(client: AsyncClient) -> None:
    """GET /api/admin/scrapers/flaresolverr returns sensible defaults."""
    await _setup_and_login(client)

    resp = await client.get("/api/admin/scrapers/flaresolverr")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["base_url"] == ""
    assert data["timeout_s"] == 60
    assert data["priority"] == 1


@pytest.mark.asyncio
async def test_put_flaresolverr_settings_roundtrip(client: AsyncClient) -> None:
    """PUT /api/admin/scrapers/flaresolverr: values are persisted and returned."""
    csrf = await _setup_and_login(client)

    resp = await client.put(
        "/api/admin/scrapers/flaresolverr",
        json={
            "enabled": True,
            "base_url": "http://myhost:8191",
            "timeout_s": 90,
            "priority": 3,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["base_url"] == "http://myhost:8191"
    assert data["timeout_s"] == 90
    assert data["priority"] == 3


@pytest.mark.asyncio
async def test_put_flaresolverr_invalid_timeout_rejected(client: AsyncClient) -> None:
    """PUT /api/admin/scrapers/flaresolverr: timeout_s < 1 returns 422."""
    csrf = await _setup_and_login(client)
    resp = await client.put(
        "/api/admin/scrapers/flaresolverr",
        json={"timeout_s": 0},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_agentql_priority_and_timeout(client: AsyncClient) -> None:
    """PUT /api/admin/agentql: new priority/timeout_s fields round-trip."""
    csrf = await _setup_and_login(client)

    resp = await client.put(
        "/api/admin/agentql",
        json={"priority": 5, "timeout_s": 180},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["priority"] == 5
    assert data["timeout_s"] == 180


# ---------------------------------------------------------------------------
# 8. Test-connection endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flaresolverr_test_connection_no_base_url(client: AsyncClient) -> None:
    """Test connection returns ok=False when base_url is not configured."""
    csrf = await _setup_and_login(client)

    resp = await client.post(
        "/api/admin/scrapers/flaresolverr/test-connection",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "base url" in data["message"].lower() or "not configured" in data["message"].lower()


@pytest.mark.asyncio
async def test_agentql_test_connection_no_key(client: AsyncClient) -> None:
    """Test connection returns ok=False when AgentQL API key is not configured."""
    csrf = await _setup_and_login(client)

    resp = await client.post(
        "/api/admin/scrapers/agentql/test-connection",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "not configured" in data["message"].lower() or "api key" in data["message"].lower()


# ---------------------------------------------------------------------------
# 9. GET /api/admin/scrapers/usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_scraper_usage_empty(client: AsyncClient) -> None:
    """GET /api/admin/scrapers/usage returns empty list when no calls made."""
    await _setup_and_login(client)
    resp = await client.get("/api/admin/scrapers/usage")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_all_scraper_usage_multi_provider(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /api/admin/scrapers/usage returns per-provider totals."""
    await _setup_and_login(client)

    now = datetime.now(UTC)
    db_session.add(ScraperUsage(
        created_at=now, provider="agentql",
        source_url="https://makerworld.com/1", success=True, est_cost_usd=0.02,
    ))
    db_session.add(ScraperUsage(
        created_at=now, provider="flaresolverr",
        source_url="https://makerworld.com/2", success=True, est_cost_usd=0.0,
    ))
    db_session.add(ScraperUsage(
        created_at=now, provider="flaresolverr",
        source_url="https://makerworld.com/3", success=False, est_cost_usd=0.0,
    ))
    await db_session.flush()

    resp = await client.get("/api/admin/scrapers/usage")
    assert resp.status_code == 200
    data = resp.json()
    providers = {r["provider"]: r for r in data}
    assert "agentql" in providers
    assert "flaresolverr" in providers
    assert providers["agentql"]["calls"] == 1
    assert providers["flaresolverr"]["calls"] == 2

    # Filter by provider
    resp2 = await client.get("/api/admin/scrapers/usage?provider=flaresolverr")
    data2 = resp2.json()
    assert len(data2) == 1
    assert data2[0]["provider"] == "flaresolverr"
    assert data2[0]["calls"] == 2


# ---------------------------------------------------------------------------
# 10. DELETE /api/admin/scrapers/usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_scraper_usage_all(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """DELETE /api/admin/scrapers/usage clears all providers' rows."""
    csrf = await _setup_and_login(client)

    now = datetime.now(UTC)
    for provider in ("agentql", "flaresolverr"):
        db_session.add(ScraperUsage(
            created_at=now, provider=provider,
            source_url=f"https://x.com/{provider}", success=True, est_cost_usd=0.0,
        ))
    await db_session.flush()

    resp = await client.delete(
        "/api/admin/scrapers/usage",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 204

    # Verify cleared
    usage_resp = await client.get("/api/admin/scrapers/usage")
    assert usage_resp.json() == []


@pytest.mark.asyncio
async def test_clear_scraper_usage_per_provider(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """DELETE /api/admin/scrapers/usage?provider=X clears only that provider."""
    csrf = await _setup_and_login(client)

    now = datetime.now(UTC)
    db_session.add(ScraperUsage(
        created_at=now, provider="agentql",
        source_url="https://makerworld.com/aql", success=True, est_cost_usd=0.02,
    ))
    db_session.add(ScraperUsage(
        created_at=now, provider="flaresolverr",
        source_url="https://makerworld.com/fs", success=True, est_cost_usd=0.0,
    ))
    await db_session.flush()

    # Clear only flaresolverr
    resp = await client.delete(
        "/api/admin/scrapers/usage?provider=flaresolverr",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 204

    usage_resp = await client.get("/api/admin/scrapers/usage")
    data = usage_resp.json()
    providers = {r["provider"]: r for r in data}
    assert "agentql" in providers
    assert "flaresolverr" not in providers


# ---------------------------------------------------------------------------
# 11. __NEXT_DATA__ enrichment (MakerWorld)
# ---------------------------------------------------------------------------

import json as _json  # noqa: E402  (used only in fixtures below)

_MAKERWORLD_NEXT_DATA = _json.dumps({
    "props": {
        "pageProps": {
            "design": {
                "title": "Knitted Goose",
                "designCreator": {
                    "name": "Smoggy3D",
                    "handle": "Smoggy3D",
                },
                "categories": [
                    {"name": "Animals"},
                    {"name": "Miniatures"},
                ],
            }
        }
    }
})

_MAKERWORLD_HTML = f"""<html>
<head>
  <meta property="og:title"
        content="Knitted Goose - Free 3D Print Model - MakerWorld" />
  <meta property="og:description" content="A nice model" />
  <meta property="og:site_name" content="MakerWorld" />
  <script id="__NEXT_DATA__" type="application/json">{_MAKERWORLD_NEXT_DATA}</script>
</head>
<body></body>
</html>"""


def test_next_data_makerworld_happy_path() -> None:
    """NEXT_DATA enrichment: clean title, creator name+URL, and category tags."""
    from app.storage.scraper import extract_metadata_from_html

    sr = extract_metadata_from_html(
        _MAKERWORLD_HTML,
        "https://makerworld.com/en/models/2990447-knitted-goose",
        "makerworld.com",
        20,
    )
    # Clean title from NEXT_DATA (no site-suffix boilerplate)
    assert sr.title == "Knitted Goose"
    # Creator from NEXT_DATA (no meta author present)
    assert sr.creator_name == "Smoggy3D"
    assert sr.creator_profile_url == "https://makerworld.com/en/@Smoggy3D"
    # Categories appended as tags
    assert "Animals" in sr.raw_tags
    assert "Miniatures" in sr.raw_tags
    assert sr.blocked is False


def test_next_data_malformed_json_degrades_gracefully() -> None:
    """Malformed __NEXT_DATA__ JSON leaves the scrape intact (doesn't raise)."""
    from app.storage.scraper import extract_metadata_from_html

    html = """<html>
    <head>
      <meta property="og:title" content="Some Model" />
      <script id="__NEXT_DATA__" type="application/json">{ THIS IS NOT JSON </script>
    </head>
    <body></body>
    </html>"""

    sr = extract_metadata_from_html(
        html,
        "https://makerworld.com/en/models/1",
        "makerworld.com",
        20,
    )
    # og:title-derived title still present; enrichment silently skipped
    assert sr.title == "Some Model"
    assert sr.creator_name is None
    assert sr.creator_profile_url is None
    assert sr.blocked is False


def test_next_data_meta_author_wins_over_next_data() -> None:
    """Existing meta author takes priority; NEXT_DATA creator is not applied."""
    from app.storage.scraper import extract_metadata_from_html

    nd = _json.dumps({
        "props": {
            "pageProps": {
                "design": {
                    "title": "Clean Title",
                    "designCreator": {
                        "name": "NDCreator",
                        "handle": "ndcreator",
                    },
                }
            }
        }
    })
    html = f"""<html>
    <head>
      <meta property="og:title" content="Clean Title" />
      <meta name="author" content="MetaAuthor" />
      <script id="__NEXT_DATA__" type="application/json">{nd}</script>
    </head>
    <body></body>
    </html>"""

    sr = extract_metadata_from_html(
        html,
        "https://makerworld.com/en/models/2",
        "makerworld.com",
        20,
    )
    # Meta author wins
    assert sr.creator_name == "MetaAuthor"
    # NEXT_DATA creator never applied
    assert sr.creator_name != "NDCreator"


def test_next_data_non_makerworld_shape_no_effect() -> None:
    """NEXT_DATA with a different JSON shape produces no enrichment."""
    from app.storage.scraper import extract_metadata_from_html

    nd = _json.dumps({
        "props": {
            "initialState": {
                "thing": {"creator": "SomeCreator"},
            }
        }
    })
    html = f"""<html>
    <head>
      <meta property="og:title" content="Some Other Site Model" />
      <script id="__NEXT_DATA__" type="application/json">{nd}</script>
    </head>
    <body></body>
    </html>"""

    sr = extract_metadata_from_html(
        html,
        "https://othernextjssite.com/model/42",
        "othernextjssite.com",
        20,
    )
    # og:title kept (NEXT_DATA had no matching path)
    assert sr.title == "Some Other Site Model"
    assert sr.creator_name is None
    assert sr.creator_profile_url is None
