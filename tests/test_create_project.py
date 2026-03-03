from lfp_build import workspace_create


def test_create_project_command(tmp_path):
    workspace_create.project("agent-demo", path=tmp_path)

    root = tmp_path / "agent-demo"
    assert (root / "pyproject.toml").is_file()
    assert (root / ".gitignore").is_file()

    common = root / "packages" / "common"
    assert common.is_dir()
    assert (common / "pyproject.toml").is_file()

    pyproject_text = (root / "pyproject.toml").read_text()
    assert '[tool.pixi.workspace]' in pyproject_text
    assert 'name = "agent-demo"' in pyproject_text


def test_create_project_copies_local_parent_gitignore(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / ".gitignore").write_text("dist/\n.cache/\n")

    monkeypatch.chdir(parent)
    workspace_create.project("agent-local-gitignore", path=parent)

    project_root = parent / "agent-local-gitignore"
    assert (project_root / ".gitignore").is_file()
    assert (project_root / ".gitignore").read_text() == "dist/\n.cache/\n"

