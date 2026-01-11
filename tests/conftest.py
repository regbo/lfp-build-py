import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

from lfp_build import pyproject


@pytest.fixture
def temp_workspace():
    """Create a temporary uv workspace with a git repo."""
    old_cwd = os.getcwd()
    # Resolve the temp directory to handle macOS /private/var symlink
    tmp_dir = pathlib.Path(tempfile.mkdtemp()).resolve()
    os.chdir(tmp_dir)

    # Init git
    subprocess.run(["git", "init"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True)

    # Create root pyproject.toml
    # Added empty exclude list to avoid crash in _workspace_member_paths
    root_pyproject = tmp_dir / "pyproject.toml"
    root_pyproject.write_text("""
[project]
name = "test-workspace"
version = "0.1.0"
requires-python = ">=3.11"

[tool.uv.workspace]
members = ["packages/*"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.member-project]
dependencies = ["requests"]
""")

    # Commit initial state
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], check=True)

    yield tmp_dir

    os.chdir(old_cwd)
    shutil.rmtree(tmp_dir)


@pytest.fixture
def sample_pyproject(temp_workspace):
    """Provide a path to a sample pyproject.toml."""
    path = temp_workspace / "sample-project"
    path.mkdir()
    pyproject_path = path / "pyproject.toml"
    pyproject_path.write_text("""
[project]
name = "sample-project"
version = "0.1.0"
dependencies = []
""")
    return pyproject.PyProject(pyproject_path)
