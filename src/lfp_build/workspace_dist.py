import os
import pathlib
import re
import shutil
import tempfile
import urllib.parse
import zipfile

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
_REQUIRES_DIST_FILE_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[^\]]+\])?)\s*@\s*(?P<uri>file://\S+)(?:\s*;\s*(?P<marker>.+))?$"
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
    metadata = workspace.metadata()
    members = _resolve_members(name=name, metadata=metadata)
    workspace_root = metadata.workspace_root.resolve(strict=False)
    workspace_member_paths = {
        member.path.resolve(strict=False) for member in metadata.members
    }
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
            _normalize_wheel_metadata_for_workspace_paths(
                wheel_dir=temp_out_dir,
                workspace_root=workspace_root,
                workspace_member_paths=workspace_member_paths,
            )
            _copy_overwrite(source_dir=temp_out_dir, destination_dir=output_dir)


def _resolve_members(
    name: list[str] | None, metadata: workspace.Metadata
) -> list[workspace.MetadataMember]:
    """
    Resolve workspace members to build, preserving requested order when filtered.
    """
    members = metadata.members
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


def _normalize_wheel_metadata_for_workspace_paths(
    *,
    wheel_dir: pathlib.Path,
    workspace_root: pathlib.Path,
    workspace_member_paths: set[pathlib.Path],
) -> None:
    """
    Rewrite wheel METADATA entries that point to local workspace projects.

    For `Requires-Dist` entries in `name @ file://...` form, replace them with
    `name` when the file URI resolves to a path for a workspace member.
    """
    for wheel_path in wheel_dir.glob("*.whl"):
        _normalize_wheel_requires_dist(
            wheel_path=wheel_path,
            workspace_root=workspace_root,
            workspace_member_paths=workspace_member_paths,
        )


def _normalize_wheel_requires_dist(
    *,
    wheel_path: pathlib.Path,
    workspace_root: pathlib.Path,
    workspace_member_paths: set[pathlib.Path],
) -> None:
    metadata_member_name = _wheel_metadata_member_name(wheel_path=wheel_path)
    if metadata_member_name is None:
        return

    with zipfile.ZipFile(wheel_path, "r") as wheel_zip:
        metadata_bytes = wheel_zip.read(metadata_member_name)
        metadata_text = metadata_bytes.decode("utf-8")
        metadata_lines = metadata_text.splitlines(keepends=True)
        updated_lines: list[str] = []
        changed = False
        for line in metadata_lines:
            if not line.startswith("Requires-Dist:"):
                updated_lines.append(line)
                continue
            requires_dist_value = line.split(":", maxsplit=1)[1].strip()
            updated_requires_dist = _strip_workspace_file_uri_from_requirement(
                requirement=requires_dist_value,
                workspace_root=workspace_root,
                workspace_member_paths=workspace_member_paths,
            )
            if updated_requires_dist is None:
                updated_lines.append(line)
                continue
            newline = "\n" if line.endswith("\n") else ""
            updated_lines.append(f"Requires-Dist: {updated_requires_dist}{newline}")
            changed = True

    if not changed:
        return
    updated_metadata_bytes = "".join(updated_lines).encode("utf-8")
    _replace_wheel_member(
        wheel_path=wheel_path,
        member_name=metadata_member_name,
        replacement_bytes=updated_metadata_bytes,
    )


def _wheel_metadata_member_name(*, wheel_path: pathlib.Path) -> str | None:
    try:
        with zipfile.ZipFile(wheel_path, "r") as wheel_zip:
            for member_name in wheel_zip.namelist():
                if member_name.endswith(".dist-info/METADATA"):
                    return member_name
    except zipfile.BadZipFile:
        LOG.warning("Skipping invalid wheel archive while inspecting metadata: %s", wheel_path)
    return None


def _strip_workspace_file_uri_from_requirement(
    *,
    requirement: str,
    workspace_root: pathlib.Path,
    workspace_member_paths: set[pathlib.Path],
) -> str | None:
    match = _REQUIRES_DIST_FILE_RE.match(requirement)
    if match is None:
        return None
    requirement_name = match.group("name")
    marker = match.group("marker")
    uri = match.group("uri")
    parsed_uri = urllib.parse.urlparse(uri)
    if parsed_uri.scheme != "file":
        return None
    local_path = pathlib.Path(urllib.parse.unquote(parsed_uri.path)).resolve(strict=False)
    if not local_path.is_relative_to(workspace_root):
        return None
    if local_path not in workspace_member_paths:
        return None
    if marker:
        return f"{requirement_name}; {marker}"
    return requirement_name


def _replace_wheel_member(
    *, wheel_path: pathlib.Path, member_name: str, replacement_bytes: bytes
) -> None:
    temp_file_descriptor, temp_file_name = tempfile.mkstemp(
        suffix=".whl",
        prefix=f"{wheel_path.stem}-",
        dir=wheel_path.parent,
    )
    os.close(temp_file_descriptor)
    temp_wheel = pathlib.Path(temp_file_name)
    try:
        with zipfile.ZipFile(wheel_path, "r") as source_zip:
            with zipfile.ZipFile(temp_wheel, "w") as target_zip:
                for file_info in source_zip.infolist():
                    data = source_zip.read(file_info.filename)
                    if file_info.filename == member_name:
                        data = replacement_bytes
                    target_zip.writestr(file_info, data)
        temp_wheel.replace(wheel_path)
    finally:
        if temp_wheel.exists():
            temp_wheel.unlink()

