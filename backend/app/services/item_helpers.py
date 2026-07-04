"""Shared item helpers — extracted from items.py for reuse by import sessions and worker."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.file import File
from ..models.image import Image, ImageSource
from ..models.item import Item
from ..models.tag import ItemTag, Tag, TagStatus
from ..storage.sidecar import SidecarFile, SidecarImage, build_sidecar, write_sidecar

log = logging.getLogger(__name__)


async def _get_or_create_tag(
    db: AsyncSession,
    name: str,
    status: TagStatus = TagStatus.active,
) -> Tag:
    """Get a tag by name or create it if absent.

    The *status* parameter controls the status assigned to **newly-created** tags
    only — it has no effect when the tag already exists.  Callers on the import
    path pass ``status=TagStatus.pending`` so freshly-minted tags enter the admin
    approval queue instead of becoming immediately canonical.
    """
    result = await db.execute(select(Tag).where(Tag.name == name))
    tag = result.scalar_one_or_none()
    if tag is None:
        tag = Tag(name=name, status=status)
        db.add(tag)
        await db.flush()
    return tag


async def _attach_tags(
    db: AsyncSession,
    item: Item,
    tag_names: list[str],
    new_tag_status: TagStatus = TagStatus.active,
) -> None:
    """Replace the item's tags with the given list.

    *new_tag_status* is forwarded to :func:`_get_or_create_tag` and only
    affects tags that do not yet exist in the database.  Import-path callers
    pass ``new_tag_status=TagStatus.pending`` so any brand-new tags are queued
    for admin approval rather than becoming active immediately.
    """
    # Remove existing
    await db.execute(
        ItemTag.__table__.delete().where(ItemTag.item_id == item.id)  # type: ignore[attr-defined]
    )
    for name in tag_names:
        name = name.strip()
        if not name:
            continue
        tag = await _get_or_create_tag(db, name, status=new_tag_status)
        db.add(ItemTag(item_id=item.id, tag_id=tag.id))
    await db.flush()


async def _update_search_vector(
    db: AsyncSession,
    item_id: int,
    title: str,
    description: str | None,
    tag_names: list[str],
) -> None:
    """Maintain the items.search_vector tsvector column.

    The vector is built from title (weighted A), description (weighted B), and
    tag names (weighted C) so title matches rank highest.  Called after any write
    that changes these fields.

    Uses raw SQL to avoid SQLAlchemy type-mapping complexity with TSVECTOR.
    """
    parts: list[str] = [title]
    if description:
        parts.append(description)
    if tag_names:
        parts.append(" ".join(tag_names))
    combined = " ".join(parts)
    await db.execute(
        sa.text(
            "UPDATE items SET search_vector = to_tsvector('english', :text)"
            " WHERE id = :id"
        ),
        {"text": combined, "id": item_id},
    )


async def _build_sidecar_data(
    db: AsyncSession,
    item: Item,
) -> tuple[list[str], list[SidecarFile], list[SidecarImage], str | None]:
    """Return (tag_names, sidecar_files, sidecar_images, default_image_path)."""
    tag_result = await db.execute(
        select(Tag).join(ItemTag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id == item.id)
    )
    tags = [t.name for t in tag_result.scalars().all()]

    file_result = await db.execute(
        select(File).where(File.item_id == item.id)
    )
    sidecar_files = [
        SidecarFile(
            path=f.path,
            role=f.role.value,
            size=f.size,
            sha256=f.sha256,
            mtime=f.mtime.strftime("%Y-%m-%dT%H:%M:%SZ") if f.mtime else None,
        )
        for f in file_result.scalars().all()
    ]

    img_result = await db.execute(
        select(Image).where(Image.item_id == item.id).order_by(Image.order)
    )
    images_list = img_result.scalars().all()
    # Renders and embedded thumbnails are derived/regenerable — exclude them
    # from the sidecar so it stays portable (renders are regenerated from mesh;
    # embedded thumbnails are regenerated from the portable 3MF on scan).
    _SIDECAR_EXCLUDED = {ImageSource.render, ImageSource.embedded}
    sidecar_images = [
        SidecarImage(path=img.path, source=img.source.value, order=img.order)
        for img in images_list
        if img.source not in _SIDECAR_EXCLUDED
    ]
    default_img = next((img.path for img in images_list if img.is_default), None)

    return tags, sidecar_files, sidecar_images, default_img


async def _write_item_sidecar(db: AsyncSession, item: Item) -> None:
    """Write (or overwrite) the sidecar for an item."""
    # created_at / updated_at are server-generated (server_default / onupdate), so a
    # preceding flush EXPIRES them. build_sidecar() reads them synchronously, which
    # would trigger an illegal lazy reload in the async session
    # (MissingGreenlet: "greenlet_spawn has not been called"). Reload just these two
    # scalars here, in the async context, before the sync build. We scope to these
    # attribute names so already-loaded relationships (e.g. item.creator) stay intact.
    await db.refresh(item, attribute_names=["created_at", "updated_at"])
    tags, files, images, default_img = await _build_sidecar_data(db, item)
    data = build_sidecar(
        item, tags=tags, files=files, images=images, default_image=default_img
    )
    item_dir = Path(item.dir_path)
    write_sidecar(item_dir, data, item.title, item.key)


# Small delay applied to background jobs so the caller's transaction — which
# holds the queued Job row and, on the create/import path, the not-yet-committed
# item that row FKs — commits before the worker can pop the job and claim the
# row.  See job_tracker.claim_or_create_job for the full race rationale (#20).
_ENQUEUE_DEFER_S = 1.0


async def _write_queued_row_and_enqueue(
    item_id: int,
    *,
    pool: ArqRedis,
    db: AsyncSession | None,
    task: str,
    job_type: str,
    enqueue_kwargs: dict[str, Any] | None = None,
) -> None:
    """Write a ``queued`` Job row (when *db* is given) and enqueue *task*.

    Issue #20/#30: a Job row is now created at **enqueue** time (status
    ``queued``) so backlogged work is visible before any worker starts it.  We
    self-assign the arq job id so the queued row and the arq job agree on it; the
    worker later claims that exact row (:func:`claim_or_create_job`).

    Fully fire-and-forget: the row write (isolated in a SAVEPOINT so a failure
    cannot poison the caller's transaction) and the enqueue are independently
    guarded — neither may block or roll back item creation/rescan.  When *db* is
    None (a caller that cannot supply a session) we simply enqueue without a
    queued row; the worker's claim-or-create still tracks the job.
    """
    arq_job_id = uuid.uuid4().hex
    row_written = False

    if db is not None:
        try:
            from ..models.job import Job  # noqa: PLC0415

            async with db.begin_nested():
                db.add(
                    Job(
                        type=job_type,
                        status="queued",
                        payload={"item_id": item_id},
                        item_id=item_id,
                        arq_job_id=arq_job_id,
                    )
                )
                await db.flush()
            row_written = True
        except Exception:
            log.exception(
                "%s: failed to write queued Job row for item %s", task, item_id
            )

    kwargs: dict[str, Any] = {"_defer_by": _ENQUEUE_DEFER_S}
    # Only pin the arq job id when the queued row was written, so the worker's
    # ctx["job_id"] matches the row it must claim.  If the row write failed we let
    # arq assign its own id and the worker falls back to inserting a running row.
    if row_written:
        kwargs["_job_id"] = arq_job_id
    if enqueue_kwargs:
        kwargs.update(enqueue_kwargs)

    try:
        await pool.enqueue_job(task, item_id, **kwargs)
        log.debug("%s: enqueued for item %s (queued_row=%s)", task, item_id, row_written)
    except Exception:
        log.exception("%s: failed to enqueue for item %s", task, item_id)


async def _enqueue_render(
    item_id: int,
    *,
    pool: ArqRedis,
    db: AsyncSession | None = None,
    model_extensions: list[str] | None = None,
) -> None:
    """Fire-and-forget: enqueue a render_item arq task for an item.

    Failure to enqueue (e.g. Redis not available) is logged but does NOT
    propagate — it must never block item creation or rescan.

    The "off" short-circuit here reads the env/config setting only (not the DB
    render.mode setting).  render_item is the single authoritative gate: it reads
    the DB setting first and enforces all render modes before creating a Job row.

    Args:
        item_id:          DB id of the item.
        model_extensions: Optional list of model file extensions for the item
                          (e.g. ['.3mf', '.stl']).  When all extensions are .3mf,
                          rendering is skipped entirely — 3MF files use embedded
                          slicer thumbnails extracted by the analyze task instead.
                          Pass None to always enqueue (the render task will skip
                          .3mf files individually).
    """
    if settings.RENDER_MODE == "off":
        log.debug("_enqueue_render: RENDER_MODE=off — not enqueuing render for item %s", item_id)
        return

    # Skip enqueueing if all model files are .3mf (no renderable geometry)
    if model_extensions is not None:
        renderable = [e for e in model_extensions if e.lower() not in (".3mf",)]
        if not renderable and model_extensions:
            log.debug(
                "_enqueue_render: all model files are .3mf — skipping render for item %s",
                item_id,
            )
            return

    await _write_queued_row_and_enqueue(
        item_id, pool=pool, db=db, task="render_item", job_type="render"
    )


async def _enqueue_analyze(
    item_id: int, *, pool: ArqRedis, db: AsyncSession | None = None
) -> None:
    """Fire-and-forget: enqueue analyze_item alongside render on item events.

    Phase 16: called on item create / file change / per-item Rescan.
    Issue #30: writes a ``queued`` Job row (type=analyze) so mesh-analysis work
    is visible before and while it runs.  Never blocks item creation.
    """
    await _write_queued_row_and_enqueue(
        item_id, pool=pool, db=db, task="analyze_item", job_type="analyze"
    )


async def _enqueue_extract_archives(
    item_id: int, *, pool: ArqRedis, db: AsyncSession | None = None
) -> None:
    """Fire-and-forget: enqueue extract_archives for an item that contains ZIPs.

    Phase B (render-rework-B): called on import-session commit when the item
    contains at least one role=zip file.  Never blocks item creation.
    """
    await _write_queued_row_and_enqueue(
        item_id,
        pool=pool,
        db=db,
        task="extract_archives",
        job_type="extract_archives",
    )
