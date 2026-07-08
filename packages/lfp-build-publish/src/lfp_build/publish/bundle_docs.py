import pathlib
import shutil

from lfp_logging import logs

"""
Bundle-docs staging logic for ``lfp-build-publish``.

Populates the lfp-build package's ``docs/`` subpackage from the canonical
authored content at the workspace root's ``ai/`` directory so ``uv_build``
picks it up in the wheel. Runs before ``uv build --wheel`` (either
directly as ``uv run lfp-build-publish stage-docs`` or as the
stage-docs step of the default release workflow, and in CI before
publishing to PyPI).

The **source** layout under ``ai/`` groups content by kind:

- ``ai/skills/<name>/SKILL.md`` (plus any supporting files at the skill
  root) - skills for agent hosts.
- ``ai/docs/<name>.md`` - Markdown reference docs.

The **target** layout under ``src/lfp_build/docs/`` is flat:

- ``<name>/SKILL.md`` - skill subdirectory.
- ``<name>.md`` - reference doc file at the root.

The ``docs/`` subpackage's ``__init__.py`` is always preserved so
``importlib.resources.files("lfp_build.docs")`` continues to work on a
freshly staged tree.
"""

LOG = logs.logger(__name__)

_INIT_FILENAME = "__init__.py"
_SOURCE_SKILLS_DIRNAME = "skills"
_SOURCE_DOCS_DIRNAME = "docs"
_SKILL_MANIFEST_NAME = "SKILL.md"


def stage(*, source: pathlib.Path, target: pathlib.Path, clean: bool = True) -> None:
    """
    Copy the authored bundle at ``source`` onto ``target``.

    Parameters
    ----------
    source
        Path to the ``ai/`` directory holding authored content. May be
        absent, in which case the operation is a no-op after any
        requested clean step.
    target
        Path to the packaged bundle directory. Created if missing,
        along with a fresh ``__init__.py`` so the subpackage is
        resolvable via ``importlib.resources``.
    clean
        When True, remove existing staged content under ``target``
        (everything except ``__init__.py``) before copying, so entries
        removed from ``source`` never linger in the wheel.
    """
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    _ensure_init(target)

    if clean:
        _clean_target(target)

    if not source.is_dir():
        LOG.info("No bundle source at %s - target left cleaned only", source)
        return
    source = source.resolve()

    skill_count = _copy_skills(source_skills=source / _SOURCE_SKILLS_DIRNAME, target=target)
    doc_count = _copy_docs(source_docs=source / _SOURCE_DOCS_DIRNAME, target=target)
    LOG.info(
        "Staged bundle - source:%s target:%s skills:%d docs:%d",
        source,
        target,
        skill_count,
        doc_count,
    )


def clean(*, target: pathlib.Path) -> None:
    """
    Remove staged content from ``target`` while keeping ``__init__.py``.

    Parameters
    ----------
    target
        Path to the packaged bundle directory. If it does not exist,
        the call is a no-op.
    """
    target = target.resolve()
    if not target.is_dir():
        LOG.debug("Nothing to clean - target absent: %s", target)
        return
    _clean_target(target)
    _ensure_init(target)
    LOG.info("Cleaned bundle target: %s", target)


def _ensure_init(target: pathlib.Path) -> None:
    """
    Guarantee an empty ``__init__.py`` exists at ``target``.

    ``importlib.resources.files("<pkg>.docs")`` requires the subpackage
    to be resolvable; the tracked ``__init__.py`` is what keeps that
    contract intact even when the rest of the directory is gitignored.
    """
    init_path = target / _INIT_FILENAME
    if not init_path.is_file():
        init_path.touch()


def _clean_target(target: pathlib.Path) -> None:
    """
    Delete every entry under ``target`` except ``__init__.py``.
    """
    for entry in target.iterdir():
        if entry.name == _INIT_FILENAME:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def _copy_skills(*, source_skills: pathlib.Path, target: pathlib.Path) -> int:
    """
    Copy every ``<source_skills>/<name>/`` skill into ``<target>/<name>/``.

    A subdirectory qualifies as a skill only when it contains a
    ``SKILL.md`` at its root; other subdirectories are skipped with a
    warning so accidental drops (empty dirs, half-authored skills)
    surface visibly.
    """
    if not source_skills.is_dir():
        return 0
    count = 0
    for child in sorted(source_skills.iterdir(), key=lambda c: c.name):
        if child.name.startswith((".", "_")):
            continue
        if not child.is_dir():
            LOG.warning("Skipping non-directory skill entry: %s", child)
            continue
        if not (child / _SKILL_MANIFEST_NAME).is_file():
            LOG.warning("Skipping skill without %s: %s", _SKILL_MANIFEST_NAME, child)
            continue
        destination = target / child.name
        shutil.copytree(child, destination)
        count += 1
        LOG.debug("Staged skill - source:%s destination:%s", child, destination)
    return count


def _copy_docs(*, source_docs: pathlib.Path, target: pathlib.Path) -> int:
    """
    Copy every top-level ``*.md`` under ``source_docs`` to ``target/``.
    """
    if not source_docs.is_dir():
        return 0
    count = 0
    for child in sorted(source_docs.iterdir(), key=lambda c: c.name):
        if child.name.startswith((".", "_")):
            continue
        if not child.is_file() or not child.name.endswith(".md"):
            LOG.warning("Skipping non-Markdown doc entry: %s", child)
            continue
        destination = target / child.name
        shutil.copyfile(child, destination)
        count += 1
        LOG.debug("Staged doc - source:%s destination:%s", child, destination)
    return count
