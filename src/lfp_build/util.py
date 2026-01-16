import logging
import pathlib
import subprocess
import threading
from typing import Any, Iterator

from lfp_logging import logs

"""
Common utilities for the lfp-build package.

Provides subprocess management tools used across the workspace management CLI.
"""

LOG = logs.logger(__name__)


def process_start(
    program: Any,
    *args: Any,
    program_name: str | None = None,
    stdout_log_level: int | None = None,
    stderr_log_level: int | None = logging.DEBUG,
    stderr_log_background: bool = False,
    check=True,
    cwd: pathlib.Path = None,
    env: dict | None = None,
) -> Iterator[str]:
    """
    Start a subprocess and yield its stdout line by line.

    Logs stdout and stderr to the configured logger at the specified levels.
    Stderr is logged but not yielded.

    Args:
        program: The executable to run
        *args: Command line arguments
        program_name: Name used in log prefix (defaults to executable path)
        stdout_log_level: Level to log stdout (None to disable)
        stderr_log_level: Level to log stderr (defaults to DEBUG)
        stderr_log_background: If True, drain and log stderr in a background thread
        check: If True, raises CalledProcessError on non-zero exit code
        cwd: Working directory for the process
        env: Environment variables for the process

    Yields:
        Lines from stdout as they are produced
    """
    commands = [str(c) for c in [program, *args]]
    proc = subprocess.Popen(
        commands,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL if stderr_log_level is None else subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
        bufsize=1,
    )

    def _read_stream(stream) -> Iterator[str]:
        for line in stream:
            if line:
                yield line[:-1]

    def _log_line(line: str, log_level: int):
        LOG.log(
            log_level,
            f"[{program_name if program_name else commands[0]}] | {line}",
        )

    thread: threading.Thread | None = None
    try:
        if stderr_log_level is not None:

            def _log_stderr():
                for line in _read_stream(proc.stderr):
                    _log_line(line, stderr_log_level)

            if stderr_log_background:
                thread = threading.Thread(target=_log_stderr)
                thread.start()
            else:
                _log_stderr()

        for line in _read_stream(proc.stdout):
            if stdout_log_level is not None:
                _log_line(line, stdout_log_level)
            yield line
    finally:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
        proc.wait()
        if thread is not None:
            thread.join()
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(
                returncode=proc.returncode, cmd=proc.args
            )


def process_run(*args, strip: bool = True, **kwargs) -> str:
    """
    Run a process and return its full stdout as a string.

    Args:
        *args: Passed to process_start
        strip: Whether to strip whitespace from the output
        **kwargs: Passed to process_start

    Returns:
        The complete stdout of the process
    """
    std_out = "\n".join(process_start(*args, **kwargs))
    return std_out.strip() if strip else std_out


if __name__ == "__main__":
    pass
