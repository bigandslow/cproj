# cproj - AI-First Parallel Development

Scale your development with multiple AI agents working in parallel using Git worktrees for complete isolation.

## Quick Start

```bash
# Install
make install

# Initialize (one-time system setup)
cproj init

# Configure a project (from within any git repo)
cproj init-project --template web-app

# Create an isolated workspace
cproj w create --branch feature/my-feature

# Check status of all workspaces
cproj status

# Clean up merged workspaces
cproj cleanup
```

## Core Commands

| Command | Description |
|---------|-------------|
| `cproj w create --branch <name>` | Create isolated workspace (re-run to resume an interrupted setup; `--recreate` to start over, keeping the branch) |
| `cproj w create --where local\|cloud --branch <name>` | Create on the project's cloud env instead (`--cloud`/`--local`; see [Cloud Envs](#cloud-envs)) |
| `cproj cloud ls\|attach\|bootstrap` | List, attach to, or install cproj on the cloud env |
| `cproj status` | Show all workspace statuses |
| `cproj list` | List worktrees |
| `cproj review open` | Create PR |
| `cproj merge` | Merge and cleanup |
| `cproj cleanup` | Remove stale workspaces |
| `cproj sync-env` | Sync .env files between worktree and main |

## Project Configuration

Configure per-project behavior in `.cproj/project.yaml`:

```yaml
name: my-project
type: web-app
base_branch: develop  # Default branch for new worktrees

features:
  claude_workspace: true   # Setup .claude directory
  nvm_setup: true          # Node.js/nvm integration
  port_allocation: true    # Auto port offsets for parallel dev
  auto_terminal: true      # Open terminal after worktree creation

# Automatic port offset allocation
port_config:
  base_port: 3000
  max_slots: 99

# Variables to ignore when checking for unsync'd .env changes
env_diff_ignore_vars:
  - API_URL
  - DATABASE_PORT

# Custom actions run after worktree creation
custom_actions:
  - type: copy_env_files
    description: Copy .env files from main repo

  - type: run_command
    description: Run setup script
    command: bash tools/setup.sh

# MCP servers for Claude integration
mcp_servers:
  - name: linear-server
    transport: sse
    url: 'https://mcp.linear.app/sse'
```

### Custom Action Types

| Type | Description |
|------|-------------|
| `copy_env_files` | Copy .env files from main repo |
| `copy_directory` | Copy a directory (e.g., `.vercel`) |
| `copy_workspace_file` | Copy with rename pattern |
| `allocate_port` | Allocate unique port offset |
| `run_command` | Run shell command |

Custom actions run again when an interrupted `cproj w create` is resumed, so `run_command` scripts should be safe to re-run.

### run_command Placeholders

Commands support these placeholders:
- `{worktree_path}` - Absolute path to worktree
- `{repo_path}` - Absolute path to main repo
- `{worktree_name}` - Directory name of worktree
- `{branch}` - Full branch name

Example:
```yaml
- type: run_command
  description: Launch development session
  command: rc start {worktree_path} --name "{worktree_name}"
```

### Feature Flags

| Feature | Default | Description |
|---------|---------|-------------|
| `claude_workspace` | false | Setup .claude directory with agents/commands |
| `claude_symlink` | false | Symlink .claude instead of copy |
| `nvm_setup` | false | Create setup-claude.sh for Node.js |
| `port_allocation` | false | Enable automatic port offsets |
| `auto_terminal` | true | Open terminal after worktree creation |
| `review_agents` | false | Enable AI review agents |

## Cloud Envs

Worktrees and Claude sessions on a VM reached over ssh, each in a VM tmux
session. Design: [docs/cloud-envs-design.md](docs/cloud-envs-design.md).

User config (`~/.config/cproj/config.json`):

```json
{
  "cloud_envs": { "agent-vm": { "host": "chris@100.119.63.101" } },
  "default_cloud_env": "agent-vm",
  "attach_command": "c2h attach {host} {session} --repo {repo_path} --label {label}"
}
```

Optional per env: `work_root` (default `work`, under the VM `$HOME`),
`env_file` (default `/run/agent-vm/{user}/env`, `{user}` = the VM user),
`remote_cproj` (default `.local/bin/cproj`). `projects.<name>.cloud_env`
picks an env per project. Without `attach_command`, cproj opens Terminal
running `ssh -t <host> tmux new -A -s <session>`.

Project config (`.cproj/project.yaml`):

```yaml
cloud:
  enabled: true
  default_location: ask   # ask | local | cloud
  remote_control: true    # claude starts with --remote-control <name> (--no-rc to skip)
  worktree_dir: .claude/worktrees
custom_actions:
  - type: run_command
    where: [local, cloud]  # default [local]
    command: ...
```

- `cproj cloud bootstrap [--dry-run]` copies this `cproj.py` to the VM
  (`~/.local/share/cproj`, wrapper `~/.local/bin/cproj`, run with the VM's
  python3, which needs PyYAML). Re-run it after updating cproj; cproj warns
  when the VM copy differs.
- `cproj w create --cloud --branch feature/x` checks the VM first (clone
  present with the same origin; branch, worktree and tmux name free), fetches
  with the VM user's env file loaded, adds the worktree (tracking
  `origin/<branch>` if it exists, else from the base without tracking), runs
  `where: cloud` actions, starts claude in tmux and attaches. Nothing is
  created locally.
- `cproj cloud ls`, `cproj cloud attach <name>`.

## Environment Setup## Environment Setup

cproj automatically detects and configures:

- **Python**: Uses `uv` (preferred) or `venv`, installs from `pyproject.toml` or `requirements.txt`
- **Node.js**: Uses `nvm`, honors `.nvmrc`, runs `npm ci`
- **Java**: Detects Maven/Gradle, optional initial build

### Port Allocation

Each worktree gets a unique port offset (0-99):

```bash
# In your worktree
source .cproj/setup-claude.sh
echo $CPROJ_PORT_OFFSET  # e.g., 2

# Calculate ports
API_PORT=$((3000 + CPROJ_PORT_OFFSET))  # 3002
```

Manage ports:
```bash
cproj ports list       # Show allocations
cproj ports free 5     # Free offset 5
```

## Status & Cleanup

```bash
# Show all worktrees needing attention
cproj status

# Show all worktrees including clean ones
cproj status --detailed

# Interactive cleanup
cproj cleanup

# Force cleanup of merged branches
cproj cleanup --merged-only --force
```

Status indicators:
- `COMMIT` - Has uncommitted changes
- `PUSH` - Needs to push commits
- `CREATE PR` - Ready for PR creation
- `REVIEW` - PR under review
- `CLEANUP` - PR merged, safe to remove

## Syncing Environment Files

Sync .env files between worktrees and main repo:

```bash
# Pull all .env changes from worktree to main
cproj sync-env

# Pull only specific keys
cproj sync-env --keys API_KEY,SECRET_TOKEN

# Push from main to current worktree
cproj sync-env --push

# Push specific keys to ALL worktrees (e.g., rotate secrets)
cproj sync-env --push --keys API_KEY,SECRET_TOKEN --all-worktrees

# Preview changes first
cproj sync-env --push --keys API_KEY --all-worktrees --dry-run
```

Options:
- `--push` - Push from main to worktree (default: pull from worktree to main)
- `--keys KEY1,KEY2` - Sync only specific variables
- `--all-worktrees` - Push to all managed worktrees (requires --push)
- `--file .env.local` - Sync only a specific file
- `--backup` - Create backup before overwriting
- `--dry-run` - Preview changes without applying

## Installation

```bash
# Standalone (recommended)
make install

# Or with pipx
pipx install .

# Uninstall
make uninstall
```

## Global Options

```bash
--terminal iTerm|Terminal|none  # Terminal app
--editor code|vim|...           # Editor command
--yes                           # Skip confirmations
--json                          # JSON output
```

## Troubleshooting

```bash
# Git worktree issues
git worktree list
git worktree prune

# Force remove stuck worktree
git worktree remove --force /path/to/worktree

# Check tool availability
which uv nvm gh
```

## License

MIT
