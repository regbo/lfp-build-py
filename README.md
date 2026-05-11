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

# Create new projects
uv run lfp-build create new-service
```

### For lfp-build Development

```bash
# Clone and install in editable mode
git clone https://github.com/regbo/lfp-build-py.git
cd lfp-build-py
pip install -e .
```

## Commands

### Create

<!-- BEGIN:cmd lfp-build create --help -->
```shell
Usage: lfp-build create COMMAND

Create new workspace members or bootstrap a new workspace root project.

╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ member   Create a new member project in the workspace.                       │
│ project  Create a new workspace root project.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│ --working-directory  Set the current working directory.                      │
╰──────────────────────────────────────────────────────────────────────────────╯
```
<!-- END:cmd -->

```bash
# Create a new member package under packages/
uv run lfp-build create member my-project

# Create a member with dependencies on other workspace projects
uv run lfp-build create member my-api \
  --project-dependency my-core \
  --project-dependency my-models

# Create in a specific subdirectory within the workspace
uv run lfp-build create member my-project --path services

# Bootstrap a new workspace root project (writes root pyproject.toml and creates packages/common)
uv run lfp-build create project agent-demo
```

Member projects include:

- Standard Python src layout (`src/<package_name>/`)
- Configured `pyproject.toml` with optional dependencies
- An empty `__init__.py` for the package
- Automatic workspace dependency wiring via `lfp-build sync`

#### Create member vs create project

- `lfp-build create member` creates a new member package under the workspace.
- `lfp-build create project` bootstraps a new workspace root project with:
  - a minimal root `pyproject.toml` configured for uv and pixi
  - `packages/common` created as an initial member
  - a copied local `.gitignore` template (cwd, parent, then repo fallback) if the target project does not already have one
  - a `.githooks/pre-commit` script that runs `lfp-build sync` before each commit

### Sync

<!-- BEGIN:cmd lfp-build sync --help -->
```shell
Usage: lfp-build sync [OPTIONS]

Synchronize project configurations across the workspace.                        

This command performs several synchronization tasks to keep member projects     
aligned with the root project settings and ensure consistent dependencies.

╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│ --working-directory           Set the current working directory.             │
│ --name                        Specific member project names to sync.         │
│ --version                     Sync version from git history to all member    │
│                               projects. [default: True]                      │
│ --build-system                Sync [build-system] from root project to all   │
│                               member projects. [default: True]               │
│ --member-project-tool         Sync [tool.member-project] from root project   │
│                               to all member projects. [default: True]        │
│ --member-project-dependencie  Sync internal member dependencies and uv       │
│   s                           workspace sources. Set                         │
│                               LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE=true │
│                               to write workspace deps as name @              │
│                               file://${PROJECT_ROOT}/... references;         │
│                               otherwise plain member names are used.         │
│                               [default: True]                                │
│ --member-paths                Sync member path patterns. [default: True]     │
│ --reorder-pyproject           Order pyproject entries where applicable.      │
│                               [default: True]                                │
│ --format-pyproject            Format pyproject.toml files using taplo.       │
│                               [default: True]                                │
│ --format-python               Run ruff format and check on all projects.     │
│                               [default: True]                                │
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

### Dist

<!-- BEGIN:cmd lfp-build dist --help -->
```shell
Usage: lfp-build dist [OPTIONS]

Build wheel artifacts for workspace projects.                                   

When LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE=true, built wheels are inspected 
in the temporary output directory and workspace-local Requires-Dist: name @     
file://... entries are normalized to plain package requirements before copying  
artifacts to out_dir.

╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│ --working-directory  Set the current working directory.                      │
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
uv run lfp-build dist

# Build wheel artifacts for selected projects
uv run lfp-build dist --name common --name api
```

### Rename

<!-- BEGIN:cmd lfp-build rename --help -->
```shell
Usage: lfp-build rename [ARGS]

Bulk rename strings inside files and directory names.

╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│ --working-directory     Set the current working directory.                   │
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

### README

<!-- BEGIN:cmd lfp-build readme --help -->
```shell
Usage: lfp-build readme COMMAND

Refresh README command-help sentinel blocks from live --help output.

╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ update-cmd  Update README command sentinel blocks.                           │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│ --working-directory  Set the current working directory.                      │
╰──────────────────────────────────────────────────────────────────────────────╯
```
<!-- END:cmd -->

Automatically update README.md files by executing help commands embedded in sentinel blocks.

```bash
# Update all command blocks in README
uv run lfp-build readme update-cmd

# Specify a different README file
uv run lfp-build readme update-cmd --readme docs/CLI.md

# Only update specific commands (filter by regex)
uv run lfp-build readme update-cmd --filter "sync"

# Preview changes without writing
uv run lfp-build readme update-cmd --write false

# Control parallelism
uv run lfp-build readme update-cmd --jobs 4
```

> **Note**: This README's command documentation was automatically generated using `lfp-build readme`,
> which executes commands and embeds their help output into sentinel blocks.

#### How It Works

The `readme update-cmd` command looks for sentinel blocks in your README:

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
[tool.member-project]
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

### cli.py

Top-level Cyclopts entry point that wires together every subcommand group.

### _config.py

Environment configuration loader. Auto-runs at interpreter startup via
`sitecustomize-entrypoints` to load a dotenv file and resolve runtime flags.

### util.py

Subprocess helpers used across the CLI for logging child stdout/stderr.

### pyproject.py

Read, update, order, and format `pyproject.toml` files via tomlkit, with
optional taplo/tombi formatting.

### workspace.py

Retrieve uv workspace metadata with a filesystem-scan fallback and a
best-effort source repair pass when uv reports a misconfigured workspace.

### workspace_create.py

Scaffold new workspace member projects and bootstrap a workspace root.

### workspace_sync.py

Core synchronization logic for versions, build systems, member settings, uv
workspace member path patterns, and internal workspace dependencies.

### workspace_dist.py

Build wheel distribution artifacts for workspace projects, with optional
``Requires-Dist`` rewriting for workspace-local file URIs.

### readme.py

Automated README documentation updater using command output sentinels.

### rename.py

Bulk file-content and directory rename utilities.

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

1. Create a new module in `src/lfp_build/`
2. Define a Cyclopts app with your commands
3. Add it to `cli.py` to integrate with the CLI

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
