Got it — here’s a single, self-contained “master prompt” you can drop into your AI tool to generate a **git-worktree–based CLI** that adopts **uv** for Python, records **.agent.json**, and supports: **start a new project**, **create a branch/workspace**, and **review + merge**. I’ve also included a few highly useful extra commands and all the UX/details the AI should ask for before generating code. (Per your request, this is just the prompt — no code.)

---

# MASTER PROMPT — Build a multi-project CLI with `git worktree` + `uv` (IMPROVED)

**Goal:** Generate a production-ready CLI tool (installable binary or `pipx`/`npm`/single-file) that orchestrates parallel project work using **Git worktrees** and per-workspace environments. Default to **Python env via `uv`** (fallback to `venv` if `uv` not present), support Node (nvm) and Java. Persist lightweight metadata in **`.agent.json`**. Integrate with Linear and GitHub for review flows.

## Key Improvements in This Version

- **Enhanced Security & Privacy**: Config validation, 1Password CLI integration, optional network request controls
- **Better Error Handling**: Graceful degradation, atomic operations with rollback, health checks
- **Improved UX**: Interactive setup prompts, dry-run flags, progress indicators, color-coded output with no-color option  
- **Cross-platform Support**: Abstracted terminal automation, platform-appropriate temp dirs
- **Performance**: Caching, parallel operations, offline mode support
- **Maintainability**: Structured logging, modern Python packaging, schema versioning
- **Installation**: Standalone installer with isolated environments to avoid conflicts

## Capabilities (top-level commands)

Implement these commands (with short aliases in parentheses):

1. **`init`** (`new`, `start`) — Start a new project directory and bootstrap it

   * Creates/normalizes a canonical repo folder (or clones it), writes base config, ensures required tools are discoverable.
2. **`worktree create`** (`ws create`, `branch create`) — Create a new isolated **worktree** and branch

   * Names and creates the branch from a base, prepares an isolated working directory, sets up env (Python via `uv`, Node via `nvm`, Java), writes `.agent.json`, optional Linear link, and optionally opens Terminal/iTerm and editor.
3. **`review open`** (`review`) — Prep a review: run checks, push branch, open/create PR, attach Linear link, post summary
4. **`merge`** — Merge the reviewed branch back to base (squash by default), delete remote/local branch, and remove the worktree safely
5. **`list`** (`ls`) — List active worktrees/branches with status (ahead/behind, dirty, age)
6. **`status`** (`st`) — Show detailed status for a workspace (env health, last run, Linear link, PR link)
7. **`cleanup`** — Remove stale worktrees (by age, merged state, or interactively)
8. **`open`** — Open the workspace in Terminal/iTerm and editor, and open Linear/PR in the browser
9. **`config`** — Set or print defaults (Terminal app, editor, Node LTS, base branch, temp root, etc.)

> If you believe any small helper subcommands are necessary (e.g., `doctor`, `validate`), include them.

## What to ask the user (interactive bootstrap)

Before generating code, interview the user and capture sane defaults (also allow override via flags/env):

* **Project identity**

  * Project name (display name)
  * **Canonical repo**: local path (preferred for worktree) and/or remote URL (fallback)
  * Default **base branch** (e.g., `main`, `develop`)
* **Workspace policy**

  * **Temp root** for worktrees (default: `$TMPDIR` or `~/.cache/workspaces`)
  * Branch naming scheme: `feature/<ticket>-<slug>`, `fix/…`, `chore/…`
  * Auto-cleanup policy (age threshold, only merged branches, confirm deletion)
* **Env setup**

  * Python: prefer **`uv`**? (default yes). If `uv` absent, use `venv`. Auto-install from `pyproject.toml` or `requirements.txt`?
  * Node: use `nvm`, honor `.nvmrc`, fallback to LTS?
  * Java: detect Maven/Gradle; initial build?
  * Optional: `direnv` support, `pre-commit` hooks, Conventional Commits/commitlint (if Node)
* **Terminals & editors**

  * Terminal app: `Terminal` or `iTerm2` (macOS)
  * Editor command: e.g., `code`, `idea`, `cursor`, `vim`
* **Integrations**

  * **Linear**: org URL pattern or none; default to prompting for issue URL per workspace
  * **GitHub**: use `gh` CLI for PRs? default draft PRs? required reviewers?
* **Security & secrets**

  * If using 1Password CLI or other manager, enable optional key-load steps (no secrets stored)

## Behavior details (what the tool must implement)

### Git worktree flow (required)

* Requires **local canonical repo** with `.git`.
* `worktree create`:

  1. `git -C <repo> fetch --all --prune`
  2. Ensure `<base>` exists locally (create from `origin/<base>` if missing), fast-forward it
  3. Create **new worktree** at `<tempRoot>/<project>_<branch>_<timestamp>`

     * If branch exists, attach it; else create with `-b <branch> <base>`
  4. Write **`.agent.json`** file to the worktree (see schema)
  5. Prepare env (see below)
  6. Optionally open Terminal/iTerm tab titled `<project>:<branch>` and `cd` into the worktree; optionally open editor
* `merge`:

  * Validate PR state (if GitHub), ensure CI green (if configured), then **squash merge** by default (configurable)
  * Delete remote branch (optional flag), **remove local worktree**, and delete local branch if safe
  * Update `.agent.json` with final state and write an audit entry/log
* `list` & `status`:

  * Show per-worktree info: branch, base, repo path, age, dirty status, ahead/behind counts, Linear link, PR URL

### `.agent.json` (required)

Create in **worktree root**; include at minimum:

```json
{
  "agent": { "name": "<user/agent name or id>", "email": "<optional>" },
  "project": { "name": "<Project Name>", "repo_path": "<canonical local repo path>" },
  "workspace": {
    "path": "<absolute path>",
    "branch": "<branch-name>",
    "base": "<base-branch>",
    "created_at": "<ISO8601>",
    "created_by": "<cli-version or 'manual'>"
  },
  "links": {
    "linear": "<url or empty>",
    "pr": "<url or empty>"
  },
  "env": {
    "python": { "manager": "uv|venv|none", "active": true, "pyproject": true, "requirements": true },
    "node":   { "manager": "nvm|none", "node_version": "<resolved or empty>" },
    "java":   { "build": "maven|gradle|none" }
  },
  "notes": "<free text>"
}
```

* Update `links.pr` when PR is created.
* Update `workspace.closed_at` on merge/cleanup.

### Environment setup rules

* **Python via `uv` (preferred)**

  * If `uv` present: create/activate `.venv` with `uv venv`; install deps if `pyproject.toml` or `requirements.txt` and the user enabled auto-install.
  * Fallback: `python3 -m venv .venv` + `pip install -r requirements.txt` (if present).
  * Record chosen manager in `.agent.json.env.python.manager`.
* **Node via `nvm`**

  * Source `nvm` from `~/.nvm/nvm.sh` (or detect via shell rc files).
  * If `.nvmrc` exists: `nvm install && nvm use`; else use LTS if configured.
  * Install deps: `npm ci` if `package-lock.json`, else `npm install` (only if user enabled auto-install).
* **Java**

  * Detect Maven (`pom.xml`) or Gradle (`build.gradle*`); optional initial build (`-DskipTests`).
* **Extras**

  * If `pre-commit` config exists and enabled, run `pre-commit install`.
  * If `direnv` enabled, create minimal `.envrc` and run `direnv allow`.

### Review & merge flow

* **`review open`**:

  * Ensure branch exists and is pushed (`git push -u origin <branch>`).
  * If GitHub and `gh` available, `gh pr create` (draft by default; configurable), set title/description using branch name + Linear reference, assign reviewers if configured.
  * Run optional local checks before opening PR: format, lint, unit tests; summarize results.
  * Persist PR URL to `.agent.json.links.pr`; echo it to the console.
* **`merge`**:

  * If GitHub: `gh pr merge` using **squash** by default, with delete-branch option if configured.
  * On success: remove worktree (`git worktree remove -f <path>`), optionally delete local branch, and update `.agent.json` with `closed_at`.

### Terminal/editor UX

* Support **`--terminal=iterm|terminal|none`**; default to user config.
* Title new tab/window as `<project>:<branch>`.
* **`open`** command launches terminal/editor/browsers per current workspace.

### Safety & guardrails

* Never reuse a worktree path for a different branch.
* Prevent `merge` if branch is **dirty** (unless `--force`).
* Confirm deletion on `cleanup` unless `--yes`.
* Handle missing tools with actionable guidance (install commands) and fallback paths.
* Always log key actions with timestamps; store last log at `<worktree>/.project/last_run.log`.
* Validate all config inputs to prevent shell injection attacks.
* Use 1Password CLI for secure token storage (never store secrets in config files).
* Implement atomic operations with automatic rollback on failure.
* Add `--dry-run` flag for all destructive operations to preview changes.

## Flags & non-interactive usage

For each command, implement CLI flags to bypass prompts and support automation:

* Global: `--repo`, `--base`, `--temp-root`, `--terminal`, `--editor`, `--yes`, `--verbose`, `--json`, `--no-color`, `--offline`
* `worktree create`: `--branch`, `--linear <url>`, `--python-install`, `--node-install`, `--java-build`, `--no-open`
* `review open`: `--draft/--ready`, `--assign <user1,user2>`, `--labels <…>`, `--no-push`, `--no-checks`
* `merge`: `--squash|--merge|--rebase`, `--delete-remote`, `--keep-worktree`, `--no-ff-check`, `--force`
* `cleanup`: `--older-than <days>`, `--merged-only`, `--dry-run`
* All destructive operations support `--dry-run` to preview changes without executing

## Detection & defaults

* Auto-detect languages from files: `pyproject.toml`/`requirements.txt`, `package.json`, `pom.xml`/`build.gradle*`.
* If multiple languages present, prep Python → Node → Java in that order.
* If neither repo path nor remote URL is provided, prompt the user.
* Default editor = `code` if present, else skip. Default terminal = `Terminal` on macOS.

## Integrations

* **Linear**: Store provided URL in `.agent.json.links.linear`; optionally open in browser during `open` and echo on `list/status`.
* **GitHub**: Prefer `gh` CLI; if absent, print equivalent git/URL steps. Optionally apply Conventional Commit scopes using branch name + Linear key.

## Output requirements

* The tool must produce clear, colorized console output with actionable next steps at the end of each command.
* Provide `--json` mode for `list`/`status` to allow orchestration by other tools.
* Include a `doctor` summary on first run (optional) to verify `git`, `uv`, `nvm`, and terminal automation.

## Testing & portability

* Target macOS primarily (Terminal/iTerm AppleScript), with abstraction layer for Linux/Windows support.
* Make terminal opening optional so CI can run the CLI in headless mode.
* Include unit tests for argument parsing, worktree lifecycle, and `.agent.json` read/write.
* Add integration tests that verify end-to-end workflows.
* Test error handling and recovery scenarios.
* Platform-specific test suites for terminal automation.

## Documentation the AI should generate with the code

* A concise README with:

  * Install instructions (e.g., `pipx install`, `brew`, or single-file usage)
  * Quickstart (init → worktree create → review open → merge → cleanup)
  * Troubleshooting for `nvm`, `uv`, AppleScript permissions
  * Safe rollback notes (restoring base branch, removing stuck worktrees)

---

### Non-negotiables to honor

* Use **git worktrees** for isolation (option 1), not clones.
* Adopt **`uv`** for Python by default; fallback to `venv` only if `uv` missing.
* Persist **`.agent.json`** exactly as specified (extendable fields allowed).
* Do **not** embed secrets - use 1Password CLI for secure credential storage when needed.
* Provide both interactive prompts **and** scriptable flags.
* Implement proper input validation and sanitization for all user inputs.
* Support graceful degradation when optional tools are missing.
* Include comprehensive error handling with helpful error messages.
* Provide standalone installation method to avoid Python environment conflicts.

---

**Deliverables:**
Generate the complete CLI implementation (code + README + tests) per this spec. Ensure the user can install it and run:

```
# One possible happy-path
tool init --repo ~/dev/my-repo --base main
tool worktree create --branch feature/ABC-123-awesome --linear https://linear.app/...
tool review open
tool merge --squash --delete-remote
tool cleanup --merged-only --older-than 7
```

Return the code and docs in your standard output.

