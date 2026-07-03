"""Print records API — Phase 7 (PRD §9).

CRUD + gcode/photo upload for print history records.

POST   /api/items/{key}/print-records                       → create
GET    /api/items/{key}/print-records                       → list
GET    /api/items/{key}/print-records/{record_id}           → get one
PATCH  /api/items/{key}/print-records/{record_id}           → update
DELETE /api/items/{key}/print-records/{record_id}           → delete
POST   /api/items/{key}/print-records/{record_id}/gcode     → upload gcode, parse metadata
POST   /api/items/{key}/print-records/{record_id}/photo     → upload print photo
GET    /api/print-stats                                     → aggregate stats (§9.2)

Auth: all endpoints require authentication (session cookie or API key Bearer).
      Owner or admin can create/edit/delete.  Listing respects visibility:
        - Authenticated owner/admin: all records (public + private).
        - Via public share endpoint: public-only (handled in shares.py).

§9.3: the API-key Bearer path makes it usable by external integrations (OctoPrint etc.)
      via the same create endpoint with Authorization: Bearer <key>.

Visibility values: "private" (default) | "public"
"""

import logging
import uuid
from datetime import UTC, datetime
from datetime import date as _Date
from pathlib import Path
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_current_user, get_db
from ..models.item import Item
from ..models.print_record import PrintRecord
from ..models.user import User, UserRole
from ..storage.gcode_parser import parse_gcode_file

log = logging.getLogger(__name__)

router = APIRouter(tags=["print-records"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PrintRecordIn(BaseModel):
    note: str | None = None
    visibility: str = "private"
    date: _Date | None = None
    printer: str | None = None
    material: str | None = None
    filament_color: str | None = None
    nozzle_diameter: float | None = None
    layer_height: float | None = None
    supports: bool | None = None
    success: bool | None = None
    rating: int | None = None


class PrintRecordPatch(BaseModel):
    note: str | None = None
    visibility: str | None = None
    date: _Date | None = None
    printer: str | None = None
    material: str | None = None
    filament_color: str | None = None
    nozzle_diameter: float | None = None
    layer_height: float | None = None
    supports: bool | None = None
    success: bool | None = None
    rating: int | None = None


class PrintRecordOut(BaseModel):
    id: int
    item_key: str
    note: str | None
    visibility: str
    date: _Date | None
    printer: str | None
    material: str | None
    filament_color: str | None
    nozzle_diameter: float | None
    layer_height: float | None
    supports: bool | None
    success: bool | None
    rating: int | None
    filament_length_mm: float | None
    filament_weight_g: float | None
    estimated_print_time_s: int | None
    gcode_file_path: str | None
    print_photo_path: str | None
    logged_by_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PrintStatsOut(BaseModel):
    total_prints: int
    success_count: int
    fail_count: int
    success_rate: float | None  # None when no success/fail data recorded
    total_filament_length_mm: float
    total_filament_weight_g: float
    total_print_time_s: int
    avg_print_time_s: float | None  # None when no timed records
    most_printed_items: list[dict]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_item_or_404(key: str, db: AsyncSession) -> Item:
    result = await db.execute(select(Item).where(Item.key == key))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    return item


async def _get_record_or_404(record_id: int, item_id: int, db: AsyncSession) -> PrintRecord:
    result = await db.execute(
        select(PrintRecord).where(
            PrintRecord.id == record_id,
            PrintRecord.item_id == item_id,
        )
    )
    rec = result.scalar_one_or_none()
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Print record not found."
        )
    return rec


def _record_to_out(rec: PrintRecord, item: Item) -> PrintRecordOut:
    return PrintRecordOut(
        id=rec.id,
        item_key=item.key,
        note=rec.note,
        visibility=rec.visibility,
        date=rec.date,
        printer=rec.printer,
        material=rec.material,
        filament_color=rec.filament_color,
        nozzle_diameter=rec.nozzle_diameter,
        layer_height=rec.layer_height,
        supports=rec.supports,
        success=rec.success,
        rating=rec.rating,
        filament_length_mm=rec.filament_length_mm,
        filament_weight_g=rec.filament_weight_g,
        estimated_print_time_s=rec.estimated_print_time_s,
        gcode_file_path=rec.gcode_file_path,
        print_photo_path=rec.print_photo_path,
        logged_by_id=rec.logged_by_id,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def _require_record_owner_or_admin(rec: PrintRecord, user: User) -> None:
    """Reject writes to a print record not owned by *user* (admins exempt).

    Read access is intentionally NOT gated per-user: within an authenticated
    household everyone shares an item's print history (the "private" visibility
    only hides a record from anonymous public-share viewers, filtered in
    shares.py). Write access, however, is restricted to the record's owner or an
    admin so one household member cannot edit/delete another's records.
    """
    if rec.logged_by_id != user.id and user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only modify your own print records.",
        )


def _validate_visibility(v: str) -> None:
    if v not in ("private", "public"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="visibility must be 'private' or 'public'",
        )


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.post("/api/items/{key}/print-records", response_model=PrintRecordOut, status_code=201)
async def create_print_record(
    key: str,
    body: PrintRecordIn,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrintRecordOut:
    """Create a print record for an item.

    Accessible via session cookie or API key Bearer (§9.3: OctoPrint integration).
    """
    _validate_visibility(body.visibility)
    item = await _get_item_or_404(key, db)

    rec = PrintRecord(
        item_id=item.id,
        logged_by_id=user.id,
        note=body.note,
        visibility=body.visibility,
        date=body.date,
        printer=body.printer,
        material=body.material,
        filament_color=body.filament_color,
        nozzle_diameter=body.nozzle_diameter,
        layer_height=body.layer_height,
        supports=body.supports,
        success=body.success,
        rating=body.rating,
    )
    db.add(rec)
    await db.flush()
    await db.refresh(rec)
    return _record_to_out(rec, item)


@router.get("/api/items/{key}/print-records", response_model=list[PrintRecordOut])
async def list_print_records(
    key: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    visibility: str | None = Query(None, description="Filter by 'public' or 'private'"),
) -> list[PrintRecordOut]:
    """List print records for an item.

    Admin or authenticated users see all records (public + private).
    Public-only view is served through the shares router (un-authenticated).
    """
    item = await _get_item_or_404(key, db)

    q = select(PrintRecord).where(PrintRecord.item_id == item.id)
    if visibility is not None:
        _validate_visibility(visibility)
        q = q.where(PrintRecord.visibility == visibility)
    q = q.order_by(PrintRecord.created_at.desc())

    result = await db.execute(q)
    records = list(result.scalars().all())
    return [_record_to_out(r, item) for r in records]


@router.get("/api/items/{key}/print-records/{record_id}", response_model=PrintRecordOut)
async def get_print_record(
    key: str,
    record_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrintRecordOut:
    """Get a single print record."""
    item = await _get_item_or_404(key, db)
    rec = await _get_record_or_404(record_id, item.id, db)
    return _record_to_out(rec, item)


@router.patch("/api/items/{key}/print-records/{record_id}", response_model=PrintRecordOut)
async def update_print_record(
    key: str,
    record_id: int,
    body: PrintRecordPatch,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrintRecordOut:
    """Update a print record (partial update)."""
    item = await _get_item_or_404(key, db)
    rec = await _get_record_or_404(record_id, item.id, db)
    _require_record_owner_or_admin(rec, user)

    if body.note is not None:
        rec.note = body.note
    if body.visibility is not None:
        _validate_visibility(body.visibility)
        rec.visibility = body.visibility
    if body.date is not None:
        rec.date = body.date
    if body.printer is not None:
        rec.printer = body.printer
    if body.material is not None:
        rec.material = body.material
    if body.filament_color is not None:
        rec.filament_color = body.filament_color
    if body.nozzle_diameter is not None:
        rec.nozzle_diameter = body.nozzle_diameter
    if body.layer_height is not None:
        rec.layer_height = body.layer_height
    if body.supports is not None:
        rec.supports = body.supports
    if body.success is not None:
        rec.success = body.success
    if body.rating is not None:
        rec.rating = body.rating

    rec.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(rec)
    return _record_to_out(rec, item)


@router.delete("/api/items/{key}/print-records/{record_id}", status_code=204)
async def delete_print_record(
    key: str,
    record_id: int,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a print record (does NOT delete attached files from disk)."""
    item = await _get_item_or_404(key, db)
    rec = await _get_record_or_404(record_id, item.id, db)
    _require_record_owner_or_admin(rec, user)
    await db.delete(rec)
    await db.flush()


# ---------------------------------------------------------------------------
# File upload endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/api/items/{key}/print-records/{record_id}/gcode",
    response_model=PrintRecordOut,
)
async def upload_gcode(
    key: str,
    record_id: int,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
) -> PrintRecordOut:
    """Upload a gcode file for a print record.

    The file is saved to {item_dir}/prints/{original_filename} (with UUID prefix
    to avoid collisions).  Metadata (filament, time) is parsed and stored on the
    record.  Best-effort parse — missing fields are left null.
    """
    item = await _get_item_or_404(key, db)
    rec = await _get_record_or_404(record_id, item.id, db)
    _require_record_owner_or_admin(rec, user)

    # Build destination path
    item_dir = Path(item.dir_path)
    prints_dir = item_dir / "prints"
    prints_dir.mkdir(parents=True, exist_ok=True)

    # Unique filename
    original = file.filename or "upload.gcode"
    stem = Path(original).stem
    suffix = Path(original).suffix.lower() or ".gcode"
    unique_name = f"{stem}-{uuid.uuid4().hex[:8]}{suffix}"
    dest = prints_dir / unique_name

    # Write file
    content = await file.read()
    dest.write_bytes(content)

    # Relative path for storage
    rel_path = str(dest.relative_to(item_dir))
    rec.gcode_file_path = rel_path

    # Parse gcode metadata (best-effort)
    try:
        meta = parse_gcode_file(dest)
        if meta.filament_length_mm is not None:
            rec.filament_length_mm = meta.filament_length_mm
        if meta.filament_weight_g is not None:
            rec.filament_weight_g = meta.filament_weight_g
        if meta.estimated_print_time_s is not None:
            rec.estimated_print_time_s = meta.estimated_print_time_s
    except Exception:
        log.exception(
            "gcode parse failed for record %s at %s — continuing without metadata",
            record_id,
            dest,
        )

    rec.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(rec)
    return _record_to_out(rec, item)


@router.post(
    "/api/items/{key}/print-records/{record_id}/photo",
    response_model=PrintRecordOut,
)
async def upload_print_photo(
    key: str,
    record_id: int,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
) -> PrintRecordOut:
    """Upload a print photo for a print record.

    Saved to {item_dir}/prints/photo-{uuid}.{ext}.
    """
    item = await _get_item_or_404(key, db)
    rec = await _get_record_or_404(record_id, item.id, db)
    _require_record_owner_or_admin(rec, user)

    item_dir = Path(item.dir_path)
    prints_dir = item_dir / "prints"
    prints_dir.mkdir(parents=True, exist_ok=True)

    original = file.filename or "photo.jpg"
    suffix = Path(original).suffix.lower() or ".jpg"
    unique_name = f"photo-{uuid.uuid4().hex[:12]}{suffix}"
    dest = prints_dir / unique_name

    content = await file.read()
    dest.write_bytes(content)

    rec.print_photo_path = str(dest.relative_to(item_dir))
    rec.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(rec)
    return _record_to_out(rec, item)


# ---------------------------------------------------------------------------
# Print stats (§9.2)
# ---------------------------------------------------------------------------


@router.get("/api/print-stats", response_model=PrintStatsOut)
async def get_print_stats(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit_most_printed: int = Query(default=10, ge=1, le=50),
) -> PrintStatsOut:
    """Aggregate print statistics across all items.

    Returns total prints, success/fail rates, filament totals, time totals,
    and a list of most-printed items.
    """
    # Total count
    total_result = await db.execute(
        sa.select(func.count(PrintRecord.id))
    )
    total_prints: int = total_result.scalar_one() or 0

    # Success / fail counts
    success_result = await db.execute(
        sa.select(func.count(PrintRecord.id)).where(
            PrintRecord.success.is_(True)
        )
    )
    success_count: int = success_result.scalar_one() or 0

    fail_result = await db.execute(
        sa.select(func.count(PrintRecord.id)).where(
            PrintRecord.success.is_(False)
        )
    )
    fail_count: int = fail_result.scalar_one() or 0

    # Success rate
    rated = success_count + fail_count
    success_rate: float | None = (success_count / rated) if rated > 0 else None

    # Filament totals
    filament_result = await db.execute(
        sa.select(
            func.coalesce(func.sum(PrintRecord.filament_length_mm), 0.0),
            func.coalesce(func.sum(PrintRecord.filament_weight_g), 0.0),
        )
    )
    fil_row = filament_result.one()
    total_filament_length_mm: float = float(fil_row[0])
    total_filament_weight_g: float = float(fil_row[1])

    # Print time totals
    time_result = await db.execute(
        sa.select(
            func.coalesce(func.sum(PrintRecord.estimated_print_time_s), 0),
            func.avg(PrintRecord.estimated_print_time_s),
        )
    )
    time_row = time_result.one()
    total_print_time_s: int = int(time_row[0])
    avg_print_time_s: float | None = (
        float(time_row[1]) if time_row[1] is not None else None
    )

    # Most-printed items
    most_printed_result = await db.execute(
        sa.select(
            PrintRecord.item_id,
            func.count(PrintRecord.id).label("cnt"),
        )
        .group_by(PrintRecord.item_id)
        .order_by(sa.desc("cnt"))
        .limit(limit_most_printed)
    )
    most_printed_rows = most_printed_result.all()

    # Fetch titles for those item IDs
    most_printed: list[dict] = []
    if most_printed_rows:
        from ..models.item import Item  # noqa: PLC0415

        item_ids = [r[0] for r in most_printed_rows]
        items_result = await db.execute(
            sa.select(Item.id, Item.key, Item.title).where(
                Item.id.in_(item_ids)
            )
        )
        items_map = {row[0]: (row[1], row[2]) for row in items_result.all()}

        for item_id, cnt in most_printed_rows:
            key_title = items_map.get(item_id)
            most_printed.append(
                {
                    "item_id": item_id,
                    "item_key": key_title[0] if key_title else None,
                    "title": key_title[1] if key_title else None,
                    "count": cnt,
                }
            )

    return PrintStatsOut(
        total_prints=total_prints,
        success_count=success_count,
        fail_count=fail_count,
        success_rate=success_rate,
        total_filament_length_mm=total_filament_length_mm,
        total_filament_weight_g=total_filament_weight_g,
        total_print_time_s=total_print_time_s,
        avg_print_time_s=avg_print_time_s,
        most_printed_items=most_printed,
    )
