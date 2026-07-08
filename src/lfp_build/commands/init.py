import importlib.resources
import os
import pathlib
import shutil
from typing import Annotated

import cyclopts
from lfp_logging import logs

from lfp_build import _config
from lfp_build.commands import add as add_cmd
from lfp_build.commands import hooks as hooks_cmd

"""
Implements ``lfp-build init``.

Bootstraps a new uv workspace: writes a minimal root ``pyproject.toml``
from a bundled template, copies a local ``.gitignore`` template, installs
the lfp-build managed pre-commit hook, and seeds a ``packages/common``
member project.
"""

LOG = logs.logger(__name__)

# Resource location of the bundled root ``pyproject.toml`` template. Lives
# in the ``templates`` subpackage next to ``commands`` inside the top-level
# distribution package so ``uv_build`` ships it in both the wheel and the
# sdist, and ``importlib.resources`` can load it at runtime regardless of
# whether the package is installed or running from a source checkout.
#
# The template package name is resolved relative to this module at runtime
# (``__package__`` here is ``"<dist>.commands"``, so ``rpartition('.')[0]``
# is the top-level distribution package). This avoids hardcoding the
# distribution name.
_INIT_PYPROJECT_TEMPLATE_SUBPACKAGE = "templates"
_INIT_PYPROJECT_TEMPLATE_PACKAGE = (
    f"{__package__.rpartition('.')[0]}.{_INIT_PYPROJECT_TEMPLATE_SUBPACKAGE}"
)
_INIT_PYPROJECT_TEMPLATE_NAME = "init_pyproject.toml"


def init(
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
    Initialize a new workspace root project.

    Writes a minimal root ``pyproject.toml`` from the bundled template and
    creates a ``common`` member package under ``packages/``.

    Parameters
    ----------
    name
        Name of the new workspace. Used as the project directory name.
    path
        Parent directory to create the workspace in.
    dependency
        Additional dependency strings to add to the ``common`` member package.
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

    root_pyproject = project_dir / _config.PYPROJECT_FILE_NAME
    root_pyproject.write_text(_render_init_pyproject())

    (project_dir / "packages").mkdir(exist_ok=True)

    _copy_local_gitignore_template(project_dir, project_parent_dir=parent)

    hooks_cmd.install(project_dir)

    old_cwd = pathlib.Path.cwd()
    try:
        os.chdir(project_dir)
        common_deps = [
            "lfp-logging",
            *(dependency or []),
        ]
        add_cmd.add("core", path=add_cmd.DEFAULT_PARENT_PATH, dependency=common_deps)
    finally:
        os.chdir(old_cwd)

    LOG.info("Workspace project created: %s", project_dir)


def _render_init_pyproject() -> str:
    """
    Read the bundled root ``pyproject.toml`` template.

    The template is shipped inside the ``lfp_build.templates`` subpackage
    and read via ``importlib.resources`` so it works both when the package
    is installed (the file lives inside the wheel) and when running from a
    source checkout.
    """
    return (
        importlib.resources.files(_INIT_PYPROJECT_TEMPLATE_PACKAGE)
        .joinpath(_INIT_PYPROJECT_TEMPLATE_NAME)
        .read_text(encoding="utf-8")
    )


def _resolve_gitignore_source(project_parent_dir: pathlib.Path) -> pathlib.Path | None:
    """
    Resolve the best local ``.gitignore`` source file for new projects.

    Priority order:
    1. Current working directory ``.gitignore``
    2. The parent directory used for project creation
    3. This repository's ``.gitignore`` (when running from a source checkout)
    """
    candidates = [
        pathlib.Path.cwd() / ".gitignore",
        project_parent_dir / ".gitignore",
        pathlib.Path(__file__).resolve().parents[3] / ".gitignore",
    ]
    for source in candidates:
        if source.is_file():
            return source
    return None


def _copy_local_gitignore_template(
    target_dir: pathlib.Path, project_parent_dir: pathlib.Path
) -> None:
    """
    Copy a local ``.gitignore`` template to ``target_dir`` if missing.
    """
    target = target_dir / ".gitignore"
    if target.exists():
        return
    source = _resolve_gitignore_source(project_parent_dir=project_parent_dir)
    if source:
        target.write_text(source.read_text())
