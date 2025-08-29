#!/usr/bin/env python3
"""
Test suite for cproj
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from cproj import (
    Config, GitWorktree, AgentJson, EnvironmentSetup, 
    TerminalAutomation, GitHubIntegration, CprojCLI, CprojError
)


class TestConfig(unittest.TestCase):
    """Test Config class"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_path = self.temp_dir / 'config.json'
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_config_creation(self):
        config = Config(self.config_path)
        self.assertEqual(config._config, {})
    
    def test_config_get_set(self):
        config = Config(self.config_path)
        config.set('test_key', 'test_value')
        self.assertEqual(config.get('test_key'), 'test_value')
        self.assertEqual(config.get('missing_key', 'default'), 'default')
    
    def test_config_persistence(self):
        config = Config(self.config_path)
        config.set('persistent_key', 'persistent_value')
        
        # Create new config instance
        config2 = Config(self.config_path)
        self.assertEqual(config2.get('persistent_key'), 'persistent_value')


class TestAgentJson(unittest.TestCase):
    """Test AgentJson class"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_agent_json_creation(self):
        agent_json = AgentJson(self.temp_dir)
        self.assertIn('schema_version', agent_json.data)
        self.assertIn('agent', agent_json.data)
        self.assertIn('project', agent_json.data)
        self.assertIn('workspace', agent_json.data)
        self.assertIn('links', agent_json.data)
        self.assertIn('env', agent_json.data)
    
    def test_agent_json_save_load(self):
        agent_json = AgentJson(self.temp_dir)
        agent_json.set_project('Test Project', '/test/repo')
        agent_json.set_workspace('/test/workspace', 'feature/test', 'main')
        agent_json.save()
        
        # Load from file
        agent_json2 = AgentJson(self.temp_dir)
        self.assertEqual(agent_json2.data['project']['name'], 'Test Project')
        self.assertEqual(agent_json2.data['workspace']['branch'], 'feature/test')
    
    def test_agent_json_links(self):
        agent_json = AgentJson(self.temp_dir)
        agent_json.set_link('linear', 'https://linear.app/test')
        agent_json.set_link('pr', 'https://github.com/test/test/pull/1')
        
        self.assertEqual(agent_json.data['links']['linear'], 'https://linear.app/test')
        self.assertEqual(agent_json.data['links']['pr'], 'https://github.com/test/test/pull/1')


class TestEnvironmentSetup(unittest.TestCase):
    """Test EnvironmentSetup class"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_setup_python_no_files(self):
        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_python()
        
        self.assertEqual(result['manager'], 'none')
        self.assertFalse(result['active'])
        self.assertFalse(result['pyproject'])
        self.assertFalse(result['requirements'])
    
    def test_setup_python_with_requirements(self):
        # Create requirements.txt
        (self.temp_dir / 'requirements.txt').write_text('requests==2.28.0\n')
        
        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_python()
        
        self.assertTrue(result['requirements'])
    
    def test_setup_python_with_pyproject(self):
        # Create pyproject.toml
        (self.temp_dir / 'pyproject.toml').write_text('[project]\nname = "test"\n')
        
        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_python()
        
        self.assertTrue(result['pyproject'])
    
    def test_setup_node_no_package_json(self):
        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_node()
        
        self.assertEqual(result['manager'], 'none')
        self.assertEqual(result['node_version'], '')
    
    def test_setup_node_with_package_json(self):
        # Create package.json
        (self.temp_dir / 'package.json').write_text('{"name": "test", "version": "1.0.0"}')
        
        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_node()
        
        # Should detect package.json even if nvm isn't available
        self.assertEqual(result['manager'], 'none')  # nvm not available in test
    
    def test_setup_java_maven(self):
        # Create pom.xml
        (self.temp_dir / 'pom.xml').write_text('<project></project>')
        
        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_java()
        
        self.assertEqual(result['build'], 'maven')
    
    def test_setup_java_gradle(self):
        # Create build.gradle
        (self.temp_dir / 'build.gradle').write_text('apply plugin: "java"')
        
        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_java()
        
        self.assertEqual(result['build'], 'gradle')
    
    def test_setup_java_no_build_file(self):
        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_java()
        
        self.assertEqual(result['build'], 'none')


class TestGitHubIntegration(unittest.TestCase):
    """Test GitHubIntegration class"""
    
    @patch('shutil.which')
    def test_is_available_true(self, mock_which):
        mock_which.return_value = '/usr/bin/gh'
        self.assertTrue(GitHubIntegration.is_available())
        mock_which.assert_called_with('gh')
    
    @patch('shutil.which')
    def test_is_available_false(self, mock_which):
        mock_which.return_value = None
        self.assertFalse(GitHubIntegration.is_available())
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_create_pr_success(self, mock_which, mock_run):
        mock_which.return_value = '/usr/bin/gh'
        mock_run.return_value = Mock(stdout='https://github.com/test/test/pull/1\n', returncode=0)
        
        result = GitHubIntegration.create_pr('Test PR', 'Test body', draft=True)
        
        self.assertEqual(result, 'https://github.com/test/test/pull/1')
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_create_pr_failure(self, mock_which, mock_run):
        mock_which.return_value = '/usr/bin/gh'
        mock_run.side_effect = subprocess.CalledProcessError(1, 'gh')
        
        result = GitHubIntegration.create_pr('Test PR', 'Test body')
        
        self.assertIsNone(result)


class TestCprojCLI(unittest.TestCase):
    """Test CprojCLI class"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_path = self.temp_dir / 'config.json'
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    @patch('cproj.Config')
    def test_cli_creation(self, mock_config_class):
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        
        cli = CprojCLI()
        
        self.assertEqual(cli.config, mock_config)
        mock_config_class.assert_called_once()
    
    def test_create_parser(self):
        cli = CprojCLI()
        parser = cli.create_parser()
        
        # Test that parser is created
        self.assertIsNotNone(parser)
        
        # Test that it can parse basic commands
        args = parser.parse_args(['init', '--name', 'test'])
        self.assertEqual(args.command, 'init')
        self.assertEqual(args.name, 'test')
    
    def test_parser_worktree_create(self):
        cli = CprojCLI()
        parser = cli.create_parser()
        
        args = parser.parse_args(['worktree', 'create', '--branch', 'feature/test'])
        self.assertEqual(args.command, 'worktree')
        self.assertEqual(args.worktree_command, 'create')
        self.assertEqual(args.branch, 'feature/test')
    
    def test_parser_review_open(self):
        cli = CprojCLI()
        parser = cli.create_parser()
        
        args = parser.parse_args(['review', 'open', '--draft'])
        self.assertEqual(args.command, 'review')
        self.assertEqual(args.review_command, 'open')
        self.assertTrue(args.draft)
    
    def test_parser_config(self):
        cli = CprojCLI()
        parser = cli.create_parser()
        
        args = parser.parse_args(['config', 'editor', 'vim'])
        self.assertEqual(args.command, 'config')
        self.assertEqual(args.key, 'editor')
        self.assertEqual(args.value, 'vim')


class TestIntegration(unittest.TestCase):
    """Integration tests"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo_dir = self.temp_dir / 'test_repo'
        self.repo_dir.mkdir()
        
        # Initialize git repo
        import subprocess
        subprocess.run(['git', 'init'], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], 
                      cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], 
                      cwd=self.repo_dir, check=True, capture_output=True)
        
        # Create initial commit
        (self.repo_dir / 'README.md').write_text('# Test Repo')
        subprocess.run(['git', 'add', 'README.md'], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Initial commit'], 
                      cwd=self.repo_dir, check=True, capture_output=True)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_git_worktree_creation(self):
        git = GitWorktree(self.repo_dir)
        
        # Test worktree creation
        worktree_path = self.temp_dir / 'test_worktree'
        created_path = git.create_worktree(worktree_path, 'feature/test', 'main')
        
        self.assertEqual(created_path, worktree_path)
        self.assertTrue(worktree_path.exists())
        self.assertTrue((worktree_path / 'README.md').exists())
    
    def test_agent_json_workflow(self):
        # Create worktree
        worktree_path = self.temp_dir / 'test_worktree'
        worktree_path.mkdir()
        
        # Test AgentJson workflow
        agent_json = AgentJson(worktree_path)
        agent_json.set_project('Test Project', str(self.repo_dir))
        agent_json.set_workspace(str(worktree_path), 'feature/test', 'main')
        agent_json.set_link('linear', 'https://linear.app/test/issue/123')
        agent_json.save()
        
        # Verify file exists and is valid JSON
        json_file = worktree_path / '.agent.json'
        self.assertTrue(json_file.exists())
        
        with open(json_file) as f:
            data = json.load(f)
        
        self.assertEqual(data['project']['name'], 'Test Project')
        self.assertEqual(data['workspace']['branch'], 'feature/test')
        self.assertEqual(data['links']['linear'], 'https://linear.app/test/issue/123')


if __name__ == '__main__':
    unittest.main()