import functools
import os
import pathlib
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from os import PathLike
from typing import Generic, TypeVar

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

PYPROJECT_FILE_NAME = "pyproject.toml"

_T = TypeVar("T")
_ENVAR_CONFIG_PREFIX = "LFP_BUILD_"


@dataclass
class _EnvarConfig(Generic[_T]):
    name: str
    load_fn: Callable[[str | None], _T]

    def get(self) -> _T:
        value = os.getenv(_ENVAR_CONFIG_PREFIX + self.name, None)
        if value is not None:
            value = value.strip()
        return self.load_fn(value)


PYTHON_DOTENV_FILE = _EnvarConfig[str](name="PYTHON_DOTENV_FILE", load_fn=lambda v: v or ".dev.env")
MEMBER_PROJECT_DIRECT_REFERENCE = _EnvarConfig[bool](
    name="MEMBER_PROJECT_DIRECT_REFERENCE",
    load_fn=lambda v: str(v).strip().lower() in {"true", "1", "yes", "on"} if v else False,
)


@functools.cache
def load() -> None:
    _load_dotenv()


def _load_dotenv() -> None:
    env_file_name = PYTHON_DOTENV_FILE.get()

    seen: set[pathlib.Path] = set()

    for dir_fn in (pathlib.Path.cwd, _root_dir):
        if dir_path := dir_fn():
            dir_path = dir_path.resolve()

            if dir_path in seen:
                continue
            seen.add(dir_path)

            env_file = dir_path / env_file_name
            if env_file.is_file():
                load_dotenv(env_file, override=False)


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
        if (cur / PYPROJECT_FILE_NAME).is_file():
            return cur
        else:
            parent = cur.parent
            if not parent or parent == cur:
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
            return _dir(proc.stdout.strip())
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
