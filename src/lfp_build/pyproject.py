import functools
import hashlib
import logging
import os
import pathlib
from dataclasses import dataclass, field
from typing import Collection, Mapping
from urllib.parse import urlparse

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.items import Table

from lfp_build import util, workspace

"""
Utility for managing and manipulating pyproject.toml files.

This module provides the PyProject class for high-level operations on
pyproject.toml files, including reading, updating, and persisting changes
while preserving formatting using tomlkit.
"""

LOG = util.logger(__name__)
FILE_NAME = "pyproject.toml"
_MAX_BLANK_LINES = 1
_INDENT = " " * 4


class PyProject:
    """
    Interface for interacting with a pyproject.toml file.

    Handles lazy loading, modification, and persistence of project metadata
    using tomlkit for round-trip compatibility and taplo for formatting.
    """

    def __init__(self, path: pathlib.Path):
        """
        Initialize a PyProject instance.
        """
        self.path = _file_path(path)
        self._data: TOMLDocument | None = None

    @property
    def data(self) -> TOMLDocument:
        """
        Lazily load and return the TOML data from the pyproject.toml file.
        """
        if self._data is None:
            LOG.debug("Reading: %s", self.path)
            with self.path.open("rb") as f:
                self._data = tomlkit.load(f)
        return self._data

    def persist(self, force_format: bool = False) -> bool:
        """
        Save the current state of the project configuration to disk.

        If the content has changed, it writes to a temporary file, formats it
        using taplo, and then moves it to the destination.
        """
        hash_stat: tuple[str, os.stat_result] | None = None
        data = self._data
        if data is not None:
            LOG.debug("Persisting: %s", self.path)
            _prune(data)
            hash_stat = _hash_stat(self.path)
            with self.path.open("w") as f:
                tomlkit.dump(data, f)
            _format(self.path)
        elif force_format:
            hash_stat = _hash_stat(self.path)
            _format(self.path)
        if hash_stat is not None:
            updated_hash_stat = _hash_stat(self.path)
            if hash_stat[0] != updated_hash_stat[0]:
                return True
            LOG.debug("File unchanged reverting utime: %s", self)
            st = hash_stat[1]
            os.utime(self.path, (st.st_atime, st.st_mtime))
        self._data = None
        return False

    def table(self, *keys: str, create: bool = False) -> Table | None:
        """
        Navigate to a specific table in the TOML hierarchy.

        Optionally creates the table path if it doesn't exist.
        """
        cur_table = self.data
        for key in keys:
            value = cur_table.get(key, None)
            if not isinstance(value, Mapping):
                if create:
                    value = tomlkit.table(True)
                    if key in cur_table:
                        cur_table.remove(key)
                    else:
                        cur_table.add(key, value)
                else:
                    return None
            cur_table = value
        return cur_table

    def __repr__(self):
        if data := self._data:
            name = data.get("project", {}).get("name", "[UNKNOWN]")
        else:
            name = "[UNLOADED]"
        return f"{self.__class__.__name__}(name={name} path={self.path})"


@dataclass
class PyProjectTree:
    """
    Represents the hierarchical structure of a uv workspace.

    Includes the root project and all discovered member projects.
    """

    name: str
    root: PyProject
    filtered: bool = field(default=False, init=False)
    members: dict[str, PyProject] = field(default_factory=dict)

    def projects(self) -> list[PyProject]:
        """
        Return a list of all projects in the tree, starting with the root.
        """
        return [self.root, *self.members.values()]

    def filter_members(
        self, names: list[str] | None, required: bool = False
    ) -> "PyProjectTree":
        """
        Filter the members dictionary to only include specified names.

        Args:
            names: List of member names to keep. If None, no filtering is performed.
            required: If True, raises ValueError if a specified name is not found.
        """
        if not names:
            return self
        members_copy: dict[str, PyProject] = {}
        for name in [names, *self.members.keys()]:
            if name in members_copy:
                continue
            member_proj = self.members.get(name, None)
            if member_proj is None:
                if required:
                    raise ValueError("Member %s not found" % name)
                continue
            members_copy[name] = member_proj
        pyproject_tree_copy = PyProjectTree(
            name=name, root=self.root, members=members_copy
        )
        pyproject_tree_copy.filtered = True
        return pyproject_tree_copy


def tree(metadata: workspace.Metadata | None = None) -> PyProjectTree:
    """
    Discover and load all projects within a uv workspace into a tree.

    Args:
        metadata: Optional workspace metadata. If omitted, it is retrieved automatically.
    """
    if metadata is None:
        metadata = workspace.metadata()
    root_proj_name: str | None = None
    member_projs: dict[str, PyProject] = {}
    for member in metadata.members:
        if metadata.workspace_root == member.path:
            root_proj_name = member.name
            continue
        member_projs[member.name] = PyProject(member.path)
    root_proj: PyProject = PyProject(metadata.workspace_root)
    return PyProjectTree(
        name=root_proj_name or _git_repo_name(root_proj.path) or root_proj.path.name,
        root=root_proj,
        members=member_projs,
    )


def _prune(data: Mapping):
    def _is_empty(d) -> bool:
        if not isinstance(d, str) and isinstance(d, (Collection, Mapping)):
            return len(d) == 0
        else:
            return False

    if isinstance(data, Mapping):
        for k in list(data.keys()):
            v = data[k]
            _prune(v)
            if _is_empty(v):
                del data[k]
    elif not isinstance(data, str) and isinstance(data, Collection):
        for i in range(len(data) - 1, -1, -1):
            v = data[i]
            _prune(v)
            if _is_empty(v):
                del data[i]


def _hash_stat(path: pathlib.Path) -> tuple[str, os.stat_result]:
    with open(path, "rb") as f:
        hash = hashlib.file_digest(f, "sha256").hexdigest()
    stat = path.stat()
    return hash, stat


def _git_repo_name(path: pathlib.Path) -> str | None:
    """
    Attempt to determine the git repository name from the origin remote URL.
    """
    args = ["git", "remote", "get-url", "origin"]
    cwd = path.parent if path is not None and path.is_file() else path
    git_origin_url = util.process_run(
        "git", "remote", "get-url", "origin", check=False, cwd=cwd
    )
    if git_origin_url:
        # Normalize SSH form to URL so urlparse can handle it
        if git_origin_url.startswith("git@"):
            # git@github.com:owner/repo.git -> ssh://git@github.com/owner/repo.git
            git_origin_url = "ssh://" + git_origin_url.replace(":", "/", 1)
        git_origin_url_path = urlparse(git_origin_url).path
        if git_origin_url_path:
            repo_name = (
                git_origin_url_path.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
            )
            if repo_name:
                return repo_name
    LOG.debug(
        "Git remote url not found - git_origin_url:%s args:%s", git_origin_url, args
    )
    return None


def _file_path(path: pathlib.Path) -> pathlib.Path:
    """
    Normalize a path to a pyproject.toml file, creating parent directories if needed.
    """
    if path.is_dir():
        return path / FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _format(path: pathlib.Path):
    """
    Apply taplo formatting to a TOML file with workspace-specific options.
    """
    if taplo_commands := _taplo_commands():
        program = taplo_commands[0]
        args = taplo_commands[1:]
        args.extend(
            [
                "fmt",
                "--option",
                f"allowed_blank_lines={_MAX_BLANK_LINES}",
                "--option",
                f"indent_string={_INDENT}",
                path.absolute(),
            ]
        )
        util.process_run(
            program, *args, program_name="taplo", stdout_log_level=logging.DEBUG
        )
    else:
        program = "tombi"
        util.process_run(
            "uv",
            "tool",
            "run",
            "--",
            program,
            "format",
            program_name=program,
            stdout_log_level=logging.DEBUG,
        )


@functools.cache
def _taplo_commands() -> list[str] | None:
    program = "taplo"
    for commands in [[program], ["uv", "tool", "run", "--", program]]:
        try:
            if util.process_run(
                commands[0], *commands[1:], "--version", stderr_log_level=None
            ):
                return commands
        except Exception:
            continue
    LOG.debug("Taplo unavailable")
    return None


if __name__ == "__main__":
    print(_git_repo_name(pathlib.Path.cwd()))
