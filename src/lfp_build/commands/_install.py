import pathlib
from typing import Literal

from lfp_logging import logs

from lfp_build import bundle

"""
Shared install workflow for the ``lfp-build skills`` and
``lfp-build docs`` verbs.

Both verbs resolve one or more agent hosts, delegate the actual copying
to :mod:`lfp_build.bundle`, and log a consistent per-host summary.
Keeping the workflow here avoids duplicating the same argument-to-call
plumbing (and the same summary logging) in each command module.
"""

LOG = logs.logger(__name__)


def run_install(
    *,
    kind: bundle.Kind,
    target: Literal["cursor", "claude", "all"],
    install_global: bool,
    force: bool,
    dry_run: bool,
    names: list[str] | None,
    base_dir: pathlib.Path | None,
) -> None:
    """
    Execute an install pass across the selected host(s).

    Parameters
    ----------
    kind
        ``"skills"`` or ``"docs"``.
    target
        Which host(s) to install for. ``"all"`` expands to every host
        exposed by :func:`bundle.hosts` in that fixed order, so callers
        automatically pick up any hosts added to the catalog later.
    install_global
        When True, install into the user's home directory.
    force
        Overwrite existing files whose content differs from the bundled
        source.
    dry_run
        Log the plan without touching the filesystem.
    names
        Restrict the install to specific bundled entries by name.
    base_dir
        Base directory for non-global installs (defaults to CWD when
        None).
    """
    for host in _resolve_hosts(target):
        report = bundle.install(
            kind=kind,
            host=host,
            global_install=install_global,
            names=names,
            force=force,
            dry_run=dry_run,
            base_dir=base_dir,
        )
        _log_report(kind=kind, host=host, report=report)


def _resolve_hosts(target: Literal["cursor", "claude", "all"]) -> tuple[bundle.Host, ...]:
    """
    Expand a ``target`` value into an ordered tuple of concrete hosts.
    """
    if target == "all":
        return bundle.hosts()
    return (target,)


def _log_report(
    *,
    kind: bundle.Kind,
    host: bundle.Host,
    report: bundle.InstallReport,
) -> None:
    """
    Emit a single-line summary of an install pass for a host.
    """
    tag = " [dry-run]" if report.dry_run else ""
    LOG.info(
        "%s.%s%s: installed=%d updated=%d skipped=%d",
        host,
        kind,
        tag,
        len(report.installed),
        len(report.updated),
        len(report.skipped),
    )
