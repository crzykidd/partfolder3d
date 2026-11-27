"""Per-user printer profiles API tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.test_phase7_print_history import _create_user_and_login, _setup_admin

URL = "/api/me/printer-profiles"


def _h(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


@pytest.mark.asyncio
async def test_crud_happy_path(client: AsyncClient) -> None:
    csrf = await _setup_admin(client)
    r = await client.post(
        URL,
        json={
            "name": "X1C PLA",
            "printer": "Bambu X1C",
            "material": "PLA",
            "nozzle_diameter": 0.4,
            "layer_height": 0.2,
            "supports": False,
        },
        headers=_h(csrf),
    )
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["name"] == "X1C PLA"
    assert p["is_default"] is False
    assert p["supports"] is False
    assert p["filament_color"] is None

    listed = await client.get(URL)
    assert [x["id"] for x in listed.json()] == [p["id"]]

    patched = await client.patch(
        f"{URL}/{p['id']}",
        json={"material": "PETG", "filament_color": "Black"},
        headers=_h(csrf),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["material"] == "PETG"
    assert patched.json()["printer"] == "Bambu X1C"  # untouched

    d = await client.delete(f"{URL}/{p['id']}", headers=_h(csrf))
    assert d.status_code == 204
    assert (await client.get(URL)).json() == []


@pytest.mark.asyncio
async def test_list_order_default_first_then_name(client: AsyncClient) -> None:
    csrf = await _setup_admin(client)
    for name in ("B", "A", "C"):
        await client.post(URL, json={"name": name}, headers=_h(csrf))
    await client.post(URL, json={"name": "Z", "is_default": True}, headers=_h(csrf))
    names = [x["name"] for x in (await client.get(URL)).json()]
    assert names == ["Z", "A", "B", "C"]


@pytest.mark.asyncio
async def test_single_default_invariant(client: AsyncClient) -> None:
    csrf = await _setup_admin(client)
    a = (await client.post(URL, json={"name": "A", "is_default": True}, headers=_h(csrf))).json()
    b = (await client.post(URL, json={"name": "B"}, headers=_h(csrf))).json()
    assert a["is_default"] is True

    r = await client.patch(f"{URL}/{b['id']}", json={"is_default": True}, headers=_h(csrf))
    assert r.status_code == 200
    by_id = {x["id"]: x for x in (await client.get(URL)).json()}
    assert by_id[b["id"]]["is_default"] is True
    assert by_id[a["id"]]["is_default"] is False

    # Creating a new default also unsets the previous one.
    c = (await client.post(URL, json={"name": "C", "is_default": True}, headers=_h(csrf))).json()
    defaults = [x["id"] for x in (await client.get(URL)).json() if x["is_default"]]
    assert defaults == [c["id"]]


@pytest.mark.asyncio
async def test_duplicate_name_conflict(client: AsyncClient) -> None:
    csrf = await _setup_admin(client)
    await client.post(URL, json={"name": "Same"}, headers=_h(csrf))
    dup = await client.post(URL, json={"name": "Same"}, headers=_h(csrf))
    assert dup.status_code == 409

    other = (await client.post(URL, json={"name": "Other"}, headers=_h(csrf))).json()
    ren = await client.patch(f"{URL}/{other['id']}", json={"name": "Same"}, headers=_h(csrf))
    assert ren.status_code == 409


@pytest.mark.asyncio
async def test_per_user_isolation(client: AsyncClient) -> None:
    admin_csrf = await _setup_admin(client)
    a = (
        await client.post(URL, json={"name": "Mine", "is_default": True}, headers=_h(admin_csrf))
    ).json()

    user_csrf = await _create_user_and_login(client, admin_csrf, "b@test.com", "userpass1234")
    assert (await client.get(URL)).json() == []
    assert (
        await client.patch(f"{URL}/{a['id']}", json={"name": "x"}, headers=_h(user_csrf))
    ).status_code == 404
    assert (await client.delete(f"{URL}/{a['id']}", headers=_h(user_csrf))).status_code == 404

    # Same name is allowed for a different user, and has its own default.
    b = await client.post(
        URL, json={"name": "Mine", "is_default": True}, headers=_h(user_csrf)
    )
    assert b.status_code == 201, b.text


@pytest.mark.asyncio
async def test_csrf_required_on_mutations(client: AsyncClient) -> None:
    csrf = await _setup_admin(client)
    p = (await client.post(URL, json={"name": "P"}, headers=_h(csrf))).json()
    assert (await client.post(URL, json={"name": "Q"})).status_code == 403
    assert (await client.patch(f"{URL}/{p['id']}", json={"name": "Q"})).status_code == 403
    assert (await client.delete(f"{URL}/{p['id']}")).status_code == 403


@pytest.mark.asyncio
async def test_requires_auth(client: AsyncClient) -> None:
    resp = await client.get(URL)
    assert resp.status_code in (401, 403)
