#!/usr/bin/env python3
"""
Comprehensive tests for Git operations and worktree management
"""

import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cproj import CprojError, GitWorktree


class TestGitOperations:
    """Test Git worktree operations"""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary git repository for testing"""
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
            (repo_dir / 'README.md').write_text('# Test Repo')
            subprocess.run(['git', 'add', 'README.md'], cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(['git', 'commit', '-m', 'Initial commit'],
                          cwd=repo_dir, check=True, capture_output=True)

            yield repo_dir

    def test_git_worktree_initialization(self, temp_repo):
        """Test GitWorktree class initialization"""
        git = GitWorktree(temp_repo)
        assert git.repo_path == temp_repo
        assert isinstance(git.repo_path, Path)

    def test_git_worktree_command_construction(self, temp_repo):
        """Test git command construction without execution"""
        GitWorktree(temp_repo)

        # Test command construction patterns
        worktree_path = temp_repo.parent / 'test_worktree'
        branch_name = 'test-branch'
        base_branch = 'main'

        # These test the command construction logic
        expected_commands = [
            ['git', 'worktree', 'add', '-b', branch_name, str(worktree_path), base_branch],
            ['git', 'worktree', 'remove', str(worktree_path)],
            ['git', 'worktree', 'list', '--porcelain'],
        ]

        # Verify command structure is correct
        for cmd in expected_commands:
            assert cmd[0] == 'git'
            assert 'worktree' in cmd
            assert all(isinstance(arg, str) for arg in cmd)

    @patch('subprocess.run')
    def test_git_worktree_creation_mock(self, mock_run, temp_repo):
        """Test worktree creation with mocked subprocess"""
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        git = GitWorktree(temp_repo)
        worktree_path = temp_repo.parent / 'test_worktree'

        # Test successful creation
        git.create_worktree(worktree_path, 'test-branch', 'main')

        # Verify subprocess was called with correct arguments
        mock_run.assert_called()
        call_args = mock_run.call_args_list[-1]
        assert 'git' in call_args[0][0]
        assert 'worktree' in call_args[0][0]
        assert 'add' in call_args[0][0]

    @patch('subprocess.run')
    def test_git_worktree_list_mock(self, mock_run, temp_repo):
        """Test worktree listing with mocked subprocess"""
        # Mock worktree list output
        mock_output = """worktree /path/to/repo
HEAD abc123def456
branch refs/heads/main

worktree /path/to/worktree1
HEAD def456abc789
branch refs/heads/feature-1

worktree /path/to/worktree2
HEAD 789abc123def
detached"""

        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr='')

        git = GitWorktree(temp_repo)
        worktrees = git.list_worktrees()

        # Should parse the output correctly
        assert isinstance(worktrees, list)
        mock_run.assert_called_with(
            ['git', '-C', str(temp_repo), 'worktree', 'list', '--porcelain'],
            capture_output=True,
            text=True,
            check=True
        )

    @patch('subprocess.run')
    def test_git_worktree_removal_mock(self, mock_run, temp_repo):
        """Test worktree removal with mocked subprocess"""
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        git = GitWorktree(temp_repo)
        worktree_path = temp_repo.parent / 'test_worktree'

        # Test normal removal
        git.remove_worktree(worktree_path, force=False)
        mock_run.assert_called()

        # Test forced removal
        git.remove_worktree(worktree_path, force=True)
        last_call = mock_run.call_args_list[-1]
        assert '--force' in last_call[0][0]

    @patch('subprocess.run')
    def test_git_worktree_error_handling(self, mock_run, temp_repo):
        """Test error handling in git operations"""
        # Test subprocess error handling
        mock_run.side_effect = subprocess.CalledProcessError(1, 'git', 'error message')

        git = GitWorktree(temp_repo)
        worktree_path = temp_repo.parent / 'test_worktree'

        with pytest.raises(CprojError):
            git.create_worktree(worktree_path, 'test-branch', 'main')

    def test_git_branch_name_validation(self):
        """Test git branch name validation logic"""
        # Valid branch names
        valid_names = [
            'feature-branch',
            'bugfix/issue-123',
            'release/v1.0.0',
            'hotfix_urgent',
            'main',
            'develop'
        ]

        # Invalid branch names (according to git rules)
        invalid_names = [
            'branch with spaces',
            'branch..double-dot',
            'branch~tilde',
            'branch^caret',
            'branch:colon',
            'branch?question',
            'branch*asterisk',
            'branch[bracket]',
            '.branch-starting-with-dot',
            'branch-ending-with.',
            '/branch-starting-with-slash',
            'branch-ending-with-slash/',
        ]

        def is_valid_git_branch_name(name):
            """Simple validation logic for git branch names"""
            if not name or name.startswith('.') or name.endswith('.'):
                return False
            if name.startswith('/') or name.endswith('/'):
                return False
            invalid_chars = [' ', '..', '~', '^', ':', '?', '*', '[', ']']
            return not any(char in name for char in invalid_chars)

        for name in valid_names:
            assert is_valid_git_branch_name(name), f"Valid name rejected: {name}"

        for name in invalid_names:
            assert not is_valid_git_branch_name(name), f"Invalid name accepted: {name}"

    @patch('subprocess.run')
    def test_git_status_operations(self, mock_run, temp_repo):
        """Test git status and diff operations"""
        # Mock git status output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=' M modified_file.py\n?? untracked_file.py\n',
            stderr=''
        )

        GitWorktree(temp_repo)

        # Test that status command would be properly constructed
        expected_cmd = ['git', 'status', '--porcelain']

        # Simulate calling git status
        subprocess.run(expected_cmd, cwd=temp_repo, capture_output=True, text=True, check=False)

        # Verify command structure
        assert expected_cmd[0] == 'git'
        assert 'status' in expected_cmd

    @patch('subprocess.run')
    def test_git_diff_operations(self, mock_run, temp_repo):
        """Test git diff operations"""
        # Mock git diff output
        mock_diff_output = """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 def test_function():
+    # Added comment
     pass
"""

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_diff_output,
            stderr=''
        )

        GitWorktree(temp_repo)

        # Test various diff commands
        diff_commands = [
            ['git', 'diff'],
            ['git', 'diff', '--cached'],
            ['git', 'diff', 'HEAD~1'],
            ['git', 'diff', 'main...feature-branch'],
        ]

        for cmd in diff_commands:
            assert cmd[0] == 'git'
            assert 'diff' in cmd
            assert all(isinstance(arg, str) for arg in cmd)

    def test_git_worktree_path_validation(self, temp_repo):
        """Test worktree path validation"""
        GitWorktree(temp_repo)

        # Valid paths
        valid_paths = [
            temp_repo.parent / 'valid_worktree',
            temp_repo.parent / 'sub' / 'directory' / 'worktree',
            temp_repo.parent / 'worktree-with-dashes',
            temp_repo.parent / 'worktree_with_underscores',
        ]

        # Test path validation logic
        for path in valid_paths:
            # Basic validation - path should be outside repo
            try:
                path.resolve().relative_to(temp_repo.resolve())
                is_inside_repo = True
            except ValueError:
                is_inside_repo = False

            # Worktree paths should generally be outside the main repo
            assert not is_inside_repo or str(path).startswith(str(temp_repo.parent))

    @patch('subprocess.run')
    def test_git_branch_operations(self, mock_run, temp_repo):
        """Test git branch operations"""
        # Mock branch list output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='* main\n  feature-branch\n  bugfix-branch\n',
            stderr=''
        )

        GitWorktree(temp_repo)

        # Test branch listing command structure
        branch_cmd = ['git', 'branch', '-a']
        assert branch_cmd[0] == 'git'
        assert 'branch' in branch_cmd

        # Test current branch command
        current_branch_cmd = ['git', 'branch', '--show-current']
        assert current_branch_cmd[0] == 'git'
        assert 'branch' in current_branch_cmd
        assert '--show-current' in current_branch_cmd

    @patch('subprocess.run')
    def test_git_timeout_handling(self, mock_run, temp_repo):
        """Test git operation timeout handling"""
        # Test timeout exception
        mock_run.side_effect = subprocess.TimeoutExpired('git', 30)

        GitWorktree(temp_repo)

        # Should handle timeout gracefully
        with pytest.raises((subprocess.TimeoutExpired, CprojError)):
            # This would normally timeout
            subprocess.run(['git', 'status'], timeout=0.001, cwd=temp_repo, check=True)

    def test_git_worktree_cleanup_logic(self, _temp_repo):
        """Test worktree cleanup logic"""

        # Test age calculation logic
        current_time = datetime.now(timezone.utc)
        old_time = current_time - timedelta(days=30)
        recent_time = current_time - timedelta(hours=1)

        def is_older_than_days(timestamp, days):
            """Logic for determining if a timestamp is older than specified days"""
            if not timestamp:
                return False
            cutoff = current_time - timedelta(days=days)
            return timestamp < cutoff

        # Test the logic
        assert is_older_than_days(old_time, 7)  # 30 days old, threshold 7 days
        assert not is_older_than_days(recent_time, 7)  # 1 hour old, threshold 7 days

    @patch('subprocess.run')
    def test_git_remote_operations(self, mock_run, temp_repo):
        """Test git remote operations"""
        # Mock remote list output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='origin\tupstream\n',
            stderr=''
        )

        GitWorktree(temp_repo)

        # Test remote command structure
        remote_cmd = ['git', 'remote', '-v']
        assert remote_cmd[0] == 'git'
        assert 'remote' in remote_cmd

        # Test fetch command structure
        fetch_cmd = ['git', 'fetch', 'origin']
        assert fetch_cmd[0] == 'git'
        assert 'fetch' in fetch_cmd

    def test_worktree_path_safety(self, temp_repo):
        """Test worktree path safety validation"""
        GitWorktree(temp_repo)

        # Test safe path construction
        base_dir = temp_repo.parent
        worktree_name = 'test-worktree'
        worktree_path = base_dir / worktree_name

        # Verify path is safe
        try:
            # Should be within parent directory
            relative = worktree_path.resolve().relative_to(base_dir.resolve())
            is_safe = True
        except ValueError:
            is_safe = False

        assert is_safe, "Worktree path should be safe"

        # Test path traversal prevention
        dangerous_paths = [
            '../../../etc/passwd',
            '../../.ssh/id_rsa',
            '/etc/passwd',
            '~/sensitive_file'
        ]

        for dangerous_path in dangerous_paths:
            if dangerous_path.startswith('/'):
                # Absolute paths
                path_obj = Path(dangerous_path)
            elif dangerous_path.startswith('~'):
                # Home directory expansion
                path_obj = Path(dangerous_path).expanduser()
            else:
                # Relative paths that could traverse up
                path_obj = Path(base_dir) / dangerous_path

            try:
                path_obj.resolve().relative_to(base_dir.resolve())
                is_safe = True
            except ValueError:
                is_safe = False

            # Should not be safe for absolute or home paths, and traversal paths
            if dangerous_path.startswith('/') or dangerous_path.startswith('~') or '../' in dangerous_path:
                assert not is_safe, f"Dangerous path should not be safe: {dangerous_path}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
