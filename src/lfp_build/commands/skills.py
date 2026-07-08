import pathlib
from typing import Annotated, Literal

import cyclopts
from lfp_logging import logs

from lfp_build import bundle
from lfp_build.commands import _install

"""
Implements ``lfp-build skills`` (currently with a single ``install`` verb).

Installs the SKILL.md skills bundled with lfp-build into a consumer's
Cursor / Claude host directories so agents in downstream projects know
how to work inside an lfp-build workspace.
"""

LOG = logs.logger(__name__)

app = cyclopts.App(
    help="Install lfp-build agent skills into Cursor / Claude host directories.",
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
    Install bundled lfp-build agent skills.

    Copies every bundled skill (or the subset selected with ``--name``)
    into the target host directory for each selected ``--target``:

    - Cursor: ``<base_dir>/.cursor/skills/`` (or ``~/.cursor/skills/``
      with ``--global``).
    - Claude: ``<base_dir>/.claude/skills/`` (or ``~/.claude/skills/``
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
        Overwrite existing skill files whose content differs from the
        bundled source. Without ``--force``, divergent existing files
        are left alone and reported as skipped.
    dry_run
        Preview what would be installed without touching the filesystem.
    name
        Restrict the install to specific skill names (repeatable).
        Unknown names raise an error listing what is available.
    base_dir
        Base directory for non-global installs. Defaults to the current
        working directory.
    """
    _install.run_install(
        kind="skills",
        target=target,
        install_global=install_global,
        force=force,
        dry_run=dry_run,
        names=name,
        base_dir=base_dir,
    )


@app.command(name="list")
def list_skills() -> None:
    """
    List the names of bundled lfp-build agent skills.
    """
    for skill_name in bundle.list_bundled_names("skills"):
        LOG.info("%s", skill_name)
