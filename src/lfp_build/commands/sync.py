import logging
import pathlib
from collections import defaultdict
from collections.abc import Collection, Iterable
from copy import deepcopy
from typing import Annotated, Any

import cyclopts
import mergedeep
import tomlkit
from lfp_logging import logs

from lfp_build import _config, pyproject, util, workspace
from lfp_build.pyproject import PyProject, PyProjectTree
from lfp_build.version import derive as _derive_version

"""
Implements ``lfp-build sync``.

Synchronizes versions, build systems, shared tool settings, internal member
dependencies, and uv workspace member path patterns across the root project
and its member projects.
"""

LOG = logs.logger(__name__)


def sync(
    *,
    name: list[str] | None = None,
    version: bool = True,
    build_system: bool = True,
    member_project: bool = True,
    sources: bool = True,
    member_paths: bool = True,
    pyrefly: bool = True,
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
    member_project
        Sync [tool.lfp-build.member-project] from root project to all member projects.
    sources
        Sync ``[tool.uv.sources]`` on both the root project and every
        member project, and normalize internal member dependency entries.
        Set ``LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE=true`` to write
        workspace deps as ``name @ file://${PROJECT_ROOT}/...`` references;
        otherwise plain member names are used.
    member_paths
        Sync member path patterns.
    pyrefly
        Maintain ``[tool.pyrefly].search-path`` on the root project as
        ``["."]`` plus, for each member that declares
        ``[tool.uv.build-backend].module-root``, the relative path to that
        module root.
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
    if member_project:
        sync_member_project(pyproject_tree)
    if sources:
        sync_sources(unfiltered_pyproject_tree, pyproject_tree)
    if member_paths:
        sync_member_paths(unfiltered_pyproject_tree)
    if pyrefly:
        sync_pyrefly(unfiltered_pyproject_tree)
    if reorder_pyproject:
        pyproject.reorder_document(pyproject_tree)
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
                version = _derive_version(current_version)

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


def sync_member_project(pyproject_tree: PyProjectTree) -> None:
    """
    Merge the [tool.lfp-build.member-project] configuration from root to all member projects.
    """
    member_project_data = (
        pyproject_tree.root.data.get("tool", {}).get("lfp-build", {}).get("member-project", {})
    )
    LOG.debug("Member project data: %s", member_project_data)
    if member_project_data:
        for member in pyproject_tree.members.values():
            mergedeep.merge(member.data, member_project_data)


def sync_sources(unfiltered_pyproject_tree: PyProjectTree, pyproject_tree: PyProjectTree) -> None:
    """
    Synchronize ``[tool.uv.sources]`` on the root project and all members.

    For the root project, every workspace member is registered as a
    ``workspace = true`` source. For each member project, internal
    dependency entries (``project.dependencies``) are normalized and the
    member's own ``[tool.uv.sources]`` table is rewritten so it lists only
    the internal members the project actually depends on.

    Dependency formatting on member projects is controlled by the
    ``LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE`` env var:

    - unset / ``false``: internal dependencies are plain names (for uv
      workspace resolution).
    - ``true``: internal dependencies are written as
      ``name @ file://${PROJECT_ROOT}/...`` references.

    In both modes, ``tool.uv.sources.<dep> = { workspace = true }`` is
    maintained for detected internal member dependencies.
    """
    if unfiltered_pyproject_tree.filtered:
        raise ValueError("Unfiltered workspace tree required for sources sync")
    member_names = unfiltered_pyproject_tree.members.keys()
    _sync_sources(proj=pyproject_tree.root, member_dependencies=member_names)

    for proj in pyproject_tree.members.values():
        _sync_member_sources(unfiltered_pyproject_tree, proj)


def _sync_sources(*, proj: PyProject, member_dependencies: Iterable[str]) -> None:
    """
    Rewrite ``[tool.uv.sources]`` for ``proj`` to match ``member_dependencies``.

    Each entry is written as an inline table so it renders as
    ``dep = { workspace = true }`` under a single ``[tool.uv.sources]``
    header rather than as a separate ``[tool.uv.sources.<dep>]`` sub-table.

    Existing workspace source entries for dependencies that are no longer
    present are removed. When ``member_dependencies`` is empty, the entire
    ``sources`` table is removed.
    """
    member_dependencies = sorted(member_dependencies) if member_dependencies else []
    sources_table_required = bool(member_dependencies)
    source_table = proj.table("tool", "uv", "sources", create=sources_table_required)
    if source_table is None:
        return
    elif not sources_table_required:
        proj.data.get("tool", {}).get("uv", {}).pop("sources", None)
        return
    else:
        workspace_key = "workspace"
        for dep in list(source_table.keys()):
            workspace_value = source_table.get(dep, {}).get(workspace_key, None)
            if workspace_value is True and dep not in member_dependencies:
                source_table.remove(dep)
                LOG.debug(
                    "Removed source - key:%s proj:%s dependency:%s",
                    workspace_key,
                    proj.path,
                    dep,
                )
        for member_dependency_name in member_dependencies:
            LOG.debug(
                "Setting source - key:%s proj:%s dependency:%s",
                workspace_key,
                proj.path,
                member_dependency_name,
            )
            inline_value = tomlkit.inline_table()
            inline_value[workspace_key] = True
            source_table[member_dependency_name] = inline_value


def _sync_member_sources(pyproject_tree: PyProjectTree, proj: PyProject) -> None:
    """
    Sync ``[tool.uv.sources]`` for a single member project.

    Normalizes ``project.dependencies`` entries that point at other
    workspace members (per ``LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE``)
    and then delegates the sources-table write to :func:`_sync_sources`
    with only the internal members this project actually depends on.
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

    _sync_sources(proj=proj, member_dependencies=member_dependencies)


def sync_member_paths(
    unfiltered_pyproject_tree: PyProjectTree,
) -> None:
    """
    Refresh ``[tool.uv.workspace].members`` patterns on the root project.

    Member directories discovered in the workspace are consolidated into the
    smallest set of literal paths and ``parent/*`` glob patterns that still
    match every member while honoring existing exclude patterns.
    """
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
            member_table: Any = workspace_table[members_key]
            member_table.clear()
            member_table.extend(member_patterns)
        else:
            workspace_table.remove(members_key)
    elif member_patterns:
        workspace_table.update({members_key: member_patterns})


def sync_pyrefly(unfiltered_pyproject_tree: PyProjectTree) -> None:
    """
    Maintain ``[tool.pyrefly].search-path`` on the root project.

    The array always starts with ``"."`` and then, for every member
    project that declares ``[tool.uv.build-backend].module-root``,
    appends the path ``<member_dir>/<module-root>`` rendered relative
    to the root project. Member entries are sorted for deterministic
    output. Other keys under ``[tool.pyrefly]`` are left untouched.
    """
    if unfiltered_pyproject_tree.filtered:
        raise ValueError("Unfiltered workspace tree required for pyrefly sync")
    root_proj = unfiltered_pyproject_tree.root
    root_dir = root_proj.path.parent.resolve()

    extra_paths: list[str] = []
    for member in unfiltered_pyproject_tree.members.values():
        # tool.uv.build-backend.module-root is set by uv-build-style projects
        # to point at the directory holding the importable package.
        build_backend = member.data.get("tool", {}).get("uv", {}).get("build-backend", {})
        module_root = build_backend.get("module-root", None)
        if not module_root:
            continue
        module_root_path = (member.path.parent / str(module_root)).resolve()
        try:
            rel_path = module_root_path.relative_to(root_dir).as_posix()
        except ValueError:
            LOG.debug(
                "Skip pyrefly entry - module_root outside root: member=%s path=%s",
                member,
                module_root_path,
            )
            continue
        extra_paths.append(rel_path)

    search_paths = [".", *sorted(extra_paths)]
    # Walk via setdefault so this works whether ``[tool]`` is a real Table
    # or an OutOfOrderTableProxy synthesized by tomlkit when several
    # ``[tool.X]`` sub-tables exist - the OutOfOrderTableProxy supports
    # MutableMapping.setdefault but not PyProject.table(create=True).
    tool_table = root_proj.data.setdefault("tool", tomlkit.table())
    pyrefly_table = tool_table.setdefault("pyrefly", tomlkit.table())
    pyrefly_table["search-path"] = search_paths


def _workspace_member_paths(
    root: pathlib.Path, paths: Iterable[pathlib.Path], excludes: list[str] | None
) -> list[str]:
    """
    Consolidate project paths into parent wildcards (e.g., ``packages/*``).

    A parent directory is only collapsed to ``parent/*`` when every non-hidden,
    non-excluded subdirectory beneath it is part of the input paths. Otherwise
    member directories are emitted as literal relative paths.
    """
    root = root.resolve()
    resolved_paths: set[pathlib.Path] = {p.resolve() for p in paths if p != root}

    if not all(p.is_relative_to(root) for p in resolved_paths):
        raise ValueError("All paths must be under root")

    excludes = excludes or []

    original_rels = {p.relative_to(root) for p in resolved_paths}
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
