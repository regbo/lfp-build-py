# lfp-build

A workspace management CLI for multi-project Python repositories. It helps bootstrap member packages, keep workspace
`pyproject.toml` files aligned, build wheels, automate README command docs, and perform bulk rename operations.

## Features

- **Workspace Sync**: Keep shared build settings, member dependency wiring, and workspace paths consistent.
- **Project Creation**: Create new member packages or bootstrap a new workspace root with a starter package.
- **Wheel Builds**: Build wheel artifacts for all workspace members or a selected subset.
- **README Automation**: Refresh command output blocks embedded in documentation files.
- **Bulk Renames**: Rewrite names across files and directories, with optional dash-to-underscore handling.

## Installation

This package requires Python >= 3.10.12 and is published to PyPI:
[pypi.org/project/lfp-build](https://pypi.org/project/lfp-build/).

Install the latest released version from PyPI:

```bash
pip install lfp-build
```

To install the latest unreleased version directly from GitHub:

```bash
pip install git+https://github.com/regbo/lfp-build-py.git
```

### As a Dev Dependency (Recommended)

lfp-build is designed to be used as a development dependency so it stays out of your project's runtime
dependencies while remaining available to every contributor and CI job. Add it to your `pyproject.toml`:

```toml
[dependency-groups]
dev = [
    "lfp-build",
]
```

Or, to track the latest unreleased version from GitHub:

```toml
[dependency-groups]
dev = [
    "lfp-build @ git+https://github.com/regbo/lfp-build-py.git",
]
```

Then invoke it through `uv run`:

```bash
# Sync configurations
uv run lfp-build sync

# Initialize a new workspace
uv run lfp-build init new-service

# Add a member to the current workspace
uv run lfp-build add my-package
```

### For lfp-build Development

```bash
# Clone and install in editable mode
git clone https://github.com/regbo/lfp-build-py.git
cd lfp-build-py
pip install -e .
```

## Commands

The CLI follows a uv-style flat verb shape. Top-level verbs cover the common
workflow (`init`, `sync`, `build`, `add`, `hooks`, `rename`), with a single
subcommand group for `readme`.

### Init

<!-- BEGIN:cmd lfp-build init --help -->
```shell
Usage: lfp-build init [OPTIONS] NAME

Initialize a new workspace root project.                                        

Writes a minimal root pyproject.toml from the bundled template and creates a    
common member package under packages/.

╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│    --working-directory  Set the current working directory before dispatching │
│                         to a subcommand.                                     │
│ *  NAME --name          Name of the new workspace. Used as the project       │
│                         directory name. [required]                           │
│    --path -p            Parent directory to create the workspace in.         │
│                         [default: .]                                         │
│    --dependency -d      Additional dependency strings to add to the common   │
│                         member package.                                      │
│    --force -f           If True, remove an existing target directory before  │
│                         creating the project. [default: False]               │
╰──────────────────────────────────────────────────────────────────────────────╯
```
<!-- END:cmd -->

Bootstraps a new uv workspace: writes a minimal root `pyproject.toml`
from a bundled template, copies a local `.gitignore` template, and seeds
a `packages/common` member project. Also installs the lfp-build managed
`.githooks/pre-commit` block (the same logic exposed by `lfp-build hooks`)
so that `lfp-build sync` runs before each commit.

```bash
# Bootstrap a new workspace at ./agent-demo
uv run lfp-build init agent-demo

# Bootstrap with extra dependencies pre-wired into packages/common
uv run lfp-build init agent-demo --dependency requests --dependency pydantic

# Overwrite an existing target directory
uv run lfp-build init agent-demo --force
```

### Add

<!-- BEGIN:cmd lfp-build add --help -->
```shell
Usage: lfp-build add [OPTIONS] NAME

Add a new member project to the workspace.                                      

Sets up a pyproject.toml and a standard src/<package>/__init__.py layout.       
Internal workspace dependencies are automatically synchronized after creation.

╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│    --working-directory      Set the current working directory before         │
│                             dispatching to a subcommand.                     │
│ *  NAME --name              The name of the new project (used for directory  │
│                             and package name). [required]                    │
│    --path -p                Optional parent directory within the workspace   │
│                             root. Defaults to packages/. [default: packages] │
│    --project-dependency -c  List of existing workspace projects to depend    │
│                             on.                                              │
│    --dependency -d          Additional dependency strings to add to the new  │
│                             project's project.dependencies array.            │
╰──────────────────────────────────────────────────────────────────────────────╯
```
<!-- END:cmd -->

Adds a new member project to the current workspace. Sets up a
`pyproject.toml` and a standard `src/<package_name>/__init__.py` layout, then
runs a workspace sync so the member is wired into `[tool.uv.workspace]`
immediately.

```bash
# Add a member package under packages/
uv run lfp-build add my-project

# Add a member with dependencies on other workspace projects
uv run lfp-build add my-api \
  --project-dependency my-core \
  --project-dependency my-models

# Add in a specific subdirectory within the workspace
uv run lfp-build add my-project --path services
```

Created members include:

- Standard Python src layout (`src/<package_name>/`)
- A `pyproject.toml` seeded with optional dependencies
- An empty `__init__.py`
- Automatic workspace dependency wiring via `lfp-build sync`

### Sync

<!-- BEGIN:cmd lfp-build sync --help -->
```shell
Usage: lfp-build sync [OPTIONS]

Synchronize project configurations across the workspace.                        

This command performs several synchronization tasks to keep member projects     
aligned with the root project settings and ensure consistent dependencies.

╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│ --working-directory  Set the current working directory before dispatching to │
│                      a subcommand.                                           │
│ --name               Specific member project names to sync.                  │
│ --version            Sync version from git history to all member projects.   │
│                      [default: True]                                         │
│ --build-system       Sync [build-system] from root project to all member     │
│                      projects. [default: True]                               │
│ --member-project     Sync [tool.lfp-build.member-project] from root project  │
│                      to all member projects. [default: True]                 │
│ --sources            Sync [tool.uv.sources] on both the root project and     │
│                      every member project, and normalize internal member     │
│                      dependency entries. Set                                 │
│                      LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE=true to write │
│                      workspace deps as name @ file://${PROJECT_ROOT}/...     │
│                      references; otherwise plain member names are used.      │
│                      [default: True]                                         │
│ --member-paths       Sync member path patterns. [default: True]              │
│ --pyrefly            Maintain [tool.pyrefly].search-path on the root project │
│                      as ["."] plus, for each member that declares            │
│                      [tool.uv.build-backend].module-root, the relative path  │
│                      to that module root. [default: True]                    │
│ --reorder-pyproject  Order pyproject entries where applicable. [default:     │
│                      True]                                                   │
│ --format-pyproject   Format pyproject.toml files using taplo. [default:      │
│                      True]                                                   │
│ --format-python      Run ruff format and check on all projects. [default:    │
│                      True]                                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
```
<!-- END:cmd -->

```bash
# Sync all configuration
uv run lfp-build sync

# Sync specific projects only
uv run lfp-build sync --name project1 --name project2

# Disable specific sync tasks
uv run lfp-build sync --no-version --no-format-python
```

### Build

<!-- BEGIN:cmd lfp-build build --help -->
```shell
Usage: lfp-build build [OPTIONS]

Build wheel artifacts for workspace projects.

╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│ --working-directory  Set the current working directory before dispatching to │
│                      a subcommand.                                           │
│ --name               Optional member project names to build. If omitted, all │
│                      workspace projects from metadata are built in metadata  │
│                      order.                                                  │
│ --out-dir            Destination directory for built artifacts. Builds are   │
│                      performed in a temporary directory first, then copied   │
│                      into this directory with overwrite semantics. [default: │
│                      dist]                                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
```
<!-- END:cmd -->

```bash
# Build wheel artifacts for every workspace project
uv run lfp-build build

# Build wheel artifacts for selected projects
uv run lfp-build build --name common --name api
```

### Hooks

<!-- BEGIN:cmd lfp-build hooks --help -->
```shell
Usage: lfp-build hooks

Install or refresh the lfp-build managed pre-commit hook.                       

Discovers the workspace root via uv metadata, initializes a git repository there
if one does not already exist, configures git to use .githooks as               
core.hooksPath, and writes (or refreshes) the lfp-build managed block in        
.githooks/pre-commit. Hook content outside the managed markers is left          
untouched.

╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│ --working-directory  Set the current working directory before dispatching to │
│                      a subcommand.                                           │
╰──────────────────────────────────────────────────────────────────────────────╯
```
<!-- END:cmd -->

Install or refresh the lfp-build managed git pre-commit hook. The hook
runs `lfp-build sync` before each commit and stages any `pyproject.toml`
updates the sync produces. The managed portion of the hook is delimited by
`# >>> lfp-build managed pre-commit >>>` / `# <<< lfp-build managed
pre-commit <<<` markers, so re-running the command updates that block in
place without overwriting any user-added hook content.

```bash
# Install or refresh the managed pre-commit hook
uv run lfp-build hooks
```

`lfp-build init` already runs this on workspace bootstrap; use `lfp-build
hooks` directly to (re)install the hook into an existing workspace, refresh
a stale managed block, or after manually editing `.githooks/pre-commit`.

### Rename

<!-- BEGIN:cmd lfp-build rename --help -->
```shell
Usage: lfp-build rename [ARGS]

Bulk rename strings inside files and directory names.

╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│ --working-directory     Set the current working directory before dispatching │
│                         to a subcommand.                                     │
│ TRANSFORM --transform   One or more old:new substitution pairs. [default:    │
│                         []]                                                  │
│ DRY-RUN --dry-run       Preview changes without writing or renaming.         │
│                         [default: False]                                     │
│ DASH-TO-UNDERSCORE      Also rewrite underscore variants (old_name ->        │
│   --dash-to-underscore  new_name). [default: False]                          │
╰──────────────────────────────────────────────────────────────────────────────╯
```
<!-- END:cmd -->

```bash
# Rename strings in files and folder names recursively
uv run lfp-build rename old-name:new-name

# Preview rename changes without writing
uv run lfp-build rename old-name:new-name --dry-run

# Also rewrite underscore variants (old_name -> new_name)
uv run lfp-build rename old-name:new-name --dash-to-underscore
```

### Readme

<!-- BEGIN:cmd lfp-build readme --help -->
```shell
Usage: lfp-build readme COMMAND

README documentation automation.

╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ update  Update README command sentinel blocks.                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│ --working-directory  Set the current working directory before dispatching to │
│                      a subcommand.                                           │
╰──────────────────────────────────────────────────────────────────────────────╯
```
<!-- END:cmd -->

Automatically update README.md files by executing commands embedded in
sentinel blocks and replacing the body with the captured output.

```bash
# Update all command blocks in README
uv run lfp-build readme update

# Specify a different README file
uv run lfp-build readme update --readme docs/CLI.md

# Only update specific commands (filter by regex)
uv run lfp-build readme update --filter "sync"

# Preview changes without writing
uv run lfp-build readme update --write false

# Control parallelism
uv run lfp-build readme update --jobs 4
```

> **Note**: This README's command documentation is automatically generated by
> `lfp-build readme update`, which executes commands and embeds their help
> output into sentinel blocks.

#### How It Works

The `readme update` command looks for sentinel blocks in your README:

```markdown
<!-- BEGIN:cmd lfp-build sync --help -->
<!-- END:cmd -->
```

It executes the command between `BEGIN:cmd` and `--help`, captures the output, and replaces the content between the
BEGIN and END markers with a formatted code block containing the command's output.

**Features**:

- **Parallel Execution**: Runs multiple commands in parallel for faster updates
- **Smart Help Filtering**: Automatically removes `--help` option rows from help output to reduce noise
- **Empty Section Removal**: Removes empty Options sections when `--help` is the only option
- **Selective Updates**: Use `--filter` to update only specific commands
- **Safe by Default**: Preview mode available with `--write false`

This approach ensures your documentation stays in sync with actual command behavior, preventing documentation drift.

## Adopting lfp-build in Your Project

### Initial Setup

1. **Install lfp-build** in your project's dependencies
2. **Create a root pyproject.toml** if you don't have one
3. **Configure workspace members** to tell lfp-build which projects to manage
4. **Run your first sync** to align configurations

### Project Structure

The tool works with any workspace layout that has a root `pyproject.toml` and member projects:

```
your-workspace/
├── pyproject.toml              # Root configuration
├── core/                       # Your projects
│   ├── pyproject.toml
│   └── src/
│       └── core/
├── api/
│   ├── pyproject.toml
│   └── src/
│       └── api/
├── services/
│   ├── pyproject.toml
│   └── src/
│       └── services/
└── packages/                    # Optional subdirectory for projects
```

### Workspace Configuration

Add workspace configuration to your root `pyproject.toml`:

```toml
[tool.uv.workspace]
members = ["core", "api", "services"]
# Or use globs for flexibility
members = ["*/"]
exclude = ["legacy", "archived"]

[build-system]
requires = ["uv_build>=0.9.6,<0.10.0"]
build-backend = "uv_build"

# This section will be synced to all member projects
[tool.lfp-build.member-project]
# Shared configuration for all projects
```

### Common Workflows

**Keeping Projects in Sync**:

```bash
# Sync everything (run after changing root config)
uv run lfp-build sync

# Or sync specific aspects
uv run lfp-build sync --format-python
```

**Before Committing**:

```bash
# Sync and format
uv run lfp-build sync
```

## Module Reference

The package layout mirrors the CLI tree: each top-level command lives in its
own module under `commands/`, with shared logic at the package root.

```
src/lfp_build/
├── cli.py               # Cyclopts entry point; mounts each command
├── _config.py           # dotenv loader + runtime flag config
├── workspace.py         # uv workspace metadata + path consolidation
├── pyproject.py         # pyproject.toml read/write/order/format
├── version.py           # git-derived semver helpers
├── util.py              # subprocess helpers
├── commands/
│   ├── init.py          # `lfp-build init`
│   ├── add.py           # `lfp-build add`
│   ├── sync.py          # `lfp-build sync`
│   ├── build.py         # `lfp-build build`
│   ├── hooks.py         # `lfp-build hooks`
│   ├── rename.py        # `lfp-build rename`
│   └── readme.py        # `lfp-build readme update`
└── templates/
    └── init_pyproject.toml  # bundled root pyproject.toml template
```

### cli.py

Top-level Cyclopts entry point. Imports each command from `commands/` and
mounts it as a flat verb. No business logic.

### _config.py

Environment configuration loader. Auto-runs at interpreter startup via
`sitecustomize-entrypoints` to load a dotenv file and resolve runtime flags.

### workspace.py

Retrieve uv workspace metadata with a filesystem-scan fallback and a
best-effort source repair pass when uv reports a misconfigured workspace.

### pyproject.py

Read, update, reorder, and format `pyproject.toml` files via tomlkit, with
optional taplo/tombi formatting.

### version.py

Derive a normalized `major.minor.patch` semver string with optional
`+devN` / `+revN` suffix from `git describe` output and the working-tree
state. Used by `commands.sync` to refresh `project.version` on every
member during sync.

### util.py

Subprocess helpers used across the CLI for logging child stdout/stderr.

### commands/init.py

Bootstrap a new uv workspace: write the root `pyproject.toml` from the
bundled template at `lfp_build/templates/init_pyproject.toml`, copy a
local `.gitignore` template, install the managed pre-commit hook via
`commands.hooks.install`, and seed `packages/common`.

### commands/add.py

Add a new member project to the current workspace. Sets up the directory,
seeds `pyproject.toml`, creates the `src/<package>/__init__.py`, then runs
`commands.sync.sync` so the new member is wired in. Hook bootstrap is
intentionally not part of `add` - use `init` (for new workspaces) or
`hooks` (to install/refresh the hook on an existing workspace).

### commands/hooks.py

Install or refresh the lfp-build managed git pre-commit hook. Manages a
marker-delimited block in `.githooks/pre-commit` so re-running the install
logic is idempotent and preserves any user-added hook content outside the
markers. The CLI verb (`lfp-build hooks`) calls `install`, and
`commands.init` reuses the same `install` function during workspace
bootstrap.

### commands/sync.py

Core synchronization driver and step implementations: versions, build
system, member tool config, member dependencies, uv workspace member path
patterns, ruff format, and pyproject reorder/format.

### commands/build.py

Build wheel distribution artifacts for workspace projects, with optional
`Requires-Dist` rewriting for workspace-local file URIs.

### commands/rename.py

Bulk file-content and directory rename utilities, workspace-aware so the
enclosing tooling workspace itself is never modified.

### commands/readme.py

README documentation automation. Currently exposes a single `update` verb
that re-runs `BEGIN:cmd ... END:cmd` sentinel commands and embeds their
output back into the markdown.

## Development

### Dependencies

Core dependencies:

- `uv`: Workspace and dependency management
- `ruff`: Python formatting and linting
- `cyclopts`: CLI framework
- `lfp-logging`: Logging facade used across the CLI
- `python-dotenv`: Loads environment configuration from `.env` files
- `tomlkit`: TOML manipulation
- `mergedeep`: Deep merge support for synced config tables
- `sitecustomize-entrypoints`: Automatic config initialization via `lfp_build._config:load` (loads `.dev.env` by default, override with `LFP_BUILD_PYTHON_DOTENV_FILE`)

Optional external tools:

- `taplo`: Preferred TOML formatter when available
- `tombi`: Fallback TOML formatter used when `taplo` is unavailable on supported platforms

### Environment Variables

- `LOG_LEVEL`: Control logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL).
- `LFP_BUILD_PYTHON_DOTENV_FILE`: Override the dotenv file loaded at startup.
  Defaults to `.dev.env` (searched in the current working directory and the
  detected workspace root).
- `LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE`: Controls how internal workspace
  dependencies are written during sync and metadata repair.
  - `false` (default): keep internal dependencies as plain names (for example,
    `common`) and maintain `tool.uv.sources.<dep> = { workspace = true }`.
  - `true`: write internal dependencies as
    `name @ file://${PROJECT_ROOT}/...`. During `dist`, built wheel metadata
    is inspected and workspace-local `Requires-Dist: ... @ file://...`
    entries are rewritten to plain dependency names before copy.

## Extending lfp-build

The tool is designed to be extended for your specific needs:

### Adding New Commands

The modular architecture makes it easy to add new commands for your specific needs:

1. Create a new module in `src/lfp_build/commands/` (one file per top-level
   verb).
2. Either expose a plain function (for leaf verbs like `init`, `sync`, etc.)
   or a `cyclopts.App` (when the command owns its own subcommand group, as
   `readme` does).
3. Mount it in `cli.py` via `app.command(my_module.handler, name="...")`.

## Real-World Examples

Use lfp-build to manage a Python monorepo where packages share workspace metadata, internal dependencies, formatting,
and release artifacts.

## License

See [LICENSE](LICENSE) file for details.

## Contributing

Contributions that enhance workspace management capabilities are welcome. Maintain these principles:

- Preserve existing variable names and logic unless explicitly refactoring
- Add comprehensive documentation to all new or significantly modified code
- Follow Python standard ordering for globals, functions, and classes
- Use `_` prefix for private functions with limited scope

## Support

For issues, questions, or feature requests related to using lfp-build in your project, please open an issue on
GitHub.
