# cproj Alternatives & Competitors

This document tracks alternative tools and competitors in the git worktree management and parallel development space.

---

## tree-me

**Link:** https://haacked.com/archive/2025/11/21/tree-me/?utm_source=tldrnewsletter
**Creator:** Phil Haack
**Repository:** Available via Phil Haack's dotfiles repository
**License:** MIT

### Overview
tree-me is a minimal bash wrapper around git's native worktree commands, designed to reduce the friction of creating and managing git worktrees manually. It focuses on simplicity and automation of basic worktree operations.

### Core Features
- `tree-me create <branch>` - Create new worktree branches
- `tree-me checkout <branch>` - Switch to existing worktrees
- `tree-me pr <number>` - Fetch and checkout GitHub pull requests
- `tree-me list` - Display all active worktrees
- `tree-me remove <branch>` - Clean up worktree directories
- `tree-me prune` - Remove stale worktree files
- Auto-detection of repository name from git remotes
- Default branch identification (checks origin/HEAD, falls back to main)
- Organized directory structure: `$WORKTREE_ROOT/<repo-name>/<branch-name>`
- Tab completion support for bash/zsh
- Automatic navigation into newly created worktrees

### Dependencies
- Git
- Bash
- GitHub CLI (`gh`) - optional, for PR functionality

### Strengths vs cproj

1. **Simplicity & Learning Curve**
   - Single bash script - extremely easy to understand and modify
   - Minimal dependencies (just git and bash)
   - Lower learning curve for developers already familiar with git worktrees
   - No Python dependency or virtual environment management

2. **Lightweight Footprint**
   - Single file implementation
   - No additional runtime overhead
   - Fast startup time
   - Easy to integrate into existing dotfiles

3. **GitHub PR Integration**
   - Built-in `tree-me pr <number>` command for quick PR checkouts
   - Simpler for teams focused primarily on PR reviews

4. **Shell Integration**
   - Automatic cd into worktrees after creation
   - Native bash/zsh tab completion
   - Better integration with traditional shell workflows

### Weaknesses vs cproj

1. **No AI Integration**
   - No support for AI agents or automated development workflows
   - No ticket generation, code review automation, or SDLC orchestration
   - Manual development process only

2. **Limited Environment Management**
   - No automatic environment setup (Python/Node/Java)
   - No virtual environment isolation or dependency management
   - No per-workspace environment configuration
   - Developers must manually set up each worktree's dependencies

3. **Basic Workspace Tracking**
   - No `.agent.json` metadata tracking
   - Limited visibility into workspace purpose, creation date, or ownership
   - No status tracking or progress monitoring
   - No Linear/JIRA integration for project management

4. **Manual Workflow Only**
   - No automation of testing, review, or deployment
   - No parallel development orchestration
   - No intelligent cleanup or resource management
   - No specialized workflows for experimentation or A/B testing

5. **Single Repository Focus**
   - No multi-project configuration or management
   - No project-specific templates or automation
   - No configurable base branch per project
   - No port allocation system for parallel environments

6. **Limited PR/Integration Features**
   - No automated PR creation with descriptions
   - No reviewer assignment or status tracking
   - No merge conflict assistance
   - No integration with CI/CD pipelines

7. **No Enterprise Features**
   - No project-wide configuration management
   - No custom actions or hooks system
   - No MCP server integration
   - No workspace templates or standardization

### Use Case Fit

**tree-me is better for:**
- Individual developers who want simple worktree automation
- Teams already comfortable with git worktrees
- Projects without complex environment requirements
- Quick PR reviews and branch switching
- Minimal dependency environments
- Developers who prefer bash scripting

**cproj is better for:**
- AI-driven parallel development workflows
- Teams using multiple AI agents simultaneously
- Complex projects with multiple technology stacks (Python/Node/Java)
- Enterprise environments requiring isolation and automation
- Projects needing full SDLC automation
- Teams integrating with Linear, GitHub, and other tools
- Experimentation-heavy workflows
- Projects requiring port allocation for parallel instances
- Organizations standardizing development workflows

### Competitive Positioning

tree-me occupies the "simple worktree wrapper" category, appealing to developers who want basic automation without the overhead of a full orchestration platform. cproj targets the "AI-first parallel development orchestrator" category, designed for teams leveraging multiple AI agents and requiring comprehensive SDLC automation.

The tools serve different market segments with limited overlap - tree-me competes more directly with manual git worktree usage, while cproj competes with development workflow orchestration platforms and AI agent coordination tools.

### Market Differentiation

cproj's key differentiators remain:
- **AI-first design** for autonomous agent workflows
- **Complete environment isolation** with automatic setup
- **Full lifecycle automation** from requirements to deployment
- **Project-aware intelligence** adapting to technology stacks
- **Enterprise-grade features** for teams and organizations
- **Parallel experimentation** with risk-free rollback

tree-me's differentiation:
- **Extreme simplicity** - single bash file
- **Zero overhead** - no runtime dependencies beyond bash
- **Easy customization** - readable bash script
- **Shell-native** - natural integration with terminal workflows

---

## Other Tools to Research

Future additions to this document should include analysis of:
- Git-machete
- Git-town
- Worktree management features in IDEs (VS Code, JetBrains)
- GitHub Copilot Workspace
- Other AI-assisted development platforms
