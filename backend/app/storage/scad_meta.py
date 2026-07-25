"""Deterministic title/description extraction from an OpenSCAD `.scad` header.

Self-designed items (owner- or Claude-authored `.scad`) conventionally lead
with a rich comment header describing the part. `extract_scad_header` pulls
that header out — no AI, no network call — so import can pre-fill the item
title/description for free. The AI "Describe from SCAD" action
(`app.ai.client.describe_scad`) is the optional, additive companion for files
with no usable header or where a nicer prose description is wanted.

Supported header styles (either one, at the very top of the file, before the
first non-comment line):
* A run of contiguous `//` line comments (blank lines tolerated in between).
* A single leading `/* ... */` block comment (Javadoc-style `* ` continuation
  lines are unwrapped).

Comment markers (`//`, `/*`, `*/`, leading `*`) are stripped, as are
"decorative rule" lines made up only of `=`, `-`, `#`, and whitespace (banner
underlines). The first remaining substantive line becomes the title; the rest
becomes the description. Returns `{"title": None, "description": None}` when
there is no usable header (e.g. the file starts directly with code).
"""

from __future__ import annotations

import re

_DECORATIVE_RE = re.compile(r"^[=\-#\s]*$")


def extract_scad_header(text: str) -> dict[str, str | None]:
    """Extract `{"title": ..., "description": ...}` from a `.scad`'s leading header.

    Deterministic — no AI, no network call. Returns None for both fields when
    the leading comment block yields no substantive text (including files that
    start directly with code).
    """
    lines = text.splitlines()
    n = len(lines)

    # Skip leading blank lines before deciding the comment style.
    i = 0
    while i < n and lines[i].strip() == "":
        i += 1

    raw_block: list[str]
    if i < n and lines[i].strip().startswith("/*"):
        raw_block = _collect_block_comment(lines, i)
    else:
        raw_block = _collect_line_comments(lines, i)

    cleaned = _clean_lines(raw_block)

    # Trim leading/trailing blank separators.
    while cleaned and cleaned[0] == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()

    if not cleaned:
        return {"title": None, "description": None}

    title_idx = next((idx for idx, line in enumerate(cleaned) if line), None)
    if title_idx is None:
        return {"title": None, "description": None}

    title = cleaned[title_idx]
    rest = cleaned[:title_idx] + cleaned[title_idx + 1 :]
    while rest and rest[0] == "":
        rest.pop(0)
    while rest and rest[-1] == "":
        rest.pop()

    description = "\n".join(rest).strip() or None
    return {"title": title or None, "description": description}


def _collect_block_comment(lines: list[str], start: int) -> list[str]:
    """Collect the contents of a leading `/* ... */` block (marker stripped)."""
    block: list[str] = []
    started = False
    i = start
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()
        if not started:
            stripped = stripped[2:]  # drop leading "/*"
            started = True
        close_idx = stripped.find("*/")
        if close_idx != -1:
            block.append(stripped[:close_idx])
            break
        block.append(stripped)
        i += 1
    return block


def _collect_line_comments(lines: list[str], start: int) -> list[str]:
    """Collect a contiguous run of `//` line comments (marker stripped).

    Blank lines between `//` lines are tolerated (kept as paragraph breaks);
    the run stops at the first non-blank, non-`//` line.
    """
    collected: list[str] = []
    i = start
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()
        if stripped == "":
            collected.append("")
            i += 1
            continue
        if stripped.startswith("//"):
            collected.append(stripped[2:])
            i += 1
            continue
        break
    # Drop trailing blank lines that just precede the code — not part of the header.
    while collected and collected[-1] == "":
        collected.pop()
    return collected


def _clean_lines(raw_block: list[str]) -> list[str]:
    """Strip continuation markers and decorative rule lines from a raw block."""
    cleaned: list[str] = []
    for raw_line in raw_block:
        line = raw_line.strip()
        if line.startswith("*") and not line.startswith("*/"):
            line = line[1:].strip()
        if line != "" and _DECORATIVE_RE.match(line):
            continue  # decorative banner rule (====, ----, ####) — drop entirely
        cleaned.append(line)
    return cleaned
