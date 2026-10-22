#!/usr/bin/env python3
"""Tests for resuming and recreating interrupted worktree creates"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from cproj import (  # noqa: E402
    AgentJson,
    CprojCLI,
    CprojError,
    EnvironmentSetup,
    PortRegistry,
    find_env_files,
)


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


class TestWorktreeResume(unittest.TestCase):
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

        (self.repo_dir / ".cproj").mkdir()
        (self.repo_dir / ".cproj" / "project.yaml").write_text(
            "name: proj\n"
            "features:\n"
            "  port_allocation: true\n"
            "custom_actions:\n"
            "  - type: allocate_port\n"
        )

        self.temp_root = self.temp_dir / "worktrees"
        self.home = self.temp_dir / "home"
        self.home.mkdir()
        home_patch = patch.object(Path, "home", return_value=self.home)
        home_patch.start()
        self.addCleanup(home_patch.stop)

        self.cli = CprojCLI()
        self.cli._skip_prompts = True

        self.original_cwd = Path.cwd()
        os.chdir(self.repo_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)

    def _args(self, **overrides):
        args = dict(
            repo=str(self.repo_dir),
            branch="feature/x",
            base="main",
            temp_root=str(self.temp_root),
            linear=None,
            python_install=False,
            shared_venv=False,
            node_install=False,
            java_build=False,
            copy_env=False,
            open_editor=False,
            no_terminal=True,
            terminal=None,
            editor=None,
            setup_claude=False,
            no_claude=True,
            recreate=False,
        )
        args.update(overrides)
        return SimpleNamespace(**args)

    def _branch_worktrees(self):
        out = _git(self.repo_dir, "worktree", "list", "--porcelain")
        paths, current = [], None
        for line in out.splitlines():
            if line.startswith("worktree "):
                current = Path(line[len("worktree ") :])
            elif line == "branch refs/heads/feature/x":
                paths.append(current)
        return paths

    def _interrupted_create(self):
        with patch.object(EnvironmentSetup, "setup_node", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.cli.cmd_worktree_create(self._args())
        (path,) = self._branch_worktrees()
        return path

    def test_interrupted_create_leaves_incomplete_marker(self):
        path = self._interrupted_create()
        agent = AgentJson(path)
        self.assertEqual(agent.data["workspace"]["branch"], "feature/x")
        self.assertFalse(agent.is_setup_complete())

    def test_rerun_resumes_same_worktree_and_reuses_port(self):
        path = self._interrupted_create()
        # Simulate a port slot taken before the interruption
        PortRegistry().allocate("proj", path, 7)

        self.cli.cmd_worktree_create(self._args())

        self.assertEqual(self._branch_worktrees(), [path])
        self.assertTrue(AgentJson(path).is_setup_complete())
        self.assertEqual(PortRegistry().list_allocations("proj"), {str(path): 7})

    def test_rerun_after_complete_is_noop(self):
        self.cli.cmd_worktree_create(self._args())
        (path,) = self._branch_worktrees()
        completed_at = AgentJson(path).data["workspace"]["setup_completed_at"]

        self.cli.cmd_worktree_create(self._args())

        self.assertEqual(self._branch_worktrees(), [path])
        self.assertEqual(AgentJson(path).data["workspace"]["setup_completed_at"], completed_at)

    def test_recreate_replaces_worktree_and_keeps_branch_commits(self):
        path = self._interrupted_create()
        PortRegistry().allocate("proj", path, 7)
        (path / "work.txt").write_text("work")
        _git(path, "add", "work.txt")
        _git(path, "commit", "-m", "work")
        (path / ".cproj" / "stale").write_text("from interrupted run")

        self.cli.cmd_worktree_create(self._args(recreate=True))

        (new_path,) = self._branch_worktrees()
        self.assertFalse((new_path / ".cproj" / "stale").exists())
        self.assertTrue((new_path / "work.txt").exists())
        self.assertTrue(AgentJson(new_path).is_setup_complete())
        self.assertEqual(PortRegistry().list_allocations("proj"), {str(new_path): 0})

    def test_recreate_refuses_dirty_worktree(self):
        path = self._interrupted_create()
        (path / "README.md").write_text("edited")

        with self.assertRaisesRegex(CprojError, "uncommitted changes"):
            self.cli.cmd_worktree_create(self._args(recreate=True))
        self.assertTrue(path.exists())

    def test_non_cproj_worktree_errors_with_path(self):
        other = self.temp_dir / "manual"
        _git(self.repo_dir, "worktree", "add", "-b", "feature/x", str(other))

        with self.assertRaisesRegex(CprojError, f"checked out in {other}"):
            self.cli.cmd_worktree_create(self._args())
        with self.assertRaisesRegex(CprojError, "not a cproj worktree"):
            self.cli.cmd_worktree_create(self._args(recreate=True))
        self.assertTrue(other.exists())

    def test_branch_checked_out_in_main_repo_errors(self):
        _git(self.repo_dir, "checkout", "-b", "feature/x")

        with self.assertRaisesRegex(CprojError, "checked out in the main repo"):
            self.cli.cmd_worktree_create(self._args(base="main", recreate=True))
        self.assertTrue(self.repo_dir.exists())


class TestFindEnvFiles(unittest.TestCase):
    def test_skips_hidden_and_dependency_dirs(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        for rel in [
            ".env",
            "app/.env.local",
            "app/.envrc",
            ".claude/worktrees/x/.env",
            ".devcontainer/.env",
            "node_modules/pkg/.env",
            "venv/.env",
        ]:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text("A=1")

        self.assertEqual(set(find_env_files(root)), {root / ".env", root / "app" / ".env.local"})


if __name__ == "__main__":
    unittest.main()
