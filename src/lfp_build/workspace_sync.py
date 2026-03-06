import logging
import os
import pathlib
import re
import time
from collections import defaultdict
from collections.abc import Collection
from copy import deepcopy
from typing import Annotated, Any

import cyclopts
import mergedeep
from cyclopts import App
from lfp_logging import logs
from packaging.version import Version

from lfp_build import _config, pyproject, util, workspace
from lfp_build.pyproject import PyProject, PyProjectTree

"""
Sync utility for managing multiple pyproject.toml files in a uv workspace.

This module provides tools to synchronize versions, build systems, tool settings,
and dependencies across the root project and its member projects.
"""

LOG = logs.logger(__name__)

app = App()


@app.default
def sync(
    *,
    name: list[str] | None = None,
    version: bool = True,
    build_system: bool = True,
    member_project_tool: bool = True,
    member_project_dependencies: bool = True,
    member_paths: bool = True,
    reorder_pyproject: bool = True,
    format_pyproject: bool = True,
    format_python: bool = True,
    new_pyprojects: Annotated[
        dict[str, PyProject] | None,
        cyclopts.Parameter(show=False),
    ] = None,
) -> None:
    """
    Synchronize project configurations across the workspace.

    This command performs several synchronization tasks to keep member projects
    aligned with the root project settings and ensure consistent dependencies.

    Parameters
    ----------
    name
        Specific member project names to sync.
    version
        Sync version from git history to all member projects.
    build_system
        Sync [build-system] from root project to all member projects.
    member_project_tool
        Sync [tool.member-project] from root project to all member projects.
    member_project_dependencies
        Sync internal member dependencies and uv workspace sources. Dependency
        format is controlled by `_config.MEMBER_PROJECT_DIRECT_REFERENCE.get()`
        (plain names when False, `${PROJECT_ROOT}` file references when True).
    member_paths
        Sync member path patterns.
    reorder_pyproject
        Order pyproject entries where applicable.
    format_pyproject
        Format pyproject.toml files using taplo.
    format_python
        Run ruff format and check on all projects.
    new_pyprojects
        Internal use only.
    """
    unfiltered_pyproject_tree = pyproject.tree()
    if new_pyprojects:
        for n, proj in new_pyprojects.items():
            unfiltered_pyproject_tree.members[n] = proj
    pyproject_tree = unfiltered_pyproject_tree.filter_members(name)
    LOG.debug("Syncing projects: %s", pyproject_tree)
    if version:
        sync_version(pyproject_tree.projects())
    if build_system:
        sync_build_system(pyproject_tree)
    if member_project_tool:
        sync_member_project_tool(pyproject_tree)
    if member_project_dependencies:
        sync_member_project_dependencies(unfiltered_pyproject_tree, pyproject_tree)
    if member_paths:
        sync_member_paths(unfiltered_pyproject_tree)
    if reorder_pyproject:
        sync_pyproject_order(pyproject_tree)
    if format_python:
        ruff_format(pyproject_tree.projects())
    for proj_name, proj in {
        pyproject_tree.name: pyproject_tree.root,
        **pyproject_tree.members,
    }.items():
        hash = proj.persist(
            force_format=format_pyproject,
        )
        LOG.info(
            "%s %s - path:%s",
            "Checked" if hash is None else "Updated",
            proj_name,
            proj.path,
        )


def sync_version(projs: Collection[PyProject], version: str | None = None) -> None:
    """
    Update the version field in the [project] table for a collection of projects.

    If no version is provided, it is generated automatically from the git history.
    """
    for proj in projs:
        project_data = proj.data.get("project", None)
        if project_data is not None:
            key = "version"
            current_version = project_data.get(key, None)
            if not version:
                version = _version(current_version)

            if current_version == version:
                continue
            project_data[key] = version
            LOG.debug(
                "Updated version - key:%s proj:%s version:%s previous_version:%s",
                key,
                proj,
                version,
                current_version,
            )


def _version(current_version: str | None = None) -> str:
    version: Version | None = _version_parse(current_version)
    git_version, git_commit_count = _version_git()
    max_version = max((v for v in (version, git_version) if v is not None), default="0.0.1")
    if git_commit_count is not None:
        rev = f"dev{git_commit_count}" if git_commit_count else ""
    else:
        git_rev = _version_git_rev()
        rev = f"rev{git_rev}" if git_rev else f"ts{int(time.time())}"
    return f"{max_version}.{rev}"


def _version_git() -> tuple[Version | None, int | None]:
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
            if version := _version_parse(describe):
                _, count, _ = describe.rsplit("-", 2)
                if count:
                    return version, int(count)
                else:
                    return version, None
    except Exception:
        pass
    return None, None


def _version_git_rev() -> str | None:
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
        # git not installed or not runnable
        return None

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
        return None
    return rev.strip() or None


def _version_parse(version: Any) -> Version | None:
    if version:
        version_parts = []
        for part in version.split("."):
            if match := re.search(r"\d+", part):
                version_parts.append(match.group(0))
            if len(version_parts) == 3:
                break
        version = ".".join(version_parts)
    if version:
        try:
            return Version(version)
        except Exception:
            raise
    return None


def sync_build_system(pyproject_tree: PyProjectTree) -> None:
    """
    Synchronize the [build-system] table from the root project to all member projects.
    """
    key = "build-system"
    data = pyproject_tree.root.data.get(key, {})
    LOG.debug("Build system - key:%s data:%s", key, data)
    if data:
        for member in pyproject_tree.members.values():
            member.data[key] = deepcopy(data)


def sync_member_project_tool(pyproject_tree: PyProjectTree) -> None:
    """
    Merge the [tool.member-project] configuration from root to all member projects.
    """
    member_project_data = pyproject_tree.root.data.get("tool", {}).get("member-project", {})
    LOG.debug("Member project data: %s", member_project_data)
    if member_project_data:
        for member in pyproject_tree.members.values():
            mergedeep.merge(member.data, member_project_data)


def sync_member_project_dependencies(
    unfiltered_pyproject_tree: PyProjectTree, pyproject_tree: PyProjectTree
) -> None:
    """
    Synchronize internal workspace dependencies and uv source entries.

    Dependency formatting is controlled by
    `_config.MEMBER_PROJECT_DIRECT_REFERENCE.get()`:
    - False: internal dependencies are plain names (for uv workspace resolution)
    - True: internal dependencies use `file://${PROJECT_ROOT}/...` references

    In both modes, `tool.uv.sources.<dep>.workspace = true` is maintained for
    detected internal member dependencies.
    """
    if unfiltered_pyproject_tree.filtered:
        raise ValueError("Unfiltered workspace tree required for member project dependencies sync")
    for proj in pyproject_tree.projects():
        _sync_member_project_dependencies(unfiltered_pyproject_tree, proj)


def _sync_member_project_dependencies(pyproject_tree: PyProjectTree, proj: PyProject) -> None:
    """
    Internal helper to synchronize dependencies and uv sources for a specific project.
    """
    direct_reference = _config.MEMBER_PROJECT_DIRECT_REFERENCE.get()
    member_paths_by_name = {
        pyproject_tree.name: pyproject_tree.root.path.parent,
        **{name: member.path.parent for name, member in pyproject_tree.members.items()},
    }
    member_dependencies: list[str] = []
    dependencies = proj.data.get("project", {}).get("dependencies", [])
    if dependencies:
        for idx, dependency in enumerate(dependencies):
            normalized_dep, member_dependency_name = workspace.normalize_member_dependency(
                dependency=str(dependency),
                member_proj_dir=proj.path.parent,
                member_paths_by_name=member_paths_by_name,
                direct_reference=direct_reference,
            )
            if member_dependency_name is None:
                continue
            dependencies[idx] = normalized_dep
            member_dependencies.append(member_dependency_name)

    source_table = proj.table("tool", "uv", "sources", create=bool(member_dependencies))
    if source_table is not None:
        workspace.sync_workspace_sources(
            source_table=source_table,
            member_dependencies=member_dependencies,
            proj_name=str(proj.path),
        )


def sync_member_paths(
    unfiltered_pyproject_tree: PyProjectTree,
) -> None:
    if unfiltered_pyproject_tree.filtered:
        raise ValueError("Unfiltered workspace tree required for member path sync")
    root_proj = unfiltered_pyproject_tree.root
    workspace_key_path = ["tool", "uv", "workspace"]
    exclude_patterns: list[str] | None = None
    if workspace_table := root_proj.table(*workspace_key_path):
        if exclude_item := workspace_table.get("exclude", None):
            exclude_patterns = [item.value for item in exclude_item]
    member_paths = [p.path.parent for p in unfiltered_pyproject_tree.members.values()]
    member_patterns = _workspace_member_paths(
        root_proj.path.parent,
        member_paths,
        exclude_patterns,
    )
    workspace_table = root_proj.table(*workspace_key_path, create=True)
    members_key = "members"
    if members_key in workspace_table:
        if member_patterns:
            member_table = workspace_table[members_key]
            member_table.clear()
            member_table.extend(member_patterns)
        else:
            workspace_table.remove(members_key)
    elif member_patterns:
        workspace_table.update({members_key: member_patterns})


def _workspace_member_paths(
    root: pathlib.Path, paths: list[pathlib.Path], excludes: list[str] | None
) -> list[str]:
    """
    Consolidate project paths into parent wildcards (e.g., 'packages/*') strictly.
    """

    root = root.resolve()
    paths = {p.resolve() for p in paths if p != root}

    if not all(p.is_relative_to(root) for p in paths):
        raise ValueError("All paths must be under root")

    # Ensure excludes is a list to avoid iteration errors
    excludes = excludes or []

    original_rels = {p.relative_to(root) for p in paths}
    final_paths = set(original_rels)

    by_parent: dict[pathlib.Path, set[pathlib.Path]] = defaultdict(set)
    for p in original_rels:
        by_parent[p.parent].add(p)

    for parent, children in by_parent.items():
        if parent == pathlib.Path("."):
            LOG.debug("Skip parent=root")
            continue

        parent_full = root / parent
        if not parent_full.is_dir():
            LOG.debug("Skip parent=%s reason=not_dir", parent)
            continue

        try:
            fs_items = [item for item in parent_full.iterdir() if item.is_dir()]
        except OSError as e:
            LOG.debug("Skip parent=%s reason=iterdir_error err=%s", parent, e)
            continue

        valid_fs_children = []
        skipped = []

        for item in fs_items:
            if item.name.startswith(".") or item.name == "__pycache__":
                skipped.append(item.name)
                continue

            item_rel = parent / item.name
            if any(item_rel.match(ex) for ex in excludes):
                skipped.append(item.name)
                continue

            valid_fs_children.append(item_rel)

        if set(children) != set(valid_fs_children):
            LOG.debug(
                "NoCollapse parent=%s expected=%s actual=%s skipped=%s",
                parent,
                list(children),
                valid_fs_children,
                skipped,
            )
            continue

        LOG.debug(
            "Collapse parent=%s children=%s",
            parent,
            list(children),
        )

        final_paths -= children
        final_paths.add(parent)

    results = []
    for p in sorted(final_paths, key=lambda p: p.parts):
        if p in original_rels:
            results.append(p.as_posix())
        else:
            results.append(f"{p.as_posix()}/*")

    return results


def sync_pyproject_order(
    pyproject_tree: PyProjectTree,
) -> None:
    def _order(proj: PyProject) -> PyProject:
        data = proj.data  # tomlkit document

        items = list(data.items())

        build_system = []
        project = []
        project_children = []
        dependency_groups = []
        rest = []

        for key, value in items:
            if key == "build-system":
                build_system.append((key, value))
            elif key == "project":
                project.append((key, value))
            elif key.startswith("project."):
                project_children.append((key, value))
            elif key == "dependency-groups":
                dependency_groups.append((key, value))
            else:
                rest.append((key, value))

        data.clear()

        for group in (
            build_system,
            project,
            project_children,
            dependency_groups,
            rest,
        ):
            for k, v in group:
                data.add(k, v)

        return proj

    for proj in pyproject_tree.projects():
        _order(proj)


def ruff_format(projs: list[PyProject]) -> None:
    """
    Execute ruff formatting and linting fixes on a collection of projects.
    """
    for proj in projs:
        _ruff_format(proj.path.parent)


def _ruff_format(path: pathlib.Path) -> None:
    """
    Internal helper to run ruff check and ruff format on a specific directory.
    """
    check_select = ["UP007", "UP006", "F401", "I"]
    run_arg_options = {
        "check": ["--select", ",".join(check_select), "--fix", "--exit-zero"],
        "format": [],
    }
    for arg, options in run_arg_options.items():
        util.process_run("ruff", arg, *options, cwd=path, stdout_log_level=logging.DEBUG)


if "__main__" == __name__:
    os.chdir("/Users/reggie.pierce/Projects/reggie-bricks-py")
    sync()
