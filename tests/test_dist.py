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
    monkeypatch.setattr(workspace_dist.workspace, "metadata", lambda: metadata)

    calls: list[tuple[tuple, dict]] = []

    def _process_run(*args, **kwargs):
        calls.append((args, kwargs))
        return ""

    monkeypatch.setattr(workspace_dist.util, "process_run", _process_run)

    workspace_dist.dist()

    assert len(calls) == 2
    assert calls[0][0] == ("uv", "build", "--wheel")
    assert calls[0][1]["cwd"] == pathlib.Path(root)
    assert calls[1][0] == ("uv", "build", "--wheel")
    assert calls[1][1]["cwd"] == pathlib.Path(pkg)


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

