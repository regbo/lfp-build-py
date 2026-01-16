#!/usr/bin/env python3
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Iterable

import cyclopts
from lfp_logging import logs

from lfp_build import workspace

LOG = logs.logger(__name__)

_SKIP_DIR_NAMES = (
    "node_modules",
    "train",
    "venv",
    "build",
    "dist",
    "cache",
)

app = cyclopts.App()


@cyclopts.Parameter(name="*")
@dataclass
class RenameArgs:
    transforms: Annotated[list[str], cyclopts.Parameter(name="transform")] = field(
        default_factory=list
    )
    dry_run: bool = False
    dash_to_underscore: bool = False

    def mapping(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for transform in self.transforms:
            parts = transform.split(":")
            if len(parts) != 2:
                raise ValueError(f"Invalid transform: {transform}")
            mapping[parts[0]] = parts[1]
        return mapping


# noinspection PyBroadException
@app.default()
def rename(
    rename_args: Annotated[RenameArgs, cyclopts.Parameter(negative_iterable="")] | None,
) -> None:
    if rename_args is None:
        raise ValueError("RenameArgs cannot be None")
    file_path = pathlib.Path(__file__).parent
    workspace_root: pathlib.Path | None = workspace.metadata(file_path).workspace_root
    LOG.info(f"workspace_root: {workspace_root}")

    root = Path(".").resolve()

    _process_files(root=root, workspace_root=workspace_root, args=rename_args)
    _rename_dirs(root=root, workspace_root=workspace_root, args=rename_args)


# noinspection PyBroadException
def _is_binary(path: Path, chunk_size: int = 8192) -> bool:
    try:
        with path.open("rb") as f:
            return b"\x00" in f.read(chunk_size)
    except Exception:
        return True


def _is_in_workspace(path: Path, workspace_root: Path) -> bool:
    try:
        path.resolve().relative_to(workspace_root)
        return True
    except ValueError:
        return False


def _should_prune(path: Path, workspace_root: Path) -> bool:
    if _is_in_workspace(path, workspace_root):
        return True

    for part in path.parts:
        if part.startswith("."):
            return True
        if part.startswith("_"):
            return True
        if part in _SKIP_DIR_NAMES:
            return True
    return False


def _variants(value: str, dash_to_underscore: bool) -> Iterable[str]:
    if dash_to_underscore:
        yield value
        yield value.replace("-", "_")
    else:
        yield value


def _walk_dirs(root: Path, workspace_root: Path) -> Iterable[Path]:
    for dirpath, dirnames, _ in os.walk(root, topdown=True):
        current = Path(dirpath)

        dirnames[:] = [
            d for d in dirnames if not _should_prune(current / d, workspace_root)
        ]

        yield current


# noinspection PyBroadException
def _process_files(root: Path, workspace_root: Path, args: RenameArgs) -> None:
    mappings = args.mapping()

    for directory in _walk_dirs(root, workspace_root):
        if _is_in_workspace(directory, workspace_root):
            continue

        LOG.debug(f"visiting dir: {directory}")

        for file in directory.iterdir():
            if not file.is_file():
                continue
            if _is_binary(file):
                continue
            if _is_in_workspace(file, workspace_root):
                continue

            try:
                text = file.read_text(encoding="utf-8")
            except Exception:
                continue

            updated = text
            changed = False

            for src, dst in mappings.items():
                for s in _variants(src, args.dash_to_underscore):
                    d = dst if s == src else dst.replace("-", "_")
                    if s in updated:
                        updated = updated.replace(s, d)
                        changed = True

            if changed:
                LOG.info(f"updated file: {file}")
                if not args.dry_run:
                    file.write_text(updated, encoding="utf-8")


def _rename_dirs(root: Path, workspace_root: Path, args: RenameArgs) -> None:
    mappings = args.mapping()
    dirs: list[Path] = []

    for dirpath, _, _ in os.walk(root, topdown=False):
        current = Path(dirpath)
        if _should_prune(current, workspace_root):
            continue
        dirs.append(current)

    for src, dst in mappings.items():
        for s in _variants(src, args.dash_to_underscore):
            d = dst if s == src else dst.replace("-", "_")

            for directory in dirs:
                if _is_in_workspace(directory, workspace_root):
                    continue
                if s not in directory.name:
                    continue

                new_path = directory.with_name(directory.name.replace(s, d))
                LOG.info(f"renamed dir: {directory} -> {new_path}")

                if not args.dry_run:
                    try:
                        directory.rename(new_path)
                    except FileNotFoundError:
                        pass


if __name__ == "__main__":
    app()
