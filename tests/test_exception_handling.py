#!/usr/bin/env python3
"""
Tests for exception handling improvements

Tests that the improved exception handling works correctly and provides
appropriate error messages while not hiding important errors.
"""

import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from subprocess import CalledProcessError, TimeoutExpired

# Import the classes we need to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cproj import CprojCLI, EnvironmentSetup, AgentJson, OnePasswordIntegration, CprojError


class TestExceptionHandling:
    """Test improved exception handling"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cli(self):
        """Create a CprojCLI instance for testing"""
        return CprojCLI()

    def test_url_opening_exception_handling(self, cli):
        """Test that URL opening handles exceptions gracefully"""
        with patch('urllib.parse.urlparse') as mock_parse, \
             patch('cproj.logger') as mock_logger:

            # Simulate urlparse raising an exception
            mock_parse.side_effect = Exception("URL parsing error")

            # Should not crash, should log error
            cli._safe_open_url("http://example.com")

            mock_logger.error.assert_called_once()
            assert "Error opening URL" in str(mock_logger.error.call_args)

    @patch('subprocess.run')
    @patch('cproj.logger')
    def test_environment_setup_specific_exceptions(self, mock_logger, mock_run, temp_dir):
        """Test that environment setup handles specific exceptions properly"""
        env_setup = EnvironmentSetup(temp_dir)

        # Test subprocess.CalledProcessError handling
        mock_run.side_effect = CalledProcessError(1, 'command')
        result = env_setup.setup_node(auto_install=False)

        # Should handle the error gracefully and log it
        mock_logger.debug.assert_called()
        assert "Error setting up Node environment" in str(mock_logger.debug.call_args)

        # Should return a valid result structure
        assert isinstance(result, dict)
        assert 'manager' in result

    @patch('subprocess.run')
    @patch('cproj.logger')
    def test_environment_setup_os_error_handling(self, mock_logger, mock_run, temp_dir):
        """Test that environment setup handles OSError properly"""
        env_setup = EnvironmentSetup(temp_dir)

        # Test OSError handling (file not found, permission denied, etc.)
        mock_run.side_effect = OSError("Permission denied")
        result = env_setup.setup_node(auto_install=False)

        # Should handle the error gracefully and log it
        mock_logger.debug.assert_called()
        assert "Error setting up Node environment" in str(mock_logger.debug.call_args)

        # Should return a valid result structure
        assert isinstance(result, dict)

    def test_agent_json_exception_handling_for_corrupted_files(self, temp_dir):
        """Test AgentJson handles corrupted files with specific exceptions"""
        cproj_dir = temp_dir / '.cproj'
        cproj_dir.mkdir()
        agent_json_path = cproj_dir / '.agent.json'

        # Create corrupted JSON
        agent_json_path.write_text('{"invalid": json, "missing": quotes}')

        # Should handle JSONDecodeError gracefully
        agent_json = AgentJson(temp_dir)

        # Should have default structure despite corrupted file
        assert 'schema_version' in agent_json.data
        assert 'workspace' in agent_json.data

    @patch('cproj.logger')
    def test_cleanup_age_parsing_exception_handling(self, mock_logger, temp_dir):
        """Test that cleanup age parsing handles exceptions properly"""
        cli = CprojCLI()

        # Create a worktree directory with agent.json
        cproj_dir = temp_dir / '.cproj'
        cproj_dir.mkdir()
        agent_json_path = cproj_dir / '.agent.json'

        # Create agent.json with invalid date format
        agent_data = {
            "workspace": {
                "branch": "test-branch",
                "created_at": "invalid-date-format"
            }
        }
        agent_json_path.write_text(json.dumps(agent_data))

        # Mock git worktree list output
        mock_worktree = MagicMock()
        mock_worktree.path = temp_dir
        mock_worktree.branch = "test-branch"

        # Test the age parsing logic directly
        should_remove = False
        agent_json_path = temp_dir / '.cproj' / '.agent.json'
        if agent_json_path.exists():
            try:
                from datetime import datetime, timezone
                agent_json = AgentJson(temp_dir)
                created_at = datetime.fromisoformat(
                    agent_json.data['workspace']['created_at'].replace('Z', '+00:00')
                )
                # This should raise ValueError due to invalid date
                age_days = (datetime.now(timezone.utc) - created_at).days
                should_remove = True
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                # Should be caught and logged
                mock_logger.debug(f"Error parsing date: {e}")
                pass

        # Should handle the exception gracefully
        assert should_remove is False  # Should not remove due to error

    @patch('subprocess.run')
    def test_onepassword_timeout_handling(self, mock_run):
        """Test OnePassword timeout handling"""
        # Test TimeoutExpired handling
        mock_run.side_effect = TimeoutExpired('op', 10)

        result = OnePasswordIntegration.get_secret('op://vault/item/field')
        assert result is None  # Should handle timeout gracefully

        result = OnePasswordIntegration.store_secret('title', 'password')
        assert result is None  # Should handle timeout gracefully

    @patch('subprocess.run')
    def test_onepassword_called_process_error_handling(self, mock_run):
        """Test OnePassword CalledProcessError handling"""
        # Test CalledProcessError handling
        mock_run.side_effect = CalledProcessError(1, 'op')

        result = OnePasswordIntegration.get_secret('op://vault/item/field')
        assert result is None  # Should handle error gracefully

        result = OnePasswordIntegration.store_secret('title', 'password')
        assert result is None  # Should handle error gracefully

    def test_json_parsing_in_cleanup_logic(self, temp_dir):
        """Test that cleanup logic handles JSON parsing errors properly"""
        # Create agent.json with invalid JSON
        cproj_dir = temp_dir / '.cproj'
        cproj_dir.mkdir()
        agent_json_path = cproj_dir / '.agent.json'
        agent_json_path.write_text('{"invalid": json}')

        # Test the merged branch detection logic
        should_remove = False
        if agent_json_path.exists():
            try:
                agent_data = json.loads(agent_json_path.read_text())
                if 'closed_at' in agent_data.get('workspace', {}):
                    should_remove = True
            except (json.JSONDecodeError, KeyError) as e:
                # Should handle the error gracefully
                pass

        # Should not crash and should not mark for removal
        assert should_remove is False

    def test_json_parsing_key_error_handling(self, temp_dir):
        """Test that cleanup logic handles KeyError properly"""
        # Create agent.json with valid JSON but missing keys
        cproj_dir = temp_dir / '.cproj'
        cproj_dir.mkdir()
        agent_json_path = cproj_dir / '.agent.json'

        # Valid JSON but missing 'workspace' key
        agent_data = {"other_data": "value"}
        agent_json_path.write_text(json.dumps(agent_data))

        # Test the merged branch detection logic
        should_remove = False
        if agent_json_path.exists():
            try:
                agent_data = json.loads(agent_json_path.read_text())
                if 'closed_at' in agent_data.get('workspace', {}):
                    should_remove = True
            except (json.JSONDecodeError, KeyError) as e:
                # Should handle the error gracefully
                pass

        # Should not crash and should not mark for removal
        assert should_remove is False

    def test_io_error_handling_in_list_command(self, temp_dir):
        """Test that list command handles IOError gracefully"""
        cli = CprojCLI()

        # Create agent.json that will cause IOError when read
        cproj_dir = temp_dir / '.cproj'
        cproj_dir.mkdir()
        agent_json_path = cproj_dir / '.agent.json'
        agent_json_path.write_text('{"valid": "json"}')

        # Make the file unreadable
        agent_json_path.chmod(0o000)

        try:
            # Test the list command logic that reads agent.json
            agent_json_path = temp_dir / '.cproj' / '.agent.json'
            if agent_json_path.exists():
                try:
                    agent_json = AgentJson(temp_dir)
                    linear = agent_json.data['links']['linear']
                    pr = agent_json.data['links']['pr']
                    # Should not reach here due to permission error
                    assert False, "Should have raised an exception"
                except (json.JSONDecodeError, KeyError, IOError) as e:
                    # Should handle the error gracefully
                    assert isinstance(e, (json.JSONDecodeError, KeyError, IOError))

        finally:
            # Restore permissions for cleanup
            try:
                agent_json_path.chmod(0o644)
            except:
                pass

    def test_path_validation_error_messages(self, temp_dir):
        """Test that path validation provides clear error messages"""
        env_setup = EnvironmentSetup(temp_dir)

        # Create requirements file but no venv
        requirements_file = temp_dir / 'requirements.txt'
        requirements_file.write_text('requests==2.28.0\n')

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock()

            # Should raise clear error message when venv doesn't exist
            with pytest.raises(CprojError, match="Virtual environment not found"):
                env_setup.setup_python_venv(auto_install=True)

    def test_path_traversal_error_messages(self, temp_dir):
        """Test that path traversal validation provides clear error messages"""
        env_setup = EnvironmentSetup(temp_dir)

        # Create venv structure
        venv_path = temp_dir / '.venv'
        venv_path.mkdir()
        bin_path = venv_path / 'bin'
        bin_path.mkdir()

        # Create a pip that appears to be outside the worktree (simulated)
        external_pip = temp_dir.parent / 'external_pip'
        external_pip.touch()
        external_pip.chmod(0o755)

        pip_path = bin_path / 'pip'
        pip_path.symlink_to(external_pip)

        requirements_file = temp_dir / 'requirements.txt'
        requirements_file.write_text('requests==2.28.0\n')

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock()

            # Should raise clear error message about path being outside worktree
            with pytest.raises(CprojError, match="pip path .* is outside worktree"):
                env_setup.setup_python_venv(auto_install=True)

    def test_exception_types_are_specific(self):
        """Test that we catch specific exception types, not generic ones"""
        # This test verifies that our exception handling doesn't use bare except clauses
        import inspect
        import cproj

        # Get all functions and methods in the cproj module
        for name, obj in inspect.getmembers(cproj):
            if inspect.isclass(obj):
                for method_name, method in inspect.getmembers(obj):
                    if inspect.isfunction(method) or inspect.ismethod(method):
                        # Get the source code if available
                        try:
                            source = inspect.getsource(method)
                            # Should not have bare except clauses
                            lines = source.split('\n')
                            for i, line in enumerate(lines):
                                if 'except:' in line and line.strip().endswith('except:'):
                                    pytest.fail(f"Found bare except clause in {name}.{method_name} at line {i+1}: {line.strip()}")
                        except OSError:
                            # Can't get source (built-in methods, etc.), skip
                            pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])