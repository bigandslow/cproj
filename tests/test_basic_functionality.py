#!/usr/bin/env python3
"""
Tests for basic functionality of cproj core classes

Tests Config, AgentJson, GitWorktree, and other core functionality
to ensure the security fixes don't break existing features.
"""

import json

# Import the classes we need to test
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cproj import AgentJson, Config, CprojError, EnvironmentSetup, GitWorktree


class TestConfig:
    """Test Config class functionality"""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary directory for config tests"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_config_initialization(self, temp_config_dir):
        """Test that Config initializes correctly"""
        config_path = temp_config_dir / 'config.json'
        config = Config(config_path)

        assert config.config_path == config_path
        assert isinstance(config._config, dict)

    def test_config_save_and_load(self, temp_config_dir):
        """Test that Config can save and load data"""
        config_path = temp_config_dir / 'config.json'
        config = Config(config_path)

        # Set some test data
        test_data = {
            'repo_path': '/test/repo',
            'project_name': 'Test Project',
            'base_branch': 'main'
        }

        for key, value in test_data.items():
            config.set(key, value)

        # Create a new config instance and verify data persisted
        config2 = Config(config_path)
        for key, value in test_data.items():
            assert config2.get(key) == value

    def test_config_get_with_default(self, temp_config_dir):
        """Test Config.get() with default values"""
        config_path = temp_config_dir / 'config.json'
        config = Config(config_path)

        # Test getting non-existent key with default
        assert config.get('nonexistent', 'default_value') == 'default_value'
        assert config.get('nonexistent') is None

        # Set a value and verify it's returned instead of default
        config.set('existing_key', 'actual_value')
        assert config.get('existing_key', 'default_value') == 'actual_value'

    def test_config_handles_missing_parent_directory(self, temp_config_dir):
        """Test that Config creates parent directories if needed"""
        config_path = temp_config_dir / 'nested' / 'subdir' / 'config.json'
        config = Config(config_path)

        config.set('test_key', 'test_value')

        assert config_path.exists()
        assert config_path.parent.exists()


class TestAgentJson:
    """Test AgentJson class functionality"""

    @pytest.fixture
    def temp_worktree(self):
        """Create a temporary worktree directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir)
            cproj_dir = worktree_path / '.cproj'
            cproj_dir.mkdir()
            yield worktree_path

    def test_agent_json_initialization_new(self, temp_worktree):
        """Test AgentJson initialization for new workspace"""
        agent_json = AgentJson(temp_worktree)

        assert agent_json.path == temp_worktree / '.cproj' / '.agent.json'
        assert 'schema_version' in agent_json.data
        assert 'agent' in agent_json.data
        assert 'project' in agent_json.data
        assert 'workspace' in agent_json.data
        assert 'links' in agent_json.data
        assert 'env' in agent_json.data

    def test_agent_json_save_and_load(self, temp_worktree):
        """Test that AgentJson can save and load data"""
        agent_json = AgentJson(temp_worktree)

        # Set some test data
        agent_json.set_project('Test Project', '/test/repo')
        agent_json.set_workspace(str(temp_worktree), 'test-branch', 'main')
        agent_json.set_link('linear', 'https://linear.app/test')

        # Save the data
        agent_json.save()

        # Load it again and verify
        agent_json2 = AgentJson(temp_worktree)
        assert agent_json2.data['project']['name'] == 'Test Project'
        assert agent_json2.data['workspace']['branch'] == 'test-branch'
        assert agent_json2.data['links']['linear'] == 'https://linear.app/test'

    def test_agent_json_handles_corrupted_file(self, temp_worktree):
        """Test that AgentJson handles corrupted JSON files gracefully"""
        agent_json_path = temp_worktree / '.cproj' / '.agent.json'

        # Write corrupted JSON
        agent_json_path.write_text('{"invalid": json, content}')

        # Should create new data instead of crashing
        agent_json = AgentJson(temp_worktree)
        assert 'schema_version' in agent_json.data  # Should have default structure

    def test_agent_json_set_methods(self, temp_worktree):
        """Test AgentJson setter methods"""
        agent_json = AgentJson(temp_worktree)

        # Test set_project
        agent_json.set_project('My Project', '/path/to/repo')
        assert agent_json.data['project']['name'] == 'My Project'
        assert agent_json.data['project']['repo_path'] == '/path/to/repo'

        # Test set_workspace
        agent_json.set_workspace('/path/to/workspace', 'feature-branch', 'main')
        assert agent_json.data['workspace']['path'] == '/path/to/workspace'
        assert agent_json.data['workspace']['branch'] == 'feature-branch'
        assert agent_json.data['workspace']['base'] == 'main'
        assert 'created_at' in agent_json.data['workspace']

        # Test set_link
        agent_json.set_link('pr', 'https://github.com/user/repo/pull/123')
        assert agent_json.data['links']['pr'] == 'https://github.com/user/repo/pull/123'


class TestEnvironmentSetup:
    """Test EnvironmentSetup class functionality"""

    @pytest.fixture
    def temp_worktree(self):
        """Create a temporary worktree directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_environment_setup_initialization(self, temp_worktree):
        """Test EnvironmentSetup initialization"""
        env_setup = EnvironmentSetup(temp_worktree)
        assert env_setup.worktree_path == temp_worktree

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_setup_python_uv_success(self, mock_which, mock_run, temp_worktree):
        """Test successful Python setup with uv"""
        mock_which.return_value = '/usr/bin/uv'
        mock_run.return_value = MagicMock(returncode=0)

        # Create pyproject.toml
        (temp_worktree / 'pyproject.toml').write_text('[project]\nname = "test"\n')

        env_setup = EnvironmentSetup(temp_worktree)
        result = env_setup.setup_python(auto_install=False)

        assert result['manager'] == 'uv'
        assert result['active'] is True

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_setup_python_venv_fallback(self, mock_which, mock_run, temp_worktree):
        """Test Python setup falls back to venv when uv unavailable"""
        # uv not available
        mock_which.side_effect = lambda cmd: None if cmd == 'uv' else '/usr/bin/python3'
        mock_run.return_value = MagicMock(returncode=0)

        # Create requirements.txt
        (temp_worktree / 'requirements.txt').write_text('requests==2.28.0\n')

        env_setup = EnvironmentSetup(temp_worktree)
        result = env_setup.setup_python(auto_install=False)

        assert result['manager'] == 'venv'
        assert result['active'] is True

    def test_detect_python_files(self, temp_worktree):
        """Test Python file detection"""
        env_setup = EnvironmentSetup(temp_worktree)

        # No Python files initially
        result = env_setup.setup_python(auto_install=False)
        assert not result['pyproject']
        assert not result['requirements']

        # Create Python files
        (temp_worktree / 'pyproject.toml').write_text('[project]\nname = "test"\n')
        (temp_worktree / 'requirements.txt').write_text('requests==2.28.0\n')

        result = env_setup.setup_python(auto_install=False)
        assert result['pyproject']
        assert result['requirements']

    def test_detect_node_files(self, temp_worktree):
        """Test Node.js file detection"""
        env_setup = EnvironmentSetup(temp_worktree)

        # Create package.json
        package_json = {
            "name": "test-project",
            "version": "1.0.0",
            "dependencies": {
                "express": "^4.18.0"
            }
        }
        (temp_worktree / 'package.json').write_text(json.dumps(package_json))

        # Should detect Node.js project
        setup_result = env_setup.setup_node(auto_install=False)
        # Basic structure should be returned even without nvm
        assert 'manager' in setup_result

    def test_detect_java_files(self, temp_worktree):
        """Test Java file detection"""
        env_setup = EnvironmentSetup(temp_worktree)

        # Test Maven detection
        (temp_worktree / 'pom.xml').write_text('<project></project>')
        java_result = env_setup.setup_java(auto_build=False)
        assert 'build' in java_result

        # Clean up and test Gradle detection
        (temp_worktree / 'pom.xml').unlink()
        (temp_worktree / 'build.gradle').write_text('apply plugin: "java"')
        java_result = env_setup.setup_java(auto_build=False)
        assert 'build' in java_result


class TestGitWorktree:
    """Test GitWorktree class functionality"""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary git repository"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize git repo
            import subprocess
            subprocess.run(['git', 'init'], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.email', 'test@example.com'],
                          cwd=repo_path, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.name', 'Test User'],
                          cwd=repo_path, check=True, capture_output=True)

            # Create initial commit
            (repo_path / 'README.md').write_text('# Test Repo')
            subprocess.run(['git', 'add', 'README.md'], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(['git', 'commit', '-m', 'Initial commit'],
                          cwd=repo_path, check=True, capture_output=True)
            subprocess.run(['git', 'branch', '-M', 'main'], cwd=repo_path, check=True, capture_output=True)

            yield repo_path

    def test_git_worktree_initialization(self, temp_repo):
        """Test GitWorktree initialization"""
        git_wt = GitWorktree(temp_repo)
        assert git_wt.repo_path == temp_repo

    def test_git_worktree_invalid_repo(self):
        """Test GitWorktree with invalid repository"""
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_repo = Path(tmpdir)
            with pytest.raises(CprojError, match="Not a git repository"):
                GitWorktree(invalid_repo)

    @patch('subprocess.run')
    def test_git_worktree_fetch_all(self, mock_run, temp_repo):
        """Test fetch_all method"""
        mock_run.return_value = MagicMock(returncode=0)

        git_wt = GitWorktree(temp_repo)
        git_wt.fetch_all()

        # Should have called git fetch
        mock_run.assert_called()
        call_args = mock_run.call_args[0][0]
        assert 'fetch' in call_args
        assert '--all' in call_args
        assert '--prune' in call_args

    def test_git_worktree_branch_exists(self, temp_repo):
        """Test branch_exists method"""
        git_wt = GitWorktree(temp_repo)

        # Main branch should exist
        assert git_wt.branch_exists('main') is True

        # Non-existent branch should not exist
        assert git_wt.branch_exists('nonexistent-branch') is False

    def test_git_worktree_find_git_root(self, temp_repo):
        """Test _find_git_root method"""
        git_wt = GitWorktree(temp_repo)

        # Should find the git root
        assert git_wt._find_git_root(temp_repo) == temp_repo

        # Should work from subdirectory
        subdir = temp_repo / 'subdir'
        subdir.mkdir()
        assert git_wt._find_git_root(subdir) == temp_repo


class TestCprojIntegration:
    """Test integration between components"""

    @pytest.fixture
    def temp_setup(self):
        """Create a complete temporary setup"""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Create repo directory
            repo_path = base_path / 'repo'
            repo_path.mkdir()

            # Create worktree directory
            worktree_path = base_path / 'worktree'
            worktree_path.mkdir()
            (worktree_path / '.cproj').mkdir()

            # Create config directory
            config_path = base_path / 'config'
            config_path.mkdir()

            yield {
                'base': base_path,
                'repo': repo_path,
                'worktree': worktree_path,
                'config': config_path
            }

    def test_config_agent_json_integration(self, temp_setup):
        """Test that Config and AgentJson work together"""
        config_path = temp_setup['config'] / 'config.json'
        config = Config(config_path)

        # Set up config
        config.set('project_name', 'Test Project')
        config.set('repo_path', str(temp_setup['repo']))

        # Create AgentJson
        agent_json = AgentJson(temp_setup['worktree'])
        agent_json.set_project(
            config.get('project_name'),
            config.get('repo_path')
        )

        # Verify integration
        assert agent_json.data['project']['name'] == 'Test Project'
        assert agent_json.data['project']['repo_path'] == str(temp_setup['repo'])

    def test_environment_agent_json_integration(self, temp_setup):
        """Test that EnvironmentSetup and AgentJson work together"""
        # Create Python files
        worktree_path = temp_setup['worktree']
        (worktree_path / 'requirements.txt').write_text('requests==2.28.0\n')

        # Set up environment
        env_setup = EnvironmentSetup(worktree_path)

        with patch('subprocess.run') as mock_run, \
             patch('shutil.which') as mock_which:

            mock_which.return_value = None  # No uv, fall back to venv
            mock_run.return_value = MagicMock(returncode=0)

            python_env = env_setup.setup_python(auto_install=False)

        # Create AgentJson and record environment
        agent_json = AgentJson(worktree_path)
        agent_json.data['env']['python'] = python_env

        # Verify integration
        assert 'python' in agent_json.data['env']
        assert agent_json.data['env']['python']['manager'] == 'venv'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
