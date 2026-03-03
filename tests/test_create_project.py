from lfp_build import workspace_create


def test_create_project_command(tmp_path):
    workspace_create.project("agent-demo", path=tmp_path)

    root = tmp_path / "agent-demo"
    assert (root / "pyproject.toml").is_file()
    assert (root / "bootstrap.sh").is_file()
    assert (root / "bootstrap.ps1").is_file()
    assert (root / ".gitignore").is_file()

    common = root / "packages" / "common"
    assert common.is_dir()
    assert (common / "pyproject.toml").is_file()

    pyproject_text = (root / "pyproject.toml").read_text()
    assert '[tool.pixi.workspace]' in pyproject_text
    assert 'name = "agent-demo"' in pyproject_text

    assert "[tasks]" in pixi_toml_text
    assert 'uvr = "uv run ' in pixi_toml_text

