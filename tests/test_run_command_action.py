#!/usr/bin/env python3
"""
Tests for the run_command custom action.

Covers the contract that the action's environment carries CPROJ_NO_TERMINAL
when cproj is invoked with --no-terminal, so user-defined commands that
launch terminals (osascript, gnome-terminal, etc.) can suppress themselves.
This was a regression: --no-terminal previously gated only cproj's built-in
terminal launcher, not user-defined run_command actions.
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cproj import CprojCLI


@pytest.fixture
def cli():
    return CprojCLI()


@pytest.fixture
def workspace(tmp_path):
    """Worktree + repo dirs and an out.log path that actions can write to."""
    wt = tmp_path / "wt"
    wt.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    out = tmp_path / "out.log"
    return wt, repo, out


class TestRunCommandActionNoTerminalPropagation:
    """`--no-terminal` must propagate to run_command actions as
    CPROJ_NO_TERMINAL=1 so custom terminal launchers can opt out."""

    def test_default_invocation_has_no_cproj_no_terminal(self, cli, workspace):
        wt, repo, out = workspace
        action = {
            "type": "run_command",
            "command": f'echo "[$CPROJ_NO_TERMINAL]" > {out}',
        }
        cli._execute_run_command(action, wt, repo, "feature/x")
        # Empty / unset → action sees an empty string in $CPROJ_NO_TERMINAL
        assert out.read_text().strip() == "[]"

    def test_no_terminal_true_sets_env_var_to_1(self, cli, workspace):
        wt, repo, out = workspace
        action = {
            "type": "run_command",
            "command": f'echo "[$CPROJ_NO_TERMINAL]" > {out}',
        }
        cli._execute_run_command(action, wt, repo, "feature/x", no_terminal=True)
        assert out.read_text().strip() == "[1]"

    def test_no_terminal_false_does_not_set_env_var(self, cli, workspace):
        wt, repo, out = workspace
        action = {
            "type": "run_command",
            "command": f'echo "[$CPROJ_NO_TERMINAL]" > {out}',
        }
        cli._execute_run_command(action, wt, repo, "feature/x", no_terminal=False)
        assert out.read_text().strip() == "[]"

    def test_gate_pattern_skips_terminal_launch(self, cli, workspace, monkeypatch):
        """The exact pattern user projects (e.g. trivalley) use: a shell
        if-block that skips osascript when CPROJ_NO_TERMINAL is set.
        Regressing the env-var propagation would re-open the original bug
        where 'cproj --no-terminal' still launched terminals from custom
        actions."""
        wt, repo, out = workspace
        # Write 'launched' or 'skipped' based on the env var
        action = {
            "type": "run_command",
            "command": f'''
                if [ -n "$CPROJ_NO_TERMINAL" ]; then
                    echo "skipped" > {out}
                else
                    echo "launched" > {out}
                fi
            ''',
        }

        cli._execute_run_command(action, wt, repo, "feature/x", no_terminal=False)
        assert out.read_text().strip() == "launched"

        cli._execute_run_command(action, wt, repo, "feature/x", no_terminal=True)
        assert out.read_text().strip() == "skipped"


class TestCustomActionsPlumbing:
    """_execute_custom_actions must forward no_terminal to run_command,
    not just call it with defaults. This is the threading layer between
    the CLI args and _execute_run_command."""

    def test_no_terminal_flows_through_dispatcher(self, cli, workspace):
        from cproj import ProjectConfig

        wt, repo, out = workspace
        cproj_dir = repo / ".cproj"
        cproj_dir.mkdir()
        (cproj_dir / "project.yaml").write_text(
            f"""
name: testproj
custom_actions:
  - type: run_command
    description: terminal-gated action
    command: |
      if [ -n "$CPROJ_NO_TERMINAL" ]; then
          echo "skipped" > {out}
      else
          echo "launched" > {out}
      fi
"""
        )
        pc = ProjectConfig(repo)

        cli._execute_custom_actions(pc, wt, repo, "feature/x", no_terminal=True)
        assert out.read_text().strip() == "skipped"

        cli._execute_custom_actions(pc, wt, repo, "feature/x", no_terminal=False)
        assert out.read_text().strip() == "launched"
