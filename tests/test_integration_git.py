#!/usr/bin/env python3
"""
Integration tests for Git operations with real repositories
"""

import tempfile
import subprocess
import pytest
import os
import json
from pathlib import Path
from datetime import datetime, timezone

# Import the classes we need to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cproj import GitWorktree, CprojCLI, Config, AgentJson, CprojError


@pytest.mark.integration
class TestGitIntegration:
    """Integration tests with real Git repositories"""

    @pytest.fixture
    def real_git_repo(self):
        """Create a real git repository for integration testing"""
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
            (repo_dir / 'README.md').write_text('# Test Repository\n\nIntegration test repository.')
            subprocess.run(['git', 'add', 'README.md'], cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(['git', 'commit', '-m', 'Initial commit'],
                          cwd=repo_dir, check=True, capture_output=True)

            # Create a main branch (modern git default)
            subprocess.run(['git', 'branch', '-m', 'main'], cwd=repo_dir, check=True, capture_output=True)

            yield repo_dir

    @pytest.fixture
    def cli_with_repo(self, real_git_repo):
        """Create CLI instance configured with real repository"""
        config_dir = real_git_repo.parent / '.config' / 'cproj'
        config_dir.mkdir(parents=True)
        config = Config(config_dir / 'config.json')
        config.set('repo_path', str(real_git_repo))

        cli = CprojCLI()
        cli.config = config
        return cli, config, real_git_repo

    def test_git_worktree_full_lifecycle(self, real_git_repo):
        """Test complete worktree lifecycle with real git operations"""
        git = GitWorktree(real_git_repo)

        # Test worktree creation
        worktree_path = real_git_repo.parent / 'test_feature_worktree'
        branch_name = 'feature/integration-test'

        # Create worktree
        git.create_worktree(worktree_path, branch_name, 'main')

        # Verify worktree was created
        assert worktree_path.exists()
        assert (worktree_path / '.git').exists()

        # Verify we're on the correct branch
        result = subprocess.run(['git', 'branch', '--show-current'],
                               cwd=worktree_path, capture_output=True, text=True, check=True)
        assert result.stdout.strip() == branch_name

        # Test making changes in worktree
        test_file = worktree_path / 'feature_test.py'
        test_file.write_text('# Integration test feature\nprint("Hello from worktree!")\n')

        subprocess.run(['git', 'add', 'feature_test.py'], cwd=worktree_path, check=True)
        subprocess.run(['git', 'commit', '-m', 'Add integration test feature'],
                      cwd=worktree_path, check=True)

        # Test worktree listing
        worktrees = git.list_worktrees()
        assert len(worktrees) >= 2  # Main repo + our worktree

        worktree_paths = [Path(wt.get('path', '')).resolve() for wt in worktrees if wt.get('path')]
        assert worktree_path.resolve() in worktree_paths

        # Test worktree removal
        git.remove_worktree(worktree_path)
        assert not worktree_path.exists()

    def test_git_worktree_with_dirty_state(self, real_git_repo):
        """Test worktree operations with uncommitted changes"""
        git = GitWorktree(real_git_repo)

        # Create worktree
        worktree_path = real_git_repo.parent / 'dirty_worktree'
        git.create_worktree(worktree_path, 'dirty-test', 'main')

        # Create uncommitted changes
        dirty_file = worktree_path / 'uncommitted.txt'
        dirty_file.write_text('This file is not committed')

        # Try to remove worktree (should fail without force)
        with pytest.raises(CprojError):
            git.remove_worktree(worktree_path, force=False)

        # Should still exist
        assert worktree_path.exists()

        # Force removal should work
        git.remove_worktree(worktree_path, force=True)
        assert not worktree_path.exists()

    def test_git_operations_with_remotes(self, real_git_repo):
        """Test git operations that involve remote repositories"""
        git = GitWorktree(real_git_repo)

        # Create a second repository to simulate remote
        remote_repo = real_git_repo.parent / 'remote_repo'
        subprocess.run(['git', 'clone', '--bare', str(real_git_repo), str(remote_repo)],
                      check=True, capture_output=True)

        # Add remote to original repo
        subprocess.run(['git', 'remote', 'add', 'origin', str(remote_repo)],
                      cwd=real_git_repo, check=True)

        # Test that we can fetch (even if nothing to fetch)
        result = subprocess.run(['git', 'fetch', 'origin'],
                               cwd=real_git_repo, capture_output=True, text=True)
        # Should succeed (exit code 0) even if no changes
        assert result.returncode == 0

    def test_agent_json_integration(self, real_git_repo):
        """Test AgentJson with real file operations"""
        # Create .cproj directory
        cproj_dir = real_git_repo / '.cproj'
        cproj_dir.mkdir()

        agent_json = AgentJson(real_git_repo)

        # Test that default data is created
        assert agent_json.data is not None
        assert 'workspace' in agent_json.data
        assert 'agent' in agent_json.data

        # Test setting workspace data
        agent_json.data['workspace']['branch'] = 'integration-test'
        agent_json.data['workspace']['created_at'] = datetime.now(timezone.utc).isoformat()
        agent_json.data['links'] = {'linear': 'https://linear.app/test/issue/123'}

        # Save and verify file exists
        agent_json.save()
        agent_file = cproj_dir / '.agent.json'
        assert agent_file.exists()

        # Test loading from file
        new_agent_json = AgentJson(real_git_repo)
        assert new_agent_json.data['workspace']['branch'] == 'integration-test'
        assert new_agent_json.data['links']['linear'] == 'https://linear.app/test/issue/123'

    def test_git_branch_operations(self, real_git_repo):
        """Test git branch operations"""
        git = GitWorktree(real_git_repo)

        # Create a new branch directly
        subprocess.run(['git', 'checkout', '-b', 'test-branch'],
                      cwd=real_git_repo, check=True)

        # Verify current branch
        result = subprocess.run(['git', 'branch', '--show-current'],
                               cwd=real_git_repo, capture_output=True, text=True, check=True)
        assert result.stdout.strip() == 'test-branch'

        # Switch back to main
        subprocess.run(['git', 'checkout', 'main'],
                      cwd=real_git_repo, check=True)

        # List all branches
        result = subprocess.run(['git', 'branch'],
                               cwd=real_git_repo, capture_output=True, text=True, check=True)
        branches = result.stdout
        assert 'main' in branches
        assert 'test-branch' in branches

    def test_git_diff_operations(self, real_git_repo):
        """Test git diff operations with real changes"""
        # Make some changes
        test_file = real_git_repo / 'test_changes.py'
        test_file.write_text('# Original content\nprint("original")\n')

        subprocess.run(['git', 'add', 'test_changes.py'], cwd=real_git_repo, check=True)
        subprocess.run(['git', 'commit', '-m', 'Add test file'], cwd=real_git_repo, check=True)

        # Modify the file
        test_file.write_text('# Modified content\nprint("modified")\n# New line\n')

        # Test git diff
        result = subprocess.run(['git', 'diff'],
                               cwd=real_git_repo, capture_output=True, text=True, check=True)

        diff_output = result.stdout
        assert 'test_changes.py' in diff_output
        assert '-print("original")' in diff_output
        assert '+print("modified")' in diff_output
        assert '+# New line' in diff_output

    def test_git_status_operations(self, real_git_repo):
        """Test git status operations with real file states"""
        # Create different types of file states

        # Untracked file
        untracked = real_git_repo / 'untracked.txt'
        untracked.write_text('untracked content')

        # Modified file (ensure it actually gets modified)
        readme = real_git_repo / 'README.md'
        if readme.exists():
            original_content = readme.read_text()
            readme.write_text(original_content + '\n\n## New section\nModified for test\n')
        else:
            # Fallback: create the file if it doesn't exist
            readme.write_text('# Test Repository\n\nModified for test\n')

        # Staged file
        staged = real_git_repo / 'staged.txt'
        staged.write_text('staged content')
        subprocess.run(['git', 'add', 'staged.txt'], cwd=real_git_repo, check=True)

        # Test git status
        result = subprocess.run(['git', 'status', '--porcelain'],
                               cwd=real_git_repo, capture_output=True, text=True, check=True)

        status_output = result.stdout
        assert 'untracked.txt' in status_output
        assert 'staged.txt' in status_output
        # README.md should be modified only if it actually exists and was changed
        if readme.exists():
            assert 'README.md' in status_output

        # Parse status output
        lines = status_output.strip().split('\n') if status_output.strip() else []
        status_map = {}
        for line in lines:
            if len(line) >= 3:
                status = line[:2]
                filename = line[3:]
                status_map[filename] = status

        # Verify status codes (be more defensive about expected files)
        if 'staged.txt' in status_map:
            assert status_map['staged.txt'].startswith('A')  # Added
        if 'README.md' in status_map:
            assert status_map['README.md'].strip().startswith('M')  # Modified
        if 'untracked.txt' in status_map:
            assert status_map['untracked.txt'] == '??'  # Untracked

        # Verify we have at least the files we expect
        assert 'staged.txt' in status_output
        assert 'untracked.txt' in status_output

    def test_worktree_with_project_files(self, real_git_repo):
        """Test worktree with realistic project structure"""
        git = GitWorktree(real_git_repo)

        # Create a realistic project structure in main repo
        (real_git_repo / 'src').mkdir()
        (real_git_repo / 'src' / '__init__.py').touch()
        (real_git_repo / 'src' / 'main.py').write_text('#!/usr/bin/env python3\nprint("Hello World")\n')

        (real_git_repo / 'tests').mkdir()
        (real_git_repo / 'tests' / 'test_main.py').write_text('import unittest\n\nclass TestMain(unittest.TestCase):\n    pass\n')

        (real_git_repo / 'pyproject.toml').write_text('''[project]
name = "test-project"
version = "0.1.0"
dependencies = []
''')

        # Commit the project structure
        subprocess.run(['git', 'add', '.'], cwd=real_git_repo, check=True)
        subprocess.run(['git', 'commit', '-m', 'Add project structure'],
                      cwd=real_git_repo, check=True)

        # Create worktree
        worktree_path = real_git_repo.parent / 'feature_worktree'
        git.create_worktree(worktree_path, 'feature/new-feature', 'main')

        # Verify project structure exists in worktree
        assert (worktree_path / 'src' / 'main.py').exists()
        assert (worktree_path / 'tests' / 'test_main.py').exists()
        assert (worktree_path / 'pyproject.toml').exists()

        # Test making changes in worktree
        feature_file = worktree_path / 'src' / 'feature.py'
        feature_file.write_text('def new_feature():\n    return "feature implemented"\n')

        subprocess.run(['git', 'add', 'src/feature.py'], cwd=worktree_path, check=True)
        subprocess.run(['git', 'commit', '-m', 'Add new feature'],
                      cwd=worktree_path, check=True)

        # Verify changes are isolated to worktree
        assert (worktree_path / 'src' / 'feature.py').exists()
        assert not (real_git_repo / 'src' / 'feature.py').exists()

        # Clean up
        git.remove_worktree(worktree_path)

    def test_error_handling_with_real_git(self, real_git_repo):
        """Test error handling with real git error conditions"""
        git = GitWorktree(real_git_repo)

        # Test creating worktree with invalid branch
        worktree_path = real_git_repo.parent / 'invalid_worktree'

        with pytest.raises(CprojError):
            git.create_worktree(worktree_path, 'new-branch', 'nonexistent-base-branch')

        # Test removing non-existent worktree
        nonexistent_path = real_git_repo.parent / 'nonexistent_worktree'

        with pytest.raises(CprojError):
            git.remove_worktree(nonexistent_path)

    def test_concurrent_worktree_operations(self, real_git_repo):
        """Test multiple worktree operations"""
        git = GitWorktree(real_git_repo)

        # Create multiple worktrees
        worktree_paths = []
        for i in range(3):
            worktree_path = real_git_repo.parent / f'worktree_{i}'
            branch_name = f'feature/test-{i}'

            git.create_worktree(worktree_path, branch_name, 'main')
            worktree_paths.append(worktree_path)

            # Verify each worktree
            assert worktree_path.exists()
            result = subprocess.run(['git', 'branch', '--show-current'],
                                   cwd=worktree_path, capture_output=True, text=True, check=True)
            assert result.stdout.strip() == branch_name

        # List all worktrees
        worktrees = git.list_worktrees()
        assert len(worktrees) >= 4  # Main + 3 worktrees

        # Clean up all worktrees
        for worktree_path in worktree_paths:
            git.remove_worktree(worktree_path)
            assert not worktree_path.exists()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'integration'])