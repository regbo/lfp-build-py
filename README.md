# lfp-build

A comprehensive workspace management tool designed to handle complicated and common code generation tasks across
multi-project Python environments. Built to be adopted by any project requiring automated code generation, workspace
synchronization, and build orchestration.

## Features

- **Zero Dependencies**: Built entirely on the Python standard library.
- **Smart Synchronization**: Keep build configs, dependencies, and tool settings consistent across all workspace projects.
- **Project Scaffolding**: Bootstrap new projects with standard layouts and automatic workspace integration.
- **Version Coordination**: Manage version strings across multiple projects with git integration.
- **Multi-platform Support**: Supports macOS (ARM/x64), Linux (ARM/x64), and Windows (x64/ARM).
- **Automated Publishing**: Integrated with GitHub Actions for automatic PyPI deployment on tagging.

## Installation

This package requires Python >= 3.11 and < 3.14.

You can install `lfp-build` directly from GitHub using `pip`:

```bash
pip install git+https://github.com/regbo/lfp-build-py.git
```

Or add it to your `pyproject.toml` dependencies:

```toml
dependencies = [
    "lfp-build @ git+https://github.com/regbo/lfp-build-py.git"
]
```

### For Use in Your Project (Recommended)

lfp-build is designed to be used as a development dependency. Add it to your `pyproject.toml`:

```toml
[dependency-groups]
dev = [
    "lfp-build @ git+https://github.com/regbo/lfp-build-py.git"
]
```

Then use it via `uv run` without polluting your production dependencies:

```bash
# Sync configurations
uv run lfp-build sync

# Create new projects
uv run lfp-build create new-service
```

Using `uv run` ensures lfp-build and its dependencies are isolated from your project's runtime dependencies while
remaining available for all developers and CI/CD environments.

### Install Scripts (Nothing Preinstalled)

If you want to run `lfp-build` from a fresh machine with nothing installed, use the install scripts in this repo.
They will:

- Ensure a usable `HOME` exists (fallback to `/home/app`, then `/home`, then `/tmp/home`)
- Install `pixi` into `$HOME/.local/bin` (using `PIXI_HOME` and `PIXI_BIN_DIR`)
- Install `uv` if missing
- Install `git` if missing (via `pixi global install --channel conda-forge git`)
- Install `lfp-build` as a uv tool
- Run the pixi shell activation hook (best effort)

Linux/macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/regbo/lfp-build-py/main/install.sh | bash
```

If you want a single command that both installs and updates your current shell's environment:

```bash
eval "$(curl -fsSL https://raw.githubusercontent.com/regbo/lfp-build-py/main/install.sh | bash -s -- --emit-env)"
```

Windows PowerShell:

```powershell
irm -useb https://raw.githubusercontent.com/regbo/lfp-build-py/main/install.ps1 | iex
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
Usage: lfp-build create COMMAND [OPTIONS] NAME

Create a new member project in the workspace.                                   


Sets up a pyproject.toml and a standard src//init.py layout. Internal workspace 
dependencies are automatically synchronized after creation.

╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ member   Create a new member project in the workspace.                       │
│ project  Create a new workspace root project.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│    --working-directory       Set the current working directory.              │
│ *  NAME --name               The name of the new project (used for directory │
│                              and package name). [required]                   │
│    --path -p                 Optional parent directory within the workspace  │
│                              root. Defaults to packages/. [default:          │
│                              packages]                                       │
│    --project-dependency -pd  List of existing workspace projects to depend   │
│                              on.                                             │
│    --dependency -d           Additional dependency strings to add to the new │
│                              project's dependencies.                         │
╰──────────────────────────────────────────────────────────────────────────────╯
```
<!-- END:cmd -->

```bash
# Create a new project
uv run lfp-build create my-project

# Create a member with dependencies on other workspace projects
uv run lfp-build create my-api \
  --project-dependency my-core \
  --project-dependency my-models

# Create in a specific path within the workspace
uv run lfp-build create my-project --path /path/to/parent

# Create a new workspace root project (writes root pyproject.toml and creates packages/common)
uv run lfp-build create project agent-demo
```

Created projects include:

- Standard Python src layout (`src/<package_name>/`)
- Configured `pyproject.toml` with optional dependencies
- `__init__.py` for package initialization
- Workspace integration support

#### Create member vs create project

- `lfp-build create` (or `lfp-build create member`) creates a new member package under the workspace.
- `lfp-build create project` bootstraps a new workspace root project with:
  - a minimal root `pyproject.toml` configured for uv and pixi
  - `packages/common` created as an initial member
  - a copied local `.gitignore` template (cwd, parent, then repo fallback) if the target project does not already have one

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
│   s                           workspace sources. Dependency format is        │
│                               controlled by                                  │
│                               _config.MEMBER_PROJECT_DIRECT_REFERENCE.get()  │
│                               (plain names when False, ${PROJECT_ROOT} file  │
│                               references when True). [default: True]         │
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

When _config.MEMBER_PROJECT_DIRECT_REFERENCE.get() is True, built wheels are    
inspected in the temporary output directory and workspace-local Requires-Dist:  
... @ file://... entries are normalized to plain package requirements before    
copying artifacts to out_dir.

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

╭─ Parameters ─────────────────────────────────────────────────────────────────╮
│ --working-directory     Set the current working directory.                   │
│ TRANSFORM --transform   [default: []]                                        │
│ DRY-RUN --dry-run       [default: False]                                     │
│ DASH-TO-UNDERSCORE      [default: False]                                     │
│   --dash-to-underscore                                                       │
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

### util.py

Common utilities including logging initialization and subprocess management.

### pyproject.py

Utility for managing and manipulating pyproject.toml files using tomlkit and taplo.

### workspace.py

Interface for uv workspace metadata retrieval.

### workspace_create.py

Utilities for creating new workspace member projects.

### workspace_sync.py

Core synchronization logic for versions, build systems, and dependencies.

### workspace_dist.py

Build distribution artifacts for workspace projects.

### readme.py

Automated README documentation updater using command output sentinels.

## Development

### Dependencies

Core dependencies:

- `uv`: Workspace and dependency management
- `ruff`: Python formatting and linting
- `taplo`: TOML formatting
- `cyclopts`: CLI framework
- `tomlkit`: TOML manipulation
- `dacite`: Dataclass conversion
- `sitecustomize-entrypoints`: Automatic config initialization via `lfp_build._config:load` (loads `.dev.env` by default, override with `PYTHON_DOTENV_FILE`)

### Environment Variables

- `LOG_LEVEL`: Control logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `LFP_BUILD_MEMBER_PROJECT_DIRECT_REFERENCE`: Controls how internal workspace
  dependencies are written during sync and metadata repair.
  - `false` (default): keep internal dependencies as plain names (for example,
    `common`) and maintain `tool.uv.sources.<dep>.workspace = true`.
  - `true`: write internal dependencies as
    `name @ file://${PROJECT_ROOT}/...`. During `dist`, built wheel metadata is
    inspected and workspace-local `Requires-Dist: ... @ file://...` entries are
    rewritten to plain dependency names before copy.

## Extending lfp-build

The tool is designed to be extended for your specific needs:

### Adding New Commands

The modular architecture makes it easy to add new commands for your specific needs:

1. Create a new module in `src/lfp_build/`
2. Define a Cyclopts app with your commands
3. Add it to `cli.py` to integrate with the CLI

## Real-World Examples

### Microservice Architecture

Use lfp-build to manage a microservice ecosystem where each service has its own project but shares common
infrastructure code, build configs, and deployment settings.

### Monorepo Management

Coordinate builds, tests, and deployments across dozens of related Python packages with consistent tooling and
dependencies.

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
