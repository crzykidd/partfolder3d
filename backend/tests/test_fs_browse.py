"""Tests for GET /api/admin/fs/browse (issue #8).

Security-guard coverage:
  - Non-admin user → 403
  - Unauthenticated → 401
  - Path outside allowlist → 400
  - ``..`` traversal → 400
  - Absolute path not under any root → 400
  - Valid listing inside allowed root → 200 with correct entries

Integration helpers mirror the pattern in test_users.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_and_login_admin(client: AsyncClient) -> str:
    """Initialize the instance and log in as admin; return CSRF token."""
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


async def _create_and_login_regular(client: AsyncClient, admin_csrf: str) -> str:
    """Create a regular (non-admin) user and log in as them; return CSRF token."""
    await client.post(
        "/api/users",
        json={
            "email": "user@test.com",
            "name": "Regular User",
            "password": "userpassword1",
            "role": "user",
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    await client.post("/api/auth/logout")
    resp = await client.post(
        "/api/auth/login",
        json={"email": "user@test.com", "password": "userpassword1"},
    )
    assert resp.status_code == 200
    return client.cookies.get("pf3d_csrf", "")


# ---------------------------------------------------------------------------
# Security: authentication and authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browse_unauthenticated_returns_401(client: AsyncClient) -> None:
    """No session cookie → 401 before any path check."""
    resp = await client.get("/api/admin/fs/browse")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_browse_non_admin_returns_403(client: AsyncClient) -> None:
    """Non-admin user → 403."""
    admin_csrf = await _setup_and_login_admin(client)
    await _create_and_login_regular(client, admin_csrf)

    resp = await client.get("/api/admin/fs/browse")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Security: path-traversal and outside-allowlist guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browse_path_outside_allowlist_returns_400(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Path resolving outside ALL configured roots → 400."""
    root = tmp_path / "library"
    root.mkdir()
    monkeypatch.setattr("app.config.settings.FS_BROWSE_ROOTS", [str(root)])

    await _setup_and_login_admin(client)

    # /tmp itself is outside our root (root is a subdir of tmp_path, not /tmp)
    resp = await client.get("/api/admin/fs/browse", params={"path": "/tmp"})
    assert resp.status_code == 400
    assert "outside the allowed" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_browse_dotdot_traversal_returns_400(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Path using .. to escape the root → 400."""
    root = tmp_path / "library"
    root.mkdir()
    subdir = root / "subdir"
    subdir.mkdir()
    monkeypatch.setattr("app.config.settings.FS_BROWSE_ROOTS", [str(root)])

    await _setup_and_login_admin(client)

    # Try to escape upward
    escape_path = str(subdir / ".." / "..")  # resolves to tmp_path, outside root
    resp = await client.get("/api/admin/fs/browse", params={"path": escape_path})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_browse_slash_etc_returns_400(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """/etc is not inside the allowlist → 400."""
    root = tmp_path / "library"
    root.mkdir()
    monkeypatch.setattr("app.config.settings.FS_BROWSE_ROOTS", [str(root)])

    await _setup_and_login_admin(client)

    resp = await client.get("/api/admin/fs/browse", params={"path": "/etc"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_browse_slash_proc_returns_400(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """/proc is not inside the allowlist → 400."""
    root = tmp_path / "library"
    root.mkdir()
    monkeypatch.setattr("app.config.settings.FS_BROWSE_ROOTS", [str(root)])

    await _setup_and_login_admin(client)

    resp = await client.get("/api/admin/fs/browse", params={"path": "/proc"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_browse_slash_root_returns_400(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filesystem root / is not inside the allowlist → 400."""
    root = tmp_path / "library"
    root.mkdir()
    monkeypatch.setattr("app.config.settings.FS_BROWSE_ROOTS", [str(root)])

    await _setup_and_login_admin(client)

    resp = await client.get("/api/admin/fs/browse", params={"path": "/"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_browse_relative_path_returns_400(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-absolute path → 400."""
    root = tmp_path / "library"
    root.mkdir()
    monkeypatch.setattr("app.config.settings.FS_BROWSE_ROOTS", [str(root)])

    await _setup_and_login_admin(client)

    resp = await client.get("/api/admin/fs/browse", params={"path": "relative/path"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Functional: listing works inside the allowlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browse_no_path_returns_roots(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No path parameter → returns the configured roots."""
    root = tmp_path / "library"
    root.mkdir()
    monkeypatch.setattr("app.config.settings.FS_BROWSE_ROOTS", [str(root)])

    await _setup_and_login_admin(client)

    resp = await client.get("/api/admin/fs/browse")
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] is None
    assert data["parent"] is None
    assert len(data["entries"]) == 1
    assert data["entries"][0]["abs_path"] == str(root)


@pytest.mark.asyncio
async def test_browse_root_lists_subdirs(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browsing the allowed root lists its subdirectories."""
    root = tmp_path / "library"
    root.mkdir()
    (root / "alpha").mkdir()
    (root / "beta").mkdir()
    (root / "readme.txt").write_text("ignored")  # files are excluded
    monkeypatch.setattr("app.config.settings.FS_BROWSE_ROOTS", [str(root)])

    await _setup_and_login_admin(client)

    resp = await client.get("/api/admin/fs/browse", params={"path": str(root)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == str(root)
    names = [e["name"] for e in data["entries"]]
    assert "alpha" in names
    assert "beta" in names
    # Files are not listed
    assert "readme.txt" not in names


@pytest.mark.asyncio
async def test_browse_subdir_has_correct_parent(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browsing a subdir returns its parent (still within the root)."""
    root = tmp_path / "library"
    root.mkdir()
    subdir = root / "models"
    subdir.mkdir()
    (subdir / "category_a").mkdir()
    monkeypatch.setattr("app.config.settings.FS_BROWSE_ROOTS", [str(root)])

    await _setup_and_login_admin(client)

    resp = await client.get("/api/admin/fs/browse", params={"path": str(subdir)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == str(subdir)
    assert data["parent"] == str(root)


@pytest.mark.asyncio
async def test_browse_at_root_has_no_parent(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browsing the root itself → parent is None (can't go above the root)."""
    root = tmp_path / "library"
    root.mkdir()
    monkeypatch.setattr("app.config.settings.FS_BROWSE_ROOTS", [str(root)])

    await _setup_and_login_admin(client)

    resp = await client.get("/api/admin/fs/browse", params={"path": str(root)})
    assert resp.status_code == 200
    data = resp.json()
    # Parent of root (tmp_path) is outside the allowlist → should be None
    assert data["parent"] is None


@pytest.mark.asyncio
async def test_browse_nonexistent_path_returns_404(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browsing a path inside the root that does not exist → 404."""
    root = tmp_path / "library"
    root.mkdir()
    monkeypatch.setattr("app.config.settings.FS_BROWSE_ROOTS", [str(root)])

    await _setup_and_login_admin(client)

    resp = await client.get(
        "/api/admin/fs/browse", params={"path": str(root / "nonexistent")}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_browse_file_path_returns_400(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browsing a file (not a directory) → 400."""
    root = tmp_path / "library"
    root.mkdir()
    afile = root / "model.stl"
    afile.write_text("binary")
    monkeypatch.setattr("app.config.settings.FS_BROWSE_ROOTS", [str(root)])

    await _setup_and_login_admin(client)

    resp = await client.get("/api/admin/fs/browse", params={"path": str(afile)})
    assert resp.status_code == 400
