import functools
import hashlib
import logging
import pathlib
import shutil
from dataclasses import dataclass, field
from tempfile import NamedTemporaryFile
from typing import Any, Collection, Mapping
from urllib.parse import urlparse

import tomlkit
from lfp_logging import logs
from tomlkit import TOMLDocument
from tomlkit.items import Table

from lfp_build import util, workspace

"""
Utility for managing and manipulating pyproject.toml files.

This module provides the PyProject class for high-level operations on
pyproject.toml files, including reading, updating, and persisting changes
while preserving formatting using tomlkit.

Formatting is applied using taplo when available, with a fallback to tombi.
"""

LOG = logs.logger(__name__)
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

    def persist(self, force_format: bool = False) -> str | None:
        """
        Save the current state of the project configuration to disk.

        If the content has changed or force_format is True, it writes to a
        temporary file, formats it using taplo (or tombi), and then moves
        it to the destination if the hash differs from the original.

        Args:
            force_format: If True, formats the file even if no data changes were made.

        Returns:
            The previous file hash if the file was updated, otherwise None.
        """
        data = self._data
        if data is None and not force_format:
            return None
        hash = _hash(self.path)
        temp_path = pathlib.Path(NamedTemporaryFile(delete=False, suffix=".toml").name)
        try:
            if data is not None:
                # Remove empty tables/arrays before saving
                _prune(data)
                data_text = tomlkit.dumps(data).strip() + "\n"
                with temp_path.open("w") as f:
                    f.write(data_text)
            else:
                # No in-memory changes, just format existing file
                shutil.copy(self.path, temp_path)

            _format(temp_path)

            # Only overwrite if the formatted output actually differs
            if hash != _hash(temp_path):
                temp_path.rename(self.path)
                temp_path = None
                return hash
            else:
                return None
        finally:
            self._data = None
            if temp_path is not None:
                temp_path.unlink()

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
        Return a list of all projects in the tree.

        Returns:
            A list containing the root project followed by all member projects.
        """
        return [self.root, *self.members.values()]

    def filter_members(
        self, names: list[str] | None, required: bool = False
    ) -> "PyProjectTree":
        """
        Create a new tree containing only the specified member projects.

        Args:
            names: List of member names to include. If None, all members are included.
            required: If True, raises ValueError if a specified name is not found in the tree.

        Returns:
            A new PyProjectTree instance with the filtered members.
        """
        if not names:
            return self
        members_copy: dict[str, PyProject] = {}
        # Iterate over both the requested names and existing members
        # to ensure we capture the requested ones correctly.
        for name in [*names, *self.members.keys()]:
            if name in members_copy:
                continue
            member_proj = self.members.get(name, None)
            if member_proj is None:
                if required and name in names:
                    raise ValueError("Member %s not found" % name)
                continue
            if name in names:
                members_copy[name] = member_proj

        # Determine the name for the new tree
        new_tree_name = self.name

        pyproject_tree_copy = PyProjectTree(
            name=new_tree_name, root=self.root, members=members_copy
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


def _prune(data: Any):
    """
    Recursively remove empty tables and arrays from a TOML document.

    This ensures that the final pyproject.toml doesn't contain noise from
    partially populated or cleared configuration sections.
    """

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


def _hash(path: pathlib.Path) -> str:
    """
    Calculate the MD5 hash of a file's content.

    Used to detect if formatting or data changes actually modified the file.
    """
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "md5").hexdigest()


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
        path = path / FILE_NAME
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return path.resolve().relative_to(pathlib.Path.cwd())
    except ValueError:
        return path


def _format(path: pathlib.Path):
    """
    Apply formatting to a TOML file.

    Attempts to use 'taplo' if available (either globally or via 'uv tool run').
    Falls back to 'tombi' via 'uv tool run' if taplo is not found.
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
            path.absolute(),
            program_name=program,
            stdout_log_level=logging.DEBUG,
        )


@functools.cache
def _taplo_commands() -> list[str] | None:
    """
    Detect the command needed to run taplo.

    Checks for a native 'taplo' installation first, then tries 'uv tool run taplo'.
    """
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
