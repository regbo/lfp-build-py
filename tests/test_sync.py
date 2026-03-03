import pathlib

from lfp_build import _config, pyproject, workspace_create, workspace_sync


def test_workspace_create_project(temp_workspace):
    """Test creating a new member project."""
    project_name = "new-pkg"
    workspace_create.create(project_name, path=pathlib.Path("packages"))

    expected_path = temp_workspace / "packages" / project_name
    assert expected_path.exists()
    assert (expected_path / _config.PYROJECT_FILE_NAME).exists()
    assert (expected_path / "src" / "new_pkg" / "__init__.py").exists()


def test_workspace_sync(temp_workspace):
    """Test synchronization of build system and versions."""
    # Create a member project manually
    pkg_dir = temp_workspace / "packages" / "pkg1"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / _config.PYROJECT_FILE_NAME).write_text("""
[project]
name = "pkg1"
version = "0.0.0"
""")

    # Run sync
    workspace_sync.sync()

    # Check if build-system was synced from root
    pkg_proj = pyproject.PyProject(pkg_dir / _config.PYROJECT_FILE_NAME)
    assert "build-system" in pkg_proj.data
    assert pkg_proj.data["build-system"]["build-backend"] == "hatchling.build"

    # Check if version was synced (it should be 0.0.1+g... or similar from git)
    assert pkg_proj.data["project"]["version"].startswith("0.0.1")


def test_workspace_sync_version_without_git_repo(tmp_path, monkeypatch):
    """Test that version syncing does not fail outside a git repo."""
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir(parents=True)
    pyproject_path = proj_dir / _config.PYROJECT_FILE_NAME
    pyproject_path.write_text(
        """
[project]
name = "no-git-proj"
version = "0.0.0"
"""
    )

    # Run in a directory with no .git
    monkeypatch.chdir(proj_dir)

    proj = pyproject.PyProject(pyproject_path)
    workspace_sync.sync_version([proj], version=None)

    # Should fall back to base version without raising
    assert proj.data["project"]["version"].startswith("0.0.1")
