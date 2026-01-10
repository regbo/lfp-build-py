from typer.testing import CliRunner

from lfp_build import cli

runner = CliRunner()


def test_cli_help():
    """Test CLI help output."""
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "sync" in result.stdout
    assert "create" in result.stdout
    assert "readme" in result.stdout


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

    # The readme logic is in a callback, so we just call 'readme'
    result = runner.invoke(cli.app, ["readme", "--readme", str(readme_path)])
    assert result.exit_code == 0

    updated_content = readme_path.read_text()
    assert updated_content.count(sentinel_begin) == 1
    assert updated_content.count(message) == 2


def test_cli_create_and_sync(temp_workspace):
    """Test create and sync via CLI."""
    # Create a project
    result = runner.invoke(cli.app, ["create", "cli-pkg"])
    assert result.exit_code == 0
    assert (temp_workspace / "packages" / "cli-pkg").exists()

    # Sync
    result = runner.invoke(cli.app, ["sync"])
    assert result.exit_code == 0
