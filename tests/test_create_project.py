import subprocess

from lfp_build import _config, workspace_create


def test_create_project_command(tmp_path):
    workspace_create.project("agent-demo", path=tmp_path)

    root = tmp_path / "agent-demo"
    assert (root / _config.PYPROJECT_FILE_NAME).is_file()
    assert (root / ".gitignore").is_file()
    assert (root / ".git").is_dir()
    assert (root / ".githooks" / "pre-commit").is_file()

    common = root / "packages" / "common"
    assert common.is_dir()
    assert (common / _config.PYPROJECT_FILE_NAME).is_file()

    pyproject_text = (root / _config.PYPROJECT_FILE_NAME).read_text()
    assert "[tool.pixi.workspace]" in pyproject_text
    assert 'name = "agent-demo"' in pyproject_text
    hook_text = (root / ".githooks" / "pre-commit").read_text()
    assert "uv run lfp-build sync" in hook_text
    assert "git add -A" in hook_text

    hooks_path = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert hooks_path == ".githooks"


def test_create_project_copies_local_parent_gitignore(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / ".gitignore").write_text("dist/\n.cache/\n")

    monkeypatch.chdir(parent)
    workspace_create.project("agent-local-gitignore", path=parent)

    project_root = parent / "agent-local-gitignore"
    assert (project_root / ".gitignore").is_file()
    assert (project_root / ".gitignore").read_text() == "dist/\n.cache/\n"


def test_create_member_preserves_existing_pre_commit(temp_workspace, monkeypatch):
    custom_hook = temp_workspace / ".githooks" / "pre-commit"
    custom_hook.parent.mkdir(parents=True, exist_ok=True)
    custom_hook.write_text("#!/bin/sh\necho custom\n")

    monkeypatch.chdir(temp_workspace)
    workspace_create.member("new-member")

    assert custom_hook.read_text() == "#!/bin/sh\necho custom\n"
