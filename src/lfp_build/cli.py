import os
import pathlib
from typing import Annotated

import cyclopts
from lfp_logging import logs

from lfp_build import readme, rename, workspace_create, workspace_dist, workspace_sync

"""
Main entry point for the lfp-build CLI.

This module aggregates all subcommands from other modules and provides
a unified interface for workspace management. The CLI provides commands for:
- Creating new projects
- Synchronizing project configurations
- Updating README documentation with command help output
"""

LOG = logs.logger(__name__)

app = cyclopts.App(default_parameter=cyclopts.Parameter(negative=""))


@app.meta.default
def launcher(
    *tokens: Annotated[str, cyclopts.Parameter(show=False, allow_leading_hyphen=True)],
    working_directory: pathlib.Path | None = None,
) -> int:
    """
    Main entry point for the lfp-build CLI.

    This function exists to support a global working directory option and then
    forward all remaining tokens to the Cyclopts app.

    Parameters
    ----------
    working_directory
        Set the current working directory.
    """
    if working_directory:
        working_directory = working_directory.resolve()
        LOG.debug("Changing working directory to: %s", working_directory)
        os.chdir(working_directory)

    return app(tokens)


app.command(workspace_create.app, name="create")
app.command(workspace_dist.app, name="dist")
app.command(workspace_sync.app, name="sync")
app.command(readme.app, name="readme")
app.command(rename.app, name="rename")


def main() -> None:
    app.meta()


if __name__ == "__main__":
    main()
