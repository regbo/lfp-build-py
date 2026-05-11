import os
import pathlib
from typing import Annotated

import cyclopts
from lfp_logging import logs

from lfp_build.commands import add, build, hooks, init, readme, rename, sync

"""
Top-level entry point for the ``lfp-build`` CLI.

The shape mirrors uv: flat top-level verbs for the common workflow, with a
small subcommand group only where one is justified (``readme``).

Commands:
- ``init NAME``: bootstrap a new uv workspace and seed ``packages/common``.
- ``add NAME``: add a new member project to the current workspace.
- ``sync``: align ``pyproject.toml`` files across the workspace.
- ``build``: build wheel artifacts for workspace projects.
- ``hooks``: install or refresh the lfp-build managed git pre-commit hook.
- ``rename``: bulk rename strings across files and directories.
- ``readme update``: refresh README command-help sentinel blocks.
"""

LOG = logs.logger(__name__)

app = cyclopts.App(default_parameter=cyclopts.Parameter(negative=""))


@app.meta.default
def launcher(
    *tokens: Annotated[str, cyclopts.Parameter(show=False, allow_leading_hyphen=True)],
    working_directory: pathlib.Path | None = None,
) -> int:
    """
    Top-level launcher with a global ``--working-directory`` option.

    Parameters
    ----------
    working_directory
        Set the current working directory before dispatching to a subcommand.
    """
    if working_directory:
        working_directory = working_directory.resolve()
        LOG.debug("Changing working directory to: %s", working_directory)
        os.chdir(working_directory)

    return app(tokens)


app.command(init.init, name="init")
app.command(add.add, name="add")
app.command(sync.sync, name="sync")
app.command(build.build, name="build")
app.command(hooks.hooks, name="hooks")
app.command(rename.app, name="rename")
app.command(readme.app, name="readme")


def main() -> None:
    app.meta()


if __name__ == "__main__":
    main()
