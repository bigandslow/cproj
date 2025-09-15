#!/usr/bin/env python3
"""
Comprehensive tests for worktree creation functionality

Tests all aspects of the cmd_worktree_create method including:
- Repository path resolution
- Interactive branch name prompting
- Linear integration prompts
- Environment setup prompts
- Git worktree creation
- Environment setup execution
- Agent.json creation
- Terminal and editor integration
"""

import tempfile
import subprocess
import pytest
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

# Import the classes we need to test
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cproj import CprojCLI, Config, CprojError


class TestWorktreeCreation:
    """Comprehensive tests for worktree creation"""

    @pytest.fixture
    def real_git_repo(self):
        """Create a real git repository for testing"""
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

            # Create main branch
            subprocess.run(['git', 'branch', '-m', 'main'], cwd=repo_dir, check=True, capture_output=True)

            yield repo_dir

    @pytest.fixture
    def cli_setup(self, real_git_repo):
        """Set up CLI with configuration"""
        config_dir = real_git_repo.parent / '.config' / 'cproj'
        config_dir.mkdir(parents=True)

        cli = CprojCLI()
        config = Config(config_dir / 'config.json')
        config.set('repo_path', str(real_git_repo))
        config.set('temp_root', str(real_git_repo.parent / 'workspaces'))
        cli.config = config

        return cli, config, real_git_repo

    def test_worktree_create_with_explicit_branch(self, cli_setup):
        """Test worktree creation with explicit branch name"""
        cli, config, repo_dir = cli_setup

        args = SimpleNamespace(
            repo=str(repo_dir),
            branch='feature/test-branch',
            base='main',
            temp_root=None,
            no_env=True,  # Skip environment setup
            no_terminal=True,  # Skip terminal opening
            open_editor=False
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            with patch.object(cli, '_is_interactive', return_value=False), \
                 patch('cproj.TerminalAutomation.open_terminal'), \
                 patch('cproj.TerminalAutomation.open_editor'):

                # Should not raise any errors
                cli.cmd_worktree_create(args)

        finally:
            os.chdir(original_cwd)

    def test_worktree_create_no_repo_error(self, cli_setup):
        """Test worktree creation error when not in a git repo"""
        cli, config, repo_dir = cli_setup

        args = SimpleNamespace(
            branch='feature/test',
            no_env=True
        )

        # Change to a non-git directory
        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir.parent)

            with patch.object(cli, '_find_git_root', return_value=None):
                # Should print error and return early
                cli.cmd_worktree_create(args)

        finally:
            os.chdir(original_cwd)

    def test_worktree_create_interactive_branch_selection(self, cli_setup):
        """Test interactive branch name selection"""
        cli, config, repo_dir = cli_setup

        args = SimpleNamespace(
            repo=str(repo_dir),
            no_env=True,
            no_terminal=True,
            open_editor=False
        )

        inputs = ['feature/interactive-test', 'n']  # Branch name, skip environment setup

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            with patch.object(cli, '_is_interactive', return_value=True), \
                 patch('builtins.input', side_effect=inputs), \
                 patch.object(cli, '_generate_branch_suggestions', return_value=['feature/auto', 'bugfix/auto']), \
                 patch('cproj.TerminalAutomation.open_terminal'), \
                 patch('cproj.TerminalAutomation.open_editor'):

                cli.cmd_worktree_create(args)

                # Should have set the branch from input
                assert args.branch == 'feature/interactive-test'

        finally:
            os.chdir(original_cwd)

    def test_worktree_create_interactive_branch_suggestion(self, cli_setup):
        """Test interactive branch selection using suggestions"""
        cli, config, repo_dir = cli_setup

        args = SimpleNamespace(
            repo=str(repo_dir),
            no_env=True,
            no_terminal=True,
            open_editor=False
        )

        inputs = ['1', 'n']  # Select first suggestion, skip environment setup

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            with patch.object(cli, '_is_interactive', return_value=True), \
                 patch('builtins.input', side_effect=inputs), \
                 patch.object(cli, '_generate_branch_suggestions', return_value=['feature/suggested', 'bugfix/another']), \
                 patch('cproj.TerminalAutomation.open_terminal'), \
                 patch('cproj.TerminalAutomation.open_editor'):

                cli.cmd_worktree_create(args)

                # Should have selected the first suggestion
                assert args.branch == 'feature/suggested'

        finally:
            os.chdir(original_cwd)

    def test_worktree_create_no_branch_non_interactive(self, cli_setup):
        """Test error when no branch provided in non-interactive mode"""
        cli, config, repo_dir = cli_setup

        args = SimpleNamespace(
            repo=str(repo_dir),
            no_env=True
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            with patch.object(cli, '_is_interactive', return_value=False), \
                 pytest.raises(CprojError, match="Branch name is required"):

                cli.cmd_worktree_create(args)

        finally:
            os.chdir(original_cwd)

    def test_worktree_create_with_linear_integration(self, cli_setup):
        """Test worktree creation with Linear integration"""
        cli, config, repo_dir = cli_setup
        config.set('linear_org', 'https://linear.app/testorg')

        args = SimpleNamespace(
            repo=str(repo_dir),
            branch='feature/with-linear',
            no_env=True,
            no_terminal=True,
            open_editor=False
        )

        inputs = ['https://linear.app/testorg/issue/TEST-123', 'n']  # Linear URL, skip environment setup

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            with patch.object(cli, '_is_interactive', return_value=True), \
                 patch('builtins.input', side_effect=inputs), \
                 patch('cproj.TerminalAutomation.open_terminal'), \
                 patch('cproj.TerminalAutomation.open_editor'):

                cli.cmd_worktree_create(args)

                # Should have set the linear URL
                assert args.linear == 'https://linear.app/testorg/issue/TEST-123'

        finally:
            os.chdir(original_cwd)

    def test_worktree_create_with_environment_setup(self, cli_setup):
        """Test worktree creation with environment setup prompts"""
        cli, config, repo_dir = cli_setup

        # Create project files to trigger environment detection
        (repo_dir / 'pyproject.toml').write_text('[project]\nname = "test"')
        (repo_dir / 'package.json').write_text('{"name": "test"}')
        (repo_dir / 'pom.xml').write_text('<?xml version="1.0"?><project></project>')

        args = SimpleNamespace(
            repo=str(repo_dir),
            branch='feature/with-env',
            no_terminal=True,
            open_editor=False
        )

        inputs = [
            'y',  # Auto-install Python
            'y',  # Auto-install Node
            'y',  # Auto-build Java
            'y',  # Copy .env files
            'n'   # Skip Claude NVM setup
        ]

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            with patch.object(cli, '_is_interactive', return_value=True), \
                 patch('builtins.input', side_effect=inputs), \
                 patch('cproj.TerminalAutomation.open_terminal'), \
                 patch('cproj.TerminalAutomation.open_editor'):

                cli.cmd_worktree_create(args)

                # Should have set environment flags
                assert args.python_install == True
                assert args.node_install == True
                assert args.java_build == True
                assert args.copy_env == True

        finally:
            os.chdir(original_cwd)

    def test_worktree_create_with_shared_venv(self, cli_setup):
        """Test worktree creation with shared venv option"""
        cli, config, repo_dir = cli_setup

        # Create Python project file
        (repo_dir / 'pyproject.toml').write_text('[project]\nname = "test"')

        args = SimpleNamespace(
            repo=str(repo_dir),
            branch='feature/shared-venv',
            no_terminal=True,
            open_editor=False
        )

        inputs = [
            'n',  # Don't auto-install Python
            'y',  # Use shared venv
            'n',  # Don't copy .env files
            'n'   # Skip Claude NVM setup
        ]

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            with patch.object(cli, '_is_interactive', return_value=True), \
                 patch('builtins.input', side_effect=inputs), \
                 patch('cproj.TerminalAutomation.open_terminal'), \
                 patch('cproj.TerminalAutomation.open_editor'):

                cli.cmd_worktree_create(args)

                # Should have set shared venv flag
                assert args.python_install == False
                assert args.shared_venv == True

        finally:
            os.chdir(original_cwd)

    def test_worktree_create_with_terminal_opening(self, cli_setup):
        """Test worktree creation with terminal opening"""
        cli, config, repo_dir = cli_setup
        config.set('terminal', 'iTerm')

        args = SimpleNamespace(
            repo=str(repo_dir),
            branch='feature/with-terminal',
            no_env=True,
            open_editor=False
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            with patch.object(cli, '_is_interactive', return_value=False), \
                 patch('cproj.TerminalAutomation.open_terminal') as mock_terminal, \
                 patch('cproj.TerminalAutomation.open_editor'):

                cli.cmd_worktree_create(args)

                # Should have opened terminal
                mock_terminal.assert_called_once()

        finally:
            os.chdir(original_cwd)

    def test_worktree_create_with_editor_opening(self, cli_setup):
        """Test worktree creation with editor opening"""
        cli, config, repo_dir = cli_setup
        config.set('editor', 'code')

        args = SimpleNamespace(
            repo=str(repo_dir),
            branch='feature/with-editor',
            no_env=True,
            no_terminal=True,
            open_editor=True,
            editor='vim'
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            with patch.object(cli, '_is_interactive', return_value=False), \
                 patch('cproj.TerminalAutomation.open_terminal'), \
                 patch('cproj.TerminalAutomation.open_editor') as mock_editor:

                cli.cmd_worktree_create(args)

                # Should have opened editor with specified editor
                mock_editor.assert_called_once()

        finally:
            os.chdir(original_cwd)

    def test_worktree_create_agent_json_creation(self, cli_setup):
        """Test that agent.json is created correctly"""
        cli, config, repo_dir = cli_setup

        args = SimpleNamespace(
            repo=str(repo_dir),
            branch='feature/agent-json',
            base='main',
            linear='https://linear.app/test/TEST-123',
            no_env=True,
            no_terminal=True,
            open_editor=False
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            with patch.object(cli, '_is_interactive', return_value=False), \
                 patch('cproj.TerminalAutomation.open_terminal'), \
                 patch('cproj.TerminalAutomation.open_editor'):

                cli.cmd_worktree_create(args)

                # Find the created worktree and check agent.json
                workspaces_dir = repo_dir.parent / 'workspaces'
                worktree_dirs = list(workspaces_dir.glob('test_repo_feature/agent-json_*'))
                assert len(worktree_dirs) > 0

                worktree_dir = worktree_dirs[0]
                agent_json_path = worktree_dir / '.cproj' / '.agent.json'
                assert agent_json_path.exists()

                agent_data = json.loads(agent_json_path.read_text())
                assert agent_data['project']['name'] == 'test_repo'
                assert agent_data['workspace']['branch'] == 'feature/agent-json'
                assert agent_data['workspace']['base'] == 'main'
                assert agent_data['links']['linear'] == 'https://linear.app/test/TEST-123'

        finally:
            os.chdir(original_cwd)

    def test_worktree_create_with_custom_temp_root(self, cli_setup):
        """Test worktree creation with custom temp root"""
        cli, config, repo_dir = cli_setup

        custom_temp = repo_dir.parent / 'custom_workspaces'
        args = SimpleNamespace(
            repo=str(repo_dir),
            branch='feature/custom-temp',
            temp_root=str(custom_temp),
            no_env=True,
            no_terminal=True,
            open_editor=False
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            with patch.object(cli, '_is_interactive', return_value=False), \
                 patch('cproj.TerminalAutomation.open_terminal'), \
                 patch('cproj.TerminalAutomation.open_editor'):

                cli.cmd_worktree_create(args)

                # Should have created worktree in custom location
                assert custom_temp.exists()
                worktree_dirs = list(custom_temp.glob('test_repo_feature/custom-temp_*'))
                assert len(worktree_dirs) > 0

        finally:
            os.chdir(original_cwd)

    def test_worktree_create_invalid_branch_interactive_retry(self, cli_setup):
        """Test interactive retry when invalid branch name is entered"""
        cli, config, repo_dir = cli_setup

        args = SimpleNamespace(
            repo=str(repo_dir),
            no_env=True,
            no_terminal=True,
            open_editor=False
        )

        inputs = ['', 'valid-branch', 'n']  # First empty (invalid), then valid, skip environment setup

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            with patch.object(cli, '_is_interactive', return_value=True), \
                 patch('builtins.input', side_effect=inputs), \
                 patch.object(cli, '_generate_branch_suggestions', return_value=['feature/auto']), \
                 patch('cproj.TerminalAutomation.open_terminal'), \
                 patch('cproj.TerminalAutomation.open_editor'):

                cli.cmd_worktree_create(args)

                # Should have accepted the valid branch name
                assert args.branch == 'valid-branch'

        finally:
            os.chdir(original_cwd)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])