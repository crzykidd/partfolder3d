"""Issues endpoints — Phase 6 reconcile engine (PRD §8.3).

Admin:
  GET  /api/issues           → list issues (filter by status/type, paginate)
  GET  /api/issues/{id}      → issue detail
  POST /api/issues/{id}/action   → generic action handler (ignore/delete/import)
  POST /api/issues/{id}/resolve  → mark resolved (legacy; kept for back-compat)
  POST /api/issues/{id}/ignore   → mark ignored (legacy; kept for back-compat)
"""

from __future__ import annotations

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

router = APIRouter(prefix="/api/issues", tags=["issues"])

# ---------------------------------------------------------------------------
# Action → issue type mapping
# ---------------------------------------------------------------------------

#: Actions available per issue type.  The ``import`` and ``delete`` actions
#: are only valid for orphan-dir issues (target_path must be an existing dir).
ISSUE_ACTIONS: dict[str, list[str]] = {
    IssueType.orphan: ["import", "delete", "ignore"],
    IssueType.conflict: ["ignore"],
    IssueType.dead_link: ["ignore"],
    IssueType.corruption: ["ignore"],
    IssueType.missing_file: ["ignore"],
    IssueType.extra_file: ["ignore"],
    IssueType.sidecar_error: ["ignore"],
    IssueType.other: ["ignore"],
}


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
        """Compute available_actions from issue_type unless already set."""
        if not self.available_actions:
            self.available_actions = list(ISSUE_ACTIONS.get(self.issue_type, ["ignore"]))
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

    Available actions depend on the issue type (see ``ISSUE_ACTIONS``).  A 422
    is returned for actions not in the issue's ``available_actions``.

    Actions:
      ``ignore``        — any type: mark ignored (durable via reconcile dedup).
      ``delete``        — orphan only: move ``target_path`` dir to trash.
      ``import``        — orphan only: create an ImportSession for the orphan
                          directory, prefilled from its sidecar if present.

    For ``import``, the issue is marked resolved immediately.  If the user
    abandons the wizard, the next reconcile scan will re-detect the orphan dir
    (since *resolved* does not suppress) and raise a fresh issue.
    """
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found.")

    available = ISSUE_ACTIONS.get(issue.issue_type, ["ignore"])
    if body.action not in available:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Action {body.action!r} is not available for issue type "
                f"{issue.issue_type!r}. Available: {available}"
            ),
        )

    import_session_id: str | None = None

    if body.action == "ignore":
        issue.status = IssueStatus.ignored
        issue.resolved_at = datetime.now(UTC)
        issue.updated_at = datetime.now(UTC)
        await db.flush()

    elif body.action == "delete":
        # Guard: need a target path that is an existing directory
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

        # Guard: target must be within a known enabled library mount (no traversal)
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

        # Move to trash using the same helper as item delete
        from ..storage.journal import move_to_trash  # noqa: PLC0415

        try:
            import hashlib  # noqa: PLC0415

            key_slug = hashlib.sha256(target.encode()).hexdigest()[:12]
            move_to_trash(target_dir, key_slug)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to move directory to trash: {exc}",
            ) from exc

        issue.status = IssueStatus.resolved
        issue.resolved_at = datetime.now(UTC)
        issue.updated_at = datetime.now(UTC)
        await db.flush()

    elif body.action == "import":
        # Guard: need an existing directory
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

        # Prefill metadata from sidecar if one exists in the orphan dir
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
                break  # use first valid sidecar found
            else:
                # Fall back to raw YAML parse (same approach as the inbox import task)
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
                        break  # parsed a valid sidecar
                except Exception:
                    pass  # not a valid sidecar — skip

        if not suggested_title:
            suggested_title = target_dir.name

        # Create the ImportSession at pending_wizard so the wizard opens immediately.
        # The sidecar was already read above; the user reviews/edits and commits.
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

        # Mark the issue resolved.  If the user abandons the wizard the next
        # reconcile scan will re-detect the orphan dir (resolved ≠ suppressed).
        issue.status = IssueStatus.resolved
        issue.resolved_at = datetime.now(UTC)
        issue.updated_at = datetime.now(UTC)
        await db.flush()

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
