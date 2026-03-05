import subprocess

from lfp_logging import logs

from lfp_build import _config, workspace

LOG = logs.logger(__name__)


def _read_pyprojects(root) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in root.rglob(_config.PYPROJECT_FILE_NAME):
        try:
            out[str(p.relative_to(root))] = p.read_text()
        except Exception as e:
            out[str(p.relative_to(root))] = f"<<FAILED TO READ: {e}>>"
    return out


def _log_pyproject_diffs(before: dict[str, str], after: dict[str, str]) -> None:
    keys = sorted(set(before) | set(after))
    for k in keys:
        b = before.get(k)
        a = after.get(k)
        if b == a:
            continue

        LOG.info("pyproject.toml changed: %s", k)
        LOG.info("---- BEFORE (%s) ----\n%s", k, b)
        LOG.info("---- AFTER (%s) ----\n%s", k, a)


def test_metadata_repairs_missing_workspace_sources(tmp_path, monkeypatch) -> None:
    """
    If `uv workspace metadata` fails (e.g. misconfigured workspace deps), metadata()
    should attempt a best-effort repair and then retry.
    """
    root = tmp_path
    (root / "packages" / "a").mkdir(parents=True)
    (root / "packages" / "b").mkdir(parents=True)

    (root / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "root-proj"
version = "0.0.0"

[tool.uv.workspace]
members = ["packages/*"]
"""
    )

    (root / "packages" / "a" / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "a"
version = "0.0.0"
dependencies = ["b"]
"""
    )
    (root / "packages" / "b" / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "b"
version = "0.0.0"
"""
    )

    # Force the first uv metadata call to fail to exercise the repair path.
    original_process_run = workspace.util.process_run
    first = {"value": True}

    def _process_run(*args, **kwargs):
        if first["value"] and len(args) >= 3 and args[:3] == ("uv", "workspace", "metadata"):
            first["value"] = False
            raise subprocess.CalledProcessError(returncode=1, cmd=list(args))
        return original_process_run(*args, **kwargs)

    monkeypatch.setattr(workspace.util, "process_run", _process_run)

    before = _read_pyprojects(root)
    md = workspace.metadata(root)
    after = _read_pyprojects(root)

    # Log before/after for any repairs
    _log_pyproject_diffs(before, after)

    names = {m.name for m in md.members}
    assert {"root-proj", "a", "b"}.issubset(names)

    # Verify that member 'a' had its uv workspace resolution repaired.
    a_text = (root / "packages" / "a" / _config.PYPROJECT_FILE_NAME).read_text()
    assert 'dependencies = ["b"]' in a_text
    assert "workspace = true" in a_text


def test_metadata_repairs_missing_workspace_sources_with_direct_reference(
    tmp_path, monkeypatch
) -> None:
    """
    When direct reference mode is enabled, metadata repair should inject file://
    dependency references for workspace members.
    """
    monkeypatch.setenv("LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE", "1")
    root = tmp_path
    (root / "packages" / "a").mkdir(parents=True)
    (root / "packages" / "b").mkdir(parents=True)

    (root / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "root-proj"
version = "0.0.0"

[tool.uv.workspace]
members = ["packages/*"]
"""
    )
    (root / "packages" / "a" / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "a"
version = "0.0.0"
dependencies = ["b"]
"""
    )
    (root / "packages" / "b" / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "b"
version = "0.0.0"
"""
    )

    original_process_run = workspace.util.process_run
    first = {"value": True}

    def _process_run(*args, **kwargs):
        if first["value"] and len(args) >= 3 and args[:3] == ("uv", "workspace", "metadata"):
            first["value"] = False
            raise subprocess.CalledProcessError(returncode=1, cmd=list(args))
        return original_process_run(*args, **kwargs)

    monkeypatch.setattr(workspace.util, "process_run", _process_run)

    workspace.metadata(root)
    a_text = (root / "packages" / "a" / _config.PYPROJECT_FILE_NAME).read_text()
    assert "file://${PROJECT_ROOT}/../b" in a_text
    assert "workspace = true" in a_text


def test_metadata_rolls_back_repairs_on_error(tmp_path, monkeypatch) -> None:
    """If uv metadata still fails after repair, any on-disk fixes are rolled back."""
    root = tmp_path
    (root / "packages" / "a").mkdir(parents=True)
    (root / "packages" / "b").mkdir(parents=True)

    (root / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "root-proj"
version = "0.0.0"

[tool.uv.workspace]
members = ["packages/*"]
"""
    )

    a_pyproject = root / "packages" / "a" / _config.PYPROJECT_FILE_NAME
    a_pyproject.write_text(
        """
[project]
name = "a"
version = "0.0.0"
dependencies = ["b"]
"""
    )
    (root / "packages" / "b" / _config.PYPROJECT_FILE_NAME).write_text(
        """
[project]
name = "b"
version = "0.0.0"
"""
    )

    original_a_text = a_pyproject.read_text()

    # Force all uv metadata calls to fail so the repair path will be rolled back.
    original_process_run = workspace.util.process_run

    def _process_run(*args, **kwargs):
        if len(args) >= 3 and args[:3] == ("uv", "workspace", "metadata"):
            raise subprocess.CalledProcessError(returncode=1, cmd=list(args))
        return original_process_run(*args, **kwargs)

    monkeypatch.setattr(workspace.util, "process_run", _process_run)

    before = _read_pyprojects(root)
    md = workspace.metadata(root)
    after = _read_pyprojects(root)

    # Log before/after; ideally no diffs due to rollback
    _log_pyproject_diffs(before, after)

    names = {m.name for m in md.members}
    assert {"root-proj", "a", "b"}.issubset(names)

    # Ensure changes were rolled back.
    assert a_pyproject.read_text() == original_a_text
