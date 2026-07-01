"""Storage path computation — the single source of truth for item directory layout.

All path derivation goes through this module so the physical layout never
diverges between create, rename, sidecar write, and URL generation.

Physical layout (per sidecar-schema.md §2 + PRD §3.2):
    <library_mount_path>/<shard>/<slug_body>-<key>/
    <library_mount_path>/<shard>/<slug_body>-<key>/<slug_body>-<key>.yml  (sidecar)

Sanitization algorithm (sidecar-schema.md §2):
    1. Unicode-normalize (NFKD) → transliterate to ASCII (via python-slugify
       which uses text-unidecode internally).
    2. Lowercase.
    3. Replace every char outside [a-z0-9] with '-'.
    4. Collapse runs of '-'; trim leading/trailing '-'.
    5. Empty result (all-CJK / all-emoji) → fall back to 'item'.
    6. Cap slug body at 80 chars (cut on char boundary, re-trim trailing '-').

Slug choice — python-slugify (text-unidecode):
    Handles NFKD + ASCII transliteration in one shot.  Produces exactly the
    [a-z0-9-] alphabet with runs collapsed and edges trimmed.
    Pinned to 8.0.4 in requirements.txt.  Recorded in docs/decisions.md.
"""

from pathlib import Path

from slugify import slugify  # python-slugify

from .keys import key_shard

# Maximum length for the slug body (before the -<key> suffix).
SLUG_BODY_MAX = 80


def sanitize_slug_body(title: str) -> str:
    """Derive the slug body from a human title.

    Returns a lowercase ASCII string matching [a-z0-9]([a-z0-9-]*[a-z0-9])?
    that is at most SLUG_BODY_MAX characters, or "item" if the title has no
    representable ASCII characters.
    """
    slug = slugify(
        title,
        max_length=SLUG_BODY_MAX,
        word_boundary=False,
        separator="-",
        lowercase=True,
    )
    if not slug:
        return "item"
    # python-slugify respects max_length but may leave a trailing '-' if the
    # cut landed mid-word boundary; strip defensively.
    return slug.rstrip("-") or "item"


def item_slug(title: str, key: str) -> str:
    """Return the full slug: <slug_body>-<key>.

    This is the dir name, the URL slug, and the sidecar `slug` field.
    """
    return f"{sanitize_slug_body(title)}-{key}"


def item_dir_name(title: str, key: str) -> str:
    """Alias for item_slug — the directory name is the slug."""
    return item_slug(title, key)


def item_dir_path(library_mount: str, key: str, title: str) -> Path:
    """Return the absolute path to the item directory.

    Structure: <library_mount>/<shard>/<slug_body>-<key>/
    """
    shard = key_shard(key)
    dir_name = item_dir_name(title, key)
    return Path(library_mount) / shard / dir_name


def sidecar_name(title: str, key: str) -> str:
    """Return the sidecar filename (same as the dir name, with .yml extension)."""
    return f"{item_dir_name(title, key)}.yml"


def sidecar_path(item_dir: Path, title: str, key: str) -> Path:
    """Return the absolute path to the sidecar file inside item_dir."""
    return item_dir / sidecar_name(title, key)
