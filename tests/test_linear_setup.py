#!/usr/bin/env python3
"""
Comprehensive tests for Linear setup functionality

Tests all aspects of the cmd_linear_setup method including:
- Interactive mode prompting
- Command-line argument handling
- Organization, team, and project configuration
- API key setup (direct and 1Password)
- Configuration validation and error handling
"""

import tempfile
import sys
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
import pytest

# Import the classes we need to test
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cproj import CprojCLI, Config


class TestLinearSetup:
    """Comprehensive tests for Linear setup functionality"""

    @pytest.fixture
    def cli(self):
        """Create a CprojCLI instance for testing"""
        return CprojCLI()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cli_setup(self, temp_dir):
        """Set up CLI with configuration"""
        config_dir = temp_dir / '.config' / 'cproj'
        config_dir.mkdir(parents=True)

        cli = CprojCLI()
        config = Config(config_dir / 'config.json')
        cli.config = config

        return cli, config, temp_dir

    def test_linear_setup_interactive_full(self, cli_setup):
        """Test interactive Linear setup with all inputs"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org=None,
            team=None,
            project=None,
            api_key=None,
            from_1password=False
        )

        inputs = [
            'https://linear.app/myorg',  # Organization
            'DEV',                       # Team
            'PROJ-123',                  # Project
            '2',                         # API key choice (enter directly)
            'lin_api_test123'           # API key
        ]

        with patch('builtins.input', side_effect=inputs), \
             patch.object(cli, '_load_linear_config', return_value={}), \
             patch.object(cli, '_store_linear_api_key') as mock_store:

            cli.cmd_linear_setup(args)

            # Verify configuration was set
            assert config.get('linear_org') == 'https://linear.app/myorg'
            assert config.get('linear_default_team') == 'DEV'
            assert config.get('linear_default_project') == 'PROJ-123'
            mock_store.assert_called_once_with('lin_api_test123')

    def test_linear_setup_interactive_minimal(self, cli_setup):
        """Test interactive Linear setup with minimal inputs"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org=None,
            team=None,
            project=None,
            api_key=None,
            from_1password=False
        )

        inputs = [
            'https://linear.app/testorg',  # Organization
            '',                            # Team (empty)
            '',                            # Project (empty)
            '3'                            # API key choice (skip)
        ]

        with patch('builtins.input', side_effect=inputs), \
             patch.object(cli, '_load_linear_config', return_value={}):

            cli.cmd_linear_setup(args)

            # Verify configuration was set
            assert config.get('linear_org') == 'https://linear.app/testorg'
            assert config.get('linear_default_team') is None
            assert config.get('linear_default_project') is None

    def test_linear_setup_interactive_existing_config(self, cli_setup):
        """Test interactive setup with existing configuration"""
        cli, config, temp_dir = cli_setup

        # Set existing configuration
        config.set('linear_org', 'https://linear.app/existing')
        config.set('linear_default_team', 'EXISTING-TEAM')
        config.set('linear_default_project', 'EXISTING-PROJ')

        args = SimpleNamespace(
            org=None,
            team=None,
            project=None,
            api_key=None,
            from_1password=False
        )

        inputs = [
            '',  # Organization (keep existing)
            '',  # Team (keep existing)
            '',  # Project (keep existing)
            '3'  # API key choice (skip)
        ]

        with patch('builtins.input', side_effect=inputs), \
             patch.object(cli, '_load_linear_config', return_value={'LINEAR_API_KEY': 'existing'}):

            cli.cmd_linear_setup(args)

            # Verify existing configuration was preserved
            assert config.get('linear_org') == 'https://linear.app/existing'
            assert config.get('linear_default_team') == 'EXISTING-TEAM'
            assert config.get('linear_default_project') == 'EXISTING-PROJ'

    def test_linear_setup_command_line_args(self, cli_setup):
        """Test Linear setup with command-line arguments"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org='https://linear.app/cmdline',
            team='CMD-TEAM',
            project='CMD-PROJ',
            api_key='cmd_api_key_123',
            from_1password=False
        )

        with patch.object(cli, '_store_linear_api_key') as mock_store:
            cli.cmd_linear_setup(args)

            # Verify configuration was set from command line
            assert config.get('linear_org') == 'https://linear.app/cmdline'
            assert config.get('linear_default_team') == 'CMD-TEAM'
            assert config.get('linear_default_project') == 'CMD-PROJ'
            mock_store.assert_called_once_with('cmd_api_key_123')

    def test_linear_setup_1password_integration(self, cli_setup):
        """Test Linear setup with 1Password integration"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org=None,
            team=None,
            project=None,
            api_key=None,
            from_1password=True
        )

        inputs = ['op://Private/linear-api-key/password']

        with patch('cproj.OnePasswordIntegration.is_available', return_value=True), \
             patch('builtins.input', side_effect=inputs), \
             patch('cproj.OnePasswordIntegration.get_secret', return_value='test_api_key'), \
             patch.object(cli, '_store_linear_1password_ref') as mock_store_ref:

            cli.cmd_linear_setup(args)

            mock_store_ref.assert_called_once_with('op://Private/linear-api-key/password')

    def test_linear_setup_1password_not_available(self, cli_setup):
        """Test Linear setup when 1Password CLI is not available"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org=None,
            team=None,
            project=None,
            api_key=None,
            from_1password=True
        )

        with patch('cproj.OnePasswordIntegration.is_available', return_value=False):
            cli.cmd_linear_setup(args)
            # Should print error message and return early

    def test_linear_setup_1password_invalid_reference(self, cli_setup):
        """Test Linear setup with invalid 1Password reference"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org=None,
            team=None,
            project=None,
            api_key=None,
            from_1password=True
        )

        inputs = ['op://Private/invalid-reference/password']

        with patch('cproj.OnePasswordIntegration.is_available', return_value=True), \
             patch('builtins.input', side_effect=inputs), \
             patch('cproj.OnePasswordIntegration.get_secret', return_value=None):

            cli.cmd_linear_setup(args)
            # Should print error message about invalid reference

    def test_linear_setup_interactive_1password_choice(self, cli_setup):
        """Test interactive setup choosing 1Password option"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org=None,
            team=None,
            project=None,
            api_key=None,
            from_1password=False
        )

        inputs = [
            'https://linear.app/test',  # Organization
            '',                         # Team (empty)
            '',                         # Project (empty)
            '1'                         # API key choice (1Password)
        ]

        with patch('builtins.input', side_effect=inputs), \
             patch.object(cli, '_load_linear_config', return_value={}), \
             patch.object(cli, '_setup_api_key_from_1password') as mock_1pass_setup:

            cli.cmd_linear_setup(args)

            mock_1pass_setup.assert_called_once()

    def test_linear_setup_api_key_storage_error(self, cli_setup):
        """Test Linear setup with API key storage error"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org=None,
            team=None,
            project=None,
            api_key='invalid_key',
            from_1password=False
        )

        with patch.object(cli, '_store_linear_api_key', side_effect=ValueError("Invalid key format")):
            cli.cmd_linear_setup(args)
            # Should print error message about failed storage

    def test_linear_setup_1password_reference_with_quotes(self, cli_setup):
        """Test Linear setup with 1Password reference containing quotes"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org=None,
            team=None,
            project=None,
            api_key=None,
            from_1password=True
        )

        # Reference with quotes (as copied from 1Password)
        inputs = ['"op://Private/linear-api-key/password"']

        with patch('cproj.OnePasswordIntegration.is_available', return_value=True), \
             patch('builtins.input', side_effect=inputs), \
             patch('cproj.OnePasswordIntegration.get_secret', return_value='test_api_key'), \
             patch.object(cli, '_store_linear_1password_ref') as mock_store_ref:

            cli.cmd_linear_setup(args)

            # Should strip quotes from reference
            mock_store_ref.assert_called_once_with('op://Private/linear-api-key/password')

    def test_linear_setup_partial_command_line_args(self, cli_setup):
        """Test Linear setup with partial command-line arguments"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org='https://linear.app/partial',
            team=None,
            project='PARTIAL-PROJ',
            api_key=None,
            from_1password=False
        )

        cli.cmd_linear_setup(args)

        # Verify only provided arguments were set
        assert config.get('linear_org') == 'https://linear.app/partial'
        assert config.get('linear_default_team') is None
        assert config.get('linear_default_project') == 'PARTIAL-PROJ'

    def test_linear_setup_empty_1password_reference(self, cli_setup):
        """Test Linear setup with empty 1Password reference"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org=None,
            team=None,
            project=None,
            api_key=None,
            from_1password=True
        )

        inputs = ['']  # Empty reference

        with patch('cproj.OnePasswordIntegration.is_available', return_value=True), \
             patch('builtins.input', side_effect=inputs):

            cli.cmd_linear_setup(args)
            # Should print error message about no reference provided

    def test_linear_setup_interactive_api_key_store_error(self, cli_setup):
        """Test interactive setup with API key storage error"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org=None,
            team=None,
            project=None,
            api_key=None,
            from_1password=False
        )

        inputs = [
            'https://linear.app/test',  # Organization
            '',                         # Team (empty)
            '',                         # Project (empty)
            '2',                        # API key choice (enter directly)
            'invalid_key'               # API key
        ]

        with patch('builtins.input', side_effect=inputs), \
             patch.object(cli, '_load_linear_config', return_value={}), \
             patch.object(cli, '_store_linear_api_key', side_effect=ValueError("Invalid format")):

            cli.cmd_linear_setup(args)
            # Should print error message about failed storage

    def test_linear_setup_1password_ref_store_error(self, cli_setup):
        """Test 1Password reference storage error"""
        cli, config, temp_dir = cli_setup

        args = SimpleNamespace(
            org=None,
            team=None,
            project=None,
            api_key=None,
            from_1password=True
        )

        inputs = ['op://Private/linear-api-key/password']

        with patch('cproj.OnePasswordIntegration.is_available', return_value=True), \
             patch('builtins.input', side_effect=inputs), \
             patch('cproj.OnePasswordIntegration.get_secret', return_value='test_api_key'), \
             patch.object(cli, '_store_linear_1password_ref', side_effect=ValueError("Storage error")):

            cli.cmd_linear_setup(args)
            # Should print error message about failed storage


if __name__ == '__main__':
    pytest.main([__file__, '-v'])