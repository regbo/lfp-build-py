import pathlib

import pytest

from lfp_build import bundle


def test_list_bundled_names_returns_seed_content() -> None:
    """The bundled resources ship with at least the seed skill and doc."""
    skills = bundle.list_bundled_names("skills")
    docs = bundle.list_bundled_names("docs")

    assert "lfp-build-workspace" in skills
    assert "lfp-build-conventions" in docs


def test_hosts_returns_cursor_and_claude() -> None:
    """The install-side host list is stable across the two commands."""
    assert set(bundle.hosts()) == {"cursor", "claude"}


def test_resolve_target_dir_workspace_layout(tmp_path: pathlib.Path) -> None:
    """Non-global installs land under ``<base>/.<host>/<kind>``."""
    cursor_dir = bundle.resolve_target_dir(
        host="cursor", kind="skills", global_install=False, base_dir=tmp_path
    )
    claude_dir = bundle.resolve_target_dir(
        host="claude", kind="docs", global_install=False, base_dir=tmp_path
    )

    assert cursor_dir == tmp_path / ".cursor" / "skills"
    assert claude_dir == tmp_path / ".claude" / "docs"


def test_resolve_target_dir_global_uses_home(tmp_path: pathlib.Path) -> None:
    """The global flag targets the user's home directory, ignoring ``base_dir``."""
    resolved = bundle.resolve_target_dir(
        host="cursor", kind="skills", global_install=True, base_dir=tmp_path
    )

    assert resolved == pathlib.Path.home() / ".cursor" / "skills"


def test_install_skills_creates_target_files(tmp_path: pathlib.Path) -> None:
    """A first-time skills install copies files and reports them as installed."""
    report = bundle.install(
        kind="skills",
        host="cursor",
        global_install=False,
        force=False,
        dry_run=False,
        base_dir=tmp_path,
    )

    target = tmp_path / ".cursor" / "skills" / "lfp-build-workspace" / "SKILL.md"
    assert target.is_file()
    assert target in report.installed
    assert not report.updated
    assert not report.skipped


def test_install_docs_creates_target_files(tmp_path: pathlib.Path) -> None:
    """A first-time docs install copies flat Markdown files under the docs dir."""
    report = bundle.install(
        kind="docs",
        host="claude",
        global_install=False,
        force=False,
        dry_run=False,
        base_dir=tmp_path,
    )

    target = tmp_path / ".claude" / "docs" / "lfp-build-conventions.md"
    assert target.is_file()
    assert target in report.installed
    assert not report.updated
    assert not report.skipped


def test_install_dry_run_does_not_touch_disk(tmp_path: pathlib.Path) -> None:
    """A dry-run install reports what would happen and writes nothing."""
    report = bundle.install(
        kind="skills",
        host="cursor",
        global_install=False,
        force=False,
        dry_run=True,
        base_dir=tmp_path,
    )

    target = tmp_path / ".cursor" / "skills" / "lfp-build-workspace" / "SKILL.md"
    assert not target.exists()
    assert target in report.installed
    assert report.dry_run is True


def test_install_skips_unchanged_files(tmp_path: pathlib.Path) -> None:
    """Re-running install against an unchanged tree reports every file as skipped."""
    bundle.install(kind="skills", host="cursor", base_dir=tmp_path)
    second = bundle.install(kind="skills", host="cursor", base_dir=tmp_path)

    assert not second.installed
    assert not second.updated
    assert second.skipped


def test_install_leaves_modified_targets_alone_without_force(tmp_path: pathlib.Path) -> None:
    """A drifted destination is preserved when ``force`` is False."""
    bundle.install(kind="skills", host="cursor", base_dir=tmp_path)
    target = tmp_path / ".cursor" / "skills" / "lfp-build-workspace" / "SKILL.md"
    target.write_text("hand-edited\n")

    report = bundle.install(kind="skills", host="cursor", base_dir=tmp_path)

    assert target.read_text() == "hand-edited\n"
    assert target in report.skipped
    assert not report.updated


def test_install_force_overwrites_drifted_targets(tmp_path: pathlib.Path) -> None:
    """``force=True`` rewrites destinations whose content diverges from the bundle."""
    bundle.install(kind="skills", host="cursor", base_dir=tmp_path)
    target = tmp_path / ".cursor" / "skills" / "lfp-build-workspace" / "SKILL.md"
    target.write_text("hand-edited\n")

    report = bundle.install(kind="skills", host="cursor", base_dir=tmp_path, force=True)

    assert target.read_text().startswith("---")
    assert target in report.updated


def test_install_unknown_name_raises(tmp_path: pathlib.Path) -> None:
    """Requesting a non-bundled name errors out with the available list."""
    with pytest.raises(ValueError, match="Unknown bundled skills"):
        bundle.install(
            kind="skills",
            host="cursor",
            base_dir=tmp_path,
            names=["does-not-exist"],
        )


def test_install_name_filters_to_selected_entries(tmp_path: pathlib.Path) -> None:
    """The ``names`` filter restricts the install to the requested entries only."""
    report = bundle.install(
        kind="skills",
        host="cursor",
        base_dir=tmp_path,
        names=["lfp-build-workspace"],
    )

    installed_dirs = {p.parent.name for p in report.installed}
    assert installed_dirs == {"lfp-build-workspace"}
