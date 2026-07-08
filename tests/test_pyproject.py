from lfp_build import _config, pyproject, workspace


def test_workspace_metadata(temp_workspace) -> None:
    """Test workspace metadata retrieval."""
    meta = workspace.metadata(temp_workspace)
    # Compare resolved paths to handle macOS /private/var symlink
    assert meta.workspace_root.resolve() == temp_workspace.resolve()
    assert isinstance(meta.members, list)


def test_pyproject_loading(sample_pyproject) -> None:
    """Test loading pyproject.toml data."""
    assert sample_pyproject.data["project"]["name"] == "sample-project"


def test_pyproject_persist(temp_workspace, sample_pyproject) -> None:
    """Test persisting changes to pyproject.toml."""
    sample_pyproject.data["project"]["version"] = "0.2.0"
    sample_pyproject.persist()

    # Reload to verify
    new_proj = pyproject.PyProject(sample_pyproject.path)
    assert new_proj.data["project"]["version"] == "0.2.0"


def test_pyproject_tree(temp_workspace) -> None:
    """Test tree discovery."""
    # Create a member project
    pkg_dir = temp_workspace / "packages" / "pkg1"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / _config.PYPROJECT_FILE_NAME).write_text(
        '[project]\nname = "pkg1"\nversion = "0.1.0"'
    )

    tree = pyproject.tree()
    assert tree.root.data["project"]["name"] == "test-workspace"
    assert "pkg1" in tree.members


def test_table_create_on_out_of_order_table(temp_workspace) -> None:
    """Creating a sub-table under a split (out-of-order) parent must not crash.

    When ``[tool.uv]`` is defined across non-contiguous headers (e.g.
    ``[tool.uv.workspace]`` and ``[tool.uv]`` separated by another table),
    tomlkit represents ``tool.uv`` as an ``OutOfOrderTableProxy`` which has
    no ``.add()`` method. ``PyProject.table(create=True)`` must still be able
    to create the missing ``sources`` child.
    """
    pyproject_path = temp_workspace / _config.PYPROJECT_FILE_NAME
    pyproject_path.write_text(
        "[project]\n"
        'name = "split"\n'
        'version = "0.1.0"\n\n'
        "[tool.uv.workspace]\n"
        'members = ["packages/*"]\n\n'
        "[dependency-groups]\n"
        'dev = ["x"]\n\n'
        "[tool.uv]\n"
        'build-constraint-dependencies = ["y"]\n'
    )
    proj = pyproject.PyProject(pyproject_path)

    sources = proj.table("tool", "uv", "sources", create=True)

    assert sources is not None
    sources["shared"] = {"workspace": True}
    assert proj.table("tool", "uv", "sources")["shared"]["workspace"] is True


def test_table_create_overwrites_non_table_value(sample_pyproject) -> None:
    """A non-table value at a key must be overwritten when create=True."""
    sample_pyproject.data["project"]["version"] = "0.1.0"

    table = sample_pyproject.table("project", "version", create=True)

    assert table is not None
    assert not isinstance(sample_pyproject.data["project"]["version"], str)
