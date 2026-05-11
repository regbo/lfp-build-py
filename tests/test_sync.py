import pathlib

from lfp_build import _config, pyproject, version
from lfp_build.commands import add as add_cmd
from lfp_build.commands import sync as sync_cmd


def test_workspace_add_member(temp_workspace) -> None:
    """Test creating a new member project. Member dirs are root-prefixed by default."""
    add_cmd.add("new-pkg", path=pathlib.Path("packages"))

    expected_path = temp_workspace / "packages" / "test-workspace-new-pkg"
    assert expected_path.exists()
    assert (expected_path / _config.PYPROJECT_FILE_NAME).exists()
    assert (expected_path / "src" / "test_workspace" / "new_pkg" / "__init__.py").exists()


def test_workspace_sync(temp_workspace) -> None:
    """Test synchronization of build system and versions."""
    pkg_dir = temp_workspace / "packages" / "pkg1"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / _config.PYPROJECT_FILE_NAME).write_text("""
[project]
name = "pkg1"
version = "0.0.0"
""")

    sync_cmd.sync()

    pkg_proj = pyproject.PyProject(pkg_dir / _config.PYPROJECT_FILE_NAME)
    assert "build-system" in pkg_proj.data
    assert pkg_proj.data["build-system"]["build-backend"] == "hatchling.build"

    assert pkg_proj.data["project"]["version"].startswith("0.")


def test_workspace_sync_version_without_git_repo(tmp_path, monkeypatch) -> None:
    """Test that version syncing does not fail outside a git repo."""
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir(parents=True)
    pyproject_path = proj_dir / _config.PYPROJECT_FILE_NAME
    pyproject_path.write_text(
        """
[project]
name = "no-git-proj"
version = "0.0.0"
"""
    )

    monkeypatch.chdir(proj_dir)

    proj = pyproject.PyProject(pyproject_path)
    sync_cmd.sync_version([proj], version=None)

    assert proj.data["project"]["version"] == "0.0.0"


def test_workspace_sync_member_deps_plain_names_when_direct_reference_off(
    temp_workspace, monkeypatch
) -> None:
    root = temp_workspace
    pkg_a_dir = root / "packages" / "pkg_a"
    pkg_b_dir = root / "packages" / "pkg_b"
    pkg_a_dir.mkdir(parents=True)
    pkg_b_dir.mkdir(parents=True)
    (pkg_a_dir / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "pkg_a"
version = "0.0.0"
dependencies = ["pkg-b @ file://${PROJECT_ROOT}/../pkg_b"]
"""
    )
    (pkg_b_dir / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "pkg-b"
version = "0.0.0"
"""
    )

    monkeypatch.setenv("LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE", "0")
    sync_cmd.sync(
        format_python=False,
        version=False,
        build_system=False,
        member_project=False,
        member_paths=False,
    )

    pkg_a_text = (pkg_a_dir / _config.PYPROJECT_FILE_NAME).read_text()
    assert 'dependencies = ["pkg-b"]' in pkg_a_text
    assert "workspace = true" in pkg_a_text


def test_workspace_sync_member_deps_file_uri_when_direct_reference_on(
    temp_workspace, monkeypatch
) -> None:
    root = temp_workspace
    pkg_a_dir = root / "packages" / "pkg_a"
    pkg_b_dir = root / "packages" / "pkg_b"
    pkg_a_dir.mkdir(parents=True)
    pkg_b_dir.mkdir(parents=True)
    (pkg_a_dir / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "pkg_a"
version = "0.0.0"
dependencies = ["pkg-b"]
"""
    )
    (pkg_b_dir / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "pkg-b"
version = "0.0.0"
"""
    )

    monkeypatch.setenv("LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE", "1")
    sync_cmd.sync(
        format_python=False,
        version=False,
        build_system=False,
        member_project=False,
        member_paths=False,
    )

    pkg_a_text = (pkg_a_dir / _config.PYPROJECT_FILE_NAME).read_text()
    assert "pkg-b @ file://${PROJECT_ROOT}/../pkg_b" in pkg_a_text
    assert "workspace = true" in pkg_a_text


def test_sync_pyrefly_collects_module_roots(temp_workspace) -> None:
    """``[tool.pyrefly].search-path`` lists ``.`` plus each member's module-root."""
    root = temp_workspace
    pkg_with = root / "packages" / "dbx-tools-core"
    pkg_with.mkdir(parents=True)
    (pkg_with / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "dbx-tools-core"
version = "0.0.0"

[tool.uv.build-backend]
module-root = "src"
module-name = "dbx_tools.core"
"""
    )
    pkg_without = root / "packages" / "no-build-backend"
    pkg_without.mkdir(parents=True)
    (pkg_without / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "no-build-backend"
version = "0.0.0"
"""
    )

    tree = pyproject.tree()
    sync_cmd.sync_pyrefly(tree)

    search_path = list(tree.root.data["tool"]["pyrefly"]["search-path"])
    assert search_path == [".", "packages/dbx-tools-core/src"]


def test_sync_pyrefly_defaults_to_dot_when_no_module_roots(temp_workspace) -> None:
    """The table is still created with ``["."]`` when no member has a module-root."""
    pkg = temp_workspace / "packages" / "plain"
    pkg.mkdir(parents=True)
    (pkg / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "plain"
version = "0.0.0"
"""
    )

    tree = pyproject.tree()
    sync_cmd.sync_pyrefly(tree)

    search_path = list(tree.root.data["tool"]["pyrefly"]["search-path"])
    assert search_path == ["."]


def test_version_parse_single_part_pads_to_three_parts() -> None:
    assert version._parse("1") == (1, 0, 0)


def test_version_parse_two_parts_pads_patch() -> None:
    assert version._parse("1.2") == (1, 2, 0)


def test_version_parse_three_parts_is_preserved() -> None:
    assert version._parse("1.2.3") == (1, 2, 3)


def test_version_parse_handles_common_version_prefixes_and_suffixes() -> None:
    assert version._parse("v1.2.3") == (1, 2, 3)
    assert version._parse("1.2.3+rev7") == (1, 2, 3)
    assert version._parse("1.2.3-dev.4") == (1, 2, 3)


def test_version_parse_invalid_values_return_none() -> None:
    assert version._parse(None) is None
    assert version._parse("") is None
    assert version._parse("abc") is None
