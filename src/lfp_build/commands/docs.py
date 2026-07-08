import pathlib
from typing import Annotated, Literal

import cyclopts
from lfp_logging import logs

from lfp_build import bundle
from lfp_build.commands import _install

"""
Implements ``lfp-build docs`` (currently with a single ``install`` verb).

Installs the Markdown reference docs bundled with lfp-build into a
consumer's Cursor / Claude host directories so agents in downstream
projects can pull in the "why" behind lfp-build's conventions.
"""

LOG = logs.logger(__name__)

app = cyclopts.App(
    help="Install lfp-build agent docs into Cursor / Claude host directories.",
    default_parameter=cyclopts.Parameter(negative=""),
)


@app.command()
def install(
    *,
    target: Literal["cursor", "claude", "all"] = "all",
    install_global: Annotated[
        bool,
        cyclopts.Parameter(name="--global", negative=""),
    ] = False,
    force: Annotated[
        bool,
        cyclopts.Parameter(alias="-f", negative=""),
    ] = False,
    dry_run: bool = False,
    name: list[str] | None = None,
    base_dir: pathlib.Path | None = None,
) -> None:
    """
    Install bundled lfp-build agent docs.

    Copies every bundled Markdown doc (or the subset selected with
    ``--name``) into the target host directory for each selected
    ``--target``:

    - Cursor: ``<base_dir>/.cursor/docs/`` (or ``~/.cursor/docs/``
      with ``--global``).
    - Claude: ``<base_dir>/.claude/docs/`` (or ``~/.claude/docs/``
      with ``--global``).

    Parameters
    ----------
    target
        Which host(s) to install for: a specific host name or ``all``
        (default) to install for every supported host.
    install_global
        When set, install into the user's home directory instead of
        ``base_dir``. Exposed on the CLI as ``--global``.
    force
        Overwrite existing doc files whose content differs from the
        bundled source. Without ``--force``, divergent existing files
        are left alone and reported as skipped.
    dry_run
        Preview what would be installed without touching the filesystem.
    name
        Restrict the install to specific doc names (repeatable, without
        the ``.md`` suffix). Unknown names raise an error listing what
        is available.
    base_dir
        Base directory for non-global installs. Defaults to the current
        working directory.
    """
    _install.run_install(
        kind="docs",
        target=target,
        install_global=install_global,
        force=force,
        dry_run=dry_run,
        names=name,
        base_dir=base_dir,
    )


@app.command(name="list")
def list_docs() -> None:
    """
    List the names of bundled lfp-build agent docs.
    """
    for doc_name in bundle.list_bundled_names("docs"):
        LOG.info("%s", doc_name)
