import pathlib
import sys

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

    member_proj = pyproject.PyProject(expected_path / _config.PYPROJECT_FILE_NAME)
    assert member_proj.data["project"]["requires-python"] == ">=3.11"


def test_add_uses_root_requires_python(temp_workspace) -> None:
    """New members inherit the root project's requires-python specifier."""
    root_pyproject = temp_workspace / _config.PYPROJECT_FILE_NAME
    root_pyproject.write_text(
        """
[project]
name = "test-workspace"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["packages/*"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""
    )

    add_cmd.add("versioned-pkg")

    member_proj = pyproject.PyProject(
        temp_workspace / "packages" / "test-workspace-versioned-pkg" / _config.PYPROJECT_FILE_NAME
    )
    assert member_proj.data["project"]["requires-python"] == ">=3.12"


def test_default_requires_python_falls_back_to_runtime() -> None:
    """When the root omits requires-python, use the running interpreter."""
    assert pyproject.default_requires_python() == (
        f">={sys.version_info.major}.{sys.version_info.minor}"
    )


def test_sync_requires_python_updates_members(temp_workspace) -> None:
    """Sync rewrites member requires-python to match the root project."""
    pkg_dir = temp_workspace / "packages" / "pkg1"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "pkg1"
version = "0.0.0"
requires-python = ">=3.6"
"""
    )

    sync_cmd.sync(
        format_python=False,
        version=False,
        build_system=False,
        member_project=False,
        member_paths=False,
        type_checkers=False,
    )

    pkg_proj = pyproject.PyProject(pkg_dir / _config.PYPROJECT_FILE_NAME)
    assert pkg_proj.data["project"]["requires-python"] == ">=3.11"


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


def test_sync_type_checkers_emits_literal_member_paths_with_default_module_root(
    temp_workspace,
) -> None:
    """Members contribute one literal ``<rel>/<module-root>`` entry each.

    Both an explicit ``module-root = "src"`` and a missing build-backend
    section (which defaults to ``"src"``) yield the same ``.../src``
    suffix, and each member is written out explicitly rather than
    collapsed into a ``packages/*`` glob. The root project is at the
    workspace root and declares ``[project]``, so its own ``src`` entry
    leads the list.
    """
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
    sync_cmd.sync_type_checkers(tree)

    search_path = list(tree.root.data["tool"]["pyrefly"]["search-path"])
    extra_paths = list(tree.root.data["tool"]["pyright"]["extraPaths"])
    expected = ["src", "packages/dbx-tools-core/src", "packages/no-build-backend/src"]
    assert sorted(search_path) == sorted(expected)
    assert sorted(extra_paths) == sorted(expected)


def test_sync_type_checkers_honors_per_member_module_root(temp_workspace) -> None:
    """Each member's own ``module-root`` decides its search-path suffix.

    With one member using ``src`` and another using ``lib``, the output
    is ``<rel>/<member-module-root>`` per project - no attempt is made
    to fold them together.
    """
    root = temp_workspace
    pkg_src = root / "packages" / "with-src"
    pkg_src.mkdir(parents=True)
    (pkg_src / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "with-src"
version = "0.0.0"

[tool.uv.build-backend]
module-root = "src"
"""
    )
    pkg_lib = root / "packages" / "with-lib"
    pkg_lib.mkdir(parents=True)
    (pkg_lib / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "with-lib"
version = "0.0.0"

[tool.uv.build-backend]
module-root = "lib"
"""
    )

    tree = pyproject.tree()
    sync_cmd.sync_type_checkers(tree)

    search_path = list(tree.root.data["tool"]["pyrefly"]["search-path"])
    extra_paths = list(tree.root.data["tool"]["pyright"]["extraPaths"])
    expected = ["src", "packages/with-lib/lib", "packages/with-src/src"]
    assert sorted(search_path) == sorted(expected)
    assert sorted(extra_paths) == sorted(expected)


def test_sync_type_checkers_root_only_project_contributes_its_module_root(
    temp_workspace,
) -> None:
    """A single-project workspace still emits the root project's ``module-root``.

    With no ``[tool.uv.workspace].members`` and a ``[project]`` table on
    the root pyproject, the search paths collapse to just the root
    project's own ``module-root`` (``"src"`` by default).
    """
    pyproject_path = temp_workspace / _config.PYPROJECT_FILE_NAME
    pyproject_path.write_text(
        """
[project]
name = "test-workspace"
version = "0.1.0"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""
    )

    tree = pyproject.tree()
    sync_cmd.sync_type_checkers(tree)

    search_path = list(tree.root.data["tool"]["pyrefly"]["search-path"])
    extra_paths = list(tree.root.data["tool"]["pyright"]["extraPaths"])
    assert search_path == ["src"]
    assert extra_paths == ["src"]


def test_sync_type_checkers_workspace_only_root_skips_root_entry(temp_workspace) -> None:
    """A workspace-only root (no ``[project]``) does not contribute a search-path entry.

    The root pyproject is pure workspace orchestration in this case, so
    only the members show up in the search paths.
    """
    pyproject_path = temp_workspace / _config.PYPROJECT_FILE_NAME
    pyproject_path.write_text(
        """
[tool.uv.workspace]
members = ["packages/live"]
"""
    )
    pkg = temp_workspace / "packages" / "live"
    pkg.mkdir(parents=True)
    (pkg / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "live"
version = "0.0.0"
"""
    )

    tree = pyproject.tree()
    sync_cmd.sync_type_checkers(tree)

    search_path = list(tree.root.data["tool"]["pyrefly"]["search-path"])
    extra_paths = list(tree.root.data["tool"]["pyright"]["extraPaths"])
    assert search_path == ["packages/live/src"]
    assert extra_paths == ["packages/live/src"]


def test_sync_type_checkers_honors_workspace_exclude(temp_workspace) -> None:
    """Excluded directories on disk must not contribute to the search paths.

    The workspace tree is treated as the authoritative member list, so a
    directory that lives under ``packages/`` but is excluded from
    ``[tool.uv.workspace]`` never leaks into the pyrefly / pyright
    search paths, even though the filesystem still contains it.
    """
    root = temp_workspace
    pyproject_path = root / _config.PYPROJECT_FILE_NAME
    pyproject_path.write_text(
        """
[project]
name = "test-workspace"
version = "0.1.0"

[tool.uv.workspace]
members = ["packages/*"]
exclude = ["packages/legacy"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""
    )

    live = root / "packages" / "live"
    live.mkdir(parents=True)
    (live / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "live"
version = "0.0.0"
"""
    )
    legacy = root / "packages" / "legacy"
    legacy.mkdir(parents=True)
    (legacy / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "legacy"
version = "0.0.0"
"""
    )

    tree = pyproject.tree()
    sync_cmd.sync_type_checkers(tree)

    search_path = list(tree.root.data["tool"]["pyrefly"]["search-path"])
    extra_paths = list(tree.root.data["tool"]["pyright"]["extraPaths"])
    expected = ["src", "packages/live/src"]
    assert sorted(search_path) == sorted(expected)
    assert sorted(extra_paths) == sorted(expected)


def test_sync_type_checkers_writes_deeply_nested_member_paths(temp_workspace) -> None:
    """Members nested more than one level deep get their full relative path.

    A member at ``app-packages/cool/alpha`` is emitted verbatim as
    ``app-packages/cool/alpha/src`` - no glob abbreviation, no depth
    limit.
    """
    root = temp_workspace
    pyproject_path = root / _config.PYPROJECT_FILE_NAME
    pyproject_path.write_text(
        """
[project]
name = "test-workspace"
version = "0.1.0"

[tool.uv.workspace]
members = ["app-packages/cool/*"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""
    )

    for pkg_name in ("alpha", "beta"):
        pkg_dir = root / "app-packages" / "cool" / pkg_name
        pkg_dir.mkdir(parents=True)
        (pkg_dir / _config.PYPROJECT_FILE_NAME).write_text(
            f"""
[project]
name = "{pkg_name}"
version = "0.0.0"

[tool.uv.build-backend]
module-root = "src"
"""
        )

    tree = pyproject.tree()
    sync_cmd.sync_type_checkers(tree)

    search_path = list(tree.root.data["tool"]["pyrefly"]["search-path"])
    extra_paths = list(tree.root.data["tool"]["pyright"]["extraPaths"])
    expected = [
        "src",
        "app-packages/cool/alpha/src",
        "app-packages/cool/beta/src",
    ]
    assert sorted(search_path) == sorted(expected)
    assert sorted(extra_paths) == sorted(expected)


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
