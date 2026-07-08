import hashlib
import importlib.abc
import importlib.resources
import pathlib
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from lfp_logging import logs

"""
Bundled agent resources shipped with lfp-build.

This module resolves and installs the SKILL.md skills and Markdown docs
that ``lfp-build`` bundles for consumers - agent-facing content that
teaches Claude / Cursor / Codex how to work inside a workspace that uses
lfp-build.

The bundled content is the source of truth and lives inside the package
at ``src/lfp_build/docs/`` (a flat layout: skill subdirectories with
``SKILL.md`` and standalone ``*.md`` reference docs). The tree is
tracked in git so every install path - PyPI wheel, ``pip install
git+...``, editable install from a source checkout - carries the
bundle. ``uv_build`` picks it up in both the wheel and the sdist, and
``importlib.resources`` can locate it at runtime regardless of whether
lfp-build is running from a wheel install or a source checkout.

The install-side verbs (``lfp-build skills install``,
``lfp-build docs install``) share a single implementation in
:func:`install`; the command modules just pin the ``kind`` and expose
CLI flags.
"""

LOG = logs.logger(__name__)

# ``importlib.resources.abc.Traversable`` only exists on 3.11+; on 3.10
# the same class is exposed from ``importlib.abc``. Alias here so callers
# import ``Traversable`` from this module and get a version-agnostic view.
Traversable = importlib.abc.Traversable

# Resolve the bundled-resources subpackage relative to the module's own
# package at runtime rather than hardcoding the distribution name.
# ``__package__`` holds the containing package (for example
# ``"lfp_build"``); the subpackage name stays as a plain suffix so
# renaming the top-level distribution needs no source changes here.
#
# The bundle uses a **flat** layout at runtime: subdirectories that
# contain a ``SKILL.md`` are skills, and top-level ``*.md`` files are
# reference docs.
_BUNDLED_SUBPACKAGE = "docs"
_BUNDLED_PACKAGE = f"{__package__}.{_BUNDLED_SUBPACKAGE}"

# Filename that marks a subdirectory of ``_BUNDLED_PACKAGE`` as a skill.
_SKILL_MANIFEST_NAME = "SKILL.md"

# Host-side layout: agent hosts (Cursor, Claude) look for skills at
# ``<host>/skills/<name>/SKILL.md`` and installed docs at
# ``<host>/docs/<name>.md``. Only the destination side needs kind
# subdirs; the source is flat.
_HOST_ROOT_DIRS: dict[str, str] = {
    "cursor": ".cursor",
    "claude": ".claude",
}
_HOST_KIND_SUBDIRS: dict[str, str] = {
    "skills": "skills",
    "docs": "docs",
}

Kind = Literal["skills", "docs"]
Host = Literal["cursor", "claude"]


@dataclass(frozen=True)
class InstallReport:
    """
    Summary of files touched by an :func:`install` invocation.

    Attributes
    ----------
    installed
        Destination paths that were newly created.
    updated
        Destination paths that already existed and were rewritten.
    skipped
        Destination paths whose content already matched the bundled
        source (identical hash) and were left alone.
    dry_run
        True when the invocation was a preview and no writes happened.
    """

    installed: list[pathlib.Path]
    updated: list[pathlib.Path]
    skipped: list[pathlib.Path]
    dry_run: bool


def hosts() -> tuple[Host, ...]:
    """
    Return the supported agent host identifiers.

    Callers use this to validate CLI ``--target`` inputs without having
    to import the module-private constant.
    """
    return tuple(_HOST_ROOT_DIRS.keys())  # type: ignore[return-value]


def resolve_target_dir(
    *,
    host: Host,
    kind: Kind,
    global_install: bool,
    base_dir: pathlib.Path | None = None,
) -> pathlib.Path:
    """
    Return the destination directory for a given host + kind.

    Parameters
    ----------
    host
        ``"cursor"`` or ``"claude"``.
    kind
        ``"skills"`` or ``"docs"``.
    global_install
        When True, target the user's home directory
        (``~/.cursor/skills``); otherwise target ``base_dir`` (defaults
        to the current working directory).
    base_dir
        Base directory used for non-global installs. Defaults to
        :func:`pathlib.Path.cwd`. Ignored when ``global_install`` is
        True.
    """
    root = pathlib.Path.home() if global_install else (base_dir or pathlib.Path.cwd())
    return root / _HOST_ROOT_DIRS[host] / _HOST_KIND_SUBDIRS[kind]


def list_bundled_names(kind: Kind) -> list[str]:
    """
    Return the sorted list of bundled skill / doc names.

    For ``kind="skills"`` the entries are directory names (each holding
    a ``SKILL.md``); for ``kind="docs"`` the entries are Markdown file
    stems.
    """
    source_root = _bundled_root()
    if not source_root.is_dir():
        return []
    return sorted(name for name, _ in _iter_bundled(kind))


def install(
    *,
    kind: Kind,
    host: Host,
    global_install: bool = False,
    names: list[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
    base_dir: pathlib.Path | None = None,
) -> InstallReport:
    """
    Copy bundled ``kind`` resources to the target host directory.

    Parameters
    ----------
    kind
        ``"skills"`` or ``"docs"``.
    host
        ``"cursor"`` or ``"claude"``.
    global_install
        When True, target ``~/.<host>/<kind>/``; otherwise target
        ``<base_dir>/.<host>/<kind>/``.
    names
        Restrict the install to specific bundled entries by name. When
        omitted, every bundled entry is installed. Unknown names raise
        :class:`ValueError`.
    force
        When True, rewrite destination files whose content differs from
        the bundled source even if they already exist. When False, an
        existing destination with divergent content is left alone and
        logged as skipped.
    dry_run
        When True, no writes happen; the returned report still reflects
        what would have been installed / updated / skipped.
    base_dir
        Base directory for non-global installs. Defaults to CWD.
    """
    source_root = _bundled_root()
    if not source_root.is_dir():
        LOG.debug("No bundled %s to install", kind)
        return InstallReport(installed=[], updated=[], skipped=[], dry_run=dry_run)

    entries = dict(_iter_bundled(kind))
    selected = _select_entries(entries=entries, names=names, kind=kind)

    target_dir = resolve_target_dir(
        host=host, kind=kind, global_install=global_install, base_dir=base_dir
    )
    LOG.info(
        "Installing bundled %s - host:%s target:%s count:%d dry_run:%s",
        kind,
        host,
        target_dir,
        len(selected),
        dry_run,
    )

    installed: list[pathlib.Path] = []
    updated: list[pathlib.Path] = []
    skipped: list[pathlib.Path] = []

    for entry_name, source in selected.items():
        for source_file, rel_path in _iter_source_files(source):
            dest_path = target_dir / rel_path
            action = _plan_action(source_file=source_file, dest_path=dest_path, force=force)
            if action == "install":
                if not dry_run:
                    _copy_file(source_file, dest_path)
                installed.append(dest_path)
            elif action == "update":
                if not dry_run:
                    _copy_file(source_file, dest_path)
                updated.append(dest_path)
            else:
                skipped.append(dest_path)
            LOG.debug(
                "Bundle %s - entry:%s action:%s source:%s dest:%s",
                kind,
                entry_name,
                action,
                source_file,
                dest_path,
            )

    return InstallReport(installed=installed, updated=updated, skipped=skipped, dry_run=dry_run)


def _bundled_root() -> Traversable:
    """
    Return the :class:`Traversable` root for bundled content.

    Skills and docs share a single flat source directory; the caller
    filters by kind in :func:`_iter_bundled`.

    Wraps :func:`importlib.resources.files` so callers work uniformly
    against a wheel install or a source checkout.
    """
    return importlib.resources.files(_BUNDLED_PACKAGE)


def _iter_bundled(kind: Kind) -> Iterator[tuple[str, Traversable]]:
    """
    Yield ``(name, resource)`` pairs for every bundled entry of ``kind``.

    Discrimination runs off the flat bundle layout:

    - ``kind == "skills"``: yields one entry per subdirectory that
      contains a ``SKILL.md`` at its root (``name`` is the dir name).
    - ``kind == "docs"``: yields one entry per top-level ``*.md`` file
      that is not a ``SKILL.md`` orphan (``name`` is the file stem).

    Dotfiles and underscore-prefixed entries (for example
    ``__init__.py``, ``__pycache__``) are always skipped so runtime
    package plumbing never surfaces as a user-visible resource.
    """
    source_root = _bundled_root()
    if not source_root.is_dir():
        return
    for child in sorted(source_root.iterdir(), key=lambda c: c.name):
        if child.name.startswith(("_", ".")):
            continue
        if kind == "skills":
            if child.is_dir() and (child / _SKILL_MANIFEST_NAME).is_file():
                yield child.name, child
        elif kind == "docs":
            if child.is_file() and child.name.endswith(".md"):
                yield child.name.removesuffix(".md"), child


def _select_entries(
    *,
    entries: dict[str, Traversable],
    names: list[str] | None,
    kind: Kind,
) -> dict[str, Traversable]:
    """
    Filter ``entries`` down to ``names`` when provided, else return all.

    Raises ``ValueError`` for any requested name that is not bundled so
    the caller sees typos immediately.
    """
    if not names:
        return entries
    missing = sorted(set(names) - set(entries.keys()))
    if missing:
        available = ", ".join(sorted(entries.keys())) or "<none>"
        raise ValueError(f"Unknown bundled {kind}: {', '.join(missing)}. Available: {available}")
    return {name: entries[name] for name in names}


def _iter_source_files(source: Traversable) -> Iterator[tuple[Traversable, pathlib.PurePosixPath]]:
    """
    Yield ``(file, relative_path)`` for every file inside ``source``.

    The relative path is already rooted at what the caller uses as the
    destination directory:

    - For a file (docs case) the yielded path is just the file's name,
      landing flat under the target directory.
    - For a directory (skills case) the yielded paths include the
      directory's own name as the top component, so nested layouts
      (``<name>/SKILL.md`` and any siblings) are preserved on disk.
    """
    if source.is_file():
        yield source, pathlib.PurePosixPath(source.name)
        return

    stack: list[tuple[Traversable, pathlib.PurePosixPath]] = [
        (source, pathlib.PurePosixPath(source.name))
    ]
    while stack:
        node, prefix = stack.pop()
        for child in node.iterdir():
            child_rel = prefix / child.name
            if child.is_file():
                yield child, child_rel
            elif child.is_dir():
                stack.append((child, child_rel))


def _plan_action(
    *, source_file: Traversable, dest_path: pathlib.Path, force: bool
) -> Literal["install", "update", "skip"]:
    """
    Decide what to do for a single ``(source_file, dest_path)`` pair.

    Returns:
    - ``"install"`` when the destination does not exist.
    - ``"skip"`` when it exists and its hash matches the bundled source.
    - ``"update"`` when it exists with a divergent hash and ``force``
      is True.
    - ``"skip"`` when it exists with a divergent hash and ``force`` is
      False (the caller has already agreed not to overwrite).
    """
    if not dest_path.exists():
        return "install"
    if _hash_traversable(source_file) == _hash_path(dest_path):
        return "skip"
    return "update" if force else "skip"


def _copy_file(source_file: Traversable, dest_path: pathlib.Path) -> None:
    """
    Copy a bundled ``source_file`` to ``dest_path``, ensuring the parent exists.

    Uses :func:`importlib.resources.as_file` so this works whether the
    resource is a real file on disk or backed by a zip loader.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with importlib.resources.as_file(source_file) as source_path:
        shutil.copyfile(source_path, dest_path)


def _hash_traversable(resource: Traversable) -> str:
    """
    Compute the SHA-256 of a bundled resource's bytes.

    Digest match is the sole signal :func:`_plan_action` uses to decide
    between skip and update, so it must be stable across environments -
    hence SHA-256 over the exact file bytes rather than any hint from
    mtime or size.
    """
    digest = hashlib.sha256()
    with importlib.resources.as_file(resource) as source_path:
        with open(source_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _hash_path(path: pathlib.Path) -> str:
    """
    Compute the SHA-256 of an on-disk file's bytes.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
