# cproj - Intelligent Project Workflow Manager

A powerful CLI tool that streamlines software development workflows using Git worktrees, AI-powered agents, and automated project management. Create isolated workspaces, generate comprehensive tickets, perform AI code reviews, and manage the complete development lifecycle.

## Overview

cproj transforms how you work on software projects by:
- **Creating isolated workspaces** for each feature/bug using Git worktrees
- **Generating detailed Linear tickets** using AI agents (product manager, UX designer, engineer)  
- **Performing comprehensive code reviews** with specialized AI agents
- **Automating environment setup** (Python/uv, Node.js, Java)
- **Managing the complete workflow** from idea to merged code

## Key Features

### 🚀 **Intelligent Workflow Automation**
- **AI-powered ticket creation** with `add-ticket` command using specialized agents
- **Comprehensive code reviews** with `review-code` command and security analysis
- **Smart workspace management** with automatic environment detection

### 🔧 **Development Environment**
- **Git worktree isolation** - Work on multiple branches simultaneously
- **Automatic environment setup** - Python (uv), Node.js (nvm), Java builds
- **IDE integration** - Auto-launch terminals and editors on macOS

### 📊 **Project Management** 
- **Linear integration** - Create detailed tickets with AI assistance
- **GitHub integration** - Automated PR creation and merging with `gh` CLI
- **Progress tracking** - Persistent workspace metadata and status

### 🧹 **Maintenance & Cleanup**
- **Intelligent cleanup** - Remove old/merged worktrees with `--force` support
- **Workspace organization** - Clean `.cproj` directory structure

## Installation

### Option 1: Standalone Installer (Recommended)
```bash
# Clone or download this repository
git clone <repository-url>
cd cproj

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
pipx install git+https://github.com/user/cproj.git
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

## Complete Development Workflow

cproj provides a complete development workflow from initial idea to merged code. Here's the step-by-step process:

### 1️⃣ **Initial Setup**
```bash
# Initialize cproj configuration (one-time setup)
cproj init
# Configure Linear integration, GitHub reviewers, environment preferences
```

### 2️⃣ **Idea to Ticket (AI-Powered)**
```bash
# Generate comprehensive Linear tickets using AI agents
add-ticket "Add user authentication system"
```
This command uses specialized AI agents to create detailed tickets:
- **Product Manager Agent**: Turns high-level ideas into crisp PRDs
- **UX Designer Agent**: Creates user-centric design specifications  
- **Senior Engineer Agent**: Plans technical implementation with tests

### 3️⃣ **Create Development Workspace**
```bash
# Create isolated worktree for your feature
cproj w create --branch feature/user-auth
```
Automatically sets up:
- ✅ Git worktree with new branch
- ✅ Python environment (uv), Node.js (nvm), Java build
- ✅ Terminal and IDE integration
- ✅ Workspace metadata tracking

### 4️⃣ **Development & Testing**
```bash
# Work in your isolated environment
# Make changes, write tests, commit code
git add . && git commit -m "Implement user authentication"
```

### 5️⃣ **AI-Powered Code Review**
```bash
# Run comprehensive AI code review before submitting
review-code
```
Specialized review agents analyze:
- **Senior Developer**: Code quality, architecture, best practices
- **QA Engineer**: Test coverage, edge cases, quality assurance  
- **Security Reviewer**: Vulnerability assessment, OWASP compliance

Options for targeted reviews:
```bash
review-code --security-only    # Security review only
review-code --full            # Review entire codebase
review-code --qa-only         # QA review only
```

### 6️⃣ **Create Pull Request**
```bash
# Open PR for human review
cproj review open
```
Automatically:
- ✅ Pushes branch to remote
- ✅ Creates GitHub PR with description
- ✅ Assigns configured reviewers
- ✅ Links to Linear ticket

### 7️⃣ **Final Review & Merge**
```bash
# After approval, merge and cleanup
cproj merge
```
Handles the complete merge process:
- ✅ Merges PR (with squash option)
- ✅ Deletes remote branch
- ✅ Removes local worktree
- ✅ Updates workspace metadata

### 🧹 **Maintenance & Cleanup**
```bash
# Clean up old/stale worktrees
cproj cleanup                    # Interactive cleanup
cproj cleanup --older-than 14   # Remove worktrees older than 14 days
cproj cleanup --force           # Force remove dirty worktrees
cproj cleanup --newer-than 1    # Remove recent test worktrees
```

### 📊 **Monitoring & Status**
```bash
# List all active worktrees
cproj list

# Check current workspace status  
cproj status

# View Linear integration status
cproj linear status
```

## Command Reference

### 🎯 **Core Workflow Commands**

| Command | Purpose | Example |
|---------|---------|---------|
| `cproj init` | Initialize project configuration | `cproj init` |
| `cproj w create` | Create isolated workspace | `cproj w create --branch feature/auth` |
| `cproj review open` | Create PR for review | `cproj review open --assign team-lead` |
| `cproj merge` | Merge and cleanup | `cproj merge --squash` |

### 🤖 **AI-Powered Commands** 

| Command | Purpose | Agents Used |
|---------|---------|-------------|
| `add-ticket` | Generate comprehensive Linear tickets | product-manager, ux-designer, senior-software-engineer |
| `review-code` | AI-powered code review | senior-developer, qa-engineer, security-reviewer |

### 📊 **Monitoring & Management**

| Command | Purpose | Example |
|---------|---------|---------|
| `cproj list` | List active worktrees | `cproj list` |
| `cproj status` | Show workspace status | `cproj status` |
| `cproj cleanup` | Remove stale worktrees | `cproj cleanup --force` |
| `cproj linear status` | Linear integration status | `cproj linear status` |

### ⚙️ **Configuration & Tools**

| Command | Purpose | Example |
|---------|---------|---------|
| `cproj config` | Manage settings | `cproj config --list` |
| `cproj open` | Open workspace tools | `cproj open --editor` |
| `cproj linear setup` | Configure Linear | `cproj linear setup` |

### 💡 **Quick Examples**

#### 🚀 **Complete Feature Workflow**
```bash
# 1. Generate ticket with AI agents
add-ticket "Add OAuth integration for Google login"

# 2. Create workspace
cproj w create --branch feature/google-oauth

# 3. Develop feature (write code, tests)
# ... development work ...

# 4. AI-powered code review
review-code

# 5. Open PR
cproj review open --assign tech-lead

# 6. Merge after approval
cproj merge
```

#### 🤖 **AI Commands Deep Dive**
```bash
# Generate comprehensive tickets
add-ticket "User dashboard with analytics"
add-ticket --complexity DEEP "Redesign payment system"

# Comprehensive code review
review-code                    # Full review with all agents
review-code --security-only    # Security-focused review
review-code --full            # Review entire codebase
```

#### 🧹 **Cleanup & Maintenance**
```bash
# Interactive cleanup (recommended)
cproj cleanup

# Automated cleanup options  
cproj cleanup --older-than 14 --force    # Remove old worktrees
cproj cleanup --newer-than 1 --force     # Clean test branches
cproj cleanup --merged-only              # Remove merged branches
```

#### ⚙️ **Configuration & Setup**
```bash
# Initial setup
cproj init

# Linear integration
cproj linear setup --org "my-company" --team "ENG"
cproj linear status

# List all settings
cproj list --json

# Show current workspace status
cproj status

# Status for specific workspace
cproj status /tmp/myproject_feature_20241201_143022
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

### Development Workflow

You can develop cproj while having it installed system-wide. Here are the recommended workflows:

#### Option 1: Development with System Install (Recommended)
```bash
# Install cproj system-wide first
make install

# Clone the repo for development  
git clone https://github.com/bigandslow/cproj.git
cd cproj

# Work on changes in your editor
# Test changes directly with Python
python3 cproj.py --help

# Run tests
make test

# When ready to test system-wide, reinstall
make install
```

#### Option 2: Development Mode with pipx
```bash
# Install in development mode with pipx
pipx install --editable .

# Or install in a virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -e .[dev]

# Make changes and test immediately
cproj --help
```

#### Option 3: Dual Installation
```bash
# Keep system install for daily use
make install  # -> ~/.local/bin/cproj

# Install dev version with different name
pip install -e .[dev]
ln -sf $(pwd)/cproj.py ~/.local/bin/cproj-dev

# Use stable version: cproj
# Use dev version: cproj-dev or python3 cproj.py
```

### Development Commands

```bash
# Run all development checks
make dev-check        # Check development environment
make smoke-test       # Quick functionality test
make test            # Run full test suite
make lint            # Code linting
make format          # Code formatting
make clean           # Clean build artifacts

# Check installation status  
make check           # Verify cproj is installed and working
```

### Testing Changes

```bash
# Test specific functionality
python3 cproj.py config --help
python3 cproj.py init --help

# Test with temporary config (avoids affecting your real config)
CPROJ_CONFIG_DIR=/tmp/cproj-test python3 cproj.py init

# Test installation process
./uninstall.sh && ./install.sh

# Test with different Python versions
python3.8 cproj.py --help
python3.11 cproj.py --help
```

### Environment Variables for Development

```bash
# Override config directory for testing
export CPROJ_CONFIG_DIR=/tmp/cproj-dev-config

# Override installation paths for testing
export CPROJ_INSTALL_DIR=/tmp/cproj-test-install
export CPROJ_BIN_DIR=/tmp/cproj-test-bin

# Use different Python version for testing
export CPROJ_PYTHON=python3.11

# Test with these settings
python3 cproj.py init
```

### Code Structure

- `CprojCLI` - Main CLI interface and command routing
- `GitWorktree` - Git worktree operations  
- `AgentJson` - Metadata file management (.agent.json)
- `EnvironmentSetup` - Language environment setup (Python/Node/Java)
- `OnePasswordIntegration` - 1Password CLI integration for secrets
- `GitHubIntegration` - GitHub API via gh CLI with 1Password auth
- `TerminalAutomation` - macOS terminal/editor opening
- `Config` - Configuration management

### Development Troubleshooting

**Multiple cproj versions installed:**
```bash
# Check which cproj is being used
which cproj
cproj --version 2>/dev/null || echo "No version info"

# See all cproj installations
find /usr/local/bin ~/.local/bin -name "cproj*" 2>/dev/null
```

**Config conflicts during development:**
```bash
# Use isolated config for development
mkdir -p /tmp/cproj-dev-config
CPROJ_CONFIG_DIR=/tmp/cproj-dev-config python3 cproj.py init

# Reset to clean state
rm -rf ~/.config/cproj
```

**Testing without affecting system worktrees:**
```bash
# Use temporary directory for test worktrees
mkdir -p /tmp/cproj-test-workspaces
python3 cproj.py init --temp-root /tmp/cproj-test-workspaces

# Clean up test workspaces
rm -rf /tmp/cproj-test-workspaces
```

**Import errors during development:**
```bash
# Ensure you're in the right directory
pwd  # Should be in cproj repo directory

# Test import works
python3 -c "import cproj; print('Import successful')"
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch: `cproj worktree create --branch feature/my-feature`
3. Make your changes and add tests
4. Open a review: `cproj review open`
5. Merge after approval: `cproj merge --squash`