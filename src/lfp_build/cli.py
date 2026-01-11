import logging
import os
import pathlib
from typing import Annotated

import typer
from lfp_logging import logs

from lfp_build import readme, workspace_create, workspace_sync

"""
Main entry point for the lfp-build CLI.

This module aggregates all subcommands from other modules and provides
a unified interface for workspace management. The CLI provides commands for:
- Creating new projects
- Synchronizing project configurations
- Updating README documentation with command help output
"""

app = typer.Typer()
app.add_typer(workspace_create.app, name="create")
app.add_typer(workspace_sync.app, name="sync")
app.add_typer(readme.app, name="readme")


@app.callback()
def _callback(
    working_directory: Annotated[
        pathlib.Path | None,
        typer.Option(
            "--working_directory",
            "-w",
            help="Set the current working directory",
        ),
    ] = None,
    log_level: Annotated[
        str | None,
        typer.Option(
            help="Set the log level explicitly (e.g. DEBUG, INFO, WARNING, ERROR).",
            envvar=logs.LOG_LEVEL_ENV_NAME,
        ),
    ] = None,
):
    if working_directory:
        os.chdir(working_directory)
    log_level_no = (
        logging.getLevelNamesMapping().get(log_level.upper(), None)
        if log_level
        else None
    )
    if log_level_no:
        logging.root.setLevel(log_level_no)


def main():
    app()


if __name__ == "__main__":
    import typer.testing

    runner = typer.testing.CliRunner()

    result = runner.invoke(
        app,
        [
            "--log-level",
            "DEBU",
            "-w",
            "/Users/reggie.pierce/Projects/reggie-bricks-py",
            "sync",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
