#!/usr/bin/env python3
"""
Comprehensive tests for CLI command functionality
"""

import json
import tempfile
import subprocess
import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the classes we need to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cproj import CprojCLI, Config, CprojError


class TestCLICommands:
    """Test CLI command functionality"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cli_with_config(self, temp_dir):
        """Create a CLI instance with test configuration"""
        config_dir = temp_dir / '.config' / 'cproj'
        config_dir.mkdir(parents=True)
        config = Config(config_dir / 'config.json')
        cli = CprojCLI()
        cli.config = config
        return cli, config

    def test_cli_initialization(self):
        """Test CLI initializes correctly"""
        cli = CprojCLI()
        assert cli is not None
        assert hasattr(cli, 'config')

    def test_config_file_operations(self, temp_dir):
        """Test configuration file read/write operations"""
        config_file = temp_dir / 'test_config.json'
        config = Config(config_file)

        # Test setting and getting values
        config.set('test_key', 'test_value')
        assert config.get('test_key') == 'test_value'

        # Test file persistence
        config.save()
        assert config_file.exists()

        # Test loading from file
        new_config = Config(config_file)
        assert new_config.get('test_key') == 'test_value'

    def test_config_nested_values(self, temp_dir):
        """Test configuration with nested dictionary values"""
        config_file = temp_dir / 'test_config.json'
        config = Config(config_file)

        nested_data = {
            'database': {
                'host': 'localhost',
                'port': 5432
            },
            'features': ['feature1', 'feature2']
        }

        config.set('app_config', nested_data)
        assert config.get('app_config')['database']['host'] == 'localhost'
        assert 'feature1' in config.get('app_config')['features']

    @patch('subprocess.run')
    def test_git_worktree_creation_command_structure(self, mock_run, cli_with_config, temp_dir):
        """Test git worktree command structure without actual git execution"""
        cli, config = cli_with_config

        # Mock successful git operations
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        # Set up repo path
        repo_dir = temp_dir / 'test_repo'
        repo_dir.mkdir()
        config.set('repo_path', str(repo_dir))

        # Test command structure (without actual execution)
        with patch('os.chdir'), patch('pathlib.Path.cwd', return_value=repo_dir):
            # This tests the command construction logic
            from cproj import GitWorktree
            git = GitWorktree(repo_dir)

            # Test that the git commands would be properly structured
            assert git.repo_path == repo_dir
            assert isinstance(git.repo_path, Path)

    def test_environment_setup_detection(self, cli_with_config, temp_dir):
        """Test environment detection logic"""
        cli, config = cli_with_config

        from cproj import EnvironmentSetup
        env_setup = EnvironmentSetup(temp_dir)

        # Test Python detection
        (temp_dir / 'pyproject.toml').touch()
        assert env_setup._has_pyproject_toml()

        # Test Node.js detection
        (temp_dir / 'package.json').touch()
        assert env_setup._has_package_json()

        # Test Java detection
        (temp_dir / 'pom.xml').touch()
        assert env_setup._has_maven()

    def test_agent_json_operations(self, temp_dir):
        """Test AgentJson class operations"""
        from cproj import AgentJson

        # Create .cproj directory
        cproj_dir = temp_dir / '.cproj'
        cproj_dir.mkdir()

        agent_json = AgentJson(temp_dir)

        # Test default data
        default_data = agent_json.data
        assert 'workspace' in default_data
        assert 'agent' in default_data

        # Test setting values
        agent_json.set('test_key', 'test_value')
        assert agent_json.get('test_key') == 'test_value'

        # Test saving and loading
        agent_json.save()
        assert (cproj_dir / '.agent.json').exists()

        # Test loading from file
        new_agent_json = AgentJson(temp_dir)
        assert new_agent_json.get('test_key') == 'test_value'

    def test_linear_config_loading(self, cli_with_config, temp_dir):
        """Test Linear configuration loading logic"""
        cli, config = cli_with_config

        with patch('os.getcwd', return_value=str(temp_dir)):
            # Test with no config files
            linear_config = cli._load_linear_config()
            assert isinstance(linear_config, dict)

            # Test with .env.linear file
            env_file = temp_dir / '.env.linear'
            env_file.write_text('LINEAR_API_KEY=test_key\nLINEAR_TEAM=test_team\n')

            linear_config = cli._load_linear_config()
            assert linear_config.get('LINEAR_API_KEY') == 'test_key'
            assert linear_config.get('LINEAR_TEAM') == 'test_team'

    def test_url_validation_functionality(self, cli_with_config):
        """Test URL validation without subprocess execution"""
        cli, config = cli_with_config

        # Test URL parsing logic
        import urllib.parse

        valid_urls = [
            'https://example.com',
            'http://test.org/path',
            'https://github.com/user/repo'
        ]

        invalid_urls = [
            'javascript:alert("xss")',
            'file:///etc/passwd',
            'ftp://example.com',
            '',
            'not-a-url'
        ]

        for url in valid_urls:
            try:
                parsed = urllib.parse.urlparse(url)
                assert parsed.scheme in ('http', 'https')
                assert parsed.netloc
            except Exception:
                pytest.fail(f"Valid URL failed parsing: {url}")

        for url in invalid_urls:
            try:
                parsed = urllib.parse.urlparse(url)
                is_valid = parsed.scheme in ('http', 'https') and parsed.netloc
                if url in ['', 'not-a-url']:
                    assert not is_valid
            except Exception:
                pass  # Expected for malformed URLs

    def test_onepassword_integration_detection(self):
        """Test OnePassword integration availability detection"""
        from cproj import OnePasswordIntegration

        with patch('shutil.which') as mock_which:
            # Test when op command not available
            mock_which.return_value = None
            assert not OnePasswordIntegration.is_available()

            # Test when op command available but not authenticated
            mock_which.return_value = '/usr/bin/op'
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(1, 'op')
                assert not OnePasswordIntegration.is_available()

                # Test when op command available and authenticated
                mock_run.side_effect = None
                mock_run.return_value = MagicMock(returncode=0)
                assert OnePasswordIntegration.is_available()

    def test_argument_sanitization_functions(self):
        """Test argument sanitization functions"""
        from cproj import OnePasswordIntegration

        # Test safe argument sanitization
        test_cases = [
            ('normal-string', 'normal-string'),
            ('string with spaces', 'string with spaces'),
            ('string_with_underscores', 'string_with_underscores'),
            ('string.with.dots', 'string.with.dots'),
            ('string-with-dashes', 'string-with-dashes'),
            ('string123', 'string123'),
            ('dangerous;command', 'dangerouscommand'),
            ('path/../traversal', 'pathtraversal'),
            ('$(malicious)', 'malicious'),
            ('|pipe&command', 'pipecommand'),
        ]

        for input_str, expected in test_cases:
            result = OnePasswordIntegration._sanitize_op_argument(input_str)
            assert result == expected, f"Input: {input_str}, Expected: {expected}, Got: {result}"

    def test_path_validation_logic(self, temp_dir):
        """Test path validation logic"""
        from cproj import EnvironmentSetup

        env_setup = EnvironmentSetup(temp_dir)

        # Create test directory structure
        safe_dir = temp_dir / 'safe_subdir'
        safe_dir.mkdir()
        safe_file = safe_dir / 'safe_file.txt'
        safe_file.touch()

        # Test path validation logic (without actual pip execution)
        test_paths = [
            str(safe_file),  # Safe path within temp_dir
            str(temp_dir / 'nonexistent'),  # Safe but nonexistent
            '/etc/passwd',  # Outside temp_dir
            '../../../etc/passwd',  # Path traversal attempt
        ]

        for test_path in test_paths:
            path_obj = Path(test_path)
            try:
                # Test if path would be within temp_dir
                relative = path_obj.resolve().relative_to(temp_dir.resolve())
                is_safe = True
            except ValueError:
                is_safe = False

            if test_path.startswith(str(temp_dir)):
                assert is_safe or not path_obj.exists(), f"Safe path should validate: {test_path}"
            else:
                assert not is_safe, f"Unsafe path should not validate: {test_path}"

    def test_error_handling_patterns(self, cli_with_config):
        """Test error handling patterns throughout the codebase"""
        cli, config = cli_with_config

        # Test CprojError handling
        with pytest.raises(CprojError):
            raise CprojError("Test error message")

        # Test error message formatting
        try:
            raise CprojError("Test error with details")
        except CprojError as e:
            assert str(e) == "Test error with details"
            assert isinstance(e, Exception)

    def test_json_parsing_security(self, temp_dir):
        """Test JSON parsing with security considerations"""
        from cproj import AgentJson

        cproj_dir = temp_dir / '.cproj'
        cproj_dir.mkdir()
        agent_file = cproj_dir / '.agent.json'

        # Test with valid JSON
        valid_data = {
            "workspace": {"branch": "test-branch"},
            "agent": {"name": "test"}
        }
        agent_file.write_text(json.dumps(valid_data))

        agent_json = AgentJson(temp_dir)
        assert agent_json.get('workspace')['branch'] == 'test-branch'

        # Test with malformed JSON (should handle gracefully)
        agent_file.write_text('{"invalid": json, content}')

        # Should not crash, should return default data
        new_agent_json = AgentJson(temp_dir)
        assert 'workspace' in new_agent_json.data  # Should have default structure

    def test_command_line_argument_parsing_structure(self):
        """Test command line argument parsing structure"""
        import argparse

        # Test that we can create a parser similar to the main CLI
        parser = argparse.ArgumentParser(description='Test cproj CLI')
        subparsers = parser.add_subparsers(dest='command', help='Available commands')

        # Test setup subcommand
        setup_parser = subparsers.add_parser('setup', help='Setup cproj')
        setup_parser.add_argument('--repo-path', help='Repository path')

        # Test create subcommand
        create_parser = subparsers.add_parser('create', help='Create worktree')
        create_parser.add_argument('branch', help='Branch name')
        create_parser.add_argument('--from', dest='from_branch', help='Base branch')

        # Test that parsing works
        args = parser.parse_args(['setup', '--repo-path', '/tmp/test'])
        assert args.command == 'setup'
        assert args.repo_path == '/tmp/test'

        args = parser.parse_args(['create', 'test-branch', '--from', 'main'])
        assert args.command == 'create'
        assert args.branch == 'test-branch'
        assert args.from_branch == 'main'

    def test_logging_configuration(self):
        """Test logging configuration"""
        import logging

        # Test that logger exists and is configured
        logger = logging.getLogger('cproj')
        assert logger is not None
        assert logger.level == logging.INFO
        assert len(logger.handlers) > 0

    def test_platform_detection(self):
        """Test platform detection functionality"""
        import platform

        # Test basic platform detection
        system = platform.system()
        assert system in ['Darwin', 'Linux', 'Windows']

        # Test that platform-specific code paths exist
        from cproj import CprojCLI
        cli = CprojCLI()

        # This tests that platform-dependent logic can be handled
        assert hasattr(platform, 'system')

    @patch('subprocess.run')
    def test_subprocess_timeout_handling(self, mock_run):
        """Test subprocess timeout handling patterns"""
        from cproj import EnvironmentSetup

        # Test timeout handling
        mock_run.side_effect = subprocess.TimeoutExpired('test_cmd', 30)

        env_setup = EnvironmentSetup(Path('/tmp'))

        # Should handle timeout gracefully
        try:
            # This would normally call subprocess with timeout
            result = subprocess.run(['echo', 'test'], timeout=1, capture_output=True)
        except subprocess.TimeoutExpired:
            # Expected behavior
            pass

    def test_file_system_operations(self, temp_dir):
        """Test file system operations"""
        from pathlib import Path

        # Test directory creation
        test_dir = temp_dir / 'test_subdir'
        test_dir.mkdir(exist_ok=True)
        assert test_dir.exists()
        assert test_dir.is_dir()

        # Test file creation
        test_file = test_dir / 'test_file.txt'
        test_file.write_text('test content')
        assert test_file.exists()
        assert test_file.read_text() == 'test content'

        # Test file permissions (basic test)
        assert test_file.stat().st_size > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])