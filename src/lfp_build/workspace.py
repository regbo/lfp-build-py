from __future__ import annotations

import functools
import json
import os
import pathlib
import re
import subprocess
from dataclasses import dataclass

import tomlkit
from lfp_logging import logs
from tomlkit import TOMLDocument

from lfp_build import _config, util

"""
Interface for uv workspace metadata.

Retrieves and parses metadata from a uv workspace via ``uv workspace
metadata``, with a best-effort filesystem scan and source repair fallback
when the uv command fails on a misconfigured workspace.
"""

LOG = logs.logger(__name__)

# PEP 508 ``name @ file://uri[; marker]`` requirement parser. Captures the
# distribution name (with optional ``[extras]``), the ``file://`` URI, and
# any environment marker. Used by both dependency-name extraction and
# wheel METADATA rewriting.
_FILE_REQUIREMENT_RE = re.compile(
    r"^\s*"
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9._\-]*(?:\[[^\]]+\])?)"
    r"\s*@\s*"
    r"(?P<uri>file://\S+)"
    r"(?:\s*;\s*(?P<marker>.+?))?"
    r"\s*$"
)


@dataclass
class Metadata:
    """
    Metadata representation of a uv workspace.
    """

    workspace_root: pathlib.Path
    members: list[MetadataMember]


@dataclass
class MetadataMember:
    """
    Representation of a member project within a uv workspace.
    """

    name: str
    path: pathlib.Path


@dataclass
class FileRequirement:
    """
    Parsed PEP 508 ``name @ file://uri[; marker]`` requirement.

    Returned by :func:`parse_file_requirement` when a dependency string is
    in the file-URI form. ``name`` includes any ``[extras]`` suffix; the
    URI is left unparsed so callers can decide how to resolve it (relative
    to a workspace root, with ``${PROJECT_ROOT}`` substitution, etc.).
    """

    name: str
    uri: str
    marker: str | None = None


def parse_file_requirement(requirement: str) -> FileRequirement | None:
    """
    Parse a ``name @ file://uri[; marker]`` requirement.

    Returns ``None`` when the input is not in this form (e.g. a plain
    ``"foo"`` or a versioned ``"foo>=1.0"`` requirement). Callers that
    only need the name should use :func:`parse_dependency_name`, which
    falls back to the stripped input when the file-URI form does not
    match.
    """
    match = _FILE_REQUIREMENT_RE.match(requirement)
    if match is None:
        return None
    return FileRequirement(
        name=match.group("name"),
        uri=match.group("uri"),
        marker=match.group("marker"),
    )


def parse_dependency_file_requirement(requirement: str) -> FileRequirement | None:
    """
    Parse a ``name @ file://uri[; marker]`` requirement.

    Returns ``None`` when the input is not in this form (e.g. a plain
    ``"foo"`` or a versioned ``"foo>=1.0"`` requirement). Callers that
    only need the name should use :func:`parse_dependency_name`, which
    falls back to the stripped input when the file-URI form does not
    match.
    """
    match = _FILE_REQUIREMENT_RE.match(requirement)
    if match is None:
        return None
    return FileRequirement(
        name=match.group("name"),
        uri=match.group("uri"),
        marker=match.group("marker"),
    )


def parse_dependency_name(dep: str) -> str:
    """
    Extract the project name from a dependency string.

    Supports entries like:
    - "foo"
    - "foo @ file://..."
    - "foo[extras] @ file://..."
    """
    file_requirement = parse_dependency_file_requirement(dep)
    return file_requirement.name if file_requirement else dep.strip()


def member_dependency(
    *,
    dep_name: str,
    member_proj_dir: pathlib.Path,
    dep_proj_dir: pathlib.Path,
) -> str:
    """
    Format an internal workspace dependency as a file:// URI using PROJECT_ROOT.

    Args:
        dep_name: Dependency project name.
        member_proj_dir: Directory containing the dependent project's pyproject.toml.
        dep_proj_dir: Directory containing the dependency project's pyproject.toml.

    Returns:
        A dependency string like: "{dep} @ file://${PROJECT_ROOT}/relative/path"
    """
    member_proj_dir = member_proj_dir.resolve(strict=False)
    dep_proj_dir = dep_proj_dir.resolve(strict=False)
    relative_path = os.path.relpath(dep_proj_dir, member_proj_dir)
    return f"{dep_name} @ file://${{PROJECT_ROOT}}/{relative_path}"


def normalize_member_dependency(
    *,
    dependency: str,
    member_proj_dir: pathlib.Path,
    member_paths_by_name: dict[str, pathlib.Path],
    direct_reference: bool,
) -> tuple[str, str | None]:
    """
    Normalize a dependency string for workspace member references.

    Parameters
    ----------
    dependency
        Dependency entry from `project.dependencies`.
    member_proj_dir
        Directory containing the dependent project's `pyproject.toml`.
    member_paths_by_name
        Mapping of workspace member names to project directories.
    direct_reference
        When True, return `name @ file://${PROJECT_ROOT}/...` for internal
        workspace dependencies. When False, return plain member names.

    Returns
    -------
    tuple[str, str | None]
        The normalized dependency string and the internal member name when the
        dependency targets another workspace member. The member name is None
        for non-workspace dependencies.
    """
    dep_name = parse_dependency_name(dependency)
    dep_proj_dir = member_paths_by_name.get(dep_name)
    if dep_proj_dir is None:
        return dependency, None
    if direct_reference:
        return (
            member_dependency(
                dep_name=dep_name,
                member_proj_dir=member_proj_dir,
                dep_proj_dir=dep_proj_dir,
            ),
            dep_name,
        )
    return dep_name, dep_name


def metadata(path: pathlib.Path | None = None) -> Metadata:
    """
    Retrieve metadata for a uv workspace with repair-and-fallback behavior.

    When `uv workspace metadata` fails, this function performs a best-effort
    repair pass on workspace dependency source entries and retries. If the retry
    still fails, any repair edits are rolled back and filesystem scanning is
    used as a fallback metadata source.
    """
    if path is None:
        path = pathlib.Path().cwd()
    cwd = path.absolute()

    # Some uv workspace configurations can be misconfigured, for example when a
    # member project has an internal workspace dependency but `tool.uv.sources`
    # is missing the required `workspace = true` entry. In these cases, `uv
    # workspace metadata` can fail. We do a best-effort "fix then retry".
    fallback: Metadata | None = None
    last_exc: Exception | None = None
    for fix in (True, False):
        try:
            return _metadata_uv(cwd)
        except Exception as e:
            last_exc = e
            if not fix:
                break

            # Best-effort: scan for members and try to repair uv workspace sources.
            try:
                fallback = _metadata_scan(cwd)
                originals = _repair_workspace_sources(fallback)
                try:
                    return _metadata_uv(cwd)
                except Exception as retry_exc:
                    last_exc = retry_exc
                    _rollback_files(originals)
            except Exception:
                # If the repair path itself fails, continue to the retry attempt.
                pass

    if fallback is not None:
        LOG.warning("uv workspace metadata failed; using scanned metadata. err=%s", last_exc)
        return fallback
    raise last_exc if last_exc is not None else RuntimeError("Failed to load workspace metadata")


def _rollback_files(originals: dict[pathlib.Path, str]) -> None:
    """
    Restore files to their original content from a backup mapping.

    Used for cleanup when workspace metadata repairs fail.
    """
    for path, text in originals.items():
        try:
            path.write_text(text)
        except Exception:
            continue


@functools.cache
def _metadata_uv(cwd: pathlib.Path) -> Metadata:
    """
    Retrieve and parse metadata from the uv workspace.

    Executes 'uv workspace metadata' and returns a Metadata instance.
    The result is cached to avoid redundant subprocess calls.
    """
    args = ["uv", "workspace", "metadata"]
    env = dict(os.environ)
    # Workspace metadata is a preview feature in some uv versions.
    env.setdefault("UV_PREVIEW", "1")
    stdout = util.process_run(*args, cwd=cwd, env=env, check=False)
    try:
        data = json.loads(stdout) if stdout else None
    except json.JSONDecodeError as e:
        raise ValueError(f"uv workspace metadata returned non-JSON output: {stdout}") from e
    if not data:
        raise subprocess.CalledProcessError(returncode=2, cmd=args)
    workspace_root = pathlib.Path(data["workspace_root"])
    members: list[MetadataMember] = []
    for member in data["members"]:
        name = member["name"]
        path = pathlib.Path(member["path"])
        members.append(MetadataMember(name=name, path=path))
    return Metadata(workspace_root=workspace_root, members=members)


def clear_metadata_cache() -> None:
    """
    Clear cached uv workspace metadata.

    This is needed when workspace membership changes during the current process
    (for example after creating a new member project).
    """
    _metadata_uv.cache_clear()


def _metadata_scan(cwd: pathlib.Path) -> Metadata:
    """
    Best-effort workspace discovery by scanning the filesystem.

    This is used when `uv workspace metadata` fails.
    """
    root = _find_workspace_root(cwd)
    if root is None:
        raise ValueError(f"Workspace root not found from cwd={cwd}")

    root_pyproject = root / _config.PYPROJECT_FILE_NAME
    config = _load_toml(root_pyproject)
    workspace_cfg = config.get("tool", {}).get("uv", {}).get("workspace", {}) if config else {}
    member_patterns = list(workspace_cfg.get("members", []) or [])
    exclude_patterns = list(workspace_cfg.get("exclude", []) or [])

    member_dirs: set[pathlib.Path] = set()
    for pattern in member_patterns:
        for path in root.glob(str(pattern)):
            if not path.is_dir():
                continue
            if any(path.relative_to(root).match(str(ex)) for ex in exclude_patterns):
                continue
            if (path / _config.PYPROJECT_FILE_NAME).is_file():
                member_dirs.add(path)

    def _project_name(pyproject_path: pathlib.Path) -> str:
        data = _load_toml(pyproject_path)
        return data.get("project", {}).get("name") if data else pyproject_path.parent.name

    members: list[MetadataMember] = []
    # Include root itself as a member entry (uv does this).
    root_name = _project_name(root_pyproject)
    members.append(MetadataMember(name=root_name, path=root))

    for member_dir in sorted(member_dirs):
        pyproject_path = member_dir / _config.PYPROJECT_FILE_NAME
        members.append(MetadataMember(name=_project_name(pyproject_path), path=member_dir))

    return Metadata(workspace_root=root, members=members)


def _repair_workspace_sources(metadata_obj: Metadata) -> dict[pathlib.Path, str]:
    """
    Best-effort repair of missing ``tool.uv.sources.<dep>.workspace = true`` entries.

    Mirrors the intent of the workspace dependency resolution logic in
    :mod:`lfp_build.workspace_sync` without importing it (to avoid circular
    imports). Returns a mapping of edited file paths to their original text
    so that callers can roll back when the repair does not unblock uv.
    """
    direct_reference = _config.MEMBER_PROJECT_DIRECT_REFERENCE.get()
    name_to_dir = {m.name: m.path for m in metadata_obj.members}
    member_names = set(name_to_dir.keys())
    originals: dict[pathlib.Path, str] = {}

    for member in metadata_obj.members:
        pyproject_path = member.path / _config.PYPROJECT_FILE_NAME
        if not pyproject_path.is_file():
            continue

        doc = _load_tomlkit(pyproject_path)
        project_tbl = doc.get("project", {})
        deps = project_tbl.get("dependencies", None)
        if not deps:
            continue

        updated = False
        sources_tbl = (
            doc.setdefault("tool", tomlkit.table())
            .setdefault("uv", tomlkit.table())
            .setdefault("sources", tomlkit.table())
        )

        member_dir = member.path
        for idx, dep in enumerate(list(deps)):
            normalized_dep, member_dependency_name = normalize_member_dependency(
                dependency=str(dep),
                member_proj_dir=member_dir,
                member_paths_by_name=name_to_dir,
                direct_reference=direct_reference,
            )
            if member_dependency_name is None or member_dependency_name not in member_names:
                continue
            deps[idx] = normalized_dep
            updated = True
            src = sources_tbl.setdefault(member_dependency_name, tomlkit.table())
            if src.get("workspace", None) is not True:
                src["workspace"] = True
                updated = True

        if updated:
            if pyproject_path not in originals:
                try:
                    originals[pyproject_path] = pyproject_path.read_text()
                except Exception:
                    originals[pyproject_path] = ""
            pyproject_path.write_text(tomlkit.dumps(doc))

    return originals


def _find_workspace_root(cwd: pathlib.Path) -> pathlib.Path | None:
    cur = cwd
    while True:
        pyproject_path = cur / _config.PYPROJECT_FILE_NAME
        if pyproject_path.is_file():
            data = _load_toml(pyproject_path)
            if data.get("tool", {}).get("uv", {}).get("workspace", None) is not None:
                return cur
        parent = cur.parent
        if parent == cur:
            return None
        cur = parent


def _load_toml(path: pathlib.Path) -> dict:
    """
    Load a TOML file as a plain dict, returning ``{}`` on read or parse errors.

    Used by best-effort scanning paths where a missing or malformed
    ``pyproject.toml`` should not crash workspace discovery.
    """
    try:
        with path.open("rb") as f:
            doc = tomlkit.load(f)
        return doc  # type: ignore[return-value]
    except Exception:
        return {}


def _load_tomlkit(path: pathlib.Path) -> TOMLDocument:
    """
    Load a TOML file as a tomlkit document, preserving formatting and comments.

    Unlike :func:`_load_toml`, this raises on missing files or parse errors so
    callers performing in-place edits fail fast instead of silently dropping
    user content.
    """
    with path.open("rb") as f:
        return tomlkit.load(f)
