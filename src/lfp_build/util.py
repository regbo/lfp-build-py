import functools
import logging
import os
import pathlib
import subprocess
import sys
import threading
from tkinter import N
from typing import Any, Callable, Iterator

"""
Common utilities for the lfp-build package.

Provides logging configuration and subprocess management tools used across
the workspace management CLI.
"""

LOG_LEVEL_ENV_NAME = "LOG_LEVEL"


def logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name, ensuring logging is configured.

    Args:
        name: The name of the logger (typically __name__)

    Returns:
        A configured logging.Logger instance
    """
    _logging_config()
    return logging.getLogger(name)


@functools.cache
def _logging_config():
    """
    Initialize the logging configuration for the application.

    This function sets up handlers for both stdout (INFO only) and stderr
    (all other levels) with specific formatting and date formats. It uses
    the LOG_LEVEL environment variable to determine the global logging level,
    defaulting to INFO.
    """
    date_format = "%Y-%m-%d %H:%M:%S"
    format_stdout = "%(message)s"
    format_stderr = (
        "%(asctime)s.%(msecs)03d | %(levelname)s | %(name)s:%(lineno)d - %(message)s"
    )
    log_level_env = os.getenv(LOG_LEVEL_ENV_NAME, "").upper()
    log_level = logging.getLevelNamesMapping().get(log_level_env, logging.INFO)

    def _create_handler(
        stream,
        level: int,
        format: str,
        filter_fn: Callable[[logging.LogRecord], bool] | None = None,
    ) -> logging.Handler:
        handler = logging.StreamHandler(stream)  # type: ignore[arg-type]
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(format))
        if filter_fn is not None:
            handler.addFilter(filter_fn)
        return handler

    handlers = [
        _create_handler(
            sys.stdout,
            logging.INFO,
            format_stdout,
            lambda record: record.levelno == logging.INFO,
        ),
        _create_handler(
            sys.stderr,
            logging.DEBUG,
            format_stderr,
            lambda record: record.levelno != logging.INFO,
        ),
    ]

    logging.basicConfig(
        level=log_level,
        datefmt=date_format,
        handlers=handlers,
    )


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
    Stderr is logged but not yielded unless specified otherwise.

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
        logger(__name__).log(
            log_level,
            f"[{program_name if program_name else commands[0]}] | {line}",
        )

    thread: threading.Thread | N = None
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
                proc.kill()
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.terminate()
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
