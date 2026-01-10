import pathlib

from lfp_build import pyproject, workspace_create, workspace_sync


def test_workspace_create_project(temp_workspace):
    """Test creating a new member project."""
    project_name = "new-pkg"
    workspace_create.create(project_name, path=pathlib.Path("packages"))

    expected_path = temp_workspace / "packages" / project_name
    assert expected_path.exists()
    assert (expected_path / "pyproject.toml").exists()
    assert (expected_path / "src" / "new_pkg" / "__init__.py").exists()


def test_workspace_sync(temp_workspace):
    """Test synchronization of build system and versions."""
    # Create a member project manually
    pkg_dir = temp_workspace / "packages" / "pkg1"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "pyproject.toml").write_text("""
[project]
name = "pkg1"
version = "0.0.0"
""")

    # Run sync
    workspace_sync.sync()

    # Check if build-system was synced from root
    pkg_proj = pyproject.PyProject(pkg_dir / "pyproject.toml")
    assert "build-system" in pkg_proj.data
    assert pkg_proj.data["build-system"]["build-backend"] == "hatchling.build"

    # Check if version was synced (it should be 0.0.1+g... or similar from git)
    assert pkg_proj.data["project"]["version"].startswith("0.0.1")
