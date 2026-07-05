"""FIX SET 6 — error-response hygiene.

Covers the global catch-all exception handler and the genericized 500/4xx error
details that previously interpolated raw exception text into the HTTP response.

The contract under test:
  - An *unhandled* server error returns a fixed generic 500 body and never leaks
    exception text, class names, or stack detail into the response.
  - HTTPException / well-formed 4xx responses are NOT swallowed by the catch-all;
    they keep their own status code and detail.
  - SSRF-blocked URLs return a generic "URL is not allowed." message and do not
    leak the resolved internal IP / block reason to the (untrusted) importer.
  - Enqueue failures return a generic action message, not the raw exception.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.main import app, unhandled_exception_handler

# A recognizable "internal" string that must never appear in any HTTP body.
_SECRET = "super-secret-internal-detail /etc/passwd host=10.11.12.13"


def _drop_route(path: str) -> None:
    """Remove a throwaway test route from the shared app router."""
    app.router.routes = [
        r for r in app.router.routes if getattr(r, "path", None) != path
    ]


# ---------------------------------------------------------------------------
# Global catch-all exception handler
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unhandled_exception_returns_generic_500_without_leak() -> None:
    """An unhandled exception → generic 500, no raw exception text in the body."""
    path = "/__test_boom__"

    async def _boom() -> None:
        raise RuntimeError(_SECRET)

    app.add_api_route(path, _boom, methods=["GET"])
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(path)
        assert resp.status_code == 500
        assert resp.json() == {"detail": "Internal server error"}
        # No internals leaked anywhere in the response text.
        assert _SECRET not in resp.text
        assert "RuntimeError" not in resp.text
        assert "Traceback" not in resp.text
    finally:
        _drop_route(path)


@pytest.mark.asyncio
async def test_httpexception_not_swallowed_by_catch_all() -> None:
    """A raised HTTPException keeps its own status + detail (handled first)."""
    path = "/__test_teapot__"

    async def _teapot() -> None:
        raise HTTPException(status_code=418, detail="I am a teapot")

    app.add_api_route(path, _teapot, methods=["GET"])
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(path)
        assert resp.status_code == 418
        assert resp.json() == {"detail": "I am a teapot"}
    finally:
        _drop_route(path)


@pytest.mark.asyncio
async def test_handler_function_directly() -> None:
    """Direct unit test of the handler: fixed generic body, no leak."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/anything",
        "headers": [],
    }
    resp = await unhandled_exception_handler(Request(scope), RuntimeError(_SECRET))
    assert resp.status_code == 500
    body = resp.body.decode()
    assert "Internal server error" in body
    assert _SECRET not in body


# ---------------------------------------------------------------------------
# Genericized error-detail sites
# ---------------------------------------------------------------------------
async def _setup_and_login(client: AsyncClient) -> str:
    """Initialize the instance, log in as admin; return the CSRF token."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@test.com",
            "admin_name": "Admin User",
            "admin_password": "adminpassword1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "adminpassword1"},
    )
    assert resp.status_code == 200
    return client.cookies.get("pf3d_csrf", "")


@pytest.mark.asyncio
async def test_ssrf_blocked_url_returns_generic_message(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """A private/loopback source URL → generic 422, no internal-topology leak."""
    csrf = await _setup_and_login(client)

    resp = await client.post(
        "/api/import-sessions",
        json={
            "source_type": "url",
            "source_url": "http://127.0.0.1:8000/internal/thing",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "URL is not allowed."
    # The block reason (resolved IP / "restricted range" wording) must not leak.
    assert "127.0.0.1" not in resp.text
    assert "restricted" not in resp.text.lower()


@pytest.mark.asyncio
async def test_enqueue_failure_returns_generic_detail(
    client: AsyncClient,
    db_session: AsyncSession,
    arq_pool: object,
    tmp_path: Path,
) -> None:
    """A failed enqueue → generic 503 message, raw exception text not leaked."""
    csrf = await _setup_and_login(client)

    # Make the injected arq stand-in blow up on enqueue with a secret-bearing error.
    arq_pool.enqueue_job.side_effect = RuntimeError(_SECRET)  # type: ignore[attr-defined]

    resp = await client.post(
        "/api/admin/backups/run",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Failed to enqueue backup."
    assert _SECRET not in resp.text
