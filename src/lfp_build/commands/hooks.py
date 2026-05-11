import pathlib
import re
import stat
import subprocess

from lfp_logging import logs

from lfp_build import workspace

"""
Implements ``lfp-build hooks`` and the underlying pre-commit installer.

Installs or refreshes the lfp-build managed git pre-commit hook in the
current uv workspace. The hook runs ``lfp-build sync`` before each commit
so any pyproject.toml updates produced by the sync land in the same
commit. The lfp-build managed portion is delimited by the
``# >>> lfp-build managed pre-commit >>>`` /
``# <<< lfp-build managed pre-commit <<<`` markers, so re-running the
install logic is idempotent and does not clobber user-added hook content.

The ``install`` function is also imported by ``commands.init`` to set up
the hook during workspace bootstrap.
"""

LOG = logs.logger(__name__)

_GIT_HOOKS_DIR = pathlib.Path(".githooks")
_PRE_COMMIT_HOOK = _GIT_HOOKS_DIR / "pre-commit"

_MARKER_BEGIN = "# >>> lfp-build managed pre-commit >>>"
_MARKER_END = "# <<< lfp-build managed pre-commit <<<"

_MANAGED_BLOCK = f"""{_MARKER_BEGIN}
# Sync workspace pyproject.toml files; stage anything the sync changed so it
# lands in this commit. Edits inside this block are overwritten the next time
# `lfp-build hooks` runs - keep custom logic outside the markers.
uv run lfp-build sync || exit 1
git add -A
if ! git diff --quiet --cached; then
    echo "pre-commit: staged version updates."
fi
{_MARKER_END}
"""

_NEW_FILE_HEADER = "#!/bin/sh\n\n"

_BLOCK_RE = re.compile(
    rf"{re.escape(_MARKER_BEGIN)}.*?{re.escape(_MARKER_END)}\n?",
    re.DOTALL,
)


def hooks() -> None:
    """
    Install or refresh the lfp-build managed pre-commit hook.

    Discovers the workspace root via uv metadata, initializes a git
    repository there if one does not already exist, configures git to
    use ``.githooks`` as ``core.hooksPath``, and writes (or refreshes)
    the lfp-build managed block in ``.githooks/pre-commit``. Hook content
    outside the managed markers is left untouched.
    """
    root_dir = workspace.metadata().workspace_root
    pre_commit_path = install(root_dir)
    LOG.info("Installed pre-commit hook: %s", pre_commit_path)


def install(root_dir: pathlib.Path) -> pathlib.Path:
    """
    Install or update the lfp-build managed pre-commit hook in ``root_dir``.

    Initializes a git repository if one does not already exist, configures
    git to use ``.githooks`` as ``core.hooksPath``, and writes the lfp-build
    managed block into ``.githooks/pre-commit``. Existing hook content
    outside the managed markers is preserved.

    Returns the path to the pre-commit hook file.
    """
    _ensure_git_repo(root_dir)
    pre_commit_path = _ensure_pre_commit_hook(root_dir)
    _enable_git_hooks(root_dir)
    return pre_commit_path


def _ensure_git_repo(root_dir: pathlib.Path) -> None:
    """
    Initialize a git repository in ``root_dir`` when one does not exist.

    Uses ``--initial-branch=main`` so freshly created workspaces start on
    ``main`` regardless of the user's global ``init.defaultBranch`` setting,
    which also silences git's default-branch hint.
    """
    if not (root_dir / ".git").exists():
        subprocess.run(
            ["git", "init", "--initial-branch=main"],
            cwd=root_dir,
            check=True,
        )


def _ensure_pre_commit_hook(root_dir: pathlib.Path) -> pathlib.Path:
    """
    Create or refresh ``.githooks/pre-commit`` with the managed block.

    Behavior depends on what already exists at the hook path:

    - No file: write a fresh hook (shebang + managed block).
    - File with our markers: replace the marked region in place.
    - File without our markers: append the managed block after the existing
      content, preserving everything the user already had.
    """
    pre_commit_path = root_dir / _PRE_COMMIT_HOOK
    pre_commit_path.parent.mkdir(parents=True, exist_ok=True)

    if not pre_commit_path.exists():
        pre_commit_path.write_text(_NEW_FILE_HEADER + _MANAGED_BLOCK)
    else:
        existing = pre_commit_path.read_text()
        if _BLOCK_RE.search(existing):
            updated = _BLOCK_RE.sub(lambda _m: _MANAGED_BLOCK, existing, count=1)
        else:
            # Ensure a blank line separates pre-existing content from the
            # appended managed block.
            if existing.endswith("\n\n"):
                separator = ""
            elif existing.endswith("\n"):
                separator = "\n"
            else:
                separator = "\n\n"
            updated = existing + separator + _MANAGED_BLOCK
        if updated != existing:
            pre_commit_path.write_text(updated)

    pre_commit_path.chmod(
        pre_commit_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )
    return pre_commit_path


def _enable_git_hooks(root_dir: pathlib.Path) -> None:
    """
    Configure the repo to use ``.githooks`` as ``core.hooksPath``.
    """
    subprocess.run(
        ["git", "config", "core.hooksPath", _GIT_HOOKS_DIR.as_posix()],
        cwd=root_dir,
        check=True,
    )
