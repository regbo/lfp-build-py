import pathlib
import zipfile
from typing import Never

import pytest

from lfp_build import workspace, workspace_dist


def test_dist_builds_all_workspace_members(monkeypatch, tmp_path) -> None:
    root = tmp_path / "root"
    pkg = tmp_path / "pkg"
    root.mkdir()
    pkg.mkdir()

    metadata = workspace.Metadata(
        workspace_root=root,
        members=[
            workspace.MetadataMember(name="root", path=root),
            workspace.MetadataMember(name="pkg", path=pkg),
        ],
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(workspace_dist.workspace, "metadata", lambda: metadata)

    calls: list[tuple[tuple, dict]] = []

    def _process_run(*args, **kwargs) -> str:
        calls.append((args, kwargs))
        out_index = args.index("--out-dir")
        temp_out_dir = pathlib.Path(args[out_index + 1])
        temp_out_dir.mkdir(parents=True, exist_ok=True)
        wheel_name = f"{kwargs['cwd'].name}-0.0.1-py3-none-any.whl"
        (temp_out_dir / wheel_name).write_text("wheel")
        return ""

    monkeypatch.setattr(workspace_dist.util, "process_run", _process_run)

    workspace_dist.dist()

    assert len(calls) == 2
    assert calls[0][0][:4] == ("uv", "build", "--wheel", "--out-dir")
    assert calls[0][1]["cwd"] == pathlib.Path(root)
    assert calls[1][0][:4] == ("uv", "build", "--wheel", "--out-dir")
    assert calls[1][1]["cwd"] == pathlib.Path(pkg)
    assert (tmp_path / "dist" / "root-0.0.1-py3-none-any.whl").is_file()
    assert (tmp_path / "dist" / "pkg-0.0.1-py3-none-any.whl").is_file()


def test_dist_fails_on_unknown_member_name(monkeypatch, tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    metadata = workspace.Metadata(
        workspace_root=root,
        members=[workspace.MetadataMember(name="root", path=root)],
    )
    monkeypatch.setattr(workspace_dist.workspace, "metadata", lambda: metadata)

    with pytest.raises(ValueError, match="not found"):
        workspace_dist.dist(name=["missing"])


def test_dist_writes_to_custom_out_dir_and_overwrites(monkeypatch, tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    out_dir = tmp_path / ".example"
    out_dir.mkdir()
    existing_wheel = out_dir / "project-0.0.1+goldsha-py3-none-any.whl"
    existing_wheel.write_text("old")
    new_wheel_name = "project-0.0.1+newsha-py3-none-any.whl"

    metadata = workspace.Metadata(
        workspace_root=project,
        members=[workspace.MetadataMember(name="project", path=project)],
    )
    monkeypatch.setattr(workspace_dist.workspace, "metadata", lambda: metadata)

    def _process_run(*args, **kwargs) -> str:
        out_index = args.index("--out-dir")
        temp_out_dir = pathlib.Path(args[out_index + 1])
        temp_out_dir.mkdir(parents=True, exist_ok=True)
        (temp_out_dir / new_wheel_name).write_text("new")
        return ""

    monkeypatch.setattr(workspace_dist.util, "process_run", _process_run)

    workspace_dist.dist(out_dir=out_dir)

    assert not existing_wheel.exists()
    assert (out_dir / new_wheel_name).read_text() == "new"


def test_dist_rewrites_workspace_file_uri_requires_dist(monkeypatch, tmp_path) -> None:
    workspace_root = tmp_path / "workspace"
    dashboard = workspace_root / "dashboard"
    common = workspace_root / "packages" / "common"
    dashboard.mkdir(parents=True)
    common.mkdir(parents=True)

    metadata = workspace.Metadata(
        workspace_root=workspace_root,
        members=[
            workspace.MetadataMember(name="dashboard", path=dashboard),
            workspace.MetadataMember(name="common", path=common),
        ],
    )
    monkeypatch.setenv("LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE", "1")
    monkeypatch.setattr(workspace_dist.workspace, "metadata", lambda: metadata)

    wheel_name = "dashboard-0.0.1-py3-none-any.whl"

    def _process_run(*args, **kwargs) -> str:
        out_index = args.index("--out-dir")
        temp_out_dir = pathlib.Path(args[out_index + 1])
        temp_out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(temp_out_dir / wheel_name, "w") as wheel_zip:
            wheel_zip.writestr(
                "dashboard-0.0.1.dist-info/METADATA",
                (
                    "Metadata-Version: 2.3\n"
                    "Name: dashboard\n"
                    "Version: 0.0.1\n"
                    f"Requires-Dist: common @ file://{common}\n"
                    "Requires-Python: >=3.12, <3.13\n"
                ),
            )
        return ""

    monkeypatch.setattr(workspace_dist.util, "process_run", _process_run)

    out_dir = tmp_path / "dist"
    workspace_dist.dist(out_dir=out_dir)

    with zipfile.ZipFile(out_dir / wheel_name, "r") as wheel_zip:
        metadata_text = wheel_zip.read("dashboard-0.0.1.dist-info/METADATA").decode("utf-8")
    assert "Requires-Dist: common @ file://" not in metadata_text
    assert "Requires-Dist: common\n" in metadata_text


def test_dist_keeps_non_workspace_file_uri_requires_dist(monkeypatch, tmp_path) -> None:
    workspace_root = tmp_path / "workspace"
    dashboard = workspace_root / "dashboard"
    dashboard.mkdir(parents=True)
    external_common = tmp_path / "external-common"
    external_common.mkdir(parents=True)

    metadata = workspace.Metadata(
        workspace_root=workspace_root,
        members=[workspace.MetadataMember(name="dashboard", path=dashboard)],
    )
    monkeypatch.setenv("LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE", "1")
    monkeypatch.setattr(workspace_dist.workspace, "metadata", lambda: metadata)

    wheel_name = "dashboard-0.0.1-py3-none-any.whl"

    def _process_run(*args, **kwargs) -> str:
        out_index = args.index("--out-dir")
        temp_out_dir = pathlib.Path(args[out_index + 1])
        temp_out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(temp_out_dir / wheel_name, "w") as wheel_zip:
            wheel_zip.writestr(
                "dashboard-0.0.1.dist-info/METADATA",
                (
                    "Metadata-Version: 2.3\n"
                    "Name: dashboard\n"
                    "Version: 0.0.1\n"
                    f"Requires-Dist: common @ file://{external_common}\n"
                    "Requires-Python: >=3.12, <3.13\n"
                ),
            )
        return ""

    monkeypatch.setattr(workspace_dist.util, "process_run", _process_run)

    out_dir = tmp_path / "dist"
    workspace_dist.dist(out_dir=out_dir)

    with zipfile.ZipFile(out_dir / wheel_name, "r") as wheel_zip:
        metadata_text = wheel_zip.read("dashboard-0.0.1.dist-info/METADATA").decode("utf-8")
    assert f"Requires-Dist: common @ file://{external_common}\n" in metadata_text


def test_dist_skips_wheel_metadata_rewrite_when_direct_reference_off(monkeypatch, tmp_path) -> None:
    workspace_root = tmp_path / "workspace"
    dashboard = workspace_root / "dashboard"
    dashboard.mkdir(parents=True)
    metadata = workspace.Metadata(
        workspace_root=workspace_root,
        members=[workspace.MetadataMember(name="dashboard", path=dashboard)],
    )
    monkeypatch.delenv("LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE", raising=False)
    monkeypatch.setattr(workspace_dist.workspace, "metadata", lambda: metadata)

    def _normalize_wheels(**kwargs) -> Never:
        raise AssertionError("wheel metadata rewrite should be skipped when disabled")

    monkeypatch.setattr(
        workspace_dist,
        "_normalize_wheel_metadata_for_workspace_paths",
        _normalize_wheels,
    )

    wheel_name = "dashboard-0.0.1-py3-none-any.whl"

    def _process_run(*args, **kwargs) -> str:
        out_index = args.index("--out-dir")
        temp_out_dir = pathlib.Path(args[out_index + 1])
        temp_out_dir.mkdir(parents=True, exist_ok=True)
        (temp_out_dir / wheel_name).write_text("wheel")
        return ""

    monkeypatch.setattr(workspace_dist.util, "process_run", _process_run)

    workspace_dist.dist(out_dir=tmp_path / "dist")
