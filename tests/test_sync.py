import pathlib
import subprocess

from lfp_build import _config, pyproject, workspace_create, workspace_sync


def test_workspace_create_project(temp_workspace) -> None:
    """Test creating a new member project."""
    project_name = "new-pkg"
    workspace_create.create(project_name, path=pathlib.Path("packages"))

    expected_path = temp_workspace / "packages" / project_name
    assert expected_path.exists()
    assert (expected_path / _config.PYPROJECT_FILE_NAME).exists()
    assert (expected_path / "src" / "new_pkg" / "__init__.py").exists()


def test_workspace_sync(temp_workspace) -> None:
    """Test synchronization of build system and versions."""
    # Create a member project manually
    pkg_dir = temp_workspace / "packages" / "pkg1"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / _config.PYPROJECT_FILE_NAME).write_text("""
[project]
name = "pkg1"
version = "0.0.0"
""")

    # Run sync
    workspace_sync.sync()

    # Check if build-system was synced from root
    pkg_proj = pyproject.PyProject(pkg_dir / _config.PYPROJECT_FILE_NAME)
    assert "build-system" in pkg_proj.data
    assert pkg_proj.data["build-system"]["build-backend"] == "hatchling.build"

    # Check if version was synced (it should be 0.0.1+g... or similar from git)
    assert pkg_proj.data["project"]["version"].startswith("0.0.1")


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

    # Run in a directory with no .git
    monkeypatch.chdir(proj_dir)

    proj = pyproject.PyProject(pyproject_path)
    workspace_sync.sync_version([proj], version=None)

    # Should fall back to base version without raising
    assert proj.data["project"]["version"].startswith("0.0.1")


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

    monkeypatch.delenv("LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE", raising=False)
    workspace_sync.sync(
        format_python=False,
        version=False,
        build_system=False,
        member_project_tool=False,
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
    workspace_sync.sync(
        format_python=False,
        version=False,
        build_system=False,
        member_project_tool=False,
        member_paths=False,
    )

    pkg_a_text = (pkg_a_dir / _config.PYPROJECT_FILE_NAME).read_text()
    assert "pkg-b @ file://${PROJECT_ROOT}/../pkg_b" in pkg_a_text
    assert "workspace = true" in pkg_a_text


def test_infer_python_return_types_applies_stub_annotations(tmp_path, monkeypatch) -> None:
    proj_dir = tmp_path / "proj"
    package_dir = proj_dir / "src" / "demo_pkg"
    package_dir.mkdir(parents=True)
    source_path = package_dir / "__init__.py"
    source_path.write_text(
        """
def name():
    return "bob"
"""
    )

    def _process_run(*args, **kwargs) -> str:
        if args[:2] == ("basedpyright", "--createstub"):
            stub_path = proj_dir / "typings" / "demo_pkg" / "__init__.pyi"
            stub_path.parent.mkdir(parents=True, exist_ok=True)
            stub_path.write_text("def name() -> str: ...\n")
        return ""

    monkeypatch.setattr(workspace_sync.util, "process_run", _process_run)
    workspace_sync._infer_python_return_types_for_project(proj_dir, ["demo_pkg"])

    assert "def name() -> str:" in source_path.read_text()
    assert not (proj_dir / "typings").exists()


def test_infer_python_return_types_cleans_stubs_on_failure(tmp_path, monkeypatch) -> None:
    proj_dir = tmp_path / "proj"
    package_dir = proj_dir / "src" / "demo_pkg"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("def name():\n    return 'bob'\n")

    def _process_run(*args, **kwargs) -> str:
        if args[:2] == ("basedpyright", "--createstub"):
            stub_path = proj_dir / "typings" / "demo_pkg" / "__init__.pyi"
            stub_path.parent.mkdir(parents=True, exist_ok=True)
            stub_path.write_text("def name() -> str: ...\n")
            raise subprocess.CalledProcessError(returncode=1, cmd=list(args))
        return ""

    monkeypatch.setattr(workspace_sync.util, "process_run", _process_run)

    try:
        workspace_sync._infer_python_return_types_for_project(proj_dir, ["demo_pkg"])
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("Expected basedpyright stub generation failure")

    assert not (proj_dir / "typings").exists()
