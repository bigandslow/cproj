#!/usr/bin/env python3
"""
Comprehensive tests for cleanup functionality

Tests all aspects of the cmd_cleanup method including:
- Interactive mode
- Age-based criteria (older than, newer than)
- Merged worktree detection
- Dry run mode
- Force removal of dirty worktrees
- Error handling
"""

import tempfile
import subprocess
import pytest
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

# Import the classes we need to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cproj import CprojCLI, Config, GitWorktree, AgentJson


class TestCleanupFunctionality:
    """Comprehensive tests for cleanup functionality"""

    @pytest.fixture
    def real_git_repo(self):
        """Create a real git repository for cleanup testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir) / 'test_repo'
            repo_dir.mkdir()

            # Initialize git repo
            subprocess.run(['git', 'init'], cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.email', 'test@example.com'],
                          cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.name', 'Test User'],
                          cwd=repo_dir, check=True, capture_output=True)

            # Create initial commit
            (repo_dir / 'README.md').write_text('# Test Cleanup Repository')
            subprocess.run(['git', 'add', 'README.md'], cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(['git', 'commit', '-m', 'Initial commit'],
                          cwd=repo_dir, check=True, capture_output=True)

            # Create main branch
            subprocess.run(['git', 'branch', '-m', 'main'], cwd=repo_dir, check=True, capture_output=True)

            yield repo_dir

    @pytest.fixture
    def cli_with_worktrees(self, real_git_repo):
        """Set up CLI with multiple test worktrees"""
        config_dir = real_git_repo.parent / '.config' / 'cproj'
        config_dir.mkdir(parents=True)

        cli = CprojCLI()
        config = Config(config_dir / 'config.json')
        config.set('repo_path', str(real_git_repo))
        cli.config = config

        git = GitWorktree(real_git_repo)

        # Create multiple test worktrees with different ages
        worktrees = []

        # Recent worktree (1 day old)
        recent_path = real_git_repo.parent / 'recent_worktree'
        git.create_worktree(recent_path, 'feature/recent', 'main')
        self._create_agent_json(recent_path, days_ago=1)
        worktrees.append(recent_path)

        # Old worktree (45 days old)
        old_path = real_git_repo.parent / 'old_worktree'
        git.create_worktree(old_path, 'feature/old', 'main')
        self._create_agent_json(old_path, days_ago=45)
        worktrees.append(old_path)

        # Merged worktree (30 days old, marked as merged)
        merged_path = real_git_repo.parent / 'merged_worktree'
        git.create_worktree(merged_path, 'feature/merged', 'main')
        self._create_agent_json(merged_path, days_ago=30, merged=True)
        worktrees.append(merged_path)

        return cli, config, real_git_repo, worktrees

    def _create_agent_json(self, worktree_path: Path, days_ago: int, merged: bool = False):
        """Create .agent.json file with specified age and merge status"""
        cproj_dir = worktree_path / '.cproj'
        cproj_dir.mkdir(exist_ok=True)

        created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)

        agent_data = {
            "project": {"name": "test-project"},
            "workspace": {
                "branch": worktree_path.name.replace('_', '/'),
                "base": "main",
                "created_at": created_at.isoformat(),
            },
            "links": {"linear": None, "pr": None}
        }

        # Add closed_at field if marked as merged
        if merged:
            agent_data["workspace"]["closed_at"] = created_at.isoformat()

        agent_json_path = cproj_dir / '.agent.json'
        with agent_json_path.open('w') as f:
            json.dump(agent_data, f, indent=2)

    def test_cleanup_no_worktrees(self, real_git_repo):
        """Test cleanup when no worktrees exist"""
        config_dir = real_git_repo.parent / '.config' / 'cproj'
        config_dir.mkdir(parents=True)

        cli = CprojCLI()
        config = Config(config_dir / 'config.json')
        config.set('repo_path', str(real_git_repo))
        cli.config = config

        # Test cleanup with no worktrees
        from types import SimpleNamespace
        args = SimpleNamespace(
            older_than=30,
            newer_than=None,
            merged_only=False,
            force=False,
            dry_run=False,
            yes=True
        )

        # Should not raise any errors
        cli.cmd_cleanup(args)

    def test_cleanup_older_than_criteria(self, cli_with_worktrees):
        """Test cleanup with older_than criteria"""
        cli, config, repo_dir, worktrees = cli_with_worktrees
        recent_path, old_path, merged_path = worktrees

        from types import SimpleNamespace
        args = SimpleNamespace(
            older_than=30,  # Remove worktrees older than 30 days
            newer_than=None,
            merged_only=False,
            force=True,
            dry_run=False,
            yes=True
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)
            cli.cmd_cleanup(args)

            # Recent worktree (1 day) should still exist
            assert recent_path.exists()

            # Old worktree (45 days) should be removed
            assert not old_path.exists()

            # Merged worktree (30 days) should still exist (exactly at threshold)
            assert merged_path.exists()

        finally:
            os.chdir(original_cwd)

    def test_cleanup_newer_than_criteria(self, cli_with_worktrees):
        """Test cleanup with newer_than criteria"""
        cli, config, repo_dir, worktrees = cli_with_worktrees
        recent_path, old_path, merged_path = worktrees

        from types import SimpleNamespace
        args = SimpleNamespace(
            older_than=None,
            newer_than=7,  # Remove worktrees newer than 7 days
            merged_only=False,
            force=True,
            dry_run=False,
            yes=True
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)
            cli.cmd_cleanup(args)

            # Recent worktree (1 day) should be removed
            assert not recent_path.exists()

            # Old worktree (45 days) should still exist
            assert old_path.exists()

            # Merged worktree (30 days) should still exist
            assert merged_path.exists()

        finally:
            os.chdir(original_cwd)

    def test_cleanup_merged_only_criteria(self, cli_with_worktrees):
        """Test cleanup with merged_only criteria"""
        cli, config, repo_dir, worktrees = cli_with_worktrees
        recent_path, old_path, merged_path = worktrees

        from types import SimpleNamespace
        args = SimpleNamespace(
            older_than=None,
            newer_than=None,
            merged_only=True,  # Remove only merged worktrees
            force=True,
            dry_run=False,
            yes=True
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)
            cli.cmd_cleanup(args)

            # Recent and old worktrees should still exist (not merged)
            assert recent_path.exists()
            assert old_path.exists()

            # Merged worktree should be removed
            assert not merged_path.exists()

        finally:
            os.chdir(original_cwd)

    def test_cleanup_dry_run(self, cli_with_worktrees):
        """Test cleanup dry run mode"""
        cli, config, repo_dir, worktrees = cli_with_worktrees
        recent_path, old_path, merged_path = worktrees

        from types import SimpleNamespace
        args = SimpleNamespace(
            older_than=1,  # Would remove all worktrees
            newer_than=None,
            merged_only=False,
            force=True,
            dry_run=True,  # Dry run mode
            yes=True
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)
            cli.cmd_cleanup(args)

            # All worktrees should still exist in dry run
            assert recent_path.exists()
            assert old_path.exists()
            assert merged_path.exists()

        finally:
            os.chdir(original_cwd)

    def test_cleanup_force_dirty_worktree(self, cli_with_worktrees):
        """Test cleanup with force removal of dirty worktree"""
        cli, config, repo_dir, worktrees = cli_with_worktrees
        recent_path, old_path, merged_path = worktrees

        # Make one worktree dirty
        dirty_file = recent_path / 'dirty_file.txt'
        dirty_file.write_text('uncommitted changes')

        from types import SimpleNamespace
        args = SimpleNamespace(
            older_than=None,
            newer_than=7,  # Remove recent worktree (1 day old)
            merged_only=False,
            force=True,  # Force removal even if dirty
            dry_run=False,
            yes=True
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)
            cli.cmd_cleanup(args)

            # Recent worktree should be removed even though it was dirty
            assert not recent_path.exists()

        finally:
            os.chdir(original_cwd)

    @patch('builtins.input', return_value='n')
    def test_cleanup_refuse_dirty_without_force(self, mock_input, cli_with_worktrees):
        """Test cleanup refuses to remove dirty worktree without force"""
        cli, config, repo_dir, worktrees = cli_with_worktrees
        recent_path, old_path, merged_path = worktrees

        # Make one worktree dirty
        dirty_file = recent_path / 'dirty_file.txt'
        dirty_file.write_text('uncommitted changes')

        from types import SimpleNamespace
        args = SimpleNamespace(
            older_than=None,
            newer_than=7,  # Would remove recent worktree (1 day old)
            merged_only=False,
            force=False,  # Don't force removal
            dry_run=False,
            yes=True
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            # Mock interactive mode to return True
            with patch.object(cli, '_is_interactive', return_value=True):
                cli.cmd_cleanup(args)

            # Recent worktree should still exist (removal refused)
            assert recent_path.exists()

        finally:
            os.chdir(original_cwd)

    def test_cleanup_combined_criteria(self, cli_with_worktrees):
        """Test cleanup with multiple criteria combined"""
        cli, config, repo_dir, worktrees = cli_with_worktrees
        recent_path, old_path, merged_path = worktrees

        from types import SimpleNamespace
        args = SimpleNamespace(
            older_than=20,  # Remove if older than 20 days
            newer_than=None,
            merged_only=True,  # AND is merged
            force=True,
            dry_run=False,
            yes=True
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)
            cli.cmd_cleanup(args)

            # Recent worktree should exist (not old enough and not merged)
            assert recent_path.exists()

            # Old worktree should exist (old enough but not merged)
            assert old_path.exists()

            # Merged worktree should be removed (old enough AND merged)
            assert not merged_path.exists()

        finally:
            os.chdir(original_cwd)

    @patch('builtins.input', side_effect=['n', 'n', 'n'])
    def test_cleanup_interactive_cancel(self, mock_input, cli_with_worktrees):
        """Test cleanup interactive mode cancellation"""
        cli, config, repo_dir, worktrees = cli_with_worktrees

        from types import SimpleNamespace
        args = SimpleNamespace(
            older_than=1,  # Would remove all
            newer_than=None,
            merged_only=False,
            force=False,
            dry_run=False,
            yes=False  # Require confirmation
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)
            cli.cmd_cleanup(args)

            # All worktrees should still exist (cancelled)
            for worktree_path in worktrees:
                assert worktree_path.exists()

        finally:
            os.chdir(original_cwd)

    def test_cleanup_no_criteria_interactive_mode(self, cli_with_worktrees):
        """Test cleanup interactive mode when no criteria specified"""
        cli, config, repo_dir, worktrees = cli_with_worktrees

        from types import SimpleNamespace
        args = SimpleNamespace(
            older_than=None,
            newer_than=None,
            merged_only=False,
            force=False,
            dry_run=False,
            yes=False
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            # Mock interactive mode and input for cancellation
            with patch.object(cli, '_is_interactive', return_value=True), \
                 patch('builtins.input', return_value='5'):  # Cancel option
                cli.cmd_cleanup(args)

            # All worktrees should still exist
            for worktree_path in worktrees:
                assert worktree_path.exists()

        finally:
            os.chdir(original_cwd)

    def test_cleanup_error_handling(self, real_git_repo):
        """Test cleanup error handling with invalid repository"""
        cli = CprojCLI()
        config = Config()
        config.set('repo_path', '/nonexistent/path')
        cli.config = config

        from types import SimpleNamespace
        args = SimpleNamespace(
            older_than=30,
            newer_than=None,
            merged_only=False,
            force=False,
            dry_run=False,
            yes=True
        )

        # Should handle non-existent repository gracefully
        cli.cmd_cleanup(args)  # Should not raise exception

    def test_cleanup_missing_agent_json(self, real_git_repo):
        """Test cleanup with worktrees missing .agent.json files"""
        config_dir = real_git_repo.parent / '.config' / 'cproj'
        config_dir.mkdir(parents=True)

        cli = CprojCLI()
        config = Config(config_dir / 'config.json')
        config.set('repo_path', str(real_git_repo))
        cli.config = config

        git = GitWorktree(real_git_repo)

        # Create worktree without .agent.json
        worktree_path = real_git_repo.parent / 'no_agent_json'
        git.create_worktree(worktree_path, 'feature/no-json', 'main')

        from types import SimpleNamespace
        args = SimpleNamespace(
            older_than=1,  # Would remove if had valid age
            newer_than=None,
            merged_only=False,
            force=True,
            dry_run=False,
            yes=True
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(real_git_repo)
            cli.cmd_cleanup(args)

            # Worktree should still exist (no age info to match criteria)
            assert worktree_path.exists()

        finally:
            os.chdir(original_cwd)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])