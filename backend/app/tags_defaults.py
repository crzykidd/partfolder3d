"""Curated starter tag vocabulary for PartFolder 3D.

Used by POST /api/tags/load-defaults to seed a fresh instance with a
reasonable default vocabulary, organized by category.  Names are
stored lowercase/slug (ASCII, hyphens for multi-word) — the project's
canonical tag convention.
"""

# (name, category) pairs — names are already in canonical form.
STARTER_TAGS: list[tuple[str, str]] = [
    # type
    ("functional", "type"),
    ("decorative", "type"),
    ("miniature", "type"),
    ("toy", "type"),
    ("tool", "type"),
    ("gadget", "type"),
    ("jewelry", "type"),
    ("cosplay", "type"),
    ("prop", "type"),
    ("replacement-part", "type"),
    ("model-kit", "type"),
    # function
    ("storage", "function"),
    ("organizer", "function"),
    ("holder", "function"),
    ("stand", "function"),
    ("mount", "function"),
    ("wall-mount", "function"),
    ("hook", "function"),
    ("clip", "function"),
    ("bracket", "function"),
    ("cable-management", "function"),
    ("enclosure", "function"),
    ("planter", "function"),
    ("vase", "function"),
    ("sign", "function"),
    # feature
    ("print-in-place", "feature"),
    ("articulated", "feature"),
    ("no-supports", "feature"),
    ("supports-required", "feature"),
    ("multipart", "feature"),
    ("multicolor", "feature"),
    ("multimaterial", "feature"),
    ("flexible", "feature"),
    # theme
    ("fantasy", "theme"),
    ("sci-fi", "theme"),
    ("animal", "theme"),
    ("holiday", "theme"),
    ("christmas", "theme"),
    ("halloween", "theme"),
    ("kawaii", "theme"),
    ("anime", "theme"),
    ("gaming", "theme"),
    # process
    ("fdm", "process"),
    ("resin", "process"),
    # audience
    ("kids", "audience"),
    ("gift", "audience"),
    ("educational", "audience"),
    # mechanical
    ("gears", "mechanical"),
    ("hinge", "mechanical"),
    ("threaded", "mechanical"),
    ("bearing", "mechanical"),
]
