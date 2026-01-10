import logging
import queue
import subprocess
import threading

import pytest

from lfp_build import util


def test_logger():
    """Test logger initialization and naming."""
    log = util.logger("test_logger")
    assert isinstance(log, logging.Logger)
    assert log.name == "test_logger"


def test_process_run_success():
    """Test process_run with a simple successful command."""
    output = util.process_run("echo", "hello world")
    assert output == "hello world"


def test_process_run_error():
    """Test process_run with a failing command."""
    with pytest.raises(subprocess.CalledProcessError):
        util.process_run("ls", "/non-existent-directory-12345", check=True)


def test_process_start_iteration():
    """Test process_start yielding lines."""
    lines = list(util.process_start("echo", "line1\nline2"))
    assert "line1" in lines
    assert "line2" in lines


def test_process_start_clean_shutdown():
    """Test that stopping iteration cleans up a long-running process without errors."""

    def _run(q: queue.Queue[str]):
        # A command that would run indefinitely printing "hello world"
        cmd = ["sh", "-c", "while true; do echo 'hello world'; sleep 0.1; done"]

        # Use a small timeout to ensure it doesn't run forever if something goes wrong
        gen = util.process_start(
            cmd[0], *cmd[1:], check=False, stderr_log_background=True
        )
        count = 0
        for line in gen:
            lines.put(line)
            count += 1
            if count == 2:
                break

    lines = queue.Queue[str]()
    thread = threading.Thread(target=_run, args=(lines,))
    thread.start()
    thread.join(timeout=5.0)
    assert lines.qsize() == 2
    while not lines.empty():
        line = lines.get()
        assert line == "hello world"
