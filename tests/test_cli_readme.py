from lfp_build import cli


def _run_cli(tokens: list[str]) -> int:
    """
    Run the Cyclopts app and return its exit code.

    Cyclopts exits via SystemExit after handling a command.
    """
    try:
        cli.app(tokens)
        return 0
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 0


def test_cli_help():
    """Test CLI help output."""
    # Cyclopts apps are just callables. We can capture stdout.
    import io
    from contextlib import redirect_stdout
    
    f = io.StringIO()
    with redirect_stdout(f):
        _run_cli(["--help"])
    output = f.getvalue()
    assert "sync" in output
    assert "create" in output
    assert "readme" in output


def test_readme_update_cmd(temp_workspace):
    """Test updating command blocks in README."""
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

    # The readme logic is in a subcommand
    assert _run_cli(["readme", "update-cmd", "--readme", str(readme_path)]) == 0

    updated_content = readme_path.read_text()
    assert updated_content.count(sentinel_begin) == 1
    assert updated_content.count(message) == 2


def test_cli_create_and_sync(temp_workspace):
    """Test create and sync via CLI."""
    # Create a project
    assert _run_cli(["create", "cli-pkg"]) == 0
    assert (temp_workspace / "packages" / "cli-pkg").exists()

    # Sync
    assert _run_cli(["sync"]) == 0
