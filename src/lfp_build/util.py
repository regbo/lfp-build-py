import logging
import pathlib
import subprocess
import threading
from collections.abc import Collection, Iterator
from typing import IO, Any, AnyStr

from lfp_logging import logs

"""
Common utilities for the lfp-build package.

Provides subprocess management tools and small predicate helpers used across
the workspace management CLI.
"""

LOG = logs.logger(__name__)





def process_start(
    program: Any,
    *args: Any,
    program_name: str | None = None,
    stdout_log_level: int | None = None,
    stderr_log_level: int | None = logging.DEBUG,
    check: bool = True,
    cwd: pathlib.Path | None = None,
    env: dict[str, str] | None = None,
) -> Iterator[str]:
    """
    Start a subprocess and yield its stdout line by line.

    Logs stdout and stderr to the configured logger at the specified levels.
    Stderr is logged but not yielded. When stderr logging is enabled, stderr is
    always drained concurrently so large stdout output cannot deadlock the
    child process.

    Args:
        program: The executable to run
        *args: Command line arguments
        program_name: Name used in log prefix (defaults to executable path)
        stdout_log_level: Level to log stdout (None to disable)
        stderr_log_level: Level to log stderr (defaults to DEBUG)
        check: If True, raises CalledProcessError on non-zero exit code
        cwd: Working directory for the process
        env: Environment variables for the process

    Yields:
        Lines from stdout as they are produced
    """
    commands = [str(c) for c in [program, *args]]
    stderr_logging_enabled = stderr_log_level is not None and LOG.isEnabledFor(stderr_log_level)
    proc = subprocess.Popen(
        commands,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if stderr_logging_enabled else subprocess.DEVNULL,
        text=True,
        cwd=cwd,
        env=env,
        bufsize=1,
    )

    def _read_stream(stream: IO[AnyStr] | None) -> Iterator[str]:
        if stream is not None:
            for line in stream:
                if line:
                    yield line[:-1]

    def _log_line(line: str, log_level: int) -> None:
        LOG.log(
            log_level,
            f"[{program_name if program_name else commands[0]}] | {line}",
        )

    thread: threading.Thread | None = None
    try:
        if stderr_logging_enabled:

            def _log_stderr() -> None:
                for line in _read_stream(proc.stderr):
                    _log_line(line, stderr_log_level)

            thread = threading.Thread(
                target=_log_stderr,
                name=f"{program_name if program_name else commands[0]}-stderr",
            )
            thread.start()

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
            raise subprocess.CalledProcessError(returncode=proc.returncode, cmd=proc.args)


def process_run(*args: Any, strip: bool = True, **kwargs: Any) -> str:
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
