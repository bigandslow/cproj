# cproj - AI-First Parallel Development Orchestrator

**Scale your development with multiple AI agents working in parallel.** cproj enables enterprise-grade isolation using Git worktrees, intelligent environment management, and complete SDLC automation - from requirements to deployment.

## Overview

**Orchestrate multiple AI agents working simultaneously** on different features, fixes, and tasks in completely isolated environments. cproj transforms software development by enabling **parallel AI-driven workflows** with enterprise-grade safety and intelligent automation.

### **Why cproj?**
- **Multiple AI agents coding in parallel** - Scale development beyond human limitations
- **Zero-risk experimentation** - Try multiple approaches simultaneously, discard failures instantly
- **Complete SDLC automation** - From requirements gathering to security review and deployment
- **Project-aware intelligence** - Automatically adapts to your tech stack and workflow
- **Enterprise-grade isolation** - Git worktrees ensure no interference between parallel efforts

## Core Capabilities

### 🤖 **Parallel AI Development Orchestration**
- **Multiple AI agents working simultaneously** on different features, fixes, and experiments
- **Agent specialization** - Requirements gathering, development, review, security, testing
- **Coordination layer** prevents conflicts and manages handoffs between parallel efforts
- **Scale beyond human limitations** - Run dozens of development streams concurrently

### 🔄 **Complete SDLC Automation**
- **Requirements to deployment pipeline** - Product manager → UX designer → Senior engineer → Security reviewer → QA tester
- **AI-powered ticket generation** with comprehensive specs and implementation plans via `add-ticket`
- **Automated code review** with specialized agents for quality, security, and testing concerns via `review-code`
- **End-to-end automation** from initial idea to production-ready code

### 🛡️ **Risk-Free Experimentation**
- **Git worktree isolation** - Each agent gets its own workspace that can be instantly discarded
- **Parallel exploration** - Try multiple approaches simultaneously, keep the best results
- **Safe rollback** - Failed experiments don't affect main codebase or other parallel work
- **Zero-downtime development** - Main branch stays stable while agents experiment

### ⚙️ **Project-Specific Environment Configuration**
- **Automatic language detection** and environment setup (Python/uv, Node.js/nvm, Java/Maven/Gradle)
- **Per-workspace configuration** via `.agent.json` metadata tracking creation, ownership, and purpose
- **Custom setup scripts** and environment variables adapted to each project's needs
- **Dependency isolation** - Each worktree gets its own virtual environment and package installs

### 📊 **Intelligent Workspace Management**
- **Real-time visibility** into all active workspaces, their status, and progress
- **Progress tracking** across multiple parallel development efforts
- **Resource optimization** - Automatic cleanup of stale, completed, or failed workspaces
- **Workspace metadata** tracks creation time, author, purpose, linked tickets, and PR status

### 🔗 **Seamless Integration Flow**
- **Automated testing and validation** before integration to main branch
- **GitHub PR automation** with configured reviewers and intelligent descriptions
- **Linear ticket integration** for comprehensive project management and tracking
- **Conflict resolution assistance** when merging multiple parallel development streams

## Key Differentiators

**What makes cproj unique:**

- **🎯 AI-first workflow** - Designed from the ground up for multiple autonomous agents, not adapted from human-centric tools
- **🏗️ Enterprise-grade isolation** - Uses Git worktrees (not just branches) for true environment separation
- **📈 Built for scale** - Handle dozens of parallel development streams without performance degradation
- **🔧 Project-aware intelligence** - Automatically adapts to each repository's technology stack and workflow patterns
- **🛡️ Full lifecycle coverage** - From initial idea through production deployment with comprehensive automation
- **⚡ Zero-risk innovation** - Experiment fearlessly with instant rollback and parallel approach testing

## Quick Start

Get up and running with parallel AI development in minutes:

```bash
# 1. Install cproj
make install

# 2. Initialize project configuration
cproj init
# Configures: repo path, base branch, environment preferences, integrations

# 3. Generate AI-powered tickets
add-ticket "Add OAuth login system"

# 4. Create isolated workspace with auto-setup
cproj w create --branch feature/oauth-login
# Auto-detects and sets up: Python/Node/Java environments

# 5. Multiple AI agents work in parallel
# Each agent gets its own isolated workspace and environment

# 6. AI-powered code review
review-code --full

# 7. Integrate changes
cproj merge
```

**🚀 You're now running parallel AI development!** Each agent works in complete isolation while cproj orchestrates the full development lifecycle.

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

## Parallel AI Development Workflows

### 🚀 **Single Agent Workflow**
Perfect for focused development tasks:

```bash
# 1. Generate comprehensive requirements
add-ticket "Add user authentication system"
# → Product Manager, UX Designer, and Senior Engineer agents collaborate

# 2. Create isolated workspace
cproj w create --branch feature/user-auth
# → Automatic environment setup (Python/uv, Node/nvm, Java)

# 3. AI agent develops in isolation
# → Write code, tests, documentation in dedicated worktree

# 4. Comprehensive AI review
review-code --full
# → Senior Developer, QA Engineer, Security Reviewer agents

# 5. Integrate changes
cproj review open && cproj merge
```

### 🔄 **Multi-Agent Parallel Workflow**
Scale development with multiple agents working simultaneously:

```bash
# Generate multiple feature tickets
add-ticket "OAuth integration"
add-ticket "User dashboard"
add-ticket "API rate limiting"

# Launch parallel development streams
cproj w create --branch feature/oauth-login      # Agent 1
cproj w create --branch feature/dashboard        # Agent 2
cproj w create --branch feature/rate-limiting    # Agent 3

# Each agent works independently in isolated environments
# → No conflicts, no interference, complete isolation

# Monitor all parallel efforts
cproj list
# Shows status of all active workspaces and their progress

# Agents complete and integrate independently
review-code --full  # In each workspace
cproj merge         # When ready
```

### ⚡ **Experimental Parallel Workflow**
Try multiple approaches simultaneously, keep the best:

```bash
# Create multiple workspaces for the same problem
cproj w create --branch experiment/approach-a    # Traditional solution
cproj w create --branch experiment/approach-b    # Innovative approach
cproj w create --branch experiment/approach-c    # Alternative framework

# Agents explore different solutions in parallel
# → Risk-free experimentation with instant rollback

# Compare results and choose the best
cproj status experiment/approach-a
cproj status experiment/approach-b
cproj status experiment/approach-c

# Keep the winner, discard the others
cproj merge --branch experiment/approach-b       # Merge the best
cproj cleanup --pattern "experiment/approach-*"  # Clean up others
```

### 🛠️ **Development & Testing**
Each workspace provides complete isolation:

```bash
# Work in your isolated environment
cd $(cproj status --workspace-path)
# Make changes, write tests, commit code
git add . && git commit -m "Implement feature"

# Environment is automatically configured
# ✅ Python virtual environment with dependencies
# ✅ Node.js version management and packages
# ✅ Java build tools and configurations
# ✅ IDE integration and terminal automation
```

### 📊 **Monitoring & Status**
Real-time visibility across all parallel efforts:

```bash
# List all active worktrees with status
cproj list

# Detailed workspace information
cproj status                    # Current workspace
cproj status feature/oauth      # Specific workspace

# View Linear integration status
cproj linear status

# Monitor resource usage
cproj cleanup --dry-run         # See what would be cleaned up
```

### 🧹 **Intelligent Cleanup**
Automated maintenance of parallel workspaces:

```bash
# Interactive cleanup (recommended)
cproj cleanup

# Automated cleanup options
cproj cleanup --older-than 14   # Remove old worktrees
cproj cleanup --merged-only     # Remove merged branches
cproj cleanup --force           # Force remove dirty worktrees
cproj cleanup --pattern "exp-*" # Remove experimental branches
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