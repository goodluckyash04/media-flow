"""
File system utilities.

All file operations use pathlib. Path traversal and unsafe directory
access are prevented by restricting operations to approved base paths.
"""

import re
import unicodedata
from pathlib import Path
from typing import Optional


# Characters that must not appear in filenames on Windows
_WIN_FORBIDDEN_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTIPLE_SPACES_RE = re.compile(r"\s{2,}")


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """
    Return a safe filename string.
    - Normalize Unicode to NFC (preserves accented characters).
    - Remove Windows-forbidden characters.
    - Collapse whitespace runs to a single space.
    - Strip leading/trailing dots and spaces.
    - Truncate to max_length while preserving the extension.
    """
    # Normalize Unicode
    name = unicodedata.normalize("NFC", name)
    # Replace Windows forbidden chars with underscores
    name = _WIN_FORBIDDEN_RE.sub("_", name)
    # Collapse whitespace
    name = _MULTIPLE_SPACES_RE.sub(" ", name).strip()
    # Remove leading dots (hidden files on Unix)
    name = name.lstrip(".")

    # Truncate preserving extension
    path = Path(name)
    stem = path.stem
    suffix = path.suffix
    max_stem = max_length - len(suffix)
    if len(stem) > max_stem:
        stem = stem[:max_stem].rstrip()
    name = stem + suffix

    return name or "unnamed"


def is_path_within(path: Path, base: Path) -> bool:
    """Return True if path is inside (or equal to) base, preventing traversal."""
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def safe_output_path(
    base_dir: Path,
    filename: str,
    *,
    increment_on_conflict: bool = True,
) -> Path:
    """
    Return a safe output path under base_dir.
    - Sanitizes the filename.
    - Prevents path traversal.
    - Increments the filename stem on conflict when requested.
    """
    base_dir = base_dir.resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    filename = sanitize_filename(filename)
    candidate = base_dir / filename

    if not is_path_within(candidate, base_dir):
        raise ValueError(f"Path traversal attempt detected: {filename!r}")

    if not increment_on_conflict or not candidate.exists():
        return candidate

    # Find a free name: file(1).ext, file(2).ext, …
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while candidate.exists():
        candidate = base_dir / f"{stem} ({counter}){suffix}"
        counter += 1

    return candidate


def human_readable_size(size_bytes: Optional[int]) -> str:
    """Convert bytes to a human-readable string."""
    if size_bytes is None:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_directory_size(path: Path) -> int:
    """Return the total size of all files in path, in bytes."""
    if not path.exists():
        return 0
    return sum(
        f.stat().st_size
        for f in path.rglob("*")
        if f.is_file()
    )
