"""OpenSCAD server-side render task — compile a .scad source into an STL (issue #46).

Optionally compiles each ``FileRole.source`` ``.scad`` file belonging to an item
into a derived STL, in an isolated subprocess (``scad_subprocess.py``), then
records it as a ``FileRole.model`` File row clearly linked back to its source
(``generated_from_file_id`` / ``generated_source_sha256``) and enqueues the
EXISTING render + analyze pipeline for it — no new preview code, the derived
STL is just another mesh asset the existing machinery already handles.

Compile-what's-uploaded-only (issue #46 first cut): every ``.scad`` source file
currently on the item is copied into the scratch workdir (preserving its
item-relative path) before compiling, so ``include``/``use`` between files
uploaded together resolves; an external library (BOSL2 etc.) that isn't
present is a normal compile failure, not a special case.

Failure handling is deliberately soft: a missing ``openscad`` binary, a bad
include, a timeout, or an OOM all fall back to "store source, skip preview" —
logged at info/warning, the Job still finishes 'succeeded' (this is expected,
not exceptional, for arbitrary uploaded .scad code), and no Issue is raised.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.file import File

log = logging.getLogger(__name__)


# Cap concurrent compiles (CPU-heavy CSG/CGAL evaluation, like render).  Lazy so
# the settings import stays deferred and the semaphore binds to the worker loop.
_scad_sem: asyncio.Semaphore | None = None


def _get_scad_sem() -> asyncio.Semaphore:
    global _scad_sem
    if _scad_sem is None:
        from app.config import settings  # noqa: PLC0415

        _scad_sem = asyncio.Semaphore(max(1, settings.SCAD_RENDER_CONCURRENCY))
    return _scad_sem


async def compile_scad_item(ctx: dict, item_id: int) -> None:
    """Arq entrypoint — throttle concurrent compiles, then compile."""
    async with _get_scad_sem():
        await _compile_scad_item_inner(ctx, item_id)


async def _claim_job(item_id: int, arq_job_id: str | None) -> object:
    from app.db import SessionLocal  # noqa: PLC0415
    from app.worker.job_tracker import claim_or_create_job  # noqa: PLC0415

    async with SessionLocal() as db:
        job_id = await claim_or_create_job(
            db,
            "scad_render",
            payload={"item_id": item_id},
            item_id=item_id,
            arq_job_id=arq_job_id,
        )
        await db.commit()
    return job_id


async def _compile_one(item_dir: Path, scad_file: File, all_source_files: list[File]) -> Path:
    """Compile one .scad File in a fresh scratch workdir; return the dest STL path.

    Copies every source file uploaded on the item into the workdir (preserving
    item-relative paths) so sibling includes resolve, compiles the target file,
    then copies the produced STL into ``<item_dir>/generated/<stem>.stl``
    (stable path — overwritten in place on recompile so render's sha-keyed
    cache naturally invalidates when the content changes).

    Raises ScadTimeout / ScadCompileError / FileNotFoundError on failure — the
    caller treats all of these as a soft "store source, skip preview" skip.
    """
    from app.config import settings  # noqa: PLC0415
    from app.worker.scad_subprocess import run_scad_compile_subprocess  # noqa: PLC0415

    workdir = Path(tempfile.mkdtemp(prefix="scad-compile-"))
    try:
        for src in all_source_files:
            src_path = item_dir / src.path
            if not src_path.exists():
                continue
            dst_path = workdir / src.path
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)

        target = workdir / scad_file.path
        if not target.exists():
            raise FileNotFoundError(f"source file missing on disk: {scad_file.path}")

        out_stl = workdir / f"{Path(scad_file.path).stem}.stl"

        await run_scad_compile_subprocess(
            target,
            out_stl,
            workdir=workdir,
            timeout_s=settings.SCAD_RENDER_TIMEOUT_S,
            mem_limit_mb=settings.SCAD_RENDER_MEM_LIMIT_MB,
            cpu_limit_s=settings.SCAD_RENDER_CPU_LIMIT_S,
        )

        generated_dir = item_dir / "generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        dest_path = generated_dir / f"{Path(scad_file.path).stem}.stl"
        shutil.copy2(out_stl, dest_path)
        return dest_path
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


async def _compile_scad_item_inner(ctx: dict, item_id: int) -> None:
    from datetime import UTC, datetime  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.file import File, FileRole  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.services.item_helpers import _enqueue_analyze, _enqueue_render  # noqa: PLC0415
    from app.storage.inventory import hash_file_sha256  # noqa: PLC0415
    from app.worker.job_tracker import finish_job  # noqa: PLC0415
    from app.worker.scad_subprocess import (  # noqa: PLC0415
        ScadCompileError,
        ScadTimeout,
        openscad_available,
    )

    job_id = await _claim_job(item_id, ctx.get("job_id"))

    async def _finish(
        succeeded: bool, error: str | None = None, log_text: str | None = None
    ) -> None:
        try:
            async with SessionLocal() as db:
                await finish_job(db, job_id, succeeded=succeeded, error=error, log_text=log_text)
                await db.commit()
        except Exception:
            log.exception("compile_scad_item: failed to finalize job %s", job_id)

    try:
        async with SessionLocal() as db:
            item_result = await db.execute(sa.select(Item).where(Item.id == item_id))
            item = item_result.scalar_one_or_none()
            if item is None:
                await _finish(succeeded=False, error=f"Item {item_id} not found")
                return
            item_dir = Path(item.dir_path)

            files_result = await db.execute(sa.select(File).where(File.item_id == item_id))
            all_files = list(files_result.scalars().all())

        scad_files = [
            f for f in all_files
            if f.role == FileRole.source and Path(f.path).suffix.lower() == ".scad"
        ]
        generated_by_source: dict[int, File] = {
            f.generated_from_file_id: f
            for f in all_files
            if f.generated_from_file_id is not None
        }

        if not scad_files:
            await _finish(succeeded=True, log_text="No .scad source files to compile.")
            return

        if not openscad_available():
            log.info(
                "compile_scad_item: item=%s openscad binary not available — "
                "skipping compile (worker image needs rebuild)",
                item_id,
            )
            await _finish(
                succeeded=True,
                log_text="openscad binary not available — skipped (store source, no preview).",
            )
            return

        compiled: list[str] = []
        skipped: list[str] = []

        for scad_file in scad_files:
            existing = generated_by_source.get(scad_file.id)
            if (
                existing is not None
                and scad_file.sha256 is not None
                and existing.generated_source_sha256 == scad_file.sha256
            ):
                skipped.append(f"{scad_file.path} (up to date)")
                continue

            try:
                dest_path = await _compile_one(item_dir, scad_file, scad_files)
            except (ScadTimeout, ScadCompileError, FileNotFoundError) as exc:
                skipped.append(f"{scad_file.path}: {exc}")
                log.info("compile_scad_item: item=%s %s", item_id, exc)
                continue
            except Exception as exc:  # noqa: BLE001 — never let one bad .scad crash the worker
                skipped.append(f"{scad_file.path}: unexpected error: {exc}")
                log.warning(
                    "compile_scad_item: item=%s unexpected compile failure for %s: %s",
                    item_id, scad_file.path, exc,
                )
                continue

            rel_path = str(dest_path.relative_to(item_dir))
            stat = dest_path.stat()
            sha256 = hash_file_sha256(dest_path)
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)

            async with SessionLocal() as db:
                if existing is not None:
                    await db.execute(
                        sa.update(File)
                        .where(File.id == existing.id)
                        .values(
                            path=rel_path,
                            size=stat.st_size,
                            sha256=sha256,
                            mtime=mtime,
                            last_seen_size=stat.st_size,
                            last_seen_mtime=mtime,
                            generated_source_sha256=scad_file.sha256,
                            object_analysis=None,  # geometry changed — force re-analyze
                        )
                    )
                else:
                    db.add(
                        File(
                            item_id=item_id,
                            path=rel_path,
                            role=FileRole.model,
                            size=stat.st_size,
                            sha256=sha256,
                            mtime=mtime,
                            last_seen_size=stat.st_size,
                            last_seen_mtime=mtime,
                            generated_from_file_id=scad_file.id,
                            generated_source_sha256=scad_file.sha256,
                        )
                    )
                await db.commit()

            compiled.append(scad_file.path)
            log.info(
                "compile_scad_item: item=%s compiled %s -> %s",
                item_id, scad_file.path, rel_path,
            )

        if compiled:
            async with SessionLocal() as db:
                await _enqueue_analyze(item_id, pool=ctx.get("redis"), db=db)
                await _enqueue_render(item_id, pool=ctx.get("redis"), db=db)
                await db.commit()

        log_lines = []
        if compiled:
            log_lines.append(f"Compiled: {', '.join(compiled)}")
        if skipped:
            log_lines.append(f"Skipped: {'; '.join(skipped)}")
        await _finish(succeeded=True, log_text="\n".join(log_lines) or "Nothing to compile.")

    except Exception as exc:
        log.exception("compile_scad_item: unexpected error for item %s", item_id)
        await _finish(succeeded=False, error=str(exc))
    except BaseException:
        log.error("compile_scad_item: cancelled/shutdown for item %s", item_id)
        await _finish(succeeded=False, error="worker stopped / cancelled")
        raise
