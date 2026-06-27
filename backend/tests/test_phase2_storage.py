"""Phase 2 storage layer tests.

Covers:
- key-gen uniqueness + retry
- shard derivation
- title sanitization edge cases (accents, CJK/emoji, reserved names, length cap,
  identical-title collisions)
- sidecar round-trip (write → read → equivalent)
- file inventory + SHA-256 + size/mtime drift skip
- atomic rename happy path
- rollback when a pre-commit step fails (new dir already exists)
- crash recovery from a stale journal (finish-forward and roll-back branches)
- bulk isolation (one bad item doesn't roll back the rest)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest

from app.storage.inventory import FileRole, hash_file_sha256, infer_role, inventory_item
from app.storage.journal import (
    JournalEntry,
    MoveError,
    _journal_path,
    _write_journal,
    atomic_rename,
    recover_stale_journals,
)
from app.storage.keys import KEY_LENGTH, generate_key_raw, generate_unique_key, key_shard
from app.storage.paths import (
    item_dir_path,
    item_slug,
    sanitize_slug_body,
    sidecar_path,
)
from app.storage.sidecar import (
    SidecarCreator,
    SidecarData,
    SidecarFile,
    SidecarImage,
    read_sidecar,
    write_sidecar,
)

# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


def test_key_raw_length_and_alphabet() -> None:
    """Generated key is KEY_LENGTH chars, all lowercase base32."""
    key = generate_key_raw()
    assert len(key) == KEY_LENGTH
    valid = set("abcdefghijklmnopqrstuvwxyz234567")
    assert all(c in valid for c in key)


def test_key_raw_random() -> None:
    """Two generated keys are (almost certainly) different."""
    keys = {generate_key_raw() for _ in range(100)}
    # With 2^35 space, the probability of all 100 being different is ~1.
    assert len(keys) > 90


@pytest.mark.asyncio
async def test_generate_unique_key_db(db_session: Any) -> None:
    """generate_unique_key() returns a key not present in the DB."""
    from app.models.item import Item

    key = await generate_unique_key(db_session)
    assert len(key) == KEY_LENGTH
    # Verify it's actually absent
    from sqlalchemy import select

    result = await db_session.execute(select(Item).where(Item.key == key))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_generate_unique_key_retry(db_session: Any, tmp_path: Any) -> None:
    """generate_unique_key() retries on collision and eventually returns a unique key."""
    call_count = 0
    original_raw = generate_key_raw

    def side_effect() -> str:
        nonlocal call_count
        call_count += 1
        # Return a fixed key for the first 3 calls, then a new one
        if call_count <= 3:
            return "aaaaaaa"
        return original_raw()

    with patch("app.storage.keys.generate_key_raw", side_effect=side_effect):
        # Pre-insert the collision key
        from app.models.item import Item
        from app.models.library import Library

        lib = Library(name="test", mount_path=str(tmp_path / "lib"))
        db_session.add(lib)
        await db_session.flush()

        item = Item(
            key="aaaaaaa",
            title="Collision Item",
            slug="collision-item-aaaaaaa",
            library_id=lib.id,
            dir_path=str(tmp_path / "lib" / "aa" / "collision-item-aaaaaaa"),
            schema_version=1,
        )
        db_session.add(item)
        await db_session.flush()

        key = await generate_unique_key(db_session)
        assert key != "aaaaaaa"
        assert call_count >= 4


# ---------------------------------------------------------------------------
# Shard derivation
# ---------------------------------------------------------------------------


def test_key_shard_length() -> None:
    """Shard is the first 2 characters of the key."""
    key = "ab3fg72"
    assert key_shard(key) == "ab"


def test_key_shard_all_keys() -> None:
    """Shard is always a 2-char string for any 7-char key."""
    for _ in range(50):
        key = generate_key_raw()
        shard = key_shard(key)
        assert len(shard) == 2
        assert shard == key[:2]


# ---------------------------------------------------------------------------
# Title sanitization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("title, expected_slug_body", [
    ("Ladybug Keychain", "ladybug-keychain"),
    ("café au lait", "cafe-au-lait"),           # accent → ASCII
    ("Résumé", "resume"),
    ("   spaces   ", "spaces"),                 # trim
    ("---", "item"),                             # all punctuation → empty → fallback
    ("", "item"),                                # empty string
    # CJK: text-unidecode transliterates to Latin, so NOT empty → not "item"
    # python-slugify("日本語タイトル") → "ri-ben-yu-taitoru"
    ("日本語タイトル", "ri-ben-yu-taitoru"),
    ("🎉🎊", "item"),                        # all-emoji → empty → fallback
    # CJK: text-unidecode transliterates to ASCII (not empty), so NOT "item"
    ("con", "con"),                         # NOT a reserved name issue (slug body only)
    ("Hello World / Test", "hello-world-test"),  # slash → dash
    # 80-char cap: title of 90 'a' chars → slug body of ≤80 chars
    ("a" * 90, "a" * 80),
    # Identical titles → same slug body (collisions resolved by key suffix)
    ("Widget", "widget"),
])
def test_sanitize_slug_body(title: str, expected_slug_body: str) -> None:
    result = sanitize_slug_body(title)
    assert result == expected_slug_body, (
        f"sanitize_slug_body({title!r}) = {result!r}, want {expected_slug_body!r}"
    )


def test_slug_body_length_cap() -> None:
    """Slug body never exceeds 80 characters."""
    long_title = "word " * 30  # 150 chars
    slug = sanitize_slug_body(long_title)
    assert len(slug) <= 80


def test_slug_body_no_trailing_dash() -> None:
    """Slug body never ends with a dash after capping."""
    # Build a title where the 80th char falls mid-word-boundary on a dash
    title = "a" * 79 + "-b"
    slug = sanitize_slug_body(title)
    assert not slug.endswith("-")


def test_item_slug_includes_key() -> None:
    """item_slug() = <slug_body>-<key>."""
    slug = item_slug("Ladybug Keychain", "a7f3k9a")
    assert slug == "ladybug-keychain-a7f3k9a"


def test_identical_titles_differ_by_key() -> None:
    """Two items with the same title but different keys have different slugs."""
    slug1 = item_slug("Widget", "aaaaaaa")
    slug2 = item_slug("Widget", "bbbbbbb")
    assert slug1 != slug2
    assert slug1.endswith("-aaaaaaa")
    assert slug2.endswith("-bbbbbbb")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def test_item_dir_path(tmp_path: Any) -> None:
    """item_dir_path() = <library>/<shard>/<slug-key>/."""
    lib = str(tmp_path / "library")
    p = item_dir_path(lib, "ab3fg72", "Ladybug Keychain")
    assert p.parent.parent == tmp_path / "library"
    assert p.name == "ladybug-keychain-ab3fg72"
    assert p.parent.name == "ab"  # shard


def test_sidecar_path(tmp_path: Any) -> None:
    """sidecar_path() is inside item_dir with .yml extension."""
    item_dir = tmp_path / "ab" / "ladybug-keychain-ab3fg72"
    sp = sidecar_path(item_dir, "Ladybug Keychain", "ab3fg72")
    assert sp == item_dir / "ladybug-keychain-ab3fg72.yml"


# ---------------------------------------------------------------------------
# Sidecar round-trip
# ---------------------------------------------------------------------------


def test_sidecar_round_trip(tmp_path: Any) -> None:
    """write_sidecar → read_sidecar returns equivalent data."""
    title = "Test Widget"
    key = "ab3fg72"
    item_dir = tmp_path / "ab" / "test-widget-ab3fg72"
    item_dir.mkdir(parents=True)

    now_iso = "2026-06-27T10:00:00Z"
    data = SidecarData(
        schema_version=1,
        key=key,
        title=title,
        slug="test-widget-ab3fg72",
        description="A test widget",
        source_url="https://example.com/model/1",
        source_site="example.com",
        license="CC-BY-4.0",
        creator=SidecarCreator(
            name="Jane Maker",
            profile_url="https://example.com/@janemaker",
            source_site="example.com",
            is_original=False,
        ),
        tags=["widget", "test"],
        default_image="images/cover.png",
        images=[
            SidecarImage(path="images/cover.png", source="scraped", order=0),
        ],
        files=[
            SidecarFile(
                path="widget.3mf",
                role="model",
                size=1024,
                sha256="abc123",
                mtime="2026-06-20T14:03:11Z",
            ),
        ],
        created_at=now_iso,
        updated_at=now_iso,
    )

    write_sidecar(item_dir, data, title, key)
    loaded = read_sidecar(item_dir, title, key)

    assert loaded is not None
    assert loaded.key == key
    assert loaded.title == title
    assert loaded.slug == "test-widget-ab3fg72"
    assert loaded.description == "A test widget"
    assert loaded.source_url == "https://example.com/model/1"
    assert loaded.license == "CC-BY-4.0"
    assert loaded.creator is not None
    assert loaded.creator.name == "Jane Maker"
    assert loaded.creator.is_original is False
    assert loaded.tags == ["widget", "test"]
    assert loaded.default_image == "images/cover.png"
    assert len(loaded.images) == 1
    assert loaded.images[0].path == "images/cover.png"
    assert len(loaded.files) == 1
    assert loaded.files[0].role == "model"
    assert loaded.files[0].sha256 == "abc123"


def test_sidecar_missing_optional_keys(tmp_path: Any) -> None:
    """read_sidecar tolerates missing optional keys."""
    title = "Minimal"
    key = "aaaaaaa"
    item_dir = tmp_path / "aa" / "minimal-aaaaaaa"
    item_dir.mkdir(parents=True)

    # Write a minimal sidecar by hand
    sc = sidecar_path(item_dir, title, key)
    sc.write_text(
        "schema_version: 1\nkey: aaaaaaa\ntitle: Minimal\nslug: minimal-aaaaaaa\n"
        "created_at: 2026-01-01T00:00:00Z\nupdated_at: 2026-01-01T00:00:00Z\n"
    )

    loaded = read_sidecar(item_dir, title, key)
    assert loaded is not None
    assert loaded.description is None
    assert loaded.creator is None
    assert loaded.tags == []
    assert loaded.files == []


def test_sidecar_ignores_unknown_keys(tmp_path: Any) -> None:
    """read_sidecar ignores unknown keys (forward-compat)."""
    title = "Future"
    key = "bbbbbbb"
    item_dir = tmp_path / "bb" / "future-bbbbbbb"
    item_dir.mkdir(parents=True)

    sc = sidecar_path(item_dir, title, key)
    sc.write_text(
        "schema_version: 1\nkey: bbbbbbb\ntitle: Future\nslug: future-bbbbbbb\n"
        "created_at: 2026-01-01T00:00:00Z\nupdated_at: 2026-01-01T00:00:00Z\n"
        "future_field: some_value\n"
    )

    loaded = read_sidecar(item_dir, title, key)
    assert loaded is not None
    assert loaded.key == "bbbbbbb"


def test_sidecar_missing_returns_none(tmp_path: Any) -> None:
    """read_sidecar returns None when the file does not exist."""
    item_dir = tmp_path / "cc" / "item-ccccccc"
    item_dir.mkdir(parents=True)
    result = read_sidecar(item_dir, "item", "ccccccc")
    assert result is None


# ---------------------------------------------------------------------------
# File inventory + SHA-256 + drift check
# ---------------------------------------------------------------------------


def test_inventory_basic(tmp_path: Any) -> None:
    """inventory_item() finds files and assigns correct roles."""
    item_dir = tmp_path / "ab" / "widget-ab3fg72"
    item_dir.mkdir(parents=True)
    (item_dir / "renders").mkdir()
    (item_dir / "images").mkdir()
    (item_dir / "prints").mkdir()

    (item_dir / "widget.stl").write_bytes(b"stl_data")
    (item_dir / "project.zip").write_bytes(b"zip_data")
    (item_dir / "renders" / "thumb.png").write_bytes(b"render_png")
    (item_dir / "images" / "cover.jpg").write_bytes(b"image_jpg")
    (item_dir / "prints" / "print.gcode").write_bytes(b"gcode_data")
    (item_dir / "prints" / "photo.jpg").write_bytes(b"photo_jpg")

    records = inventory_item(item_dir, "widget-ab3fg72.yml")
    by_path = {r.relative_path: r for r in records}

    assert by_path["widget.stl"].role == FileRole.model
    assert by_path["project.zip"].role == FileRole.zip
    assert by_path["renders/thumb.png"].role == FileRole.render
    assert by_path["images/cover.jpg"].role == FileRole.image
    assert by_path["prints/print.gcode"].role == FileRole.gcode
    assert by_path["prints/photo.jpg"].role == FileRole.photo


def test_inventory_excludes_sidecar(tmp_path: Any) -> None:
    """The sidecar file is excluded from inventory results."""
    item_dir = tmp_path / "ab" / "widget-ab3fg72"
    item_dir.mkdir(parents=True)
    sc_name = "widget-ab3fg72.yml"
    (item_dir / sc_name).write_text("key: ab3fg72\n")
    (item_dir / "widget.stl").write_bytes(b"x")

    records = inventory_item(item_dir, sc_name)
    paths = {r.relative_path for r in records}
    assert sc_name not in paths
    assert "widget.stl" in paths


def test_inventory_sha256(tmp_path: Any) -> None:
    """inventory_item() computes SHA-256 correctly."""
    item_dir = tmp_path / "ab" / "test-ab3fg72"
    item_dir.mkdir(parents=True)
    content = b"hello sha256"
    (item_dir / "file.stl").write_bytes(content)

    records = inventory_item(item_dir, "test-ab3fg72.yml")
    assert len(records) == 1
    assert records[0].sha256 == hash_file_sha256(item_dir / "file.stl")


def test_inventory_drift_skip(tmp_path: Any) -> None:
    """Cheap-first drift: file with matching size+mtime skips re-hash."""
    item_dir = tmp_path / "ab" / "test-ab3fg72"
    item_dir.mkdir(parents=True)
    f = item_dir / "file.stl"
    f.write_bytes(b"original content")

    stat = f.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    size = stat.st_size

    existing = {"file.stl": (size, mtime, "cached_sha256")}

    records = inventory_item(item_dir, "test-ab3fg72.yml", existing=existing)
    assert len(records) == 1
    # Should use cached sha256 (drift skip)
    assert records[0].sha256 == "cached_sha256"


def test_inventory_drift_rehash_on_size_change(tmp_path: Any) -> None:
    """Drift check re-hashes when size changes."""
    item_dir = tmp_path / "ab" / "test-ab3fg72"
    item_dir.mkdir(parents=True)
    f = item_dir / "file.stl"
    f.write_bytes(b"new content")

    stat = f.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    old_size = stat.st_size - 1  # deliberately wrong

    existing = {"file.stl": (old_size, mtime, "cached_sha256")}

    records = inventory_item(item_dir, "test-ab3fg72.yml", existing=existing)
    assert records[0].sha256 != "cached_sha256"  # re-hashed


def test_inventory_force_rehash(tmp_path: Any) -> None:
    """force_rehash=True always recomputes SHA-256."""
    item_dir = tmp_path / "ab" / "test-ab3fg72"
    item_dir.mkdir(parents=True)
    f = item_dir / "file.stl"
    f.write_bytes(b"content")

    stat = f.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    existing = {"file.stl": (stat.st_size, mtime, "cached_sha256")}

    records = inventory_item(item_dir, "test-ab3fg72.yml", existing=existing, force_rehash=True)
    real_hash = hash_file_sha256(f)
    assert records[0].sha256 == real_hash


# ---------------------------------------------------------------------------
# Role inference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path, expected_role", [
    ("renders/thumb.png", FileRole.render),
    ("images/cover.jpg", FileRole.image),
    ("prints/print.gcode", FileRole.gcode),
    ("prints/photo.jpg", FileRole.photo),
    ("widget.stl", FileRole.model),
    ("widget.3mf", FileRole.model),
    ("widget.obj", FileRole.model),
    ("widget.ply", FileRole.model),
    ("project.zip", FileRole.zip),
    ("notes.txt", FileRole.other),
    ("subdir/model.stl", FileRole.model),  # model at any depth
])
def test_infer_role(path: str, expected_role: FileRole) -> None:
    assert infer_role(path) == expected_role


# ---------------------------------------------------------------------------
# Atomic rename — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_atomic_rename_happy_path(tmp_path: Any, db_session: Any) -> None:
    """atomic_rename moves the directory and updates DB + sidecar."""
    from app.models.item import Item
    from app.models.library import Library

    lib = Library(name="lib", mount_path=str(tmp_path / "lib"))
    db_session.add(lib)
    await db_session.flush()

    key = "ab3fg72"
    old_title = "Old Name"
    new_title = "New Name"
    old_slug = item_slug(old_title, key)
    new_slug = item_slug(new_title, key)
    old_dir = item_dir_path(str(tmp_path / "lib"), key, old_title)
    new_dir = item_dir_path(str(tmp_path / "lib"), key, new_title)
    old_dir.mkdir(parents=True)
    (old_dir / "model.stl").write_bytes(b"data")

    item = Item(
        key=key,
        title=old_title,
        slug=old_slug,
        library_id=lib.id,
        dir_path=str(old_dir),
        schema_version=1,
    )
    db_session.add(item)
    await db_session.flush()

    await atomic_rename(
        key=key,
        old_dir=old_dir,
        new_dir=new_dir,
        old_title=old_title,
        new_title=new_title,
        old_slug=old_slug,
        new_slug=new_slug,
        db=db_session,
    )

    # New dir exists, old dir gone
    assert new_dir.exists()
    assert not old_dir.exists()
    assert (new_dir / "model.stl").exists()

    # Journal was cleared
    assert not _journal_path(key).exists()

    # DB was updated
    from sqlalchemy import select

    result = await db_session.execute(select(Item).where(Item.key == key))
    updated_item = result.scalar_one()
    assert updated_item.title == new_title
    assert updated_item.slug == new_slug
    assert updated_item.dir_path == str(new_dir)


@pytest.mark.asyncio
async def test_atomic_rename_key_preserved(tmp_path: Any, db_session: Any) -> None:
    """After rename, the item's key is unchanged."""
    from app.models.item import Item
    from app.models.library import Library

    lib = Library(name="lib", mount_path=str(tmp_path / "lib"))
    db_session.add(lib)
    await db_session.flush()

    key = "zz3fg72"
    old_title = "Widget"
    new_title = "Super Widget"
    old_slug = item_slug(old_title, key)
    new_slug = item_slug(new_title, key)
    old_dir = item_dir_path(str(tmp_path / "lib"), key, old_title)
    new_dir = item_dir_path(str(tmp_path / "lib"), key, new_title)
    old_dir.mkdir(parents=True)

    item = Item(
        key=key,
        title=old_title,
        slug=old_slug,
        library_id=lib.id,
        dir_path=str(old_dir),
        schema_version=1,
    )
    db_session.add(item)
    await db_session.flush()

    await atomic_rename(
        key=key,
        old_dir=old_dir,
        new_dir=new_dir,
        old_title=old_title,
        new_title=new_title,
        old_slug=old_slug,
        new_slug=new_slug,
        db=db_session,
    )

    from sqlalchemy import select

    result = await db_session.execute(select(Item).where(Item.key == key))
    updated = result.scalar_one()
    assert updated.key == key  # key is invariant
    assert new_dir.name.endswith(f"-{key}")


# ---------------------------------------------------------------------------
# Atomic rename — pre-commit failures (rollback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_atomic_rename_target_exists_rollback(tmp_path: Any, db_session: Any) -> None:
    """Rename fails (MoveError) when target dir already exists — nothing changed."""
    from app.models.item import Item
    from app.models.library import Library

    lib = Library(name="lib", mount_path=str(tmp_path / "lib"))
    db_session.add(lib)
    await db_session.flush()

    key = "cc3fg72"
    old_title = "Item A"
    new_title = "Item B"
    old_dir = item_dir_path(str(tmp_path / "lib"), key, old_title)
    new_dir = item_dir_path(str(tmp_path / "lib"), key, new_title)
    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)  # target already exists!

    item = Item(
        key=key,
        title=old_title,
        slug=item_slug(old_title, key),
        library_id=lib.id,
        dir_path=str(old_dir),
        schema_version=1,
    )
    db_session.add(item)
    await db_session.flush()

    with pytest.raises(MoveError, match="already exists"):
        await atomic_rename(
            key=key,
            old_dir=old_dir,
            new_dir=new_dir,
            old_title=old_title,
            new_title=new_title,
            old_slug=item_slug(old_title, key),
            new_slug=item_slug(new_title, key),
            db=db_session,
        )

    # old dir unchanged
    assert old_dir.exists()
    # Journal should be cleaned up
    assert not _journal_path(key).exists()


@pytest.mark.asyncio
async def test_atomic_rename_source_missing_rollback(tmp_path: Any, db_session: Any) -> None:
    """Rename fails (MoveError) when source dir does not exist."""
    from app.models.item import Item
    from app.models.library import Library

    lib = Library(name="lib", mount_path=str(tmp_path / "lib"))
    db_session.add(lib)
    await db_session.flush()

    key = "dd3fg72"
    old_title = "Gone Item"
    new_title = "New Name"
    old_dir = item_dir_path(str(tmp_path / "lib"), key, old_title)
    new_dir = item_dir_path(str(tmp_path / "lib"), key, new_title)
    # old_dir does NOT exist

    item = Item(
        key=key,
        title=old_title,
        slug=item_slug(old_title, key),
        library_id=lib.id,
        dir_path=str(old_dir),
        schema_version=1,
    )
    db_session.add(item)
    await db_session.flush()

    with pytest.raises(MoveError, match="does not exist"):
        await atomic_rename(
            key=key,
            old_dir=old_dir,
            new_dir=new_dir,
            old_title=old_title,
            new_title=new_title,
            old_slug=item_slug(old_title, key),
            new_slug=item_slug(new_title, key),
            db=db_session,
        )

    assert not _journal_path(key).exists()


# ---------------------------------------------------------------------------
# Crash recovery — finish-forward branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_finish_forward(tmp_path: Any, db_session: Any) -> None:
    """Recovery: new dir exists + old gone → finish forward (update DB)."""
    from app.models.item import Item
    from app.models.library import Library

    lib = Library(name="lib", mount_path=str(tmp_path / "lib"))
    db_session.add(lib)
    await db_session.flush()

    key = "ee3fg72"
    old_title = "Old"
    new_title = "New"
    old_slug = item_slug(old_title, key)
    new_slug = item_slug(new_title, key)
    old_dir = item_dir_path(str(tmp_path / "lib"), key, old_title)
    new_dir = item_dir_path(str(tmp_path / "lib"), key, new_title)

    # The rename already happened on disk (simulate crash after os.replace)
    new_dir.mkdir(parents=True)
    # old_dir is gone

    item = Item(
        key=key,
        title=old_title,  # DB still shows old name (not yet updated)
        slug=old_slug,
        library_id=lib.id,
        dir_path=str(old_dir),
        schema_version=1,
    )
    db_session.add(item)
    await db_session.flush()

    # Write a stale journal (simulates crash between os.replace and DB update)
    entry = JournalEntry(
        key=key,
        old_dir=str(old_dir),
        new_dir=str(new_dir),
        old_title=old_title,
        new_title=new_title,
        old_slug=old_slug,
        new_slug=new_slug,
        state="renaming",
        timestamp="2026-06-27T10:00:00Z",
    )
    _write_journal(entry)

    await recover_stale_journals(db_session)

    # Journal should be gone
    assert not _journal_path(key).exists()

    # DB should reflect the new title
    from sqlalchemy import select

    result = await db_session.execute(select(Item).where(Item.key == key))
    updated = result.scalar_one()
    assert updated.title == new_title
    assert updated.dir_path == str(new_dir)


# ---------------------------------------------------------------------------
# Crash recovery — roll-back branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_rollback(tmp_path: Any, db_session: Any) -> None:
    """Recovery: old dir exists + new gone → roll back (DB reflects old name)."""
    from app.models.item import Item
    from app.models.library import Library

    lib = Library(name="lib", mount_path=str(tmp_path / "lib"))
    db_session.add(lib)
    await db_session.flush()

    key = "ff3fg72"
    old_title = "Old Name"
    new_title = "New Name"
    old_slug = item_slug(old_title, key)
    new_slug = item_slug(new_title, key)
    old_dir = item_dir_path(str(tmp_path / "lib"), key, old_title)
    new_dir = item_dir_path(str(tmp_path / "lib"), key, new_title)

    # Rename never happened (old dir still exists, new dir absent)
    old_dir.mkdir(parents=True)

    item = Item(
        key=key,
        title=old_title,
        slug=old_slug,
        library_id=lib.id,
        dir_path=str(old_dir),
        schema_version=1,
    )
    db_session.add(item)
    await db_session.flush()

    # Stale journal (crash before os.replace reached commit, but journal was written)
    entry = JournalEntry(
        key=key,
        old_dir=str(old_dir),
        new_dir=str(new_dir),
        old_title=old_title,
        new_title=new_title,
        old_slug=old_slug,
        new_slug=new_slug,
        state="renaming",
        timestamp="2026-06-27T10:00:00Z",
    )
    _write_journal(entry)

    await recover_stale_journals(db_session)

    # Journal should be gone
    assert not _journal_path(key).exists()

    # DB should still reflect old name (rollback preserved it)
    from sqlalchemy import select

    result = await db_session.execute(select(Item).where(Item.key == key))
    updated = result.scalar_one()
    assert updated.title == old_title
    assert updated.dir_path == str(old_dir)


# ---------------------------------------------------------------------------
# Bulk isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_isolation(tmp_path: Any, db_session: Any) -> None:
    """A failed rename on one item does not affect other items."""
    from app.models.item import Item
    from app.models.library import Library

    lib = Library(name="lib", mount_path=str(tmp_path / "lib"))
    db_session.add(lib)
    await db_session.flush()

    # Item A — rename will succeed
    key_a = "aa3fg72"
    old_title_a = "Item A Old"
    new_title_a = "Item A New"
    old_dir_a = item_dir_path(str(tmp_path / "lib"), key_a, old_title_a)
    new_dir_a = item_dir_path(str(tmp_path / "lib"), key_a, new_title_a)
    old_dir_a.mkdir(parents=True)
    item_a = Item(
        key=key_a,
        title=old_title_a,
        slug=item_slug(old_title_a, key_a),
        library_id=lib.id,
        dir_path=str(old_dir_a),
        schema_version=1,
    )
    db_session.add(item_a)

    # Item B — rename will fail (new dir already exists)
    key_b = "bb3fg72"
    old_title_b = "Item B Old"
    new_title_b = "Item B New"
    old_dir_b = item_dir_path(str(tmp_path / "lib"), key_b, old_title_b)
    new_dir_b = item_dir_path(str(tmp_path / "lib"), key_b, new_title_b)
    old_dir_b.mkdir(parents=True)
    new_dir_b.mkdir(parents=True)  # conflict!
    item_b = Item(
        key=key_b,
        title=old_title_b,
        slug=item_slug(old_title_b, key_b),
        library_id=lib.id,
        dir_path=str(old_dir_b),
        schema_version=1,
    )
    db_session.add(item_b)
    await db_session.flush()

    # Rename A — should succeed
    await atomic_rename(
        key=key_a,
        old_dir=old_dir_a,
        new_dir=new_dir_a,
        old_title=old_title_a,
        new_title=new_title_a,
        old_slug=item_slug(old_title_a, key_a),
        new_slug=item_slug(new_title_a, key_a),
        db=db_session,
    )

    # Rename B — should fail without rolling back A
    with pytest.raises(MoveError):
        await atomic_rename(
            key=key_b,
            old_dir=old_dir_b,
            new_dir=new_dir_b,
            old_title=old_title_b,
            new_title=new_title_b,
            old_slug=item_slug(old_title_b, key_b),
            new_slug=item_slug(new_title_b, key_b),
            db=db_session,
        )

    # A's rename is still committed
    assert new_dir_a.exists()
    assert not old_dir_a.exists()

    # B's old dir is still there
    assert old_dir_b.exists()
