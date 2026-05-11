import subprocess

from lfp_build import _config
from lfp_build.commands import add as add_cmd
from lfp_build.commands import hooks as hooks_cmd
from lfp_build.commands import init as init_cmd


def test_init_command(tmp_path) -> None:
    init_cmd.init("agent-demo", path=tmp_path)

    root = tmp_path / "agent-demo"
    assert (root / _config.PYPROJECT_FILE_NAME).is_file()
    assert (root / ".gitignore").is_file()
    assert (root / ".git").is_dir()
    assert (root / ".githooks" / "pre-commit").is_file()

    common = root / "packages" / "common"
    assert common.is_dir()
    assert (common / _config.PYPROJECT_FILE_NAME).is_file()

    pyproject_text = (root / _config.PYPROJECT_FILE_NAME).read_text()
    assert "[tool.uv.workspace]" in pyproject_text
    assert "[build-system]" in pyproject_text
    assert "[tool.lfp-build.member-project]" in pyproject_text
    hook_text = (root / ".githooks" / "pre-commit").read_text()
    assert "uv run lfp-build sync" in hook_text
    assert "git add -A" in hook_text
    assert "# >>> lfp-build managed pre-commit >>>" in hook_text
    assert "# <<< lfp-build managed pre-commit <<<" in hook_text

    hooks_path = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert hooks_path == ".githooks"


def test_init_copies_local_parent_gitignore(tmp_path, monkeypatch) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / ".gitignore").write_text("dist/\n.cache/\n")

    monkeypatch.chdir(parent)
    init_cmd.init("agent-local-gitignore", path=parent)

    project_root = parent / "agent-local-gitignore"
    assert (project_root / ".gitignore").is_file()
    assert (project_root / ".gitignore").read_text() == "dist/\n.cache/\n"


def test_add_does_not_create_hook(temp_workspace, monkeypatch) -> None:
    """``add`` no longer manages git hooks - that is owned by ``hooks``."""
    monkeypatch.chdir(temp_workspace)
    hook_path = temp_workspace / ".githooks" / "pre-commit"
    assert not hook_path.exists()

    add_cmd.add("new-member")

    assert not hook_path.exists()


def test_hooks_install_creates_managed_block(temp_workspace) -> None:
    """A fresh install writes a hook with the managed block markers."""
    hooks_cmd.install(temp_workspace)
    hook_path = temp_workspace / ".githooks" / "pre-commit"
    text = hook_path.read_text()
    assert text.startswith("#!/bin/sh")
    assert "# >>> lfp-build managed pre-commit >>>" in text
    assert "# <<< lfp-build managed pre-commit <<<" in text
    assert "uv run lfp-build sync" in text


def test_hooks_install_preserves_user_content(temp_workspace) -> None:
    """Custom hook content outside the managed markers is preserved."""
    custom = "#!/bin/sh\necho custom\n"
    hook_path = temp_workspace / ".githooks" / "pre-commit"
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(custom)

    hooks_cmd.install(temp_workspace)

    text = hook_path.read_text()
    assert "echo custom" in text
    assert "# >>> lfp-build managed pre-commit >>>" in text
    assert "uv run lfp-build sync" in text


def test_hooks_install_is_idempotent(temp_workspace) -> None:
    """Re-running install replaces the managed block instead of duplicating it."""
    hooks_cmd.install(temp_workspace)
    first = (temp_workspace / ".githooks" / "pre-commit").read_text()

    hooks_cmd.install(temp_workspace)
    second = (temp_workspace / ".githooks" / "pre-commit").read_text()

    assert first == second
    assert second.count("# >>> lfp-build managed pre-commit >>>") == 1
    assert second.count("# <<< lfp-build managed pre-commit <<<") == 1


def test_hooks_install_updates_stale_managed_block(temp_workspace) -> None:
    """An existing managed block with stale contents is replaced in place."""
    hook_path = temp_workspace / ".githooks" / "pre-commit"
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(
        "#!/bin/sh\n"
        "echo before\n"
        "\n"
        "# >>> lfp-build managed pre-commit >>>\n"
        "echo old-managed-content\n"
        "# <<< lfp-build managed pre-commit <<<\n"
        "echo after\n"
    )

    hooks_cmd.install(temp_workspace)

    text = hook_path.read_text()
    assert "echo before" in text
    assert "echo after" in text
    assert "echo old-managed-content" not in text
    assert "uv run lfp-build sync" in text
    assert text.count("# >>> lfp-build managed pre-commit >>>") == 1
