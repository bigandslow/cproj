# Cloud envs in cproj — design proposal

Status: agreed with the operator 2026-11-18 (decisions in section 9).
The `c2h-cloud` branch in bigandslow/utilities is the working prototype it
replaces.

## 1. Boundary

**cproj owns worktrees wherever they live.** That covers cloud env config, VM
worktree create and remove, the git and transcript transfer, dependency setup,
cleanup, schedules and first-use clone. **c2h owns herdr only**: it opens and
attaches panes, and turns a herdr pane into a cloud session by calling cproj.

cproj runs on both sides. The laptop cproj orchestrates, and the VM cproj (the
same code, installed for the VM user) does the VM work via
`ssh <host> cproj remote <op> --json`. This replaces the bash `remote_helper`.
Running cproj on the VM is what lets dependency setup and cleanup reuse
`project.yaml` there, keeps one implementation, and puts the VM logic under
pytest.

| Prototype code (utilities `herdr/c2h`) | Moves to |
| --- | --- |
| `remote_helper` ops (check, materialize, install-transcript, start, wait-ready, new, ls) | `cproj remote …` (Python) on the VM |
| snapshot via temp index, `git push` over ssh, `stage_transcript`, slug rule | `cproj cloud move` (laptop) |
| batch planner, session registry reading | `cproj sessions` / `cproj cloud move --all` |
| `cloud_name`, config loading | cproj config |
| `herdr_cloud_pane`, `herdr_workspace_of` | stay in c2h (`c2h attach`, `c2h cloud`) |
| `session_info` `\x1f` separator fix | stays in c2h; cherry-pick on its own |
| `refs/c2h/<sid>/*` | renamed `refs/cproj/moves/<sid>/*` |

The prototype's tests come along. The cloud tests port to pytest using the
same "VM is a second `$HOME` behind a fake ssh" fixture. c2h keeps its pane
tests, with cproj stubbed.

Resulting c2h surface:
- `c2h` / `c2h --session`: terminal to herdr, unchanged.
- `c2h open`.
- `c2h cproj-hook`: now also receives the location.
- `c2h attach <host> <tmux-name>`: a herdr pane running `ssh -t host tmux new -A -s name`.
- `c2h cloud [--session id | --all] [--apply]`: calls `cproj cloud move … --json`, then opens a pane per moved session.

c2h keeps its own small session lookup for terminal→herdr moves rather than
depending on cproj. Cloud panes open as tabs in the repo's existing herdr
workspace, labelled as cloud (e.g. `<name> (cloud)`), not as separate
`<name>@vm` workspaces.

## 2. Config

The user-level config (`~/.config/cproj/config.json`) says where clouds are.
It is per person, so chris and skye each have their own:

```json
{
  "cloud_envs": {
    "agent-vm": {
      "host": "chris@100.119.63.101",
      "work_root": "work",
      "env_file": "/run/agent-vm/{user}/env"
    }
  },
  "default_cloud_env": "agent-vm",
  "attach_command": "c2h attach {host} {session}",
  "projects": { "trivalley": { "cloud_env": "agent-vm" } }
}
```

- `work_root` is relative to the VM `$HOME`.
- `attach_command` defaults, when unset, to opening Terminal with the ssh/tmux
  command, or printing it under `--no-terminal`.
- `projects.<name>.cloud_env` is an optional per-user override.
- `max_parallel_setup` (optional, per cloud env and top-level for the laptop)
  caps parallel background setups. Unset by default, meaning no limit.

The project config (`.cproj/project.yaml`, checked in) says whether the
project is cloud-capable:

```yaml
cloud:
  enabled: true
  default_location: ask      # ask | local | cloud
  remote_control: true       # default on: cloud claude starts with --remote-control <name>
  worktree_dir: .claude/worktrees   # under the VM clone; gitignored, inside the trusted dir
  # repo_url: defaults to the local origin URL (used by first-use clone)
```

`custom_actions` gain `where: [local, cloud]`. The default is `[local]`, so
existing actions don't start running on the VM. The trivalley terminal
launcher and the `.vercel` copy, for example, must stay local. trivalley's
`cloud:` block, its cloud-marked actions and its `setup:` steps land in a
separate accounting-automation PR.

## 3. Dependency setup in the background

A new `setup:` section holds slow steps that run detached after create, so the
agent starts at once. `custom_actions` stay synchronous for anything the
session needs before it starts, such as ports and env copy.

```yaml
setup:
  timeout_minutes: 30
  steps:
    - { name: node,   run: pnpm install --frozen-lockfile, where: [local, cloud] }
    - { name: python, run: poetry install --no-interaction, cwd: packages/bankrec-core, where: [local, cloud] }
```

Steps run in order, and the first failure stops the run. Steps that need
secrets stay `where: [local]` for now; VM worktrees get no `.env*` (see
section 7). When there is no
`setup:` section, today's `--python-install` / `--node-install` behaviour
applies unchanged.

**Runner.** `cproj setup run <wt>` does the work:
- **Laptop:** cproj spawns it with `Popen(start_new_session=True)`.
- **VM:** cproj starts it as `systemd-run --user --collect --unit cproj-setup-<name>`, so it survives the ssh session ending and logs to the journal.
- **Concurrency:** uncapped by default on both sides. If `max_parallel_setup` is set, a flock slot pool (`~/.cache/cproj/setup-slots/`) enforces it, so a limit can be added later from measured usage. cproj ships no guessed default; the operator monitors real usage.

**State** lives in the worktree's own git dir (`$(git rev-parse --git-dir)/cproj-setup/`), so it is never tracked or shown as untracked:
- `state.json`: queued, running, ok or failed; the current step; times; exit code.
- `log`: one section per step.

**Who sees what:**
- **Commands:** `cproj setup status [--wait] [--json]`, `cproj setup log [-f]`, `cproj setup retry [--step X]`.
- **Listings:** `cproj status`, `cproj list` and `cproj cloud ls` show a setup column.
- **The agent:** `cproj setup hook` prints one line while setup is pending or has failed ("deps installing: python 2/2; run `cproj setup wait` before tests/builds"; or "deps FAILED at node: <log path>"), and nothing once it is ok. It is wired in as a Claude Code `SessionStart` + `UserPromptSubmit` hook in trivalley's checked-in `.claude/settings.json` (same accounting-automation PR).
- **The user:** on failure, a macOS notification locally. In herdr, a `herdr notification` via c2h when the pane is in herdr.

## 4. Local vs cloud selection

- **Choosing the location in `cproj w create`:**
  - **Flags:** `--where local|cloud`, with `--cloud` / `--local` as aliases.
  - **No flag:** for a cloud-enabled project, `default_location` decides. If it is `ask` and the terminal is interactive, cproj prompts `Create <branch> [l]ocal or [c]loud? [c]`. Non-interactive runs fall back to `local`.
- **Cloud create:** the laptop runs `ssh host cproj remote create --json …`. That runs the normal create pipeline on the VM: worktree, `custom_actions` with `where: cloud`, background setup, then claude in tmux. It returns the tmux name, and the laptop runs `attach_command` unless `--no-terminal` is set.
- **Location-aware commands:**
  - `cproj list` / `cproj status` add cloud rows with one ssh call. They time out cleanly and say "VM unreachable".
  - `cproj open <name>` attaches to a cloud worktree.
  - `cproj cloud attach|ls|move [--session id | --all] [--apply]`.

## 5. Cleanup and weekly automation

**Additions to `cproj cleanup`, on both sides:**
- **Live guard:** never remove a worktree that has a live claude process under it (from the session registry) or an attached tmux session.
- **Moved worktrees:**
  - At move time cproj writes `$(git-dir)/cproj-moved.json` (session, VM, snapshot tree, time).
  - Cleanup removes a moved local worktree only if its tree still equals the snapshot tree, the VM worktree still exists or the branch has merged, and no session is live in it.
  - Otherwise it reports "moved, but edited locally since — kept".
- **VM refs and tmux:**
  - Prune `refs/cproj/moves/<sid>/*` once their worktree is gone, or after 14 days.
  - Kill a detached tmux session whose worktree was removed and that has no live claude.
- **`--auto` (the unattended policy):** removes only merged-and-clean or moved-and-unchanged worktrees. Stale unmerged worktrees are reported, never removed. Never dirty, never live, never `--force`. Each skip is logged with its reason. `--all-projects` iterates over repos found from the worktrees under `temp_root`, and over `work_root` on the VM.

**Weekly job.** `cproj schedule install [--remote]` sets it up, and `cproj schedule status|uninstall` manage it.

| | Laptop (launchd) | VM (systemd user timer) |
| --- | --- | --- |
| Unit | `~/Library/LaunchAgents/io.bigandslow.cproj-cleanup.plist` | `~/.config/systemd/user/cproj-cleanup.{service,timer}` |
| Schedule | `StartCalendarInterval` Sun 03:00 (a run missed during sleep fires on wake) | `OnCalendar=Sun 03:00`, `Persistent=true` (linger is already on) |
| Runs | `cproj cleanup --auto --all-projects` | the same, `Type=oneshot` |
| Log | `~/Library/Logs/cproj/cleanup.log` | `journalctl --user -u cproj-cleanup` |
| Installed by | `cproj schedule install` | `cproj schedule install --remote` (runs it on the VM over ssh) |

## 6. First-use clone (deferred phase)

When a cloud create or move targets a repo not under `work_root`, cproj runs
`cproj remote ensure-repo --name <repo> --url <origin url>`:
- It loads the VM env file and clones with the existing `gh` credential helper.
- It refuses non-https or unknown hosts.
- It reports a scope error clearly: the PAT is fine-grained and covers only
  the repos it was granted. Each new repo is added to the PAT one at a time,
  as an operator decision; cproj never asks for broader access.

The clone brings its own `.cproj/project.yaml`. The first claude in that repo
gets one trust prompt.

## 7. Future phases needing a security design first

- **Secrets in a VM worktree.** Probably `cproj sync-env` extended to cloud
  envs. Putting dev/staging secrets on the VM changes the VM credential model
  (plan invariant I2), so it needs its own security design before any code.
  Until then, secret-dependent setup is local only.
- **Reaching an app running in a VM worktree,** the way localhost:3xxx works
  today. This conflicts with plan invariant I7: session processes must not
  listen, even on loopback, because loopback is shared between Unix users.
  It needs its own design, for example per-user network namespaces or a
  socket proxy. Plain `ssh -L` port forwarding is not assumed acceptable.

## 8. Phases

0. Park `c2h-cloud` unmerged as reference. Cherry-pick only the `session_info` separator fix to utilities main.
1. **cproj cloud core:**
   - config schema;
   - `cproj cloud bootstrap`, which installs or updates cproj on the VM like `install.sh`, with a version handshake on every remote call;
   - `cproj remote` ops;
   - `w create --where` with the prompt;
   - `cloud ls|attach`, `attach_command`, and `where:` on `custom_actions`;
   - c2h `attach`.

   As built:
   - Bootstrap copies `cproj.py` plus a wrapper that runs the VM's own python3 (PyYAML is already there), not `install.sh`'s venv and pip, so nothing is downloaded on the VM. `claude_review_agents.py` isn't copied, so `cproj review agents` doesn't work on the VM.
   - `attach_command` (`c2h attach {host} {session} --repo {repo_path} --label {label}`) replaces the location-aware `cproj-hook`. The hook is a `run_command` action, and those default to `where: [local]`, so it already runs only for local creates and needs no change.
   - The cloud rows in `cproj list`/`status` and `cproj open <cloud name>` move to phase 2.
2. **Move:** `cproj cloud move [--session|--all]` (the prototype ported), `c2h cloud` delegating to it, cloud rows in `cproj list`/`status`, and `cproj open` for cloud worktrees.
3. **Background setup** (local + VM): `setup:`, the runner, slots, status/wait/log/retry, the hook and notifications.
4. **Cleanup:** the live guard, moved-worktree handling, VM refs and tmux, `--auto`, and `schedule install` for launchd and systemd.
5. **(Deferred)** first-use clone.
6. **(Future, security design first)** secrets in VM worktrees; reaching VM apps (section 7).

Each phase is one cproj PR (plus a utilities commit where c2h changes) with
tests. Phases 1–2 restore what the prototype does today; phases 3–4 are new.

## 9. Decisions (operator, 2026-11-18)

1. `cproj cloud bootstrap` installs cproj into the VM user's home over ssh.
2. cproj owns session moves; c2h only opens panes and keeps its own small session lookup for terminal→herdr.
3. `custom_actions` default to `where: [local]`; cloud steps go in a separate trivalley `.cproj/project.yaml` PR.
4. The setup-status hook goes in trivalley's checked-in `.claude/settings.json`.
5. Secret-dependent setup stays local only; secrets on the VM and VM app access are future phases needing security designs (I2, I7).
6. Setup concurrency is uncapped by default, locally and on the VM. `max_parallel_setup` stays an optional setting, unset by default, for a limit based on measured data later.
7. `--auto` only reports stale unmerged worktrees; never removes them.
8. Weekly, Sunday 03:00, on both sides.
9. First-use clone: widen the fine-grained PAT one repo at a time, each an operator decision.
10. herdr: cloud panes are tabs under the repo's existing herdr workspace, labelled as cloud.
11. Remote Control is on by default for cloud sessions.
12. Park the `c2h-cloud` prototype; cherry-pick only the `session_info` separator fix.
