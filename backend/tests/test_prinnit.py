"""prinnit.com metadata connector tests.

prinnit.com design pages are a client-rendered SPA with no Open Graph tags,
so the generic ``scrape_url`` only ever sees an empty shell. ``scrape_prinnit``
(``app.storage.prinnit_client``) instead calls prinnit's public, no-auth JSON
API (``GET /designers`` then ``GET /designs/<sub>`` — there is no per-design
public endpoint) and maps the result into an enriched ``ScrapeResult``.

Covers:
  1. URL parsing (`_parse_design_url`): valid design URL, www.-prefixed, a
     non-design (profile) path, and a non-prinnit domain.
  2. Designer -> sub resolution (`_find_designer_sub`): case-insensitive
     match, no assumption on list ordering, unknown name -> None.
  3. Design lookup (`_find_design`) within a designer's full design list.
  4. Full field mapping incl. the print-details block appended to the
     description, image ordering (photosUrls then descriptionPhotosUrls)
     and the max_images cap.
  5. Graceful fall-through to None: unknown designer, unknown designId, and
     an HTTP error from either endpoint — no live network involved (the
     ``guarded_fetch`` seam inside ``app.storage.prinnit_client`` is mocked).
  6. Worker wiring (`process_import_session`): the domain short-circuit uses
     the connector and skips `scrape_url` entirely on success; a None
     result falls through to the normal scrape path; a non-prinnit domain
     never touches the connector at all.

Fixtures below are trimmed/transcribed from a live capture of
``GET /designers`` and ``GET /designs/<sub>`` (see docs/decisions.md) —
no live network is used in these tests.
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_session import (
    ImportSession,
    ImportSessionImage,
    ImportSessionStatus,
    ImportSourceType,
)
from app.models.scraper_usage import ScraperUsage
from app.storage.scraper import ScrapeResult

# ---------------------------------------------------------------------------
# Fixtures (trimmed transcriptions of the live-captured API responses)
# ---------------------------------------------------------------------------

FORGECORE_SUB = "34883438-f071-706f-872f-f403f0bd784d"
LUDO_SUB = "e4e864f8-1021-706a-f554-0f0fb6a23e39"
CORE_ESSENTIALS_SUB = "34282438-0071-70de-1aa7-c2aed3c5fb89"

DESIGN_ID = "368d6R3a5jom3AZQqKxgEKF3BvC"
DESIGN_URL = f"https://prinnit.com/ForgeCore/design/{DESIGN_ID}"

# ForgeCore deliberately listed LAST — the connector must match by name, not
# assume the target designer is first in the list.
DESIGNERS_FIXTURE: dict[str, Any] = {
    "designers": [
        {"sub": LUDO_SUB, "designerName": "Ludo"},
        {"sub": CORE_ESSENTIALS_SUB, "designerName": "CoreEssentials"},
        {"sub": FORGECORE_SUB, "designerName": "ForgeCore"},
    ]
}

LILY_PAD_DESIGN: dict[str, Any] = {
    "photosUrls": [
        {
            "original": (
                "https://images.prinnit.com/designers/34883438-f071-706f-872f-"
                "f403f0bd784d/designs/368d6R3a5jom3AZQqKxgEKF3BvC/1764391982376.webp"
            ),
        },
        {
            "original": (
                "https://images.prinnit.com/designers/34883438-f071-706f-872f-"
                "f403f0bd784d/designs/368d6R3a5jom3AZQqKxgEKF3BvC/1764391981757.webp"
            ),
        },
        {
            "original": (
                "https://images.prinnit.com/designers/34883438-f071-706f-872f-"
                "f403f0bd784d/designs/368d6R3a5jom3AZQqKxgEKF3BvC/1764391982574.webp"
            ),
        },
        {
            "original": (
                "https://images.prinnit.com/designers/34883438-f071-706f-872f-"
                "f403f0bd784d/designs/368d6R3a5jom3AZQqKxgEKF3BvC/1764391981990.webp"
            ),
        },
        {
            "original": (
                "https://images.prinnit.com/designers/34883438-f071-706f-872f-"
                "f403f0bd784d/designs/368d6R3a5jom3AZQqKxgEKF3BvC/1764391982422.webp"
            ),
        },
        {
            "original": (
                "https://images.prinnit.com/designers/34883438-f071-706f-872f-"
                "f403f0bd784d/designs/368d6R3a5jom3AZQqKxgEKF3BvC/1764391982374.webp"
            ),
        },
        {
            "original": (
                "https://images.prinnit.com/designers/34883438-f071-706f-872f-"
                "f403f0bd784d/designs/368d6R3a5jom3AZQqKxgEKF3BvC/1764391981692.webp"
            ),
        },
    ],
    "title": "Lily Pad Cupholder",
    "printDifficulty": "advanced",
    "printTime": 2117,
    "designerSub": FORGECORE_SUB,
    "minPrinterDimensions": {"x": 221, "y": 157, "z": 158},
    "isMultiColor": True,
    "amsRequired": False,
    "filaments": [
        {
            "brandName": "Polymaker",
            "filamentType": "PLA",
            "productName": "Jungle Green",
        },
        {
            "brandName": "Bambu",
            "filamentType": "PLA",
            "productName": "Matte Sakura Pink",
        },
        {
            "brandName": "Bambu",
            "filamentType": "PLA",
            "productName": "Matte Lemon Yellow",
        },
    ],
    "tags": [
        "Cupholder", "Pool Float", "Cup Float", "Plant",
        "lillies", "water", "Lily", "lilies",
    ],
    "videoUrl": "https://youtube.com/shorts/yRHLrYEwA4g",
    "description": (
        "<p>I designed the Lily Pad Cupholder to hold my drinks when at the pool.</p>\n"
        "<p><strong>But how does it float?</strong></p>"
    ),
    "descriptionPhotosUrls": [
        (
            "https://images.prinnit.com/designers/34883438-f071-706f-872f-"
            "f403f0bd784d/designs/368d6R3a5jom3AZQqKxgEKF3BvC/description/"
            "1764392122891.webp"
        ),
        (
            "https://images.prinnit.com/designers/34883438-f071-706f-872f-"
            "f403f0bd784d/designs/368d6R3a5jom3AZQqKxgEKF3BvC/description/"
            "1764392123193.webp"
        ),
        (
            "https://images.prinnit.com/designers/34883438-f071-706f-872f-"
            "f403f0bd784d/designs/368d6R3a5jom3AZQqKxgEKF3BvC/description/"
            "1764392123291.webp"
        ),
    ],
    "weight": 940,
    "designId": DESIGN_ID,
}

OTHER_DESIGN: dict[str, Any] = {
    "title": "Unrelated Widget",
    "designId": "someOtherDesignIdAbc123",
    "designerSub": FORGECORE_SUB,
}

DESIGNS_LIST_FIXTURE: list[dict[str, Any]] = [OTHER_DESIGN, LILY_PAD_DESIGN]


class _FakeResp:
    """Minimal stand-in for ``GuardedResponse`` (only ``status_code``/``text`` used)."""

    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self._body = body

    @property
    def text(self) -> str:
        return json.dumps(self._body)


def _install_api_seam(
    monkeypatch: pytest.MonkeyPatch,
    *,
    designers_status: int = 200,
    designers_body: object = DESIGNERS_FIXTURE,
    designs_status: int = 200,
    designs_body: object = DESIGNS_LIST_FIXTURE,
    calls: list[str] | None = None,
) -> None:
    import app.storage.prinnit_client as prinnit_mod

    def fake_guarded_fetch(url: str, **kwargs: Any) -> _FakeResp:
        if calls is not None:
            calls.append(url)
        if url == f"{prinnit_mod._API_BASE}/designers":
            return _FakeResp(designers_status, designers_body)
        if url == f"{prinnit_mod._API_BASE}/designs/{FORGECORE_SUB}":
            return _FakeResp(designs_status, designs_body)
        return _FakeResp(404, {"message": "Missing Authentication Token"})

    monkeypatch.setattr(prinnit_mod, "guarded_fetch", fake_guarded_fetch)


# ---------------------------------------------------------------------------
# 1. URL parsing
# ---------------------------------------------------------------------------


def test_parse_design_url_valid() -> None:
    from app.storage.prinnit_client import _parse_design_url

    assert _parse_design_url(DESIGN_URL) == ("ForgeCore", DESIGN_ID)


def test_parse_design_url_www_prefix() -> None:
    from app.storage.prinnit_client import _parse_design_url

    url = f"https://www.prinnit.com/ForgeCore/design/{DESIGN_ID}"
    assert _parse_design_url(url) == ("ForgeCore", DESIGN_ID)


def test_parse_design_url_trailing_slash() -> None:
    from app.storage.prinnit_client import _parse_design_url

    url = f"https://prinnit.com/ForgeCore/design/{DESIGN_ID}/"
    assert _parse_design_url(url) == ("ForgeCore", DESIGN_ID)


def test_parse_design_url_non_design_path_returns_none() -> None:
    """A designer's store/profile page (no /design/<id> segment) isn't a design URL."""
    from app.storage.prinnit_client import _parse_design_url

    assert _parse_design_url("https://prinnit.com/ForgeCore") is None


def test_parse_design_url_wrong_domain_returns_none() -> None:
    from app.storage.prinnit_client import _parse_design_url

    assert _parse_design_url(f"https://example.com/ForgeCore/design/{DESIGN_ID}") is None


# ---------------------------------------------------------------------------
# 2. Designer -> sub resolution
# ---------------------------------------------------------------------------


def test_find_designer_sub_case_insensitive() -> None:
    from app.storage.prinnit_client import _find_designer_sub

    assert _find_designer_sub(DESIGNERS_FIXTURE, "forgecore") == FORGECORE_SUB
    assert _find_designer_sub(DESIGNERS_FIXTURE, "FORGECORE") == FORGECORE_SUB
    assert _find_designer_sub(DESIGNERS_FIXTURE, "ForgeCore") == FORGECORE_SUB


def test_find_designer_sub_unknown_name_returns_none() -> None:
    from app.storage.prinnit_client import _find_designer_sub

    assert _find_designer_sub(DESIGNERS_FIXTURE, "NoSuchDesigner") is None


def test_find_designer_sub_malformed_payload_returns_none() -> None:
    from app.storage.prinnit_client import _find_designer_sub

    assert _find_designer_sub({"unexpected": "shape"}, "ForgeCore") is None
    assert _find_designer_sub(["not", "a", "dict"], "ForgeCore") is None
    assert _find_designer_sub(None, "ForgeCore") is None


# ---------------------------------------------------------------------------
# 3. Design lookup
# ---------------------------------------------------------------------------


def test_find_design_matches_by_design_id() -> None:
    from app.storage.prinnit_client import _find_design

    found = _find_design(DESIGNS_LIST_FIXTURE, DESIGN_ID)
    assert found is not None
    assert found["title"] == "Lily Pad Cupholder"


def test_find_design_unknown_id_returns_none() -> None:
    from app.storage.prinnit_client import _find_design

    assert _find_design(DESIGNS_LIST_FIXTURE, "no-such-design-id") is None


# ---------------------------------------------------------------------------
# 4a. HTML -> plain text conversion (_html_to_text)
# ---------------------------------------------------------------------------


def test_html_to_text_multi_paragraph_br_strong_entity_and_img() -> None:
    from app.storage.prinnit_client import _html_to_text

    raw = (
        "<p>First &amp; foremost.</p>"
        "<p><strong>Bold</strong> line one<br>line two</p>"
        '<p>See <a href="https://x.test">link</a>.'
        '<img src="https://images.prinnit.com/drop-me.webp"></p>'
    )
    out = _html_to_text(raw)

    # No tags survive.
    assert "<" not in out and ">" not in out
    # Entity unescaped.
    assert "First & foremost." in out
    # Image dropped entirely (URL not kept).
    assert "drop-me" not in out
    assert "https://images.prinnit.com" not in out
    # Anchor text kept, anchor tag stripped.
    assert "See link." in out
    # <br> became a line break within the paragraph.
    assert "line one\nline two" in out
    # Paragraph breaks preserved between the three <p> blocks.
    assert "First & foremost.\n\nBold line one" in out
    # No run of 3+ newlines.
    assert "\n\n\n" not in out


def test_html_to_text_plain_string_passes_through_trimmed() -> None:
    from app.storage.prinnit_client import _html_to_text

    assert _html_to_text("  Just a widget.  ") == "Just a widget."


def test_html_to_text_empty_and_tags_only_return_empty() -> None:
    from app.storage.prinnit_client import _html_to_text

    assert _html_to_text("") == ""
    assert _html_to_text("<p></p>\n<div></div>") == ""


# ---------------------------------------------------------------------------
# 4. Full field mapping
# ---------------------------------------------------------------------------


def test_scrape_prinnit_full_field_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.storage.prinnit_client import scrape_prinnit

    _install_api_seam(monkeypatch)

    sr = scrape_prinnit(DESIGN_URL, timeout=15, max_images=20)

    assert sr is not None
    assert sr.blocked is False
    assert sr.title == "Lily Pad Cupholder"
    assert sr.raw_tags == [
        "Cupholder", "Pool Float", "Cup Float", "Plant",
        "lillies", "water", "Lily", "lilies",
    ]
    assert sr.creator_name == "ForgeCore"
    assert sr.creator_profile_url == "https://prinnit.com/ForgeCore"
    assert sr.source_site == "prinnit.com"
    assert sr.license is None

    # Description: HTML flattened to plain text, then the print-details block.
    assert sr.description is not None
    assert "<p>" not in sr.description
    assert "<strong>" not in sr.description
    assert sr.description.startswith(
        "I designed the Lily Pad Cupholder to hold my drinks when at the pool."
    )
    # Paragraph break between the two source <p> paragraphs survives.
    assert (
        "I designed the Lily Pad Cupholder to hold my drinks when at the pool."
        "\n\nBut how does it float?"
    ) in sr.description
    assert "Print details:" in sr.description
    assert "- Print time: 35h 17m" in sr.description
    assert "- Difficulty: Advanced" in sr.description
    assert "- Weight: 940 g" in sr.description
    assert "- Min. printer bed: 221 x 157 x 158 mm" in sr.description
    assert "- Printing: multi-color" in sr.description
    assert "AMS required" not in sr.description  # amsRequired is False
    assert (
        "- Filaments used: Polymaker Jungle Green (PLA), "
        "Bambu Matte Sakura Pink (PLA), Bambu Matte Lemon Yellow (PLA)"
        in sr.description
    )
    assert "- Video: https://youtube.com/shorts/yRHLrYEwA4g" in sr.description

    # Images: photosUrls (7) then descriptionPhotosUrls (3), in order.
    assert len(sr.image_urls) == 10
    assert sr.image_urls[0].endswith("1764391982376.webp")
    assert sr.image_urls[6].endswith("1764391981692.webp")
    assert sr.image_urls[7].endswith("description/1764392122891.webp")
    assert sr.image_urls[9].endswith("description/1764392123291.webp")


def test_scrape_prinnit_caps_images_at_max_images(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.storage.prinnit_client import scrape_prinnit

    _install_api_seam(monkeypatch)

    sr = scrape_prinnit(DESIGN_URL, max_images=3)

    assert sr is not None
    assert len(sr.image_urls) == 3
    # Cover (first gallery image) is preserved as the first entry.
    assert sr.image_urls[0].endswith("1764391982376.webp")


def test_scrape_prinnit_print_details_omitted_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A design with none of the print-detail fields appends nothing extra."""
    from app.storage.prinnit_client import scrape_prinnit

    bare_design = {"title": "Bare Widget", "description": "Just a widget.", "designId": DESIGN_ID}
    calls: list[str] = []
    _install_api_seam(monkeypatch, designs_body=[bare_design], calls=calls)

    sr = scrape_prinnit(DESIGN_URL)

    assert sr is not None
    assert sr.description == "Just a widget."


# ---------------------------------------------------------------------------
# 5. Graceful fall-through -> None
# ---------------------------------------------------------------------------


def test_scrape_prinnit_non_prinnit_domain_returns_none_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.storage.prinnit_client as prinnit_mod
    from app.storage.prinnit_client import scrape_prinnit

    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("guarded_fetch must not be called for a non-prinnit URL")

    monkeypatch.setattr(prinnit_mod, "guarded_fetch", boom)

    assert scrape_prinnit("https://example.com/ForgeCore/design/abc") is None


def test_scrape_prinnit_non_design_path_returns_none_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.storage.prinnit_client as prinnit_mod
    from app.storage.prinnit_client import scrape_prinnit

    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("guarded_fetch must not be called for a non-design URL")

    monkeypatch.setattr(prinnit_mod, "guarded_fetch", boom)

    assert scrape_prinnit("https://prinnit.com/ForgeCore") is None


def test_scrape_prinnit_unknown_designer_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.storage.prinnit_client import scrape_prinnit

    calls: list[str] = []
    _install_api_seam(monkeypatch, calls=calls)

    url = f"https://prinnit.com/NoSuchDesigner/design/{DESIGN_ID}"
    assert scrape_prinnit(url) is None
    # The designs list is per-designer and keyed by sub; an unresolved
    # designer must short-circuit before ever fetching it.
    assert not any("/designs/" in c for c in calls)


def test_scrape_prinnit_unknown_design_id_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.storage.prinnit_client import scrape_prinnit

    _install_api_seam(monkeypatch)

    url = "https://prinnit.com/ForgeCore/design/does-not-exist"
    assert scrape_prinnit(url) is None


def test_scrape_prinnit_designers_http_error_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.storage.prinnit_client import scrape_prinnit

    _install_api_seam(monkeypatch, designers_status=500, designers_body={})

    assert scrape_prinnit(DESIGN_URL) is None


def test_scrape_prinnit_designs_list_http_error_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.storage.prinnit_client import scrape_prinnit

    _install_api_seam(
        monkeypatch,
        designs_status=403,
        designs_body={"message": "Missing Authentication Token"},
    )

    assert scrape_prinnit(DESIGN_URL) is None


def test_scrape_prinnit_malformed_json_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.storage.prinnit_client as prinnit_mod
    from app.storage.prinnit_client import scrape_prinnit

    class _BadJsonResp:
        status_code = 200
        text = "not json {"

    monkeypatch.setattr(prinnit_mod, "guarded_fetch", lambda *a, **kw: _BadJsonResp())

    assert scrape_prinnit(DESIGN_URL) is None


# ---------------------------------------------------------------------------
# 6. Worker wiring (process_import_session)
# ---------------------------------------------------------------------------


async def _admin_setup(client: AsyncClient) -> int:
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
    return resp.json()["user_id"]


async def _make_url_session(
    db_session: AsyncSession, user_id: int, *, url: str
) -> ImportSession:
    session_obj = ImportSession(
        id=uuid.uuid4(),
        status=ImportSessionStatus.processing,
        source_type=ImportSourceType.url,
        source_url=url,
        created_by_id=user_id,
    )
    db_session.add(session_obj)
    await db_session.flush()
    return session_obj


def _make_session_local_patch(db_session: AsyncSession):  # type: ignore[no-untyped-def]
    """Return a patched SessionLocal that yields db_session (see test_manyfold_import.py)."""

    def fake_session_local():  # type: ignore[no-untyped-def]
        @asynccontextmanager
        async def _cm():  # type: ignore[no-untyped-def]
            yield db_session

        return _cm()

    return fake_session_local


@pytest.mark.asyncio
async def test_prinnit_domain_routes_and_skips_scrape_url(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.db as db_mod
    import app.storage.prinnit_client as prinnit_mod
    import app.storage.scraper as scraper_mod
    from app.worker.tasks import import_session as wi

    user_id = await _admin_setup(client)

    canned = ScrapeResult(
        url=DESIGN_URL,
        domain="prinnit.com",
        title="Lily Pad Cupholder",
        description="A floating cupholder.\n\nPrint details:\n- Weight: 940 g",
        creator_name="ForgeCore",
        creator_profile_url="https://prinnit.com/ForgeCore",
        source_site="prinnit.com",
        raw_tags=["Cupholder", "Pool Float"],
        image_urls=["https://images.prinnit.com/a.webp", "https://images.prinnit.com/b.webp"],
    )
    monkeypatch.setattr(prinnit_mod, "scrape_prinnit", lambda *a, **kw: canned)

    def fake_scrape_url(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("scrape_url must not be called when the prinnit connector succeeds")

    monkeypatch.setattr(scraper_mod, "scrape_url", fake_scrape_url)
    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    session_obj = await _make_url_session(db_session, user_id, url=DESIGN_URL)

    await wi.process_import_session({}, str(session_obj.id))

    await db_session.refresh(session_obj)
    assert session_obj.status == ImportSessionStatus.pending_wizard
    assert session_obj.confirmed_title == "Lily Pad Cupholder"
    assert session_obj.creator_name == "ForgeCore"
    assert session_obj.creator_profile_url == "https://prinnit.com/ForgeCore"
    assert session_obj.source_site == "prinnit.com"
    assert "Prinnit" in (session_obj.scrape_note or "")
    assert session_obj.tag_state == {
        "confirmed": [], "pending": ["Cupholder", "Pool Float"],
    }

    imgs_result = await db_session.execute(
        select(ImportSessionImage).where(ImportSessionImage.session_id == session_obj.id)
    )
    imgs = imgs_result.scalars().all()
    assert len(imgs) == 2
    assert all(img.is_url for img in imgs)
    assert all(img.source == "scrape" for img in imgs)

    usage_result = await db_session.execute(
        select(ScraperUsage).where(ScraperUsage.provider == "prinnit")
    )
    usage_rows = usage_result.scalars().all()
    assert len(usage_rows) == 1
    assert usage_rows[0].success is True
    assert usage_rows[0].source_url == DESIGN_URL


@pytest.mark.asyncio
async def test_prinnit_domain_unresolved_falls_through_to_normal_scrape(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prinnit.com URL the connector can't resolve still gets a normal scrape attempt."""
    import app.db as db_mod
    import app.storage.prinnit_client as prinnit_mod
    import app.storage.scraper as scraper_mod
    from app.worker.tasks import import_session as wi

    user_id = await _admin_setup(client)

    monkeypatch.setattr(prinnit_mod, "scrape_prinnit", lambda *a, **kw: None)

    scrape_calls: list[str] = []

    def fake_scrape_url(url: str, **kwargs: Any) -> ScrapeResult:
        scrape_calls.append(url)
        return ScrapeResult(url=url, domain="prinnit.com", title="Fallback Title", blocked=False)

    monkeypatch.setattr(scraper_mod, "scrape_url", fake_scrape_url)
    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    url = f"https://prinnit.com/ForgeCore/design/{DESIGN_ID}"
    session_obj = await _make_url_session(db_session, user_id, url=url)

    await wi.process_import_session({}, str(session_obj.id))

    await db_session.refresh(session_obj)
    assert scrape_calls == [url]
    assert session_obj.confirmed_title == "Fallback Title"
    assert session_obj.status == ImportSessionStatus.pending_wizard

    usage_result = await db_session.execute(
        select(ScraperUsage).where(ScraperUsage.provider == "prinnit")
    )
    usage_rows = usage_result.scalars().all()
    assert len(usage_rows) == 1
    assert usage_rows[0].success is False


@pytest.mark.asyncio
async def test_non_prinnit_domain_never_calls_prinnit_connector(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.db as db_mod
    import app.storage.prinnit_client as prinnit_mod
    import app.storage.scraper as scraper_mod
    from app.worker.tasks import import_session as wi

    user_id = await _admin_setup(client)

    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("scrape_prinnit must not be called for a non-prinnit domain")

    monkeypatch.setattr(prinnit_mod, "scrape_prinnit", boom)

    def fake_scrape_url(url: str, **kwargs: Any) -> ScrapeResult:
        return ScrapeResult(url=url, domain="example.com", title="Regular Page", blocked=False)

    monkeypatch.setattr(scraper_mod, "scrape_url", fake_scrape_url)
    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    other_url = "https://example.com/thing/1"
    session_obj = await _make_url_session(db_session, user_id, url=other_url)

    await wi.process_import_session({}, str(session_obj.id))

    await db_session.refresh(session_obj)
    assert session_obj.confirmed_title == "Regular Page"
    assert session_obj.status == ImportSessionStatus.pending_wizard

    usage_result = await db_session.execute(
        select(ScraperUsage).where(ScraperUsage.provider == "prinnit")
    )
    assert usage_result.scalars().all() == []
