#!/usr/bin/env python3
"""
Comprehensive tests for configuration prompting functionality

Tests all aspects of the _prompt_for_config method including:
- Project identity configuration
- Repository setup
- Workspace policy settings
- Environment setup preferences
- Tool configurations
- Integration settings
- Interactive prompting flow
"""

import tempfile
import sys
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest

# Import the classes we need to test
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cproj import CprojCLI, Config


class TestConfigPrompting:
    """Comprehensive tests for configuration prompting"""

    @pytest.fixture
    def cli(self):
        """Create a CprojCLI instance for testing"""
        return CprojCLI()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_minimal_config_prompting(self, cli):
        """Test configuration with minimal inputs (all defaults)"""
        # Mock all inputs to just press Enter (use defaults)
        inputs = [''] * 30  # Enough empty inputs for all prompts

        with patch('builtins.input', side_effect=inputs), \
             patch.object(cli, '_find_git_root', return_value=None), \
             patch.object(cli, '_store_linear_api_key'), \
             patch('cproj.OnePasswordIntegration.is_available', return_value=False):

            config = cli._prompt_for_config()

            # Check defaults were applied
            assert config['project_name'] == 'My Project'
            assert config['base_branch'] == 'main'
            assert config['cleanup_days'] == 14
            assert config['python_prefer_uv'] == True
            assert config['python_auto_install'] == True
            assert config['node_use_nvm'] == True
            assert config['node_auto_install'] == True
            assert config['java_auto_build'] == False
            assert config['editor'] == 'code'

    def test_full_config_prompting(self, cli, temp_dir):
        """Test configuration with all custom inputs"""
        git_root = temp_dir / 'test_repo'
        git_root.mkdir()

        inputs = [
            'Test Project',                    # Project name
            str(git_root),                     # Repository path
            'develop',                         # Base branch
            '/tmp/workspaces',                 # Temp root
            'feature/{ticket}',                # Branch scheme
            '30',                              # Cleanup days
            'n',                               # Use uv
            'n',                               # Auto-install Python
            'n',                               # Use nvm
            'n',                               # Auto-install Node
            'y',                               # Auto-build Java
            'iTerm',                           # Terminal app
            'vim',                             # Editor
            'https://linear.app/myorg',       # Linear org
            'TEAM',                            # Linear team
            'PROJ-123',                        # Linear project
            'n',                               # Setup API key now
            'user1,user2',                     # GitHub reviewers
            'y',                               # Draft PRs
            'n',                               # Claude symlink
            'n',                               # Claude nvm
            'n',                               # Claude workspace
            'y',                               # Save config
        ]

        with patch('builtins.input', side_effect=inputs), \
             patch.object(cli, '_find_git_root', return_value=git_root), \
             patch('platform.system', return_value='Darwin'), \
             patch('cproj.OnePasswordIntegration.is_available', return_value=False):

            config = cli._prompt_for_config()

            assert config['project_name'] == 'Test Project'
            assert config['repo_path'] == str(git_root)
            assert config['base_branch'] == 'develop'
            assert config['temp_root'] == '/tmp/workspaces'
            assert config['branch_scheme'] == 'feature/{ticket}'
            assert config['cleanup_days'] == 30
            assert config['python_prefer_uv'] == False
            assert config['python_auto_install'] == False
            assert config['node_use_nvm'] == False
            assert config['node_auto_install'] == False
            assert config['java_auto_build'] == True
            assert config['terminal'] == 'iTerm'
            assert config['editor'] == 'vim'
            assert config['linear_org'] == 'https://linear.app/myorg'
            assert config['linear_default_team'] == 'TEAM'
            assert config['linear_default_project'] == 'PROJ-123'
            assert config['github_reviewers'] == ['user1', 'user2']
            assert config['github_draft_default'] == True

    def test_config_with_git_url(self, cli):
        """Test configuration with a git URL"""
        inputs = [
            'My App',                          # Project name
            'https://github.com/user/repo',   # Repository URL
            '/home/user/projects/my-app',     # Clone to directory
            '',                                # Base branch (default)
            '',                                # Temp root (default)
            '',                                # Branch scheme (default)
            '',                                # Cleanup days (default)
            '',                                # Use uv (default)
            '',                                # Auto-install Python (default)
            '',                                # Use nvm (default)
            '',                                # Auto-install Node (default)
            '',                                # Auto-build Java (default)
            '',                                # Terminal (default)
            '',                                # Editor (default)
            '',                                # Linear org (skip)
            '',                                # GitHub reviewers (skip)
            '',                                # Draft PRs (default)
            '',                                # Claude symlink (default)
            '',                                # Claude nvm (default)
            '',                                # Claude workspace (default)
            'y',                               # Save config
        ]

        with patch('builtins.input', side_effect=inputs), \
             patch('platform.system', return_value='Linux'), \
             patch('cproj.OnePasswordIntegration.is_available', return_value=False):

            config = cli._prompt_for_config()

            assert config['project_name'] == 'My App'
            assert config['repo_path'] == '/home/user/projects/my-app'
            assert config['clone_url'] == 'https://github.com/user/repo'
            assert config['terminal'] == 'none'  # Linux default

    def test_config_current_directory(self, cli, temp_dir):
        """Test configuration using current directory"""
        git_root = temp_dir / '.git'
        git_root.mkdir()

        inputs = [
            'Current Project',                 # Project name
            '.',                               # Current directory
            '',                                # Base branch (default)
            '',                                # Temp root (default)
            '',                                # Branch scheme (default)
            '',                                # Cleanup days (default)
            '',                                # Use uv (default)
            '',                                # Auto-install Python (default)
            '',                                # Use nvm (default)
            '',                                # Auto-install Node (default)
            '',                                # Auto-build Java (default)
            '',                                # Terminal (default)
            '',                                # Editor (default)
            '',                                # Linear org (skip)
            '',                                # GitHub reviewers (skip)
            '',                                # Draft PRs (default)
            '',                                # Claude symlink (default)
            '',                                # Claude nvm (default)
            '',                                # Claude workspace (default)
            'y',                               # Save config
        ]

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)

            with patch('builtins.input', side_effect=inputs), \
                 patch.object(cli, '_find_git_root', return_value=temp_dir), \
                 patch('platform.system', return_value='Darwin'), \
                 patch('cproj.OnePasswordIntegration.is_available', return_value=False):

                config = cli._prompt_for_config()

                assert config['project_name'] == 'Current Project'
                assert config['repo_path'] == str(temp_dir)

        finally:
            os.chdir(original_cwd)

    def test_config_with_linear_api_key(self, cli):
        """Test configuration with Linear API key setup"""
        inputs = [
            'Linear Project',                  # Project name
            '.',                               # Current directory
            '',                                # Base branch (default)
            '',                                # Temp root (default)
            '',                                # Branch scheme (default)
            '',                                # Cleanup days (default)
            '',                                # Use uv (default)
            '',                                # Auto-install Python (default)
            '',                                # Use nvm (default)
            '',                                # Auto-install Node (default)
            '',                                # Auto-build Java (default)
            '',                                # Terminal (default)
            '',                                # Editor (default)
            'https://linear.app/myorg',       # Linear org
            'TEAM',                            # Linear team
            'PROJ',                            # Linear project
            'y',                               # Setup API key now
            'lin_api_test123',                 # API key
            '',                                # GitHub reviewers (skip)
            '',                                # Draft PRs (default)
            '',                                # Claude symlink (default)
            '',                                # Claude nvm (default)
            '',                                # Claude workspace (default)
            'y',                               # Save config
        ]

        with patch('builtins.input', side_effect=inputs), \
             patch.object(cli, '_find_git_root', return_value=None), \
             patch.object(cli, '_store_linear_api_key') as mock_store, \
             patch('platform.system', return_value='Darwin'), \
             patch('cproj.OnePasswordIntegration.is_available', return_value=False):

            config = cli._prompt_for_config()

            assert config['linear_org'] == 'https://linear.app/myorg'
            assert config['linear_default_team'] == 'TEAM'
            assert config['linear_default_project'] == 'PROJ'
            mock_store.assert_called_once_with('lin_api_test123')

    @patch('cproj.OnePasswordIntegration.is_available', return_value=True)
    def test_config_with_onepassword(self, mock_op_available, cli):
        """Test configuration with 1Password integration"""
        inputs = [
            '1Password Project',               # Project name
            '.',                               # Current directory
            '',                                # Base branch (default)
            '',                                # Temp root (default)
            '',                                # Branch scheme (default)
            '',                                # Cleanup days (default)
            '',                                # Use uv (default)
            '',                                # Auto-install Python (default)
            '',                                # Use nvm (default)
            '',                                # Auto-install Node (default)
            '',                                # Auto-build Java (default)
            '',                                # Terminal (default)
            '',                                # Editor (default)
            '',                                # Linear org (skip)
            '',                                # GitHub reviewers (skip)
            '',                                # Draft PRs (default)
            '',                                # Claude symlink (default)
            '',                                # Claude nvm (default)
            '',                                # Claude workspace (default)
            'y',                               # Use 1Password
            'Work',                            # Vault name
            'y',                               # Save config
        ]

        with patch('builtins.input', side_effect=inputs), \
             patch.object(cli, '_find_git_root', return_value=None), \
             patch('platform.system', return_value='Darwin'):

            config = cli._prompt_for_config()

            assert config['use_1password'] == True
            assert config['onepassword_vault'] == 'Work'

    def test_config_cancellation(self, cli):
        """Test configuration cancellation"""
        # Use empty strings for most inputs, then 'n' to decline saving config
        inputs = [''] * 20 + ['n']  # Answer 'n' to save config

        with patch('builtins.input', side_effect=inputs), \
             patch.object(cli, '_find_git_root', return_value=None), \
             patch('platform.system', return_value='Darwin'), \
             patch('cproj.OnePasswordIntegration.is_available', return_value=False), \
             pytest.raises(SystemExit) as exc_info:

            cli._prompt_for_config()

        assert exc_info.value.code == 1

    def test_config_invalid_cleanup_days(self, cli):
        """Test configuration with invalid cleanup days (non-numeric)"""
        inputs = [
            'Test Project',                    # Project name
            '.',                               # Current directory
            '',                                # Base branch (default)
            '',                                # Temp root (default)
            '',                                # Branch scheme (default)
            'invalid',                         # Invalid cleanup days
            '',                                # Use uv (default)
            '',                                # Auto-install Python (default)
            '',                                # Use nvm (default)
            '',                                # Auto-install Node (default)
            '',                                # Auto-build Java (default)
            '',                                # Terminal (default)
            '',                                # Editor (default)
            '',                                # Linear org (skip)
            '',                                # GitHub reviewers (skip)
            '',                                # Draft PRs (default)
            '',                                # Claude symlink (default)
            '',                                # Claude nvm (default)
            '',                                # Claude workspace (default)
            'y',                               # Save config
        ]

        with patch('builtins.input', side_effect=inputs), \
             patch.object(cli, '_find_git_root', return_value=None), \
             patch('platform.system', return_value='Darwin'), \
             patch('cproj.OnePasswordIntegration.is_available', return_value=False):

            config = cli._prompt_for_config()

            # Should default to 14 when invalid input
            assert config['cleanup_days'] == 14

    def test_config_terminal_options(self, cli):
        """Test different terminal options on macOS"""
        test_cases = [
            ('iterm', 'iTerm'),
            ('iterm2', 'iTerm'),
            ('none', 'none'),
            ('terminal', 'Terminal'),
            ('', 'Terminal'),  # Default
        ]

        for input_value, expected in test_cases:
            # Need to place terminal input at the right position (after env setup questions)
            inputs = (
                [''] * 2 +   # Project identity
                [''] +       # Base branch
                [''] * 3 +   # Workspace policy
                [''] * 5 +   # Environment setup
                [input_value] +  # Terminal app
                [''] +       # Editor
                [''] * 4 +   # Linear/GitHub/PR settings
                [''] * 3 +   # Claude settings
                ['y']        # Save config
            )

            with patch('builtins.input', side_effect=inputs), \
                 patch.object(cli, '_find_git_root', return_value=None), \
                 patch('platform.system', return_value='Darwin'), \
                 patch('cproj.OnePasswordIntegration.is_available', return_value=False):

                config = cli._prompt_for_config()
                assert config['terminal'] == expected


if __name__ == '__main__':
    pytest.main([__file__, '-v'])