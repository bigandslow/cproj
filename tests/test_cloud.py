#!/usr/bin/env python3
"""Tests for cloud envs: `cproj w create --where cloud`, `cproj cloud ...` and
the VM-side `cproj remote ...` ops.

The "VM" is a second HOME on this machine. A fake `ssh` on PATH runs the remote
command there with bash, so the remote cproj (installed into that HOME by a
real `cproj cloud bootstrap`) runs this code end to end. On the VM side, `tmux`
and `claude` are fakes: tmux runs the session command once (SHELL=true, so the
trailing login shell exits at once) and claude records its argv.
"""

import getpass
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cproj  # noqa: E402
from cproj import (  # noqa: E402
    CloudEnv,
    CprojCLI,
    CprojError,
    ProjectConfig,
    action_applies,
    cloud_session_name,
    normalize_git_url,
)

SECRET = "secret-gh-value"

FAKE_SSH = """#!/bin/bash
line="ssh"; for a in "$@"; do line="$line | $a"; done
echo "$line" >>"$STUB_LOG"
while [ $# -gt 0 ]; do
  case "$1" in -o|-p|-i|-l|-F) shift 2 ;; -*) shift ;; *) break ;; esac
done
shift   # the host
cd "$VM_HOME" && HOME="$VM_HOME" PATH="$VM_BIN:$PY_DIR:/usr/bin:/bin" exec bash -c "$*"
"""

FAKE_TMUX = """#!/bin/bash
line="vm-tmux"; for a in "$@"; do line="$line | $a"; done
echo "$line" >>"$STUB_LOG"
st="$HOME/.fake-tmux"; mkdir -p "$st"
case "$1" in
  has-session) [ -e "$st/${3#=}" ] ;;
  ls)
    for f in "$st"/*; do
      [ -e "$f" ] && printf '%s\\t0\\t%s\\n' "${f##*/}" "$(cat "$f")"
    done
    exit 0 ;;
  new-session)
    shift; name="" dir="" cmd=""
    while [ $# -gt 0 ]; do
      case "$1" in
        -d) shift ;; -s) name="$2"; shift 2 ;; -c) dir="$2"; shift 2 ;; *) cmd="$1"; shift ;;
      esac
    done
    echo "$dir" >"$st/$name"
    [ -n "$cmd" ] && (cd "$dir" && SHELL=/usr/bin/true bash -c "$cmd") ;;
esac
"""

FAKE_CLAUDE = """#!/bin/bash
{
  echo "cwd=$(pwd -P)"; echo "gh_token_set=${GH_TOKEN:+yes}"
  for a in "$@"; do echo "arg=$a"; done
} >"$HOME/claude-argv"
"""

PROJECT_YAML = """name: acct
base_branch: main
cloud:
  enabled: true
  default_location: ask
custom_actions:
  - type: run_command
    description: local-only marker
    command: touch {worktree_path}/ran-local
  - type: run_command
    description: cloud marker
    where: [cloud]
    command: touch {worktree_path}/ran-cloud
"""


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _write_exec(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


class Cloud:
    """Paths and helpers for one fake laptop + VM."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.home = tmp / "home"
        self.vm_home = tmp / "vmhome"
        self.bin = tmp / "bin"
        self.vm_bin = tmp / "vmbin"
        self.log = tmp / "calls.log"
        self.attach_log = tmp / "attach.log"
        self.origin = tmp / "remotes" / "acct.git"
        self.repo = tmp / "local" / "acct"
        self.vm_repo = self.vm_home / "work" / "acct"
        for d in (self.home, self.vm_home / "work", self.bin, self.vm_bin, self.repo.parent):
            d.mkdir(parents=True)
        self.log.touch()

    @property
    def calls(self) -> str:
        return self.log.read_text()

    def vm_worktree(self, name: str) -> Path:
        return self.vm_repo / ".claude" / "worktrees" / name

    def claude_argv(self) -> list:
        return (self.vm_home / "claude-argv").read_text().splitlines()


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    c = Cloud(tmp_path.resolve())
    _write_exec(c.bin / "ssh", FAKE_SSH)
    _write_exec(c.vm_bin / "tmux", FAKE_TMUX)
    _write_exec(c.vm_bin / "claude", FAKE_CLAUDE)
    _write_exec(
        c.bin / "attach-recorder",
        f'#!/bin/bash\nfor a in "$@"; do echo "$a"; done > {c.attach_log}\n',
    )
    (c.vm_home / f"env-{getpass.getuser()}").write_text(f"GH_TOKEN={SECRET}\n")

    for k, v in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "STUB_LOG": str(c.log),
        "VM_HOME": str(c.vm_home),
        "VM_BIN": str(c.vm_bin),
        "PY_DIR": str(Path(sys.executable).parent),
        "PATH": f"{c.bin}:{os.environ['PATH']}",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(CloudEnv, "_warned_sha", False)

    # origin (bare) -> laptop clone; the VM has its own clone.
    subprocess.run(["git", "init", "-q", "--bare", str(c.origin)], check=True)
    _git(c.origin, "symbolic-ref", "HEAD", "refs/heads/main")
    subprocess.run(["git", "init", "-q", str(c.repo)], check=True)
    _git(c.repo, "symbolic-ref", "HEAD", "refs/heads/main")
    (c.repo / ".cproj").mkdir()
    (c.repo / ".cproj" / "project.yaml").write_text(PROJECT_YAML)
    (c.repo / ".gitignore").write_text(".claude/\n")
    _git(c.repo, "add", "-A")
    _git(c.repo, "commit", "-q", "-m", "init")
    _git(c.repo, "remote", "add", "origin", str(c.origin))
    _git(c.repo, "push", "-q", "origin", "main")
    subprocess.run(["git", "clone", "-q", str(c.origin), str(c.vm_repo)], check=True)

    home_patch = patch.object(Path, "home", return_value=c.home)
    home_patch.start()
    c.cli = CprojCLI()
    c.cli.config.set(
        "cloud_envs",
        {"vm": {"host": "chris@vm", "env_file": str(c.vm_home / "env-{user}")}},
    )
    c.cli.config.set(
        "attach_command",
        f"{c.bin / 'attach-recorder'} {{host}} {{session}} {{repo_path}} {{label}}",
    )
    yield c
    home_patch.stop()


@pytest.fixture
def booted(cloud):
    assert run_cli(cloud, "cloud", "bootstrap") == 0
    assert (cloud.vm_home / ".local" / "bin" / "cproj").exists()
    cloud.log.write_text("")
    return cloud


def run_cli(cloud, *argv):
    """Run cproj in-process (fresh CLI, same patched home); return its exit code."""
    cloud.cli = CprojCLI()
    try:
        cloud.cli.run(list(argv))
    except SystemExit as e:
        return e.code
    return 0


def create(cloud, *extra):
    return run_cli(
        cloud, "--repo", str(cloud.repo), "--yes", "w", "create", "--branch", "feature/x", *extra
    )


# --- create --------------------------------------------------------------


def test_cloud_create_makes_the_worktree_and_starts_claude_on_the_vm(booted, capsys):
    assert create(booted, "--cloud") == 0
    wt = booted.vm_worktree("x")
    assert _git(wt, "symbolic-ref", "--short", "HEAD") == "feature/x"
    assert _git(wt, "rev-parse", "HEAD") == _git(booted.origin, "rev-parse", "main")
    # Branched from the base without tracking it, so a push can't land on main.
    tracking = subprocess.run(
        ["git", "-C", str(wt), "config", "branch.feature/x.merge"], capture_output=True
    )
    assert tracking.returncode != 0
    assert booted.claude_argv() == [
        f"cwd={wt}",
        "gh_token_set=yes",
        "arg=--remote-control",
        "arg=x",
    ]
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err + booted.calls


def test_cloud_create_runs_only_cloud_actions_on_the_vm_and_nothing_locally(booted):
    assert create(booted, "--where", "cloud") == 0
    wt = booted.vm_worktree("x")
    assert (wt / "ran-cloud").exists()
    assert not (wt / "ran-local").exists()
    assert _git(booted.repo, "branch", "--list", "feature/x") == ""
    assert _git(booted.repo, "worktree", "list", "--porcelain").count("worktree ") == 1


def test_cloud_create_hands_the_session_to_attach_command(booted):
    assert create(booted, "--cloud") == 0
    assert booted.attach_log.read_text().splitlines() == [
        "chris@vm",
        "x",
        str(booted.repo),
        "x",
    ]


def test_cloud_create_no_rc_and_no_terminal(booted, capsys):
    assert create(booted, "--cloud", "--no-rc", "--no-terminal") == 0
    assert "arg=--remote-control" not in booted.claude_argv()
    assert not booted.attach_log.exists()
    assert "ssh -t chris@vm tmux new -A -s x" in capsys.readouterr().out


def test_cloud_create_tracks_a_branch_that_exists_on_origin(booted):
    _git(booted.repo, "push", "-q", "origin", "main:refs/heads/feature/x")
    assert create(booted, "--cloud") == 0
    wt = booted.vm_worktree("x")
    assert _git(wt, "rev-parse", "--abbrev-ref", "@{upstream}") == "origin/feature/x"


def test_cloud_create_refuses_a_branch_already_on_the_vm(booted, capsys):
    _git(booted.vm_repo, "branch", "feature/x")
    assert create(booted, "--cloud") == 1
    assert "branch feature/x already exists" in capsys.readouterr().err
    assert "new-session" not in booted.calls
    assert not booted.vm_worktree("x").exists()


def test_cloud_create_refuses_a_vm_clone_of_a_different_origin(booted, capsys):
    _git(booted.vm_repo, "remote", "set-url", "origin", "https://github.com/someone/acct.git")
    assert create(booted, "--cloud") == 1
    assert "origin is https://github.com/someone/acct.git" in capsys.readouterr().err
    assert not booted.vm_worktree("x").exists()


# --- version handshake -----------------------------------------------------


def test_not_installed_on_the_vm_says_to_bootstrap(cloud, capsys):
    assert create(cloud, "--cloud") == 1
    err = capsys.readouterr().err
    assert "cproj is not installed on chris@vm; run: cproj cloud bootstrap" in err


def test_protocol_mismatch_is_an_error(booted, capsys, monkeypatch):
    monkeypatch.setattr(cproj, "CLOUD_PROTOCOL", 99)
    assert create(booted, "--cloud") == 1
    err = capsys.readouterr().err
    assert "protocol mismatch" in err and "cproj cloud bootstrap" in err
    assert not booted.vm_worktree("x").exists()


def test_a_different_cproj_on_the_vm_only_warns(booted, capsys):
    installed = booted.vm_home / ".local" / "share" / "cproj" / "cproj.py"
    installed.write_text(installed.read_text() + "\n# drift\n")
    assert run_cli(booted, "cloud", "ls") == 0
    assert "differs from this one" in capsys.readouterr().err


def test_bootstrap_dry_run_prints_commands_and_runs_nothing(cloud, capsys):
    assert run_cli(cloud, "cloud", "bootstrap", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "ssh -o BatchMode=yes -o ConnectTimeout=15 chris@vm" in out
    assert ".local/bin/cproj remote version --protocol 1" in out
    assert cloud.calls == ""


# --- ls / attach ----------------------------------------------------------


def test_cloud_ls_lists_sessions_and_worktrees(booted, capsys):
    assert create(booted, "--cloud", "--no-terminal") == 0
    capsys.readouterr()
    assert run_cli(booted, "cloud", "ls") == 0
    out = capsys.readouterr().out
    assert "  x " in out and "feature/x" in out


def test_cloud_attach(booted, capsys):
    assert create(booted, "--cloud", "--no-terminal") == 0
    assert run_cli(booted, "cloud", "attach", "nope") == 1
    assert "no tmux session 'nope'" in capsys.readouterr().err
    assert run_cli(booted, "cloud", "attach", "x") == 0
    assert booted.attach_log.read_text().splitlines()[:2] == ["chris@vm", "x"]


# --- location choice ------------------------------------------------------


def _loc_args(where=None):
    return SimpleNamespace(where=where)


def _project(tmp_path, cloud_block):
    (tmp_path / ".cproj").mkdir()
    text = "name: p\n" + (f"cloud: {cloud_block}\n" if cloud_block else "")
    (tmp_path / ".cproj" / "project.yaml").write_text(text)
    return ProjectConfig(tmp_path)


def test_location_flag_wins_over_default(tmp_path):
    pc = _project(tmp_path, "{enabled: true, default_location: cloud}")
    assert CprojCLI()._resolve_location(_loc_args("local"), pc, "b") == "local"
    assert CprojCLI()._resolve_location(_loc_args(), pc, "b") == "cloud"


def test_location_cloud_needs_a_cloud_enabled_project(tmp_path):
    pc = _project(tmp_path, None)
    with pytest.raises(CprojError, match="isn't set up for cloud"):
        CprojCLI()._resolve_location(_loc_args("cloud"), pc, "b")
    assert CprojCLI()._resolve_location(_loc_args(), pc, "b") == "local"


def test_location_ask_falls_back_to_local_without_a_terminal(tmp_path):
    cli = CprojCLI()
    cli._skip_prompts = True
    pc = _project(tmp_path, "{enabled: true}")
    assert cli._resolve_location(_loc_args(), pc, "b") == "local"


def test_location_ask_prompts_when_interactive(tmp_path):
    cli = CprojCLI()
    pc = _project(tmp_path, "{enabled: true}")
    with patch.object(CprojCLI, "_is_interactive", return_value=True):
        with patch("builtins.input", side_effect=["?", "l"]):
            assert cli._resolve_location(_loc_args(), pc, "b") == "local"
        with patch("builtins.input", return_value=""):
            assert cli._resolve_location(_loc_args(), pc, "b") == "cloud"


# --- where: and helpers -----------------------------------------------------


def test_local_actions_skip_cloud_only_ones(tmp_path):
    pc = _project(tmp_path, None)
    pc._config["custom_actions"] = [
        {"type": "run_command", "command": f"touch {tmp_path}/local"},
        {"type": "run_command", "where": ["cloud"], "command": f"touch {tmp_path}/cloud"},
        {"type": "run_command", "where": "local", "command": f"touch {tmp_path}/local2"},
    ]
    CprojCLI()._execute_custom_actions(pc, tmp_path, tmp_path, "b")
    assert (tmp_path / "local").exists() and (tmp_path / "local2").exists()
    assert not (tmp_path / "cloud").exists()


def test_post_sync_hooks_skip_cloud_only_actions(tmp_path):
    # ProjectConfig doesn't load post_sync_actions today (a separate bug), so
    # inject them.
    actions = [
        {"type": "run_command", "command": f"touch {tmp_path}/local"},
        {"type": "run_command", "where": ["cloud"], "command": f"touch {tmp_path}/cloud"},
    ]
    with patch.object(ProjectConfig, "_load_config", return_value={"post_sync_actions": actions}):
        CprojCLI()._run_post_sync_hooks(tmp_path, tmp_path)
    assert (tmp_path / "local").exists()
    assert not (tmp_path / "cloud").exists()


def test_action_applies_defaults_to_local_only():
    assert action_applies({}, "local") and not action_applies({}, "cloud")
    assert action_applies({"where": ["local", "cloud"]}, "cloud")
    assert action_applies({"where": "cloud"}, "cloud")


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/Process-Tangent/accounting-automation.git",
        "git@github.com:process-tangent/accounting-automation.git",
        "ssh://git@github.com/process-tangent/accounting-automation",
    ],
)
def test_normalize_git_url(url):
    assert normalize_git_url(url) == "github.com/process-tangent/accounting-automation"


def test_cloud_session_name():
    assert cloud_session_name("it's a demo") == "it-s-a-demo"
    with pytest.raises(CprojError):
        cloud_session_name("///")
