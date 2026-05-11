from lfp_build import cli


def _run_cli(tokens: list[str]) -> int:
    """
    Run the Cyclopts app and return its exit code.

    Cyclopts apps exit via SystemExit after handling a command.
    """
    try:
        cli.app(tokens)
        return 0
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 0


def test_cli_help() -> None:
    """Test CLI help output exposes the new top-level commands."""
    import io
    from contextlib import redirect_stdout

    f = io.StringIO()
    with redirect_stdout(f):
        _run_cli(["--help"])
    output = f.getvalue()
    assert "init" in output
    assert "add" in output
    assert "sync" in output
    assert "build" in output
    assert "hooks" in output
    assert "readme" in output
    assert "rename" in output


def test_readme_update(temp_workspace) -> None:
    """Test updating command blocks in README via `readme update`."""
    readme_path = temp_workspace / "README.md"
    message = "hello-from-test"
    sentinel_begin = f"<!-- BEGIN:cmd echo '{message}' -->"
    readme_path.write_text(f"""
# Test
{sentinel_begin}
<!-- END:cmd -->
""")
    content = readme_path.read_text()
    assert content.count(sentinel_begin) == 1
    assert content.count(message) == 1

    assert _run_cli(["readme", "update", "--readme", str(readme_path)]) == 0

    updated_content = readme_path.read_text()
    assert updated_content.count(sentinel_begin) == 1
    assert updated_content.count(message) == 2


def test_cli_add_and_sync(temp_workspace) -> None:
    """Test add and sync via CLI."""
    assert _run_cli(["add", "cli-pkg"]) == 0
    assert (temp_workspace / "packages" / "cli-pkg").exists()

    assert _run_cli(["sync"]) == 0


def test_cli_add_project_dependency_short_flag(temp_workspace) -> None:
    """Ensure --project-dependency works and is not confused with --path."""
    assert _run_cli(["add", "core"]) == 0
    assert _run_cli(["add", "api", "--project-dependency", "core"]) == 0
