# cproj - Multi-project CLI with git worktree + uv

A production-ready CLI tool for managing parallel project work using Git worktrees with environment isolation.

## Features

- **Git worktree-based isolation** - Work on multiple branches simultaneously without conflicts
- **Environment management** - Automatic Python (via `uv`), Node, and Java environment setup
- **Metadata tracking** - Persistent `.agent.json` files track workspace state
- **GitHub integration** - Create and merge PRs using `gh` CLI
- **Linear integration** - Link workspaces to Linear issues
- **Terminal automation** - Auto-open Terminal/iTerm and editors (macOS)
- **Cleanup tools** - Remove stale worktrees automatically

## Installation

### Option 1: Standalone Installer (Recommended)
```bash
# Clone or download this repository
git clone <repository-url>
cd cenv

# Run the installer (creates isolated environment)
make install
# or directly: ./install.sh

# Add to PATH if needed (shown after installation)
export PATH="$HOME/.local/bin:$PATH"
```

### Option 2: pipx (Python Users)
```bash
# Install with pipx for Python app isolation
pipx install .

# Or from GitHub directly
pipx install git+https://github.com/user/cenv.git
```

### Option 3: pip (Development)
```bash
# Install in development mode
make dev-install
# or directly: pip install -e .[dev]
```

### Uninstallation
```bash
make uninstall
# or directly: ./uninstall.sh
```

## Quick Start

1. **Initialize a project (Interactive)**
```bash
cproj init
# Follow the interactive prompts to configure your project
```

**Or with command-line arguments:**
```bash
cproj init --repo ~/dev/my-project --name "My Project"
```

2. **Create a new workspace**
```bash
cproj worktree create --branch feature/ABC-123-awesome --linear https://linear.app/...
```

3. **Open for review**
```bash
cproj review open
```

4. **Merge and cleanup**
```bash
cproj merge --squash --delete-remote
```

5. **Cleanup old workspaces**
```bash
cproj cleanup --merged-only --older-than 7
```

## Commands

### Core Commands

- `init` (`new`, `start`) - Initialize project configuration
- `worktree create` - Create isolated workspace with new branch
- `review open` - Prepare branch for review (push + create PR)
- `merge` - Merge branch and cleanup workspace
- `list` (`ls`) - List active workspaces
- `status` (`st`) - Show detailed workspace status
- `cleanup` - Remove stale workspaces
- `open` - Open workspace in terminal/editor/browser
- `config` - Manage configuration

### Command Examples

#### Initialize Project
```bash
# From existing local repo
cproj init --repo ~/dev/my-project --base main

# Clone from remote
cproj init --clone https://github.com/user/repo --name "My Project"
```

#### Create Workspace
```bash
# Basic usage
cproj worktree create --branch feature/new-feature

# With Linear integration and auto-setup
cproj worktree create \
  --branch feature/ABC-123-awesome \
  --linear https://linear.app/company/issue/ABC-123 \
  --python-install --node-install --java-build
```

#### Review Workflow
```bash
# Create draft PR
cproj review open --draft

# Create ready PR with reviewers
cproj review open --ready --assign user1,user2
```

#### Merge Options
```bash
# Squash merge (default)
cproj merge --squash --delete-remote

# Merge commit
cproj merge --merge --keep-worktree

# Force merge even with uncommitted changes
cproj merge --force
```

#### List and Status
```bash
# Human-readable list
cproj list

# JSON output
cproj list --json

# Show current workspace status
cproj status

# Status for specific workspace
cproj status /tmp/myproject_feature_20241201_143022
```

#### Cleanup
```bash
# Interactive cleanup
cproj cleanup

# Auto-cleanup old workspaces
cproj cleanup --older-than 7 --merged-only --yes

# Dry run to see what would be removed
cproj cleanup --older-than 30 --dry-run
```

### Global Options

- `--repo PATH` - Repository path (overrides config)
- `--base BRANCH` - Base branch (overrides config)  
- `--temp-root PATH` - Temp directory for worktrees
- `--terminal TERMINAL` - Terminal app (Terminal, iTerm, none)
- `--editor EDITOR` - Editor command (code, vim, etc.)
- `--yes` - Skip confirmations
- `--verbose` - Verbose output
- `--json` - JSON output (where supported)

## Configuration

### Initial Setup Interview
On first run, cproj will ask about:

- **Project identity**: name, repo path/URL, default base branch
- **Workspace policy**: temp root, branch naming, cleanup rules
- **Environment setup**: Python (uv preference), Node (nvm), Java detection
- **Tools**: terminal app, editor command
- **Integrations**: Linear org, GitHub settings

### Manual Configuration
```bash
# View all settings
cproj config

# Set specific values
cproj config editor code
cproj config terminal iTerm
cproj config base_branch develop
cproj config temp_root ~/.cache/workspaces

# View as JSON
cproj config --json
```

### Configuration File
Located at `~/.config/cproj/config.json`:

```json
{
  "repo_path": "/Users/me/dev/my-project",
  "project_name": "My Project", 
  "base_branch": "main",
  "temp_root": "/tmp",
  "terminal": "iTerm",
  "editor": "code"
}
```

## Environment Setup

### Python
- **Preferred**: `uv venv` + automatic dependency installation
- **Fallback**: `python3 -m venv .venv` + pip install
- **Auto-detected**: `pyproject.toml`, `requirements.txt`

### Node
- Uses `nvm` if available
- Honors `.nvmrc` files, falls back to LTS
- Auto-installs with `npm ci` or `npm install`

### Java  
- Detects Maven (`pom.xml`) or Gradle (`build.gradle*`)
- Optional initial build with `-DskipTests`

### Pre-commit & direnv
- Installs pre-commit hooks if `.pre-commit-config.yaml` exists
- Creates `.envrc` and runs `direnv allow` if enabled

## Integrations

### 1Password (Secret Management)
cproj integrates with 1Password CLI for secure secret management:

```bash
# Install 1Password CLI
# Download from: https://developer.1password.com/docs/cli/get-started/

# Authenticate with 1Password
op account add

# cproj will automatically detect and offer to use 1Password
cproj init  # Will prompt to store GitHub tokens, etc. in 1Password
```

When setting up integrations, cproj will:
- Detect if 1Password CLI is available and authenticated
- Offer to store GitHub tokens and other secrets securely
- Use stored references (like `op://Private/cproj-github-token/password`) instead of plain text
- Never store secrets in configuration files

### GitHub (via `gh` CLI)
```bash
# Install gh CLI first
brew install gh

# cproj will handle authentication (with optional 1Password integration)
cproj review open --ready --assign reviewer1,reviewer2
```

### Linear
```bash
# Link workspace to Linear issue
cproj worktree create --branch feature/ABC-123 --linear https://linear.app/...

# Opens in browser with cproj open
cproj open
```

## Workspace Metadata (.agent.json)

Each workspace contains a `.agent.json` file tracking:

```json
{
  "schema_version": "1.0",
  "agent": {"name": "username", "email": ""},
  "project": {"name": "My Project", "repo_path": "/path/to/repo"},
  "workspace": {
    "path": "/tmp/myproject_feature_20241201_143022",
    "branch": "feature/awesome",
    "base": "main", 
    "created_at": "2024-12-01T14:30:22Z",
    "created_by": "cproj-1.0.0"
  },
  "links": {
    "linear": "https://linear.app/...",
    "pr": "https://github.com/user/repo/pull/123"
  },
  "env": {
    "python": {"manager": "uv", "active": true, "pyproject": true},
    "node": {"manager": "nvm", "node_version": "20.10.0"},
    "java": {"build": "maven"}
  },
  "notes": "Custom notes"
}
```

## Troubleshooting

### Git Worktree Issues
```bash
# List all worktrees
git worktree list

# Force remove stuck worktree  
git worktree remove --force /path/to/worktree

# Prune removed worktrees
git worktree prune
```

### Environment Setup
```bash
# Check tool availability
which uv python3 nvm mvn gradle gh

# Python environment issues
uv venv --help  # Check uv is working
python3 -m venv --help  # Check venv fallback

# Node/nvm issues  
source ~/.nvm/nvm.sh  # Ensure nvm is sourced
nvm --version
```

### Terminal Automation (macOS)
- **Terminal/iTerm not opening**: Check System Preferences → Security & Privacy → Automation
- **AppleScript errors**: Enable terminal automation in Security preferences
- **Use `--terminal none`** to disable automation for CI/headless usage

### Missing Dependencies
```bash
# Install required tools
pip install uv  # or curl -LsSf https://astral.sh/uv/install.sh | sh
brew install gh
brew install nvm
```

## Safe Rollback

If something goes wrong:

1. **Restore base branch**:
   ```bash
   cd /path/to/main/repo
   git checkout main
   git reset --hard origin/main
   ```

2. **Remove stuck worktree**:
   ```bash
   git worktree remove --force /path/to/stuck/worktree
   git worktree prune
   ```

3. **Clean up temp directories**:
   ```bash
   rm -rf /tmp/*myproject*  # or your temp_root
   ```

## Development

### Running Tests
```bash
python -m pytest test_cproj.py -v
```

### Code Structure
- `CprojCLI` - Main CLI interface and command routing
- `GitWorktree` - Git worktree operations
- `AgentJson` - Metadata file management  
- `EnvironmentSetup` - Language environment setup
- `GitHubIntegration` - GitHub API via gh CLI
- `TerminalAutomation` - macOS terminal/editor opening
- `Config` - Configuration management

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch: `cproj worktree create --branch feature/my-feature`
3. Make your changes and add tests
4. Open a review: `cproj review open`
5. Merge after approval: `cproj merge --squash`