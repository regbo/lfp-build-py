#!/usr/bin/env python3
from __future__ import annotations

import re
import shlex
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
from pathlib import Path
from typing import Pattern

from cyclopts import App
from lfp_logging import logs

from lfp_build import util, workspace

"""
README documentation automation utilities.

This module provides commands to automatically update README files by executing
commands embedded in sentinel blocks and replacing the content with command output.
Supports parallel execution, smart help filtering, and selective updates.
"""

LOG = logs.logger(__name__)

app = App()

# Sentinel regex (generic)
_CMD_BLOCK_RE = re.compile(
    r"""
    \s*<!--\s*BEGIN:cmd\s+(?P<cmd>[^>]+?)\s*-->\s*
    (?P<body>.*?)
    \s*<!--\s*END:cmd\s*-->\s*
    """,
    re.DOTALL | re.VERBOSE,
)


_CODE_BLOCK_RE = re.compile(r"^([`~]{3,}).*?^\1", re.MULTILINE | re.DOTALL)


@app.command()
def update_cmd(
    *,
    readme: Path = Path("README.md"),
    write: bool = True,
    jobs: int | None = None,
    filter: str | None = None,
):
    """
    Update README command sentinel blocks.

    Only blocks whose command matches --filter are executed and updated.

    Parameters
    ----------
    readme
        Path to README file to update.
    write
        Write changes back to the README file.
    jobs
        Maximum number of parallel commands. Defaults to CPU count - 1.
    filter
        Regex to select which BEGIN:cmd blocks to update.
    """
    if jobs is None:
        jobs = max(1, cpu_count() - 1)

    if not readme.exists():
        readme = workspace.metadata().workspace_root / readme
        if not readme.exists():
            raise ValueError(f"README file not found at {readme}")

    content = readme.read_text()
    code_ranges = [m.span() for m in _CODE_BLOCK_RE.finditer(content)]

    def is_in_code_block(pos: int) -> bool:
        return any(start <= pos < end for start, end in code_ranges)

    block_matches = [
        m for m in _CMD_BLOCK_RE.finditer(content) if not is_in_code_block(m.start())
    ]
    if not block_matches:
        LOG.info("No cmd blocks found")
        return

    filter_re: Pattern[str] | None = re.compile(filter) if filter else None

    selected_cmds: list[str] = []
    for m in block_matches:
        cmd = m.group("cmd")
        if filter_re and not filter_re.search(cmd):
            continue
        selected_cmds.append(cmd)

    if not selected_cmds:
        LOG.info("No cmd blocks matched filter")
        return

    LOG.info(
        "Running cmd blocks - count:%s total:%s jobs:%s",
        len(selected_cmds),
        len(block_matches),
        jobs,
    )

    output_map: dict[str, str] = {}

    with ProcessPoolExecutor(max_workers=jobs) as executor:
        futures = {executor.submit(_run_cmd, cmd): cmd for cmd in selected_cmds}

        for future in as_completed(futures):
            cmd, output = future.result()
            output_map[cmd] = output

    def _replace(match: re.Match) -> str:
        """Replace sentinel block content with executed command output."""
        if is_in_code_block(match.start()):
            return match.group(0)

        cmd = match.group("cmd")
        if cmd not in output_map:
            return match.group(0)  # untouched
        return f"\n\n<!-- BEGIN:cmd {cmd} -->\n{output_map[cmd]}\n<!-- END:cmd -->\n\n"

    updated = _CMD_BLOCK_RE.sub(_replace, content)

    if updated == content:
        LOG.info("No changes detected")
        return

    LOG.info("README command blocks updated")

    if write:
        readme.write_text(updated)
    else:
        LOG.info("README update: %s", updated)


def _run_cmd(cmd: str) -> tuple[str, str]:
    """
    Execute command and capture output in markdown code block format.

    For commands with --help, filters out the --help option row from
    output and removes empty Options sections.

    Args:
        cmd: Shell command to execute

    Returns:
        Tuple of (command, formatted_output) where formatted_output
        is wrapped in markdown code block
    """
    args = shlex.split(cmd)
    LOG.debug("Running cmd block - args:%s", args)
    stdout = util.process_run(args[0], *args[1:])
    return cmd, f"```shell\n{stdout.strip()}\n```"


def main():
    app()


if __name__ == "__main__":
    main()
