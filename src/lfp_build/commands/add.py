import pathlib
from typing import Annotated

import cyclopts
import tomlkit
from lfp_logging import logs

from lfp_build import _config, pyproject, workspace
from lfp_build.commands import sync as sync_cmd

"""
Implements ``lfp-build add``.

Creates a new uv workspace member project. Sets up the directory layout, a
seeded ``pyproject.toml``, and a standard ``src/<package>/__init__.py``,
then runs a workspace sync so the new member is wired into the root
``[tool.uv.workspace]`` configuration immediately.
"""

LOG = logs.logger(__name__)
DEFAULT_PARENT_PATH = pathlib.Path("packages")


def add(
    name: str,
    *,
    path: Annotated[
        pathlib.Path,
        cyclopts.Parameter(alias="-p", negative=""),
    ] = DEFAULT_PARENT_PATH,
    project_dependency: Annotated[
        list[str] | None,
        cyclopts.Parameter(alias="-c", negative=""),
    ] = None,
    dependency: Annotated[
        list[str] | None,
        cyclopts.Parameter(alias="-d", negative=""),
    ] = None,
) -> None:
    """
    Add a new member project to the workspace.

    Sets up a pyproject.toml and a standard ``src/<package>/__init__.py``
    layout. Internal workspace dependencies are automatically synchronized
    after creation.

    Parameters
    ----------
    name
        The name of the new project (used for directory and package name).
    path
        Optional parent directory within the workspace root. Defaults to
        ``packages/``.
    project_dependency
        List of existing workspace projects to depend on.
    dependency
        Additional dependency strings to add to the new project's
        ``project.dependencies`` array.
    """
    metadata = workspace.metadata()
    root_dir = metadata.workspace_root
    path = root_dir / path
    if not path.is_relative_to(root_dir):
        raise ValueError(f"Path must be relative to root - root:{root_dir} path:{path}")

    project_dir = path / name
    pyproject_path = project_dir / _config.PYPROJECT_FILE_NAME

    if pyproject_path.exists():
        raise ValueError(f"Project already exists: {pyproject_path}")

    project_dir.mkdir(parents=True, exist_ok=True)
    LOG.info("Creating member project: %s", project_dir)

    pyproject_data = {
        "project": {
            "name": name,
            "version": "0",
            "requires-python": ">=3.6",
        },
    }
    pyproject_tree = pyproject.tree(metadata=metadata)
    deps = tomlkit.array()
    deps.multiline(True)
    has_deps = False

    if dependency:
        for dep in dependency:
            deps.append(dep)
            has_deps = True

    if project_dependency:
        # Validate that internal dependencies refer to known workspace projects.
        project_tree_names = [
            pyproject_tree.name,
            *pyproject_tree.members.keys(),
        ]
        for dep in project_dependency:
            if dep not in project_tree_names:
                raise ValueError(f"Invalid project dependency: {dep}")
            deps.append(dep)
            has_deps = True

    if has_deps:
        pyproject_data["project"]["dependencies"] = deps

    pyproject_path.write_text(tomlkit.dumps(pyproject_data))

    package_dir = project_dir / "src" / name.replace("-", "_")
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").touch()
    sync_cmd.sync(new_pyprojects={name: pyproject.PyProject(pyproject_path)})
    LOG.info("Member project created: %s", name)
    workspace.clear_metadata_cache()
