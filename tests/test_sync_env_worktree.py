#!/usr/bin/env python3
"""Tests for sync-env worktree detection when .cproj/.agent.json is missing"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from cproj import CprojCLI, CprojError, _linked_worktree_paths  # noqa: E402


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


class TestSyncEnvWorktreeDetection(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp()).resolve()
        self.repo_dir = self.temp_dir / "proj"
        self.repo_dir.mkdir()
        _git(self.repo_dir, "init")
        _git(self.repo_dir, "config", "user.email", "test@example.com")
        _git(self.repo_dir, "config", "user.name", "Test User")
        (self.repo_dir / "README.md").write_text("# Test")
        _git(self.repo_dir, "add", "README.md")
        _git(self.repo_dir, "commit", "-m", "init")
        _git(self.repo_dir, "branch", "-M", "main")

        # A plain `git worktree add`: no .cproj/.agent.json, like a worktree made
        # by hand or by an older cproj.
        self.worktree_dir = self.temp_dir / "wt"
        _git(self.repo_dir, "worktree", "add", "-b", "feature/x", str(self.worktree_dir))

        (self.repo_dir / "app").mkdir()
        (self.repo_dir / "app" / ".env.local").write_text("KEEP=main\nNEW_KEY=from-main\n")
        (self.worktree_dir / "app").mkdir()
        (self.worktree_dir / "app" / ".env.local").write_text("KEEP=worktree\n")

        self.cli = CprojCLI()
        self.original_cwd = Path.cwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)

    def _args(self, **overrides):
        args = dict(
            keys=None,
            force=True,
            interactive=False,
            pull=False,
            push=False,
            all_worktrees=False,
            dry_run=False,
            backup=False,
            file=None,
        )
        args.update(overrides)
        return SimpleNamespace(**args)

    def test_linked_worktree_paths_from_a_subdirectory(self):
        self.assertEqual(
            _linked_worktree_paths(self.worktree_dir / "app"),
            (self.worktree_dir, self.repo_dir),
        )

    def test_main_checkout_is_not_a_linked_worktree(self):
        self.assertIsNone(_linked_worktree_paths(self.repo_dir))

    def test_pull_without_agent_json_adds_the_requested_key(self):
        os.chdir(self.worktree_dir / "app")

        self.cli.cmd_sync_env(self._args(pull=True, keys="NEW_KEY"))

        env = (self.worktree_dir / "app" / ".env.local").read_text()
        self.assertIn("NEW_KEY=from-main", env)
        # Only the requested key moves; the worktree keeps its own values.
        self.assertIn("KEEP=worktree", env)

    def test_pull_from_main_checkout_is_still_refused(self):
        os.chdir(self.repo_dir)

        with self.assertRaisesRegex(CprojError, "--pull can only be used from a worktree"):
            self.cli.cmd_sync_env(self._args(pull=True, keys="NEW_KEY"))


if __name__ == "__main__":
    unittest.main()
