"""Pydantic request/response models for the items router package.

Split out of the former monolithic ``routers/items.py`` (audit §D). No behavior
change — these are the exact models the item endpoints validate against.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator, model_validator

from ...storage.link_url import validate_link_url


class CreatorIn(BaseModel):
    name: str
    profile_url: str | None = None
    source_site: str | None = None

    _validate_profile_url = field_validator("profile_url")(validate_link_url)


class TagIn(BaseModel):
    name: str


class ItemCreate(BaseModel):
    title: str
    library_id: int
    description: str | None = None
    source_url: str | None = None
    source_site: str | None = None
    license: str | None = None
    creator: CreatorIn | None = None
    tags: list[str] = []

    _validate_source_url = field_validator("source_url")(validate_link_url)


class ItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    source_url: str | None = None
    source_site: str | None = None
    license: str | None = None
    creator: CreatorIn | None = None
    tags: list[str] | None = None

    _validate_source_url = field_validator("source_url")(validate_link_url)


class CreatorOut(BaseModel):
    id: int
    name: str
    profile_url: str | None
    source_site: str | None

    model_config = {"from_attributes": True}


class FileOut(BaseModel):
    id: int
    path: str
    role: str
    size: int
    sha256: str | None
    # Phase 16: per-object mesh analysis (null until worker runs)
    object_analysis: Any | None = None
    # render-rework-A: true when the file can be previewed in the browser 3D viewer.
    # Gated by extension (.stl/.obj/.3mf) and file size ≤ BROWSER_PREVIEW_MAX_MB.
    preview_3d: bool = False

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _compute_preview_3d(self) -> FileOut:
        from app.config import settings  # noqa: PLC0415

        _PREVIEW_EXTS = frozenset({".stl", ".obj", ".3mf"})
        ext = Path(self.path).suffix.lower()
        max_bytes = settings.BROWSER_PREVIEW_MAX_MB * 1024 * 1024
        self.preview_3d = ext in _PREVIEW_EXTS and self.size <= max_bytes
        return self


class ImageOut(BaseModel):
    id: int
    path: str
    source: str
    is_default: bool
    order: int

    model_config = {"from_attributes": True}


class TagOut(BaseModel):
    id: int
    name: str
    category: str | None
    # 'active' | 'pending' — surfaced so item-edit UI can badge newly-added tags
    # that are awaiting admin approval (issue #47).
    status: str = "active"

    model_config = {"from_attributes": True}


class SetDefaultImageRequest(BaseModel):
    image_id: int


class ItemSummary(BaseModel):
    id: int
    key: str
    title: str
    slug: str
    library_id: int
    dir_path: str
    created_at: datetime
    updated_at: datetime
    # Phase 3 additions: enriched catalog data (default None for backward compat)
    default_image_path: str | None = None
    creator_name: str | None = None
    tag_names: list[str] = []
    favorited: bool = False
    # has_asset: True when the item has at least one model or gcode file.
    has_asset: bool = False
    # has_print_record: True when the item has at least one print record.
    has_print_record: bool = False
    # print_count: number of print records visible to the caller.
    print_count: int = 0

    model_config = {"from_attributes": False}


class ItemDetail(BaseModel):
    id: int
    key: str
    title: str
    slug: str
    library_id: int
    dir_path: str
    created_at: datetime
    updated_at: datetime
    description: str | None
    source_url: str | None
    source_site: str | None
    license: str | None
    schema_version: int
    creator: CreatorOut | None
    tags: list[TagOut]
    files: list[FileOut]
    images: list[ImageOut]
    # Phase 15: local-modification tracking
    is_modified: bool = False           # effective state (override wins over auto)
    locally_modified_at: datetime | None = None
    modified_override: str | None = None
    # Phase 16: object-analysis aggregate (null until at least one file is analyzed)
    analysis_total_objects: int | None = None
    analysis_total_colors: int | None = None
    analysis_total_est_grams: float | None = None

    model_config = {"from_attributes": True}


class PatchModifiedOverrideRequest(BaseModel):
    override: str | None = None  # 'modified' | 'original' | null


class ItemJobOut(BaseModel):
    """Slim job record surfaced on the item detail page (active + recent failed)."""
    id: str
    type: str
    status: str
    progress: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": False}


class PaginatedItems(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[ItemSummary]


class RenameFileRequest(BaseModel):
    name: str  # new basename only — no path separators


# ---------------------------------------------------------------------------
# Bulk item actions (multi-select) — tags / delete / rescan
# ---------------------------------------------------------------------------

BULK_MAX_KEYS = 500
BULK_RESCAN_MAX_KEYS = 100


def _dedupe_keys(keys: list[str]) -> list[str]:
    """De-duplicate preserving order; 1..BULK_MAX_KEYS unique keys."""
    seen: set[str] = set()
    out = [k for k in keys if not (k in seen or seen.add(k))]
    if not out:
        raise ValueError("keys must contain at least one item key")
    if len(out) > BULK_MAX_KEYS:
        raise ValueError(f"keys must contain at most {BULK_MAX_KEYS} item keys")
    return out


class BulkKeysRequest(BaseModel):
    keys: list[str]

    @field_validator("keys")
    @classmethod
    def _check_keys(cls, v: list[str]) -> list[str]:
        return _dedupe_keys(v)


class BulkRescanRequest(BulkKeysRequest):
    @field_validator("keys")
    @classmethod
    def _check_rescan_cap(cls, v: list[str]) -> list[str]:
        if len(v) > BULK_RESCAN_MAX_KEYS:
            raise ValueError(f"keys must contain at most {BULK_RESCAN_MAX_KEYS} item keys")
        return v


class BulkTagsRequest(BulkKeysRequest):
    add: list[str] = []
    remove: list[str] = []

    @model_validator(mode="after")
    def _need_one(self) -> BulkTagsRequest:
        self.add = [n.strip() for n in self.add if n.strip()]
        self.remove = [n.strip() for n in self.remove if n.strip()]
        if not self.add and not self.remove:
            raise ValueError("at least one of add / remove must be non-empty")
        return self


class BulkItemFailure(BaseModel):
    key: str
    error: str


class BulkItemResult(BaseModel):
    succeeded: list[str]
    failed: list[BulkItemFailure]
