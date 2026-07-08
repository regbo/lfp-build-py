import pathlib

from lfp_build.commands import docs as docs_cmd
from lfp_build.commands import skills as skills_cmd


def test_skills_install_default_targets_both_hosts(tmp_path: pathlib.Path) -> None:
    """``lfp-build skills install`` without ``--target`` writes to Cursor and Claude."""
    skills_cmd.install(base_dir=tmp_path)

    cursor_target = tmp_path / ".cursor" / "skills" / "lfp-build-workspace" / "SKILL.md"
    claude_target = tmp_path / ".claude" / "skills" / "lfp-build-workspace" / "SKILL.md"

    assert cursor_target.is_file()
    assert claude_target.is_file()


def test_skills_install_target_selects_single_host(tmp_path: pathlib.Path) -> None:
    """Passing ``target='cursor'`` skips the Claude directory entirely."""
    skills_cmd.install(target="cursor", base_dir=tmp_path)

    assert (tmp_path / ".cursor" / "skills").is_dir()
    assert not (tmp_path / ".claude").exists()


def test_skills_install_dry_run_writes_nothing(tmp_path: pathlib.Path) -> None:
    """Dry-run keeps the filesystem clean but still exits successfully."""
    skills_cmd.install(dry_run=True, base_dir=tmp_path)

    assert not (tmp_path / ".cursor").exists()
    assert not (tmp_path / ".claude").exists()


def test_docs_install_default_targets_both_hosts(tmp_path: pathlib.Path) -> None:
    """``lfp-build docs install`` writes flat Markdown files under each host's docs dir."""
    docs_cmd.install(base_dir=tmp_path)

    cursor_target = tmp_path / ".cursor" / "docs" / "lfp-build-conventions.md"
    claude_target = tmp_path / ".claude" / "docs" / "lfp-build-conventions.md"

    assert cursor_target.is_file()
    assert claude_target.is_file()


def test_docs_install_name_filter_installs_subset(tmp_path: pathlib.Path) -> None:
    """A ``--name`` restriction narrows the install to the named docs only."""
    docs_cmd.install(base_dir=tmp_path, name=["lfp-build-conventions"], target="cursor")

    assert (tmp_path / ".cursor" / "docs" / "lfp-build-conventions.md").is_file()
