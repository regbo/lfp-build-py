from lfp_build import pyproject, workspace


def test_workspace_metadata(temp_workspace):
    """Test workspace metadata retrieval."""
    meta = workspace.metadata(temp_workspace)
    # Compare resolved paths to handle macOS /private/var symlink
    assert meta.workspace_root.resolve() == temp_workspace.resolve()
    assert isinstance(meta.members, list)


def test_pyproject_loading(sample_pyproject):
    """Test loading pyproject.toml data."""
    assert sample_pyproject.data["project"]["name"] == "sample-project"


def test_pyproject_persist(temp_workspace, sample_pyproject):
    """Test persisting changes to pyproject.toml."""
    sample_pyproject.data["project"]["version"] = "0.2.0"
    sample_pyproject.persist()

    # Reload to verify
    new_proj = pyproject.PyProject(sample_pyproject.path)
    assert new_proj.data["project"]["version"] == "0.2.0"


def test_pyproject_tree(temp_workspace):
    """Test tree discovery."""
    # Create a member project
    pkg_dir = temp_workspace / "packages" / "pkg1"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "pyproject.toml").write_text(
        '[project]\nname = "pkg1"\nversion = "0.1.0"'
    )

    tree = pyproject.tree()
    assert tree.root.data["project"]["name"] == "test-workspace"
    assert "pkg1" in tree.members
