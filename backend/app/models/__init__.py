"""SQLAlchemy ORM models for PartFolder 3D.

All models import from this package.  Alembic env.py imports Base.metadata here.
"""

from .ai_provider import AiProvider, AiProviderType
from .ai_usage import AiUsage
from .api_key import ApiKey
from .backup import BackupRecord
from .base import Base
from .change_log import ChangeLog, ChangeSource
from .creator import Creator
from .download_bundle import DownloadBundle
from .favorite import Favorite
from .file import File, FileRole
from .image import Image, ImageSource
from .import_session import (
    ImportSession,
    ImportSessionFile,
    ImportSessionImage,
    ImportSessionStatus,
    ImportSourceType,
)
from .invite import Invite, InviteStatus
from .issue import Issue, IssueSeverity, IssueStatus, IssueType
from .item import Item
from .job import Job
from .library import Library
from .password_reset import PasswordResetToken
from .print_record import PrintRecord
from .review_item import ReviewItem, ReviewStatus
from .scheduled_job import ScheduledJob
from .scraper_usage import ScraperUsage
from .session import UserSession
from .setting import Setting
from .share_audit_event import ShareAuditEvent
from .share_link import ShareLink
from .site_capability import SiteCapability, SiteToken
from .tag import ItemTag, Tag, TagAlias, TagStatus
from .user import User, UserRole

__all__ = [
    "Base",
    "BackupRecord",
    "User",
    "UserRole",
    "ApiKey",
    "Invite",
    "InviteStatus",
    "PasswordResetToken",
    "Setting",
    "AiProvider",
    "AiProviderType",
    "AiUsage",
    "ScraperUsage",
    "UserSession",
    # Phase 2
    "Library",
    "Creator",
    "Item",
    "File",
    "FileRole",
    "Image",
    "ImageSource",
    "Tag",
    "TagStatus",
    "TagAlias",
    "ItemTag",
    # Phase 3
    "Favorite",
    "DownloadBundle",
    # Phase 4
    "Job",
    "ScheduledJob",
    # Phase 5
    "ImportSession",
    "ImportSessionFile",
    "ImportSessionImage",
    "ImportSessionStatus",
    "ImportSourceType",
    "SiteCapability",
    "SiteToken",
    # Phase 6
    "Issue",
    "IssueType",
    "IssueSeverity",
    "IssueStatus",
    "ChangeLog",
    "ChangeSource",
    "ReviewItem",
    "ReviewStatus",
    # Phase 7
    "PrintRecord",
    "ShareLink",
    "ShareAuditEvent",
]
