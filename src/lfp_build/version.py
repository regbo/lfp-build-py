import time
from typing import Any

from lfp_logging import logs

from lfp_build import util

"""
Git-derived semantic version helpers.

Produces a normalized ``major.minor.patch`` string with an optional ``+revN``
or ``+devN`` suffix derived from ``git describe`` output and the current
working-tree state. Used by ``commands.sync`` to refresh ``project.version``
on every workspace member during sync.
"""

LOG = logs.logger(__name__)


def derive(current_version: str | None = None) -> str:
    """
    Compute a semver string for the current workspace.

    Combines the highest of (parsed current version, parsed ``git describe``
    output) and appends a ``+devN`` suffix when there are commits since the
    last tag, a ``+revN`` suffix when the working tree has uncommitted
    changes, or no suffix when the tree is clean.
    """
    version = _parse(current_version)
    git_version, git_commit_count = _from_git_describe()
    max_version = max((v for v in (version, git_version) if v is not None), default=(0, 0, 1))
    if not git_commit_count:
        git_rev, git_modified = _from_git_rev()
        if not git_modified:
            rev = ""
        else:
            rev = f"rev{git_rev}" if git_rev else f"ts{int(time.time())}"
    else:
        rev = f"dev{git_commit_count}"
    if rev:
        rev = f"+{rev}"
    return f"{_format(max_version)}{rev}"


def _from_git_describe() -> tuple[tuple[int, int, int] | None, int | None]:
    """
    Run ``git describe`` and return ``(parsed_version, commits_since_tag)``.

    Returns ``(None, None)`` when no tag is reachable or git is unavailable.
    """
    try:
        describe = util.process_run(
            "git",
            "describe",
            "--tags",
            "--long",
            "--abbrev=7",
            check=False,
            stderr_log_level=None,
        ).strip()
        if describe:
            if version := _parse(describe):
                _, count, _ = describe.rsplit("-", 2)
                if count:
                    return version, int(count)
                else:
                    return version, None
    except Exception:
        pass
    return None, None


def _from_git_rev() -> tuple[str | None, bool]:
    """
    Return ``(short_rev, modified)`` for the current working tree.

    ``modified`` is True when ``git status --porcelain`` reports changes.
    The short rev points to ``HEAD`` when modified and ``HEAD~1`` otherwise,
    matching the historical behavior of ``sync_version``.
    """
    modified = False
    try:
        for _ in util.process_start(
            "git",
            "status",
            "--porcelain",
            check=False,
            stderr_log_level=None,
        ):
            modified = True
            break
    except OSError:
        return None, False

    head_arg = "HEAD" if modified else "HEAD~1"

    try:
        rev = util.process_run(
            "git",
            "rev-parse",
            "--short",
            head_arg,
            check=False,
            stderr_log_level=None,
        )
    except OSError:
        return None, False
    return rev.strip() or None, modified


def _parse(version: Any) -> tuple[int, int, int] | None:
    """
    Parse a freeform version string into a ``(major, minor, patch)`` tuple.

    Strips any non-digit prefixes/suffixes per component and pads missing
    components with zero. Returns None when no leading digit is present.
    """
    if version:
        version_parts = str(version).strip().split(".", 4)[:3]
        version_digits = ["", "", ""]
        for idx, part in enumerate(version_parts):
            for char in part:
                if char.isdigit():
                    version_digits[idx] += char
                elif version_digits[idx]:
                    break
        if version_digits[0]:
            for idx in range(2):
                offset_idx = idx + 1
                if not version_digits[offset_idx]:
                    version_digits[offset_idx] = "0"
            return (
                int(version_digits[0]),
                int(version_digits[1]),
                int(version_digits[2]),
            )
    return None


def _format(version: tuple[int, int, int]) -> str:
    """
    Format a version tuple as ``major.minor.patch``.
    """
    major, minor, patch = version
    return f"{major}.{minor}.{patch}"
