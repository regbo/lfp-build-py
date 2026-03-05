import functools
import json
import os
import pathlib
import re
import subprocess
from dataclasses import dataclass

from lfp_logging import logs

from lfp_build import _config, util

"""
Interface for uv workspace metadata.

Provides utilities for retrieving and parsing metadata from a uv workspace,
enabling easy access to the workspace root and its member projects.
"""

LOG = logs.logger(__name__)

_DEP_NAME_RE = re.compile(r"^\s*([\w\-\.\[\]]+)\s*@\s*file://")


@dataclass
class Metadata:
    """
    Metadata representation of a uv workspace.
    """

    workspace_root: pathlib.Path
    members: list["MetadataMember"]


@dataclass
class MetadataMember:
    """
    Representation of a member project within a uv workspace.
    """

    name: str
    path: pathlib.Path


def parse_dependency_name(dep: str) -> str:
    """
    Extract the project name from a dependency string.

    Supports entries like:
    - "foo"
    - "foo @ file://..."
    """
    m = _DEP_NAME_RE.match(dep)
    return m.group(1) if m else dep.strip()


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


def metadata(path: pathlib.Path = None) -> Metadata:
    """
    Retrieve metadata for a uv workspace.

    Args:
        path: Directory within the workspace. Defaults to current working directory.

    Returns:
        Parsed uv workspace metadata.
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
    Best-effort repair of missing `tool.uv.sources.<dep>.workspace = true` entries.

    This mirrors the intent of the workspace dependency resolution logic in
    `workspace_sync` without importing it (to avoid circular imports).
    """
    try:
        import tomlkit
    except Exception:
        return {}

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
            dep_name = parse_dependency_name(str(dep))
            if dep_name not in member_names:
                continue
            dep_dir = name_to_dir[dep_name]
            if direct_reference:
                deps[idx] = member_dependency(
                    dep_name=dep_name,
                    member_proj_dir=member_dir,
                    dep_proj_dir=dep_dir,
                )
            else:
                deps[idx] = dep_name
            updated = True
            src = sources_tbl.setdefault(dep_name, tomlkit.table())
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
    try:
        import tomlkit
    except Exception:
        return {}
    try:
        with path.open("rb") as f:
            doc = tomlkit.load(f)
        return doc  # type: ignore[return-value]
    except Exception:
        return {}


def _load_tomlkit(path: pathlib.Path):
    import tomlkit

    with path.open("rb") as f:
        return tomlkit.load(f)
