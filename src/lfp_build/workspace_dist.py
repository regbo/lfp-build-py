import pathlib

from cyclopts import App
from lfp_logging import logs

from lfp_build import util, workspace

"""
Build distribution artifacts for each project in a uv workspace.

This module exposes the `lfp-build dist` command, which iterates workspace
members and runs `uv build --wheel` in each project directory.
"""

LOG = logs.logger(__name__)
app = App()


@app.default
def dist(
    *,
    name: list[str] | None = None,
):
    """
    Build wheel artifacts for workspace projects.

    Parameters
    ----------
    name
        Optional member project names to build. If omitted, all workspace
        projects from metadata are built in metadata order.
    """
    metadata = workspace.metadata()
    members = metadata.members

    if name:
        requested_names = set(name)
        member_map = {member.name: member for member in members}
        missing_names = sorted(requested_names - set(member_map.keys()))
        if missing_names:
            raise ValueError(f"Member project(s) not found: {', '.join(missing_names)}")
        members = [member_map[member_name] for member_name in name]

    for member in members:
        project_dir: pathlib.Path = member.path
        LOG.info("Building wheel for project: %s - path:%s", member.name, project_dir)
        util.process_run(
            "uv",
            "build",
            "--wheel",
            cwd=project_dir,
            program_name=f"uv build ({member.name})",
        )

