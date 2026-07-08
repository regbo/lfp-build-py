# lfp-build workspace conventions

Reference doc for agents and contributors working in a uv workspace that uses
`lfp-build`. Complements the `lfp-build-workspace` skill with the "why" behind
the choices `lfp-build sync` enforces.

## Root vs. member responsibilities

- **Root `pyproject.toml`** owns cross-workspace concerns: the workspace
 members glob, the `[build-system]` used everywhere, shared tool config
 under `[tool.lfp-build.member-project]`, and type-checker search paths.
- **Member `pyproject.toml`s** own package identity (`name`, `version`
 gets synced) and their own `project.dependencies`. Member-specific
 `[tool.uv.build-backend]` may declare `module-root` and `module-name`
 when the layout diverges from the default `src/<module>/`.

The direction of truth is always **root -> members**, never members ->
root. Anything a member needs shared with siblings goes into
`[tool.lfp-build.member-project]` on the root.

## Workspace member globs

`sync` collapses concrete member directories into the smallest set of
`parent/*` globs that still fully matches disk state, honoring
`[tool.uv.workspace].exclude`. Prefer a single pattern (`packages/*`)
over per-member literals so new members are picked up automatically.

## Type-checker search paths

`sync` maintains `[tool.pyrefly].search-path` and
`[tool.pyright].extraPaths` from the workspace member patterns:

- Reads `[tool.uv.workspace].members`.
- For each pattern, appends the members' `[tool.uv.build-backend].module-root`
 (default `"src"`).
- Emits the pattern-shaped entry (e.g. `packages/*/src`) when all matching
 members share a `module-root`; expands to per-member literal paths only
 when they diverge.
- Never re-scans the filesystem - the members list from uv metadata is
 authoritative, so `exclude` patterns are honored automatically.

Consuming projects should not hand-edit these tables; `sync` is the sole
writer.

## Managing internal dependencies

Two modes, selected via `LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE`:

| Mode | Env var value | `project.dependencies` entry | `[tool.uv.sources]` |
| --- | --- | --- | --- |
| Plain names (default) | unset / `false` / `0` | `"core"` | `core = { workspace = true }` |
| Direct reference | `true` / `1` / `yes` | `"core @ file://${PROJECT_ROOT}/../core"` | `core = { workspace = true }` |

In both modes, `[tool.uv.sources].<dep> = { workspace = true }` is the
source of truth for uv's workspace resolution. Authors write intent in
`project.dependencies`; the tool writes the corresponding sources entry.

Do not write `dependencies = ["core>=1.0.0"]` for internal members - the
version specifier removes the wiring `sync` relies on to detect the
workspace relationship.

## Pre-commit hook

`lfp-build init` and `lfp-build hooks` install a managed block in
`.githooks/pre-commit` (via `core.hooksPath = .githooks`). The block:

- Runs `lfp-build sync`.
- Adds any `pyproject.toml` files updated by the sync to the staged
 changeset.

Content outside the managed markers (`# >>> lfp-build managed pre-commit
>>>` / `# <<< lfp-build managed pre-commit <<<`) is preserved on
re-install. Re-running the install is idempotent.

## Building wheels

`lfp-build build` builds each workspace project into a temporary
directory, then copies the wheels into `./dist/` (or `--out-dir`). When
direct-reference mode is on, `Requires-Dist: name @ file://...` entries
in the produced wheel `METADATA` are rewritten to plain names so the
distributed wheel does not depend on a local filesystem layout.

Prefer running through the CLI (`uv run lfp-build build`) rather than
invoking `uv build` directly - the CLI handles member ordering and
post-build metadata rewriting.

## Version derivation

Every `sync` sets `project.version` from `git describe`, normalizing to
`major.minor.patch` and appending a `+revN` or `+devN` suffix when the
working tree is not on an exact tag. If the workspace is not a git
checkout, the previously written version is preserved.

## What `sync` never touches

- Files outside `pyproject.toml` (except for ruff format on Python
 sources).
- Hand-authored `[dependency-groups]` entries.
- Unknown top-level tables (they pass through the reorder step but keep
 their contents).
- Sub-tables under `[tool.pyrefly]` / `[tool.pyright]` other than
 `search-path` / `extraPaths`.
