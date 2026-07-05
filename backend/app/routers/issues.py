"""Issues endpoints — Phase 6 reconcile engine (PRD §8.3).

Admin:
  GET  /api/issues           → list issues (filter by status/type, paginate)
  GET  /api/issues/{id}      → issue detail
  POST /api/issues/{id}/action   → generic action handler (Phase 1+3)
  POST /api/issues/{id}/resolve  → mark resolved (legacy; kept for back-compat)
  POST /api/issues/{id}/ignore   → mark ignored (legacy; kept for back-compat)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..models.issue import Issue, IssueStatus, IssueType
from ..models.user import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/issues", tags=["issues"])

# ---------------------------------------------------------------------------
# Action → issue type mapping
# ---------------------------------------------------------------------------

#: Static action map — used as the base for ``actions_for()``.
#: For ``orphan`` this is the item_id=None default; ``actions_for`` overrides
#: it when item_id is set.
ISSUE_ACTIONS: dict[str, list[str]] = {
    IssueType.orphan:        ["import", "delete", "ignore"],        # item_id=None default
    IssueType.conflict:      ["keep_db", "keep_sidecar", "ignore"],
    IssueType.dead_link:     ["clear_source", "ignore"],
    IssueType.corruption:    ["accept", "ignore"],
    IssueType.missing_file:  ["remove_record", "ignore"],
    IssueType.extra_file:    ["ignore"],
    IssueType.sidecar_error: ["retry", "ignore"],
    IssueType.other:         ["ignore"],
}


def actions_for(issue: Any) -> list[str]:
    """Return the available actions for an issue, context-aware for orphan.

    For ``orphan`` issues the correct actions depend on whether a DB item exists:
    - item_id IS NULL  → directory with no DB row → ["import", "delete", "ignore"]
    - item_id IS SET   → DB item whose directory is missing → ["delete_item", "ignore"]

    All other types delegate to ``ISSUE_ACTIONS``.
    """
    if issue.issue_type == IssueType.orphan:
        if issue.item_id is None:
            return ["import", "delete", "ignore"]
        else:
            return ["delete_item", "ignore"]
    return list(ISSUE_ACTIONS.get(issue.issue_type, ["ignore"]))


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class IssueOut(BaseModel):
    id: int
    issue_type: str
    severity: str
    status: str
    item_id: int | None
    target_path: str | None
    detail: str
    suggested_action: str | None
    available_actions: list[str] = []
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def set_available_actions(self) -> IssueOut:
        """Compute available_actions from issue_type + item_id unless already set."""
        if not self.available_actions:
            self.available_actions = actions_for(self)
        return self


class PaginatedIssues(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[IssueOut]


class ActionRequest(BaseModel):
    action: str


class ActionResponse(BaseModel):
    issue: IssueOut
    import_session_id: str | None = None


# ---------------------------------------------------------------------------
# Action handlers
#
# Each ``_action_*`` implements exactly one arm of the ``issue_action`` dispatch.
# They share a uniform signature — ``(issue, db, now, admin)`` — so the endpoint
# can look one up by name and call it.  A handler mutates ``issue`` (and the DB)
# in place, raises ``HTTPException`` on precondition failures, and returns the
# ``import_session_id`` for the ``import`` action (``None`` for all others).
# ---------------------------------------------------------------------------

async def _action_ignore(
    issue: Issue, db: AsyncSession, now: datetime, admin: User
) -> str | None:
    """ignore (any type) — mark ignored (durable via reconcile dedup)."""
    issue.status = IssueStatus.ignored
    issue.resolved_at = now
    issue.updated_at = now
    await db.flush()
    return None


async def _action_delete(
    issue: Issue, db: AsyncSession, now: datetime, admin: User
) -> str | None:
    """delete (orphan, item_id null) — move ``target_path`` dir to trash."""
    target = issue.target_path
    if not target:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Issue has no target_path; cannot delete.",
        )
    target_dir = Path(target)
    if not target_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target directory does not exist: {target}",
        )

    from ..models.library import Library  # noqa: PLC0415

    libs_result = await db.execute(
        select(Library).where(Library.enabled.is_(True))
    )
    library_mounts = [Path(lib.mount_path) for lib in libs_result.scalars().all()]
    if not any(
        target_dir == mount or target_dir.is_relative_to(mount)
        for mount in library_mounts
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Target directory is not within a known library mount.",
        )

    from ..storage.journal import move_to_trash  # noqa: PLC0415

    try:
        import hashlib  # noqa: PLC0415

        key_slug = hashlib.sha256(target.encode()).hexdigest()[:12]
        move_to_trash(target_dir, key_slug)
    except OSError as exc:
        log.exception("issue_action: failed to move directory to trash for issue %s", issue.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to move directory to trash.",
        ) from exc

    issue.status = IssueStatus.resolved
    issue.resolved_at = now
    issue.updated_at = now
    await db.flush()
    return None


async def _action_import(
    issue: Issue, db: AsyncSession, now: datetime, admin: User
) -> str | None:
    """import (orphan, item_id null) — create an ImportSession for the orphan dir."""
    target = issue.target_path
    if not target:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Issue has no target_path; cannot import.",
        )
    target_dir = Path(target)
    if not target_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target directory does not exist: {target}",
        )

    from ..models.import_session import (  # noqa: PLC0415
        ImportSession,
        ImportSessionStatus,
        ImportSourceType,
    )
    from ..routers.import_sessions.helpers import reconcile_tags  # noqa: PLC0415
    from ..storage.sidecar import read_sidecar  # noqa: PLC0415

    suggested_title: str | None = None
    description: str | None = None
    source_url: str | None = None
    license_val: str | None = None
    source_site: str | None = None
    creator_name: str | None = None
    creator_profile_url: str | None = None
    tag_state: dict[str, Any] | None = None

    for yf in sorted(target_dir.glob("*.yml")):
        sc = read_sidecar(target_dir, yf.stem, yf.stem)
        if sc is not None:
            suggested_title = sc.title or None
            description = sc.description
            source_url = sc.source_url
            license_val = sc.license
            source_site = sc.source_site
            if sc.creator:
                creator_name = sc.creator.name
                creator_profile_url = sc.creator.profile_url
            if sc.tags:
                tag_state = await reconcile_tags(db, list(sc.tags))
            break
        else:
            try:
                import yaml  # noqa: PLC0415

                raw = yaml.safe_load(yf.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "schema_version" in raw:
                    suggested_title = str(raw["title"]) if raw.get("title") else None
                    description = raw.get("description")
                    src_d = raw.get("source") or {}
                    if isinstance(src_d, dict):
                        source_url = src_d.get("url")
                        license_val = src_d.get("license")
                        source_site = src_d.get("site")
                    creator_d = raw.get("creator")
                    if isinstance(creator_d, dict):
                        creator_name = creator_d.get("name")
                        creator_profile_url = creator_d.get("profile_url")
                    raw_tags = [str(t) for t in (raw.get("tags") or [])]
                    if raw_tags:
                        tag_state = await reconcile_tags(db, raw_tags)
                    break
            except Exception:
                pass

    if not suggested_title:
        suggested_title = target_dir.name

    session_obj = ImportSession(
        status=ImportSessionStatus.pending_wizard,
        source_type=ImportSourceType.inbox,
        inbox_folder=str(target_dir),
        suggested_title=suggested_title,
        confirmed_title=suggested_title,
        description=description,
        source_url=source_url,
        license=license_val,
        source_site=source_site,
        creator_name=creator_name,
        creator_profile_url=creator_profile_url,
        tag_state=tag_state,
        created_by_id=admin.id,
    )
    db.add(session_obj)
    await db.flush()
    await db.refresh(session_obj)
    import_session_id = str(session_obj.id)

    issue.status = IssueStatus.resolved
    issue.resolved_at = now
    issue.updated_at = now
    await db.flush()
    return import_session_id


async def _action_delete_item(
    issue: Issue, db: AsyncSession, now: datetime, admin: User
) -> str | None:
    """delete_item (orphan, item_id set) — dir gone; delete DB item row."""
    if issue.item_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="delete_item requires item_id to be set on the issue.",
        )
    from ..models.item import Item  # noqa: PLC0415

    item_result = await db.execute(select(Item).where(Item.id == issue.item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {issue.item_id} not found.",
        )
    # Directory is already gone; do NOT attempt trash move.
    # The cascade on the ORM handles Files, Images, ItemTags.
    await db.delete(item)
    await db.flush()

    issue.status = IssueStatus.resolved
    issue.resolved_at = now
    issue.updated_at = now
    await db.flush()
    return None


async def _action_remove_record(
    issue: Issue, db: AsyncSession, now: datetime, admin: User
) -> str | None:
    """remove_record (missing_file) — delete the File DB row for the missing path."""
    if issue.item_id is None or not issue.target_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="remove_record requires item_id and target_path on the issue.",
        )
    from ..models.file import File  # noqa: PLC0415
    from ..models.item import Item  # noqa: PLC0415

    item_result = await db.execute(select(Item).where(Item.id == issue.item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {issue.item_id} not found.",
        )
    # target_path is absolute; File.path is relative to item.dir_path
    try:
        rel_path = str(Path(issue.target_path).relative_to(Path(item.dir_path)))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"target_path {issue.target_path!r} is not under item dir "
                f"{item.dir_path!r}."
            ),
        ) from exc
    file_result = await db.execute(
        select(File).where(File.item_id == item.id, File.path == rel_path)
    )
    file_row = file_result.scalar_one_or_none()
    if file_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File record not found for path {rel_path!r} on item {issue.item_id}.",
        )
    await db.delete(file_row)
    await db.flush()

    issue.status = IssueStatus.resolved
    issue.resolved_at = now
    issue.updated_at = now
    await db.flush()
    return None


async def _action_accept(
    issue: Issue, db: AsyncSession, now: datetime, admin: User
) -> str | None:
    """accept (corruption) — recompute sha256 from disk and accept the new hash."""
    if issue.item_id is None or not issue.target_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="accept requires item_id and target_path on the issue.",
        )
    target_file = Path(issue.target_path)
    if not target_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File no longer exists at {issue.target_path!r}; cannot accept.",
        )
    from ..models.file import File  # noqa: PLC0415
    from ..models.item import Item  # noqa: PLC0415
    from ..storage.inventory import hash_file_sha256  # noqa: PLC0415

    item_result = await db.execute(select(Item).where(Item.id == issue.item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {issue.item_id} not found.",
        )
    try:
        rel_path = str(target_file.relative_to(Path(item.dir_path)))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"target_path {issue.target_path!r} is not under item dir "
                f"{item.dir_path!r}."
            ),
        ) from exc
    file_result = await db.execute(
        select(File).where(File.item_id == item.id, File.path == rel_path)
    )
    file_row = file_result.scalar_one_or_none()
    if file_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File record not found for path {rel_path!r} on item {issue.item_id}.",
        )
    new_hash = hash_file_sha256(target_file)
    file_row.sha256 = new_hash
    await db.flush()

    issue.status = IssueStatus.resolved
    issue.resolved_at = now
    issue.updated_at = now
    await db.flush()
    return None


async def _action_clear_source(
    issue: Issue, db: AsyncSession, now: datetime, admin: User
) -> str | None:
    """clear_source (dead_link) — clear item.source_url."""
    if issue.item_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="clear_source requires item_id on the issue.",
        )
    from ..models.item import Item  # noqa: PLC0415

    item_result = await db.execute(select(Item).where(Item.id == issue.item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {issue.item_id} not found.",
        )
    item.source_url = None
    item.updated_at = now
    await db.flush()

    issue.status = IssueStatus.resolved
    issue.resolved_at = now
    issue.updated_at = now
    await db.flush()
    return None


async def _action_keep_db(
    issue: Issue, db: AsyncSession, now: datetime, admin: User
) -> str | None:
    """keep_db (conflict) — rewrite sidecar from DB state."""
    if issue.item_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="keep_db requires item_id on the issue.",
        )
    from ..models.item import Item  # noqa: PLC0415
    from ..services.item_helpers import _write_item_sidecar  # noqa: PLC0415

    item_result = await db.execute(select(Item).where(Item.id == issue.item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {issue.item_id} not found.",
        )
    item_dir = Path(item.dir_path)
    if not item_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item directory does not exist: {item.dir_path}",
        )
    await _write_item_sidecar(db, item)

    issue.status = IssueStatus.resolved
    issue.resolved_at = now
    issue.updated_at = now
    await db.flush()
    return None


async def _action_keep_sidecar(
    issue: Issue, db: AsyncSession, now: datetime, admin: User
) -> str | None:
    """keep_sidecar (conflict) — apply on-disk sidecar fields to DB."""
    if issue.item_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="keep_sidecar requires item_id on the issue.",
        )
    from ..models.item import Item  # noqa: PLC0415
    from ..services.item_helpers import _write_item_sidecar  # noqa: PLC0415
    from ..storage.sidecar import read_sidecar  # noqa: PLC0415

    item_result = await db.execute(select(Item).where(Item.id == issue.item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {issue.item_id} not found.",
        )
    item_dir = Path(item.dir_path)
    if not item_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item directory does not exist: {item.dir_path}",
        )
    sc = read_sidecar(item_dir, item.title, item.key)
    if sc is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sidecar file could not be read; cannot apply keep_sidecar.",
        )
    # Apply sidecar fields to DB (title renames require separate atomic-rename
    # flow; skip title here, same as the reconcile auto-pull path).
    changed = False
    if sc.description != item.description:
        item.description = sc.description
        changed = True
    if sc.source_url != item.source_url:
        item.source_url = sc.source_url
        changed = True
    if sc.source_site != item.source_site:
        item.source_site = sc.source_site
        changed = True
    if sc.license != item.license:
        item.license = sc.license
        changed = True
    if changed:
        item.updated_at = now
        await db.flush()
    # Re-write sidecar to stamp the new updated_at so next reconcile sees no drift.
    await _write_item_sidecar(db, item)

    issue.status = IssueStatus.resolved
    issue.resolved_at = now
    issue.updated_at = now
    await db.flush()
    return None


async def _action_retry(
    issue: Issue, db: AsyncSession, now: datetime, admin: User
) -> str | None:
    """retry (sidecar_error) — re-run reconcile for the item; resolve if clean."""
    if issue.item_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="retry requires item_id on the issue.",
        )
    from ..models.item import Item  # noqa: PLC0415
    from ..worker.reconcile import load_mode_settings, reconcile_one_item  # noqa: PLC0415

    item_result = await db.execute(select(Item).where(Item.id == issue.item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {issue.item_id} not found.",
        )
    mode_settings = await load_mode_settings(db)
    # Use auto mode so the retry actually applies fixes rather than queuing them.
    mode_settings = {**mode_settings, "sidecar_sync": "auto", "file_changes": "auto"}
    recon = await reconcile_one_item(
        db, item, mode_settings=mode_settings, source="issue_retry"
    )
    issue.updated_at = now
    if not recon.errors:
        issue.status = IssueStatus.resolved
        issue.resolved_at = now
    else:
        # Leave open; update detail with latest error
        issue.detail = f"Retry attempt failed: {'; '.join(recon.errors)}"
    await db.flush()
    return None


#: Dispatch table — every action returned by ``actions_for`` maps to one handler.
_ACTION_DISPATCH = {
    "ignore": _action_ignore,
    "delete": _action_delete,
    "import": _action_import,
    "delete_item": _action_delete_item,
    "remove_record": _action_remove_record,
    "accept": _action_accept,
    "clear_source": _action_clear_source,
    "keep_db": _action_keep_db,
    "keep_sidecar": _action_keep_sidecar,
    "retry": _action_retry,
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedIssues)
async def list_issues(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    issue_type: str | None = Query(default=None),
    item_id: int | None = Query(default=None),
) -> PaginatedIssues:
    """List issues with optional filtering."""
    q = select(Issue)
    if status_filter:
        q = q.where(Issue.status == status_filter)
    if issue_type:
        q = q.where(Issue.issue_type == issue_type)
    if item_id is not None:
        q = q.where(Issue.item_id == item_id)

    count_q = select(sa.func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * per_page
    rows_result = await db.execute(
        q.order_by(Issue.created_at.desc()).offset(offset).limit(per_page)
    )
    rows = list(rows_result.scalars().all())

    return PaginatedIssues(
        total=total,
        page=page,
        per_page=per_page,
        items=[IssueOut.model_validate(r) for r in rows],
    )


@router.get("/{issue_id}", response_model=IssueOut)
async def get_issue(
    issue_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IssueOut:
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found.")
    return IssueOut.model_validate(issue)


@router.post("/{issue_id}/action", response_model=ActionResponse)
async def issue_action(
    issue_id: int,
    body: ActionRequest,
    admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ActionResponse:
    """Perform a corrective action on an issue.

    Available actions are context-aware (see ``actions_for``).  A 422 is
    returned for actions not in the issue's ``available_actions``.  Each action
    is implemented by a dedicated ``_action_*`` handler; this endpoint validates
    the action then dispatches to it.

    Phase 1 actions:
      ``ignore``       — any type: mark ignored (durable via reconcile dedup).
      ``delete``       — orphan (item_id null): move ``target_path`` dir to trash.
      ``import``       — orphan (item_id null): create an ImportSession for the orphan
                         directory, prefilled from its sidecar if present.

    Phase 3 additions:
      ``delete_item``  — orphan (item_id set): delete the DB Item row; dir is already
                         gone so no trash move is attempted.
      ``remove_record``— missing_file: delete the File DB row for the missing path.
      ``accept``       — corruption: recompute sha256 from disk and accept the new hash.
      ``clear_source`` — dead_link: clear item.source_url.
      ``keep_db``      — conflict: rewrite sidecar from DB state.
      ``keep_sidecar`` — conflict: apply on-disk sidecar fields to DB.
      ``retry``        — sidecar_error: re-run reconcile for the item; resolve if clean.
    """
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found.")

    available = actions_for(issue)
    if body.action not in available:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Action {body.action!r} is not available for issue type "
                f"{issue.issue_type!r}. Available: {available}"
            ),
        )

    now = datetime.now(UTC)
    handler = _ACTION_DISPATCH[body.action]
    import_session_id = await handler(issue, db, now, admin)

    return ActionResponse(
        issue=IssueOut.model_validate(issue),
        import_session_id=import_session_id,
    )


@router.post("/{issue_id}/resolve", response_model=IssueOut)
async def resolve_issue(
    issue_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IssueOut:
    """Mark an issue resolved (legacy endpoint; use /action for corrective actions)."""
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found.")
    issue.status = IssueStatus.resolved
    issue.resolved_at = datetime.now(UTC)
    issue.updated_at = datetime.now(UTC)
    await db.flush()
    return IssueOut.model_validate(issue)


@router.post("/{issue_id}/ignore", response_model=IssueOut)
async def ignore_issue(
    issue_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IssueOut:
    """Mark an issue ignored (legacy endpoint; use /action for corrective actions)."""
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found.")
    issue.status = IssueStatus.ignored
    issue.updated_at = datetime.now(UTC)
    await db.flush()
    return IssueOut.model_validate(issue)
