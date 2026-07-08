---
name: lfp-build-workspace
description: Use when authoring or maintaining a uv workspace that depends on lfp-build. Covers the workspace layout, adding/removing member packages, keeping internal dependencies aligned via `lfp-build sync`, and the conventions the tool assumes.
---

# lfp-build workspace

Reach for this skill any time the user is working inside a uv workspace that has `lfp-build` in its dependency groups, or is scaffolding a new one. It applies to both the root project and its member packages.

## When to use

- Setting up a new uv workspace with `lfp-build init`.
- Adding a member package with `lfp-build add`.
- Running `lfp-build sync` after editing `pyproject.toml` files by hand.
- Wiring internal member-to-member dependencies.
- Building wheels for one or more workspace members.

## Layout the tool expects

```
workspace-root/
├── pyproject.toml              # root: [tool.uv.workspace] + [tool.lfp-build.member-project]
├── packages/                   # or any parent dir referenced in [tool.uv.workspace].members
│   └── <member>/
│       ├── pyproject.toml
│       └── src/<module>/       # module-root defaults to "src"
└── .githooks/pre-commit        # installed by `lfp-build init` or `lfp-build hooks`
```

Root `pyproject.toml` should contain, at minimum:

```toml
[tool.uv.workspace]
members = ["packages/*"]
```

Optionally, a `[tool.lfp-build.member-project]` block whose contents are deep-merged into every member's `pyproject.toml` on every `sync`.

## Commands the user is likely to run

Prefer running through `uv` so the tool resolves against the workspace lock:

```bash
uv run lfp-build sync            # align every member with the root
uv run lfp-build add my-pkg      # add a new member under packages/
uv run lfp-build build           # build wheels into ./dist
uv run lfp-build hooks           # (re)install the managed pre-commit hook
```

`sync` is idempotent: run it whenever a member's `pyproject.toml` changes or a new member appears.

## Internal member dependencies

When one member depends on another, list the dependency by **plain name** in `project.dependencies` and let `lfp-build sync` maintain the `[tool.uv.sources]` wiring:

```toml
# packages/api/pyproject.toml
[project]
dependencies = ["core"]           # bare name; sync wires this up

# NOT: dependencies = ["core>=0.1.0"]     # do not add version specifiers for workspace members
# NOT: dependencies = ["core @ file://..."] unless direct-reference mode is on
```

The tool controls the format via `LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE`:

- unset / `false` (default): plain names + `[tool.uv.sources].core = { workspace = true }`
- `true`: `name @ file://${PROJECT_ROOT}/...` references + the same sources entry

Do not hand-edit `[tool.uv.sources]` or rewrite plain names to versioned specifiers - `sync` re-derives both.

## What `sync` maintains automatically

Every `lfp-build sync` run refreshes these across the root and members:

- Version (derived from `git describe`).
- `[build-system]` copied from root to every member.
- `[tool.lfp-build.member-project]` deep-merged into every member.
- `[tool.uv.sources]` normalized on both sides.
- `[tool.uv.workspace].members` consolidated into globs (`packages/foo`, `packages/bar` -> `packages/*`).
- `[tool.pyrefly].search-path` and `[tool.pyright].extraPaths` populated as `["."` plus one entry per workspace pattern with the members' `module-root` (default `"src"`) appended, e.g. `packages/*/src`.
- Ruff format + auto-fix on all projects.
- Reorder of top-level pyproject keys and TOML formatting via taplo (fallback tombi).

If you need to skip a step for a single invocation, pass its `--no-<name>` flag (for example, `uv run lfp-build sync --no-format-python`).

## Common pitfalls

- **Editing a member's `[tool.uv.sources]` by hand.** `sync` will rewrite it. Author the intent in `project.dependencies` instead.
- **Adding an upper bound to an internal dep.** `dependencies = ["core>=1.0.0"]` breaks the workspace-source wiring; use `dependencies = ["core"]`.
- **Wrapping optional imports in try/except.** If a package isn't a real optional dep, either declare it or leave the import unguarded.
- **Committing without running `sync` first.** The managed pre-commit hook does this automatically; if you have skipped hooks, run `uv run lfp-build sync` before committing.

## Verifying a change

```bash
uv run pytest                         # if the workspace has tests
uv run ruff format --check .
uv run lfp-build sync                 # should exit clean with no file diffs
```

If `sync` re-writes any `pyproject.toml`, commit the diff along with the change that caused it.
