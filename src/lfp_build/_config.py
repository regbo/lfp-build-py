import functools
import os
import pathlib
import subprocess
from os import PathLike

from dotenv import load_dotenv

"""
Environment configuration loader for lfp-build.

This module is registered via `sitecustomize-entrypoints` (see
`pyproject.toml` under `[project.entry-points.sitecustomize]`) so it is
automatically executed on Python startup. It loads environment variables from
a dotenv file.

The dotenv file defaults to `.dev.env` and can be overridden by setting the
`PYTHON_DOTENV_FILE` environment variable.
"""

PYROJECT_FILE_NAME = "pyproject.toml"

_ENV_FILE_NAME_ENVAR_NAME = "PYTHON_DOTENV_FILE"
_ENV_FILE_NAME_DEFAULT = ".dev.env"


def load():
    _load_dotenv()


def _load_dotenv():
    env_file_name = os.getenv(_ENV_FILE_NAME_ENVAR_NAME, None) or _ENV_FILE_NAME_DEFAULT
    for dir_fn in (pathlib.Path.cwd, _root_dir):
        if dir := dir_fn():
            env_file = dir / env_file_name
            if env_file.is_file():
                load_dotenv(env_file)


def _root_dir() -> pathlib.Path | None:
    """
    Return the root directory of the uv workspace.
    """
    if root_dir := _dir(os.getenv("PROJECT_ROOT")):
        return root_dir
    elif root_dir := _uv_workspace_dir():
        return root_dir
    elif root_dir := _git_toplevel():
        return root_dir
    cur = pathlib.Path.cwd()
    while True:
        if (cur / PYROJECT_FILE_NAME).is_file():
            return cur
        else:
            parent = cur.parent
            if parent == cur:
                break
            cur = parent
    return None


@functools.cache
def _uv_workspace_dir() -> pathlib.Path | None:
    return _dir_command("uv", "workspace", "dir")


@functools.cache
def _git_toplevel() -> pathlib.Path | None:
    return _dir_command("git", "rev-parse", "--show-toplevel")


def _dir_command(*args: str) -> pathlib.Path | None:
    # noinspection PyBroadException
    try:
        proc = subprocess.run(
            list(args),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if proc.returncode == 0:
            return _dir(proc.stdout)
    except Exception:
        pass
    return None


def _dir(path: PathLike | str | None) -> pathlib.Path | None:
    if not path:
        return None
    elif isinstance(path, str):
        path = path.strip()
        if not path:
            return None
    path = pathlib.Path(path)
    return path if path.is_dir() else None
