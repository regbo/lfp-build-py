import os
import pathlib
import shutil
import stat
import subprocess
from typing import Annotated

import cyclopts
import tomlkit
from cyclopts import App
from lfp_logging import logs

from lfp_build import _config, pyproject, workspace, workspace_sync

"""
Utilities for creating workspace member projects.

Provides a command to create new member projects within a uv workspace,
setting up the directory structure, package layout, and dependencies.
"""

LOG = logs.logger(__name__)
_PATH = pathlib.Path("packages")
_LFP_BUILD_REPO_URL = "https://github.com/regbo/lfp-build-py.git"
_GIT_HOOKS_DIR = pathlib.Path(".githooks")
_PRE_COMMIT_HOOK = _GIT_HOOKS_DIR / "pre-commit"
_PRE_COMMIT_SCRIPT = """#!/bin/sh
set -e

# Run updates (updates pyproject files)
uv run lfp-build sync

# Stage any changes made by the sync so they land in THIS commit
git add -A

# Optional: tell the user what was staged
if ! git diff --quiet --cached; then
  echo "pre-commit: staged version updates."
fi
"""

app = App()


@app.command
def member(
    name: str,
    *,
    path: Annotated[
        pathlib.Path,
        cyclopts.Parameter(alias="-p", negative=""),
    ] = _PATH,
    project_dependency: Annotated[
        list[str] | None,
        cyclopts.Parameter(alias="-pd", negative=""),
    ] = None,
    dependency: Annotated[
        list[str] | None,
        cyclopts.Parameter(alias="-d", negative=""),
    ] = None,
) -> None:
    """
    Create a new member project in the workspace.

    Sets up a pyproject.toml and a standard src/<package>/__init__.py layout.
    Internal workspace dependencies are automatically synchronized after creation.

    Parameters
    ----------
    name
        The name of the new project (used for directory and package name).
    path
        Optional parent directory within the workspace root. Defaults to `packages/`.
    project_dependency
        List of existing workspace projects to depend on.
    dependency
        Additional dependency strings to add to the new project's dependencies.
    """

    metadata = workspace.metadata()
    root_dir = metadata.workspace_root
    path = root_dir / path
    # Ensure the specified path is within the workspace root
    if not path.is_relative_to(root_dir):
        raise ValueError(f"Path must be relative to root - root:{root_dir} path:{path}")

    _ensure_git_and_hooks(root_dir)

    project_dir = path / name
    pyproject_path = project_dir / _config.PYPROJECT_FILE_NAME

    # Don't overwrite existing projects
    if pyproject_path.exists():
        raise ValueError(f"Project already exists: {pyproject_path}")

    project_dir.mkdir(parents=True, exist_ok=True)
    LOG.info("Creating member project: %s", project_dir)

    # Initialize pyproject.toml
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
        # Validate internal workspace dependencies
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

    # Create the standard Python src layout and an __init__.py file
    package_dir = project_dir / "src" / name.replace("-", "_")
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").touch()
    workspace_sync.sync(new_pyprojects={name: pyproject.PyProject(pyproject_path)})
    LOG.info("Member project created: %s", name)
    workspace.clear_metadata_cache()


def _resolve_gitignore_source(project_parent_dir: pathlib.Path) -> pathlib.Path | None:
    """
    Resolve the best local .gitignore source file for new projects.

    Priority order:
    1) Current working directory .gitignore
    2) Parent directory used for project creation
    3) This repository's .gitignore (when available in source checkout)
    """
    candidates = [
        pathlib.Path.cwd() / ".gitignore",
        project_parent_dir / ".gitignore",
        pathlib.Path(__file__).resolve().parents[2] / ".gitignore",
    ]
    for source in candidates:
        if source.is_file():
            return source
    return None


def _copy_local_gitignore_template(
    target_dir: pathlib.Path, project_parent_dir: pathlib.Path
) -> None:
    """
    Copy a local .gitignore template to target_dir if missing.
    """
    target = target_dir / ".gitignore"
    if target.exists():
        return
    source = _resolve_gitignore_source(project_parent_dir=project_parent_dir)
    if source:
        target.write_text(source.read_text())


def _ensure_git_and_hooks(root_dir: pathlib.Path) -> None:
    """
    Ensure root_dir is a git repo and pre-commit hook wiring exists.
    """
    _ensure_git_repo(root_dir)
    _ensure_pre_commit_hook(root_dir)
    _enable_git_hooks(root_dir)


def _ensure_git_repo(root_dir: pathlib.Path) -> None:
    """
    Initialize a git repository in root_dir when one does not exist.
    """
    if not (root_dir / ".git").exists():
        subprocess.run(["git", "init"], cwd=root_dir, check=True)


def _ensure_pre_commit_hook(root_dir: pathlib.Path) -> None:
    """
    Create .githooks/pre-commit with default sync behavior if missing.
    """
    pre_commit_path = root_dir / _PRE_COMMIT_HOOK
    if pre_commit_path.exists():
        return
    pre_commit_path.parent.mkdir(parents=True, exist_ok=True)
    pre_commit_path.write_text(_PRE_COMMIT_SCRIPT)
    pre_commit_path.chmod(
        pre_commit_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )


def _enable_git_hooks(root_dir: pathlib.Path) -> None:
    """
    Configure git to use .githooks as core.hooksPath for this repository.
    """
    subprocess.run(
        ["git", "config", "core.hooksPath", _GIT_HOOKS_DIR.as_posix()],
        cwd=root_dir,
        check=True,
    )


@app.command
def project(
    name: str,
    *,
    path: Annotated[
        pathlib.Path,
        cyclopts.Parameter(alias="-p", negative=""),
    ] = pathlib.Path("."),
    dependency: Annotated[
        list[str] | None,
        cyclopts.Parameter(alias="-d", negative=""),
    ] = None,
    force: Annotated[
        bool,
        cyclopts.Parameter(alias="-f", negative=""),
    ] = False,
) -> None:
    """
    Create a new workspace root project.

    Writes a minimal root `pyproject.toml`, configures pixi settings,
    and creates a `common` member package under `packages/`.

    Parameters
    ----------
    name
        Name of the new workspace (also used for the pixi workspace name).
    path
        Parent directory to create the workspace in.
    dependency
        Additional dependency strings to add to the `common` member package.
    force
        If True, remove an existing target directory before creating the project.
    """
    parent = path.resolve()
    project_dir = parent / name
    if project_dir.exists():
        if force:
            shutil.rmtree(project_dir, ignore_errors=True)
        else:
            raise ValueError(f"Project already exists: {project_dir}")
    project_dir.mkdir(parents=True, exist_ok=False)

    lfp_build_dep = f"lfp-build @ git+{_LFP_BUILD_REPO_URL}"

    root_pyproject = project_dir / _config.PYPROJECT_FILE_NAME
    root_pyproject.write_text(
        f"""[build-system]
requires = ["uv_build>=0.9.6,<0.10.0"]
build-backend = "uv_build"

[dependency-groups]
dev = ["uv", "pytest", "{lfp_build_dep}"]

[tool.member-project]
project.requires-python = ">=3.12,<3.13"

[tool.uv.workspace]
members = ["packages/*"]

[tool.pixi.workspace]
name = "{name}"
channels = [ "conda-forge", "https://prefix.dev/regbo"]
platforms = [
  "linux-64",
  "linux-aarch64",
  "osx-64",
  "osx-arm64",
  "win-64"
]

[tool.pixi.environments]
default = {{ solve-group = "default" }}
dev = {{ features = ["dev"], solve-group = "default" }}

[tool.pixi.tasks]
uvr = "uv run"
uvm = "uv run -m"
"""
    )

    (project_dir / "packages").mkdir(exist_ok=True)

    _copy_local_gitignore_template(project_dir, project_parent_dir=parent)

    old_cwd = pathlib.Path.cwd()
    try:
        os.chdir(project_dir)
        common_deps = [
            "lfp-logging @ git+https://github.com/regbo/lfp-logging-py.git",
            *(dependency or []),
        ]
        member("common", path=_PATH, dependency=common_deps)
    finally:
        os.chdir(old_cwd)

    LOG.info("Workspace project created: %s", project_dir)


if "__main__" == __name__:
    pass
