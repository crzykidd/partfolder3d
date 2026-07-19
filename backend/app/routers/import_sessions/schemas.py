"""Pydantic schemas for import sessions and site capabilities."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from ...storage.link_url import validate_link_url


class CreateSessionRequest(BaseModel):
    source_type: str  # "url" or "upload" (multipart handled separately)
    source_url: str | None = None
    library_id: int | None = None
    # Optional pre-filled metadata
    title: str | None = None
    description: str | None = None
    license: str | None = None

    _validate_source_url = field_validator("source_url")(validate_link_url)


class PatchSessionRequest(BaseModel):
    confirmed_title: str | None = None
    description: str | None = None
    license: str | None = None
    source_url: str | None = None
    # Creator: either named or "own design"
    creator_name: str | None = None
    creator_profile_url: str | None = None
    creator_source_site: str | None = None

    _validate_source_url = field_validator("source_url")(validate_link_url)
    _validate_creator_profile_url = field_validator("creator_profile_url")(validate_link_url)
    creator_is_own_design: bool | None = None
    # Tag reconciliation: user-confirmed final tag list
    confirmed_tags: list[str] | None = None
    # Default image (path or URL from session images)
    default_image_path: str | None = None
    library_id: int | None = None


class ImportSessionFileOut(BaseModel):
    id: int
    staged_path: str
    original_name: str
    role: str
    size: int
    selected: bool

    model_config = {"from_attributes": True}


class PatchFileSelectionRequest(BaseModel):
    """Request body for PATCH /api/import-sessions/{id}/files/{file_id}."""

    selected: bool


class ImportSessionImageOut(BaseModel):
    id: int
    path: str
    is_url: bool
    source: str
    order: int
    is_default: bool

    model_config = {"from_attributes": True}


class TagStateOut(BaseModel):
    confirmed: list[str] = []
    pending: list[str] = []


class ImportSessionOut(BaseModel):
    id: str
    status: str
    source_type: str
    source_url: str | None
    inbox_folder: str | None
    staging_dir: str | None
    suggested_title: str | None
    confirmed_title: str | None
    description: str | None
    license: str | None
    source_site: str | None
    creator_name: str | None
    creator_profile_url: str | None
    creator_source_site: str | None
    creator_is_own_design: bool
    creator_id: int | None
    tag_state: TagStateOut | None
    default_image_path: str | None
    library_id: int | None
    job_id: str | None
    item_id: int | None
    created_by_id: int
    created_at: datetime
    updated_at: datetime
    error: str | None
    # Worker-set annotation: "Fetched via AgentQL" on agentql success, or a
    # blocked/budget message.  None for standard static scrapes.
    scrape_note: str | None
    files: list[ImportSessionFileOut]
    images: list[ImportSessionImageOut]

    model_config = {"from_attributes": False}


class PaginatedSessions(BaseModel):
    total: int
    page: int
    per_page: int
    sessions: list[ImportSessionOut]


class SiteCapabilityOut(BaseModel):
    domain: str
    can_scrape_metadata: bool
    can_scrape_images: bool
    requires_token: bool
    is_manual_only: bool
    last_probed_at: datetime | None
    notes: str | None
    has_token: bool = False

    model_config = {"from_attributes": False}


class PatchSiteCapabilityRequest(BaseModel):
    can_scrape_metadata: bool | None = None
    can_scrape_images: bool | None = None
    requires_token: bool | None = None
    is_manual_only: bool | None = None
    notes: str | None = None
    # Provide a plaintext token — it will be encrypted before storage
    token: str | None = None


class CommitResponse(BaseModel):
    item_key: str
    item_id: int
    session_id: str


class CommitOptions(BaseModel):
    """Optional request body for POST /api/import-sessions/{id}/commit.

    render: "auto" (default) preserves existing behaviour — server-side render
            is enqueued when the instance render.mode allows it.
            "off" suppresses enqueueing entirely for this commit regardless of
            the instance setting.
    """

    render: Literal["auto", "off"] = "auto"


class BulkCommitRequest(BaseModel):
    """Request body for POST /api/import-sessions/bulk-commit.

    session_ids: list of session UUIDs to commit, or null to target all
                 pending_wizard sessions visible to the caller.
    library_id: optional override — if set, this library is used for every
                session in the batch regardless of the session's own library_id
                or the default-import-library setting.
    render: "auto" (default) enqueues server-side render for mesh files when
            the instance render.mode permits.  "off" suppresses render enqueueing
            for every session in the batch (e.g. bulk migration where renders will
            be triggered later via browser capture or a separate job).
    """

    session_ids: list[str] | None = None
    library_id: int | None = None
    render: Literal["auto", "off"] = "auto"


class BulkCommitSkipped(BaseModel):
    session_id: str
    reason: str


class BulkCommitResponse(BaseModel):
    """Partial-success summary from POST /api/import-sessions/bulk-commit."""

    total: int
    committed: int
    skipped: list[BulkCommitSkipped]
    errors: list[BulkCommitSkipped]
