#!/usr/bin/env python3
"""
Integration tests for CLI commands with real subprocess execution
"""

import tempfile
import subprocess
import pytest
import os
import json
import sys
import shutil
from pathlib import Path
from unittest.mock import patch

# Import the classes we need to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cproj import CprojCLI, Config, CprojError


@pytest.mark.integration
class TestCLIIntegration:
    """Integration tests for CLI commands with real execution"""

    @pytest.fixture
    def real_git_repo(self):
        """Create a real git repository for CLI testing"""
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
            (repo_dir / 'README.md').write_text('# Test CLI Repository')
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
        cli.config = config

        return cli, config, real_git_repo

    def test_cli_help_command(self):
        """Test CLI help output"""
        # Test main help
        result = subprocess.run([sys.executable, 'cproj.py', '--help'],
                               capture_output=True, text=True)
        assert result.returncode == 0
        assert 'cproj' in result.stdout
        assert 'Multi-project CLI' in result.stdout

    def test_cli_setup_command_integration(self, cli_setup):
        """Test CLI setup command with real operations"""
        cli, config, repo_dir = cli_setup

        # Change to repo directory
        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            # Test setup command
            from types import SimpleNamespace
            args = SimpleNamespace(
                repo_path=str(repo_dir),
                agent_name='test-agent',
                agent_email='test@example.com'
            )

            # This should work without throwing exceptions
            cli.cmd_setup(args)

            # Verify config was updated
            assert config.get('repo_path') == str(repo_dir)

        finally:
            os.chdir(original_cwd)

    def test_cli_create_worktree_integration(self, cli_setup):
        """Test CLI worktree creation with real git operations"""
        cli, config, repo_dir = cli_setup

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            # Test create command
            from types import SimpleNamespace
            args = SimpleNamespace(
                branch='feature/cli-test',
                from_branch='main',
                issue=None,
                no_env=True,  # Skip environment setup for this test
                ticket=None
            )

            # Create worktree
            cli.cmd_create(args)

            # Verify worktree was created
            worktrees_dir = Path(config.get('worktrees_path', repo_dir.parent / 'worktrees'))
            expected_worktree = worktrees_dir / 'feature_cli-test'

            # The worktree should exist
            assert expected_worktree.exists() or any(
                'cli-test' in p.name for p in worktrees_dir.iterdir() if p.is_dir()
            )

        finally:
            os.chdir(original_cwd)

    def test_cli_list_command_integration(self, cli_setup):
        """Test CLI list command with real worktrees"""
        cli, config, repo_dir = cli_setup

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            # Create a worktree first
            from cproj import GitWorktree
            git = GitWorktree(repo_dir)
            worktree_path = repo_dir.parent / 'test_list_worktree'
            git.create_worktree(worktree_path, 'feature/list-test', 'main')

            # Test list command
            from types import SimpleNamespace
            args = SimpleNamespace(
                json=False,
                long=False
            )

            # This should work and show worktrees
            cli.cmd_list(args)

            # Clean up
            git.remove_worktree(worktree_path)

        finally:
            os.chdir(original_cwd)

    def test_cli_status_command_integration(self, cli_setup):
        """Test CLI status command with real git state"""
        cli, config, repo_dir = cli_setup

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            # Create some changes to show in status
            test_file = repo_dir / 'status_test.py'
            test_file.write_text('# Status test file\nprint("testing status")\n')

            # Test status command
            from types import SimpleNamespace
            args = SimpleNamespace(
                json=False
            )

            # This should work and show git status
            cli.cmd_status(args)

        finally:
            os.chdir(original_cwd)

    def test_cli_config_operations_integration(self, cli_setup):
        """Test CLI configuration operations"""
        cli, config, repo_dir = cli_setup

        # Test setting configuration values
        test_values = {
            'test_string': 'hello world',
            'test_number': '42',
            'test_path': str(repo_dir / 'test_path'),
        }

        for key, value in test_values.items():
            from types import SimpleNamespace
            args = SimpleNamespace(
                key=key,
                value=value,
                get=False,
                list=False,
                unset=False
            )

            cli.cmd_config(args)

            # Verify value was set
            assert config.get(key) == value

        # Test getting configuration values
        for key, expected_value in test_values.items():
            from types import SimpleNamespace
            args = SimpleNamespace(
                key=key,
                value=None,
                get=True,
                list=False,
                unset=False
            )

            # This should work without throwing exceptions
            cli.cmd_config(args)

        # Test listing all configuration
        from types import SimpleNamespace
        args = SimpleNamespace(
            key=None,
            value=None,
            get=False,
            list=True,
            unset=False
        )

        cli.cmd_config(args)

    def test_cli_cleanup_integration(self, cli_setup):
        """Test CLI cleanup command with real worktrees"""
        cli, config, repo_dir = cli_setup

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            # Create a worktree to clean up
            from cproj import GitWorktree
            git = GitWorktree(repo_dir)
            worktree_path = repo_dir.parent / 'cleanup_test_worktree'
            git.create_worktree(worktree_path, 'feature/cleanup-test', 'main')

            # Verify it exists
            assert worktree_path.exists()

            # Test cleanup command (dry run first)
            from types import SimpleNamespace
            args = SimpleNamespace(
                older_than=None,
                newer_than=None,
                merged_only=False,
                force=True,  # Force to avoid interactive prompts
                dry_run=True,
                yes=True
            )

            cli.cmd_cleanup(args)

            # Worktree should still exist after dry run
            assert worktree_path.exists()

            # Now do actual cleanup
            args.dry_run = False
            cli.cmd_cleanup(args)

            # Worktree should be removed
            assert not worktree_path.exists()

        finally:
            os.chdir(original_cwd)

    def test_cli_linear_integration_basic(self, cli_setup):
        """Test Linear integration setup (without real API calls)"""
        cli, config, repo_dir = cli_setup

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            # Test linear setup with manual API key
            from types import SimpleNamespace
            args = SimpleNamespace(
                api_key='test-api-key-123',
                team='test-team',
                project=None,
                org=None,
                from_1password=False
            )

            # This should create .env.linear file
            cli.cmd_linear_setup(args)

            # Verify .env.linear was created
            env_file = repo_dir / '.env.linear'
            assert env_file.exists()

            content = env_file.read_text()
            assert 'LINEAR_API_KEY=test-api-key-123' in content
            assert 'LINEAR_TEAM=test-team' in content

        finally:
            os.chdir(original_cwd)

    @pytest.mark.skipif(not shutil.which('op'), reason="1Password CLI not available")
    def test_cli_onepassword_integration(self, cli_setup):
        """Test 1Password integration (if available)"""
        cli, config, repo_dir = cli_setup

        from cproj import OnePasswordIntegration

        # Test availability check
        is_available = OnePasswordIntegration.is_available()

        if is_available:
            # Test argument sanitization
            test_ref = "op://Private/test-item/password"
            sanitized = OnePasswordIntegration._sanitize_op_argument(test_ref)
            assert sanitized == test_ref  # Should not change valid reference

            # Test with potentially dangerous input
            dangerous_ref = "op://Private/test; rm -rf /"
            sanitized = OnePasswordIntegration._sanitize_op_argument(dangerous_ref)
            assert '; rm -rf /' not in sanitized

    def test_cli_environment_detection_integration(self, cli_setup):
        """Test environment detection with real project files"""
        cli, config, repo_dir = cli_setup

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            # Create Python project files
            pyproject_content = '''[project]
name = "test-integration"
version = "0.1.0"
dependencies = ["requests>=2.28.0"]

[tool.uv]
dev-dependencies = ["pytest>=7.0.0"]
'''
            (repo_dir / 'pyproject.toml').write_text(pyproject_content)

            # Create Node.js project files
            package_json = {
                "name": "test-integration",
                "version": "1.0.0",
                "dependencies": {
                    "express": "^4.18.0"
                }
            }
            (repo_dir / 'package.json').write_text(json.dumps(package_json, indent=2))

            # Create Java project files
            pom_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>test-integration</artifactId>
    <version>1.0.0</version>
</project>'''
            (repo_dir / 'pom.xml').write_text(pom_xml)

            # Test environment detection
            from cproj import EnvironmentSetup
            env_setup = EnvironmentSetup(repo_dir)
            environments = env_setup.detect_environments()

            # Should detect all three environments
            assert environments['python']['active'] == True
            assert environments['node']['active'] == True
            assert environments['java']['active'] == True

        finally:
            os.chdir(original_cwd)

    def test_cli_error_handling_integration(self, cli_setup):
        """Test CLI error handling with real error conditions"""
        cli, config, repo_dir = cli_setup

        # Test with invalid repository path
        invalid_config = Config(repo_dir / 'invalid_config.json')
        invalid_config.set('repo_path', '/nonexistent/path')
        cli.config = invalid_config

        # This should raise appropriate errors
        from types import SimpleNamespace

        # Test create in invalid repo
        args = SimpleNamespace(
            branch='test-branch',
            from_branch='main',
            issue=None,
            no_env=True,
            ticket=None
        )

        with pytest.raises(CprojError):
            cli.cmd_create(args)

    def test_cli_full_workflow_integration(self, cli_setup):
        """Test complete CLI workflow end-to-end"""
        cli, config, repo_dir = cli_setup

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            # 1. Setup project
            from types import SimpleNamespace
            setup_args = SimpleNamespace(
                repo_path=str(repo_dir),
                agent_name='integration-test',
                agent_email='test@example.com'
            )
            cli.cmd_setup(setup_args)

            # 2. Create a worktree
            create_args = SimpleNamespace(
                branch='feature/full-workflow',
                from_branch='main',
                issue=None,
                no_env=True,
                ticket=None
            )
            cli.cmd_create(create_args)

            # 3. List worktrees
            list_args = SimpleNamespace(json=False, long=False)
            cli.cmd_list(list_args)

            # 4. Check status
            status_args = SimpleNamespace(json=False)
            cli.cmd_status(status_args)

            # 5. Set some configuration
            config_args = SimpleNamespace(
                key='test_workflow',
                value='completed',
                get=False,
                list=False,
                unset=False
            )
            cli.cmd_config(config_args)

            # 6. Verify configuration
            verify_args = SimpleNamespace(
                key='test_workflow',
                value=None,
                get=True,
                list=False,
                unset=False
            )
            cli.cmd_config(verify_args)

            # 7. Clean up (dry run)
            cleanup_args = SimpleNamespace(
                older_than=None,
                newer_than=None,
                merged_only=False,
                force=True,
                dry_run=True,
                yes=True
            )
            cli.cmd_cleanup(cleanup_args)

        finally:
            os.chdir(original_cwd)

    def test_cli_subprocess_integration(self):
        """Test CLI as subprocess (how it would be used in practice)"""
        # Test basic CLI invocation
        result = subprocess.run([sys.executable, 'cproj.py', '--version'],
                               capture_output=True, text=True)
        # Should not crash (exit code 0 or 2 for --version not implemented)
        assert result.returncode in [0, 2]

        # Test help command
        result = subprocess.run([sys.executable, 'cproj.py', '--help'],
                               capture_output=True, text=True)
        assert result.returncode == 0
        assert len(result.stdout) > 0

        # Test invalid command
        result = subprocess.run([sys.executable, 'cproj.py', 'invalid-command'],
                               capture_output=True, text=True)
        assert result.returncode != 0  # Should fail

    def test_cli_concurrent_operations(self, cli_setup):
        """Test CLI operations that might conflict"""
        cli, config, repo_dir = cli_setup

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)

            # Create multiple worktrees in sequence
            branches = ['feature/concurrent-1', 'feature/concurrent-2', 'feature/concurrent-3']

            for branch in branches:
                from types import SimpleNamespace
                args = SimpleNamespace(
                    branch=branch,
                    from_branch='main',
                    issue=None,
                    no_env=True,
                    ticket=None
                )

                # Each should succeed
                cli.cmd_create(args)

            # List should show all worktrees
            list_args = SimpleNamespace(json=False, long=False)
            cli.cmd_list(list_args)

            # Clean up all at once
            cleanup_args = SimpleNamespace(
                older_than=None,
                newer_than=None,
                merged_only=False,
                force=True,
                dry_run=False,
                yes=True
            )
            cli.cmd_cleanup(cleanup_args)

        finally:
            os.chdir(original_cwd)


if __name__ == '__main__':
    import shutil
    pytest.main([__file__, '-v', '-m', 'integration'])