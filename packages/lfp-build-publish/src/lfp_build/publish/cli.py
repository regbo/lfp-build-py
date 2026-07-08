import pathlib
from typing import Annotated, Literal

import cyclopts
from lfp_build.publish import bundle_docs, release
from lfp_logging import logs

"""
Top-level entry point for the ``lfp-build-publish`` CLI.

``lfp-build-publish`` bundles the workspace-level publishing pipeline
as two independent verbs plus a default action that composes them:

- ``stage-docs`` mirrors the agent-facing content from ``ai/`` at the
  workspace root into the lfp-build package's ``docs/`` subpackage so
  ``uv_build`` can ship it in the wheel.
- ``release`` drives the git side of the pipeline: ``ruff check --fix``
  + ``ruff format``, then ``git add . && git commit`` (if any changes
  are staged), then ``bump-my-version bump <part>``, then
  ``git push origin HEAD --tags``.
- Default action (``uv run lfp-build-publish`` with no subcommand)
  runs ``stage-docs`` followed by ``release`` so a plain invocation
  covers the full pipeline end-to-end.

The ``clean-docs`` subcommand empties the staged tree while preserving
the tracked ``__init__.py`` so ``importlib.resources`` can still
resolve the subpackage on a clean tree. CI invokes the CLI before
``uv build --wheel``; the runtime ``lfp-build skills install`` /
``lfp-build docs install`` verbs then read the staged content via
``importlib.resources``.
"""

LOG = logs.logger(__name__)

app = cyclopts.App(
    help="Build-time staging helper for the lfp-build agent-content bundle.",
)


@app.command(name="stage-docs")
def stage_docs(
    *,
    source: pathlib.Path = pathlib.Path("ai"),
    target: pathlib.Path = pathlib.Path("src/lfp_build/docs"),
    clean: bool = True,
) -> None:
    """
    Stage authored ``ai/`` content into ``src/lfp_build/docs/``.

    Reads skills from ``<source>/skills/*/SKILL.md`` and reference docs
    from ``<source>/docs/*.md`` and writes them into the flat bundle
    layout under ``<target>/``:

    - Skills become ``<target>/<name>/SKILL.md`` (plus any supporting
      files that live alongside the manifest).
    - Reference docs become ``<target>/<name>.md``.

    Parameters
    ----------
    source
        Path to the authored ``ai/`` directory. Defaults to ``ai`` in
        the current working directory (typically the workspace root).
    target
        Path to the packaged bundle directory. Defaults to
        ``src/lfp_build/docs`` in the current working directory.
    clean
        Remove any existing staged content (everything under
        ``<target>/`` except a tracked ``__init__.py``) before copying
        so stale entries never leak into the wheel.
    """
    bundle_docs.stage(source=source, target=target, clean=clean)


@app.command(name="clean-docs")
def clean_docs(
    *,
    target: pathlib.Path = pathlib.Path("src/lfp_build/docs"),
) -> None:
    """
    Remove staged content from ``<target>/`` while keeping ``__init__.py``.

    Parameters
    ----------
    target
        Path to the packaged bundle directory. Defaults to
        ``src/lfp_build/docs`` in the current working directory.
    """
    bundle_docs.clean(target=target)


@app.command(name="release")
def release_cmd(
    version_part: Literal["patch", "minor", "major"] = "patch",
    *,
    message: Annotated[
        str,
        cyclopts.Parameter(name=["--message", "-m"]),
    ] = release.DEFAULT_MESSAGE_TEMPLATE,
    format_code: bool = True,
    push: bool = True,
) -> None:
    """
    Run the git-side release workflow: format, commit, bump, push.

    Assumes ``stage-docs`` has already run (or is not needed for this
    invocation). The default CLI action composes both steps; call
    ``release`` directly to bump a release without touching the docs
    bundle.

    Parameters
    ----------
    version_part
        SemVer segment to bump. Forwarded to ``bump-my-version bump``.
    message
        Commit / tag message template forwarded to ``bump-my-version``.
        The ``{new_version}`` placeholder is resolved at bump time.
    format_code
        Run ``ruff check --fix --unsafe-fixes`` followed by ``ruff
        format`` before the pre-release commit. Pass
        ``--no-format-code`` to skip.
    push
        Push the resulting commit and tag to ``origin`` at the end.
        Pass ``--no-push`` to validate the workflow locally without
        triggering remote CI.
    """
    release.run(
        version_part=version_part,
        message=message,
        format_code=format_code,
        push=push,
    )


@app.default
def default(
    version_part: Literal["patch", "minor", "major"] = "patch",
    *,
    message: Annotated[
        str,
        cyclopts.Parameter(name=["--message", "-m"]),
    ] = release.DEFAULT_MESSAGE_TEMPLATE,
    format_code: bool = True,
    push: bool = True,
    source: pathlib.Path = pathlib.Path("ai"),
    target: pathlib.Path = pathlib.Path("src/lfp_build/docs"),
) -> None:
    """
    Run ``stage-docs`` followed by ``release`` with the given options.

    Equivalent to ``lfp-build-publish stage-docs && lfp-build-publish
    release`` in one shot, so an unadorned ``uv run lfp-build-publish``
    covers the full local pipeline. To skip either half, call the
    subcommands directly.

    Parameters
    ----------
    version_part
        SemVer segment to bump. Forwarded to the ``release`` step.
    message
        Commit / tag message template forwarded to ``bump-my-version``.
        The ``{new_version}`` placeholder is resolved at bump time.
    format_code
        Run ``ruff check --fix --unsafe-fixes`` followed by ``ruff
        format`` inside the ``release`` step. Pass
        ``--no-format-code`` to skip.
    push
        Push the resulting commit and tag to ``origin`` at the end.
        Pass ``--no-push`` to validate the workflow locally without
        triggering remote CI.
    source
        Authored bundle root passed to the ``stage-docs`` step.
    target
        Packaged bundle destination passed to the ``stage-docs`` step.
    """
    bundle_docs.stage(source=source, target=target, clean=True)
    release.run(
        version_part=version_part,
        message=message,
        format_code=format_code,
        push=push,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
