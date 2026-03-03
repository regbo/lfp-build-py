import pathlib

import pytest

from lfp_build import workspace, workspace_dist


def test_dist_builds_all_workspace_members(monkeypatch, tmp_path):
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

    def _process_run(*args, **kwargs):
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


def test_dist_fails_on_unknown_member_name(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    metadata = workspace.Metadata(
        workspace_root=root,
        members=[workspace.MetadataMember(name="root", path=root)],
    )
    monkeypatch.setattr(workspace_dist.workspace, "metadata", lambda: metadata)

    with pytest.raises(ValueError, match="not found"):
        workspace_dist.dist(name=["missing"])


def test_dist_writes_to_custom_out_dir_and_overwrites(monkeypatch, tmp_path):
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

    def _process_run(*args, **kwargs):
        out_index = args.index("--out-dir")
        temp_out_dir = pathlib.Path(args[out_index + 1])
        temp_out_dir.mkdir(parents=True, exist_ok=True)
        (temp_out_dir / new_wheel_name).write_text("new")
        return ""

    monkeypatch.setattr(workspace_dist.util, "process_run", _process_run)

    workspace_dist.dist(out_dir=out_dir)

    assert not existing_wheel.exists()
    assert (out_dir / new_wheel_name).read_text() == "new"

