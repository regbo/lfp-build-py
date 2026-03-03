import pathlib
import re
import shutil
import tempfile

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
_WHEEL_NAME_RE = re.compile(
    r"^(?P<dist>[^-]+)-(?P<version>[^-]+)(?:-[^-]+)?-[^-]+-[^-]+-[^-]+\.whl$"
)


@app.default
def dist(
    *,
    name: list[str] | None = None,
    out_dir: pathlib.Path = pathlib.Path("./dist"),
) -> None:
    """
    Build wheel artifacts for workspace projects.

    Parameters
    ----------
    name
        Optional member project names to build. If omitted, all workspace
        projects from metadata are built in metadata order.
    out_dir
        Destination directory for built artifacts. Builds are performed in a
        temporary directory first, then copied into this directory with
        overwrite semantics.
    """
    members = _resolve_members(name=name)
    output_dir = out_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    for member in members:
        project_dir: pathlib.Path = member.path
        with tempfile.TemporaryDirectory(prefix=f"lfp-build-dist-{member.name}-") as temp_dir:
            temp_out_dir = pathlib.Path(temp_dir)
            LOG.info("Building wheel for project: %s - path:%s", member.name, project_dir)
            util.process_run(
                "uv",
                "build",
                "--wheel",
                "--out-dir",
                temp_out_dir,
                cwd=project_dir,
                program_name=f"uv build ({member.name})",
            )
            _copy_overwrite(source_dir=temp_out_dir, destination_dir=output_dir)


def _resolve_members(name: list[str] | None) -> list[workspace.MetadataMember]:
    """
    Resolve workspace members to build, preserving requested order when filtered.
    """
    members = workspace.metadata().members
    if not name:
        return members

    requested_names = set(name)
    member_map = {member.name: member for member in members}
    missing_names = sorted(requested_names - set(member_map.keys()))
    if missing_names:
        raise ValueError(f"Member project(s) not found: {', '.join(missing_names)}")
    return [member_map[member_name] for member_name in name]


def _copy_overwrite(source_dir: pathlib.Path, destination_dir: pathlib.Path) -> None:
    """
    Copy files from source_dir into destination_dir, replacing existing files.
    """
    for source_path in source_dir.rglob("*"):
        if not source_path.is_file():
            continue
        relative_path = source_path.relative_to(source_dir)
        destination_path = destination_dir / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.suffix == ".whl":
            wheel_dist_name = _wheel_distribution_name(source_path.name)
            if wheel_dist_name is not None:
                _delete_matching_distribution_wheels(
                    destination_dir=destination_path.parent,
                    wheel_dist_name=wheel_dist_name,
                )
        elif destination_path.exists():
            destination_path.unlink()
        shutil.copy2(source_path, destination_path)


def _wheel_distribution_name(filename: str) -> str | None:
    """
    Extract normalized wheel distribution name from a wheel filename.
    """
    match = _WHEEL_NAME_RE.match(filename)
    if match is None:
        return None
    return match.group("dist")


def _delete_matching_distribution_wheels(
    destination_dir: pathlib.Path, wheel_dist_name: str
) -> None:
    """
    Delete existing wheel files for the same distribution in destination_dir.
    """
    for existing_wheel in destination_dir.glob("*.whl"):
        existing_dist_name = _wheel_distribution_name(existing_wheel.name)
        if existing_dist_name == wheel_dist_name:
            existing_wheel.unlink()

