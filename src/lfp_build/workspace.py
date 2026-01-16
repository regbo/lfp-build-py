import functools
import json
import pathlib
from dataclasses import dataclass

from lfp_logging import logs

from lfp_build import util

"""
Interface for uv workspace metadata.

Provides utilities for retrieving and parsing metadata from a uv workspace,
enabling easy access to the workspace root and its member projects.
"""

LOG = logs.logger(__name__)


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
    return _metadata(path.absolute())


@functools.lru_cache(maxsize=None)
def _metadata(path: pathlib.Path) -> Metadata:
    """
    Retrieve and parse metadata from the uv workspace.

    Executes 'uv workspace metadata' and returns a Metadata instance.
    The result is cached to avoid redundant subprocess calls.
    """
    args = ["uv", "workspace", "metadata"]
    data = json.loads(util.process_run(*args))
    workspace_root = pathlib.Path(data["workspace_root"])
    members: list[MetadataMember] = []
    for member in data["members"]:
        name = member["name"]
        path = pathlib.Path(member["path"])
        members.append(MetadataMember(name=name, path=path))
    return Metadata(workspace_root=workspace_root, members=members)


def root_dir() -> pathlib.Path:
    """
    Return the root directory of the uv workspace.
    """
    return metadata().workspace_root
