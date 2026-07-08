import shlex
import subprocess

from lfp_logging import logs

"""
Release workflow for ``lfp-build-publish``.

Drives the tail end of the local-release pipeline: format the tree,
commit any pending changes as a pre-release commit, bump the version
via ``bump-my-version``, and push the resulting commit + tag to the
remote. Staging the docs bundle from ``ai/`` is intentionally a
**separate** step owned by :mod:`lfp_build.publish.bundle_docs` (and
its ``stage-docs`` CLI verb) so the release workflow stays focused on
the git side of the pipeline and either half can be rerun in isolation.
The CLI's default action composes both by calling stage-docs first and
then this workflow.

Every shell invocation is logged before execution so the transcript
makes clear which external tool advanced the state of the git repo.
"""

LOG = logs.logger(__name__)

# Message committed automatically before ``bump-my-version`` runs, so
# any tree edits from the format step (or an earlier stage-docs pass)
# are captured as a distinct commit rather than folded into the
# version-bump commit.
_PRE_RELEASE_COMMIT_MESSAGE = "pre-release: staging changes"

# Default template forwarded to ``bump-my-version`` for the version-bump
# commit and tag message. ``{new_version}`` is a bump-my-version
# placeholder replaced with the resolved next version at bump time.
DEFAULT_MESSAGE_TEMPLATE = "incrementing version to {new_version}"

# Remote and ref pushed at the end of a successful release run.
_PUSH_REMOTE = "origin"
_PUSH_REF = "HEAD"


def run(
    *,
    version_part: str,
    message: str,
    format_code: bool,
    push: bool,
) -> None:
    """
    Execute the release workflow end-to-end.

    Parameters
    ----------
    version_part
        Which SemVer segment to bump. Forwarded verbatim to
        ``bump-my-version bump``; typical values are ``"patch"``,
        ``"minor"``, and ``"major"``.
    message
        Commit / tag message template. Passed to
        ``bump-my-version --message``, which expands ``{new_version}``.
    format_code
        When True, run ``ruff check --fix --unsafe-fixes`` followed by
        ``ruff format`` before the pre-release commit so any auto-fix
        churn lands in the commit rather than surfacing after tagging.
    push
        When True, ``git push origin HEAD --tags`` after bumping. Set
        to False when validating the workflow locally.
    """
    if format_code:
        _format_code()
    _stage_and_commit_pending_changes()
    _bump_version(version_part=version_part, message=message)
    if push:
        _push()


def _format_code() -> None:
    """
    Run ruff check + ruff format on the whole tree.
    """
    _run(["uv", "run", "ruff", "check", ".", "--fix", "--unsafe-fixes"])
    _run(["uv", "run", "ruff", "format", "."])


def _stage_and_commit_pending_changes() -> None:
    """
    ``git add .`` and, if anything is staged, commit it as a pre-release commit.

    Keeps the version-bump commit clean of unrelated churn from the
    format step (or an earlier stage-docs pass) by absorbing that
    churn into a separate commit first.
    """
    _run(["git", "add", "."])
    diff_result = subprocess.run(
        ["git", "diff", "--staged", "--quiet"],
        check=False,
    )
    if diff_result.returncode == 0:
        LOG.info("No staged changes to commit - skipping pre-release commit")
        return
    _run(["git", "commit", "-m", _PRE_RELEASE_COMMIT_MESSAGE])


def _bump_version(*, version_part: str, message: str) -> None:
    """
    Delegate to ``bump-my-version bump`` with the requested part and message.
    """
    _run(
        [
            "uv",
            "run",
            "bump-my-version",
            "bump",
            version_part,
            "--message",
            message,
        ]
    )


def _push() -> None:
    """
    Push the release commit and its tag to the default remote.
    """
    _run(["git", "push", _PUSH_REMOTE, _PUSH_REF, "--tags"])


def _run(args: list[str]) -> None:
    """
    Run a subprocess with logging and ``check=True``.

    Failures bubble up as :class:`subprocess.CalledProcessError` so the
    workflow aborts on the first broken step rather than silently
    marching forward with an inconsistent tree.
    """
    LOG.info("Running: %s", shlex.join(args))
    subprocess.run(args, check=True)
