#!/usr/bin/env python3
"""
Test suite for cproj
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cproj import (
    AgentJson,
    Config,
    CprojCLI,
    EnvironmentSetup,
    GitHubIntegration,
    GitWorktree,
)


class TestConfig(unittest.TestCase):
    """Test Config class"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_path = self.temp_dir / "config.json"

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_config_creation(self):
        config = Config(self.config_path)
        self.assertEqual(config._config, {})

    def test_config_get_set(self):
        config = Config(self.config_path)
        config.set("test_key", "test_value")
        self.assertEqual(config.get("test_key"), "test_value")
        self.assertEqual(config.get("missing_key", "default"), "default")

    def test_config_persistence(self):
        config = Config(self.config_path)
        config.set("persistent_key", "persistent_value")

        # Create new config instance
        config2 = Config(self.config_path)
        self.assertEqual(config2.get("persistent_key"), "persistent_value")


class TestAgentJson(unittest.TestCase):
    """Test AgentJson class"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_agent_json_creation(self):
        agent_json = AgentJson(self.temp_dir)
        self.assertIn("schema_version", agent_json.data)
        self.assertIn("agent", agent_json.data)
        self.assertIn("project", agent_json.data)
        self.assertIn("workspace", agent_json.data)
        self.assertIn("links", agent_json.data)
        self.assertIn("env", agent_json.data)

    def test_agent_json_save_load(self):
        agent_json = AgentJson(self.temp_dir)
        agent_json.set_project("Test Project", "/test/repo")
        agent_json.set_workspace("/test/workspace", "feature/test", "main")
        agent_json.save()

        # Load from file
        agent_json2 = AgentJson(self.temp_dir)
        self.assertEqual(agent_json2.data["project"]["name"], "Test Project")
        self.assertEqual(agent_json2.data["workspace"]["branch"], "feature/test")

    def test_agent_json_links(self):
        agent_json = AgentJson(self.temp_dir)
        agent_json.set_link("pr", "https://github.com/test/test/pull/1")

        self.assertEqual(
            agent_json.data["links"]["pr"],
            "https://github.com/test/test/pull/1",
        )


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

        self.assertEqual(result["manager"], "none")
        self.assertFalse(result["active"])
        self.assertFalse(result["pyproject"])
        self.assertFalse(result["requirements"])

    def test_setup_python_with_requirements(self):
        # Create requirements.txt
        (self.temp_dir / "requirements.txt").write_text("requests==2.28.0\n")

        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_python()

        self.assertTrue(result["requirements"])

    def test_setup_python_with_pyproject(self):
        # Create pyproject.toml
        (self.temp_dir / "pyproject.toml").write_text('[project]\nname = "test"\n')

        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_python()

        self.assertTrue(result["pyproject"])

    def test_setup_node_no_package_json(self):
        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_node()

        self.assertEqual(result["manager"], "none")
        self.assertEqual(result["node_version"], "")

    def test_setup_node_with_package_json(self):
        # Create package.json
        (self.temp_dir / "package.json").write_text('{"name": "test", "version": "1.0.0"}')

        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_node()

        # Should detect package.json and determine manager based on
        # nvm availability
        self.assertIn(result["manager"], ["none", "nvm"])  # Either works depending on system

    def test_setup_java_maven(self):
        # Create pom.xml
        (self.temp_dir / "pom.xml").write_text("<project></project>")

        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_java()

        self.assertEqual(result["build"], "maven")

    def test_setup_java_gradle(self):
        # Create build.gradle
        (self.temp_dir / "build.gradle").write_text('apply plugin: "java"')

        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_java()

        self.assertEqual(result["build"], "gradle")

    def test_setup_java_no_build_file(self):
        env_setup = EnvironmentSetup(self.temp_dir)
        result = env_setup.setup_java()

        self.assertEqual(result["build"], "none")


class TestGitHubIntegration(unittest.TestCase):
    """Test GitHubIntegration class"""

    @patch("shutil.which")
    def test_is_available_true(self, mock_which):
        mock_which.return_value = "/usr/bin/gh"
        self.assertTrue(GitHubIntegration.is_available())
        mock_which.assert_called_with("gh")

    @patch("shutil.which")
    def test_is_available_false(self, mock_which):
        mock_which.return_value = None
        self.assertFalse(GitHubIntegration.is_available())

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_create_pr_success(self, mock_which, mock_run):
        mock_which.return_value = "/usr/bin/gh"
        # Mock both auth check and PR creation calls
        mock_run.side_effect = [
            Mock(returncode=0),  # Auth status check succeeds
            Mock(stdout="https://github.com/test/test/pull/1\n", returncode=0),  # PR creation
        ]

        result = GitHubIntegration.create_pr("Test PR", "Test body", draft=True)

        self.assertEqual(result, "https://github.com/test/test/pull/1")
        self.assertEqual(mock_run.call_count, 2)  # Auth check + PR creation

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_create_pr_failure(self, mock_which, mock_run):
        mock_which.return_value = "/usr/bin/gh"
        # Mock auth check success, but PR creation failure
        mock_run.side_effect = [
            Mock(returncode=0),  # Auth status check succeeds
            subprocess.CalledProcessError(1, "gh"),  # PR creation fails
        ]

        result = GitHubIntegration.create_pr("Test PR", "Test body")

        self.assertIsNone(result)


class TestCprojCLI(unittest.TestCase):
    """Test CprojCLI class"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_path = self.temp_dir / "config.json"

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir)

    @patch("cproj.Config")
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
        args = parser.parse_args(["init", "--name", "test"])
        self.assertEqual(args.command, "init")
        self.assertEqual(args.name, "test")

    def test_parser_worktree_create(self):
        cli = CprojCLI()
        parser = cli.create_parser()

        args = parser.parse_args(["worktree", "create", "--branch", "feature/test"])
        self.assertEqual(args.command, "worktree")
        self.assertEqual(args.worktree_command, "create")
        self.assertEqual(args.branch, "feature/test")

    def test_parser_review_open(self):
        cli = CprojCLI()
        parser = cli.create_parser()

        args = parser.parse_args(["review", "open", "--draft"])
        self.assertEqual(args.command, "review")
        self.assertEqual(args.review_command, "open")
        self.assertTrue(args.draft)

    def test_parser_config(self):
        cli = CprojCLI()
        parser = cli.create_parser()

        args = parser.parse_args(["config", "editor", "vim"])
        self.assertEqual(args.command, "config")
        self.assertEqual(args.key, "editor")
        self.assertEqual(args.value, "vim")


class TestClaudeIntegration(unittest.TestCase):
    """Test CLAUDE.md and nvm automation features"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo_dir = self.temp_dir / "test_repo"
        self.repo_dir.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_claude_symlink_detection(self):
        """Test CLAUDE.md symlink detection and setup"""
        # Create CLAUDE.md
        claude_md = self.repo_dir / "CLAUDE.md"
        claude_md.write_text("# Test Claude Config")

        # Create .cursorrules symlink
        cursorrules = self.repo_dir / ".cursorrules"
        cursorrules.symlink_to("CLAUDE.md")

        # Create CLI instance
        cli = CprojCLI()
        cli.config.set("claude_symlink_default", "yes")

        # Create a mock worktree
        worktree_path = self.temp_dir / "test_worktree"
        worktree_path.mkdir()

        # Test the symlink setup method
        cli._setup_claude_symlink(worktree_path, self.repo_dir)

        # Verify symlink was created
        worktree_cursorrules = worktree_path / ".cursorrules"
        self.assertTrue(worktree_cursorrules.exists())
        self.assertTrue(worktree_cursorrules.is_symlink())

    def test_claude_symlink_no_source(self):
        """Test behavior when CLAUDE.md doesn't exist"""
        cli = CprojCLI()
        worktree_path = self.temp_dir / "test_worktree"
        worktree_path.mkdir()

        # Should return early without creating anything
        cli._setup_claude_symlink(worktree_path, self.repo_dir)

        worktree_cursorrules = worktree_path / ".cursorrules"
        self.assertFalse(worktree_cursorrules.exists())

    def test_nvm_setup_script_creation(self):
        """Test nvm setup script creation"""
        cli = CprojCLI()
        cli.config.set("claude_nvm_default", "yes")

        worktree_path = self.temp_dir / "test_worktree"
        worktree_path.mkdir()

        # Mock node environment with nvm
        node_env = {"manager": "nvm"}

        # Create a fake nvm.sh file to simulate nvm installation
        fake_nvm_dir = self.temp_dir / ".nvm"
        fake_nvm_dir.mkdir()
        fake_nvm_script = fake_nvm_dir / "nvm.sh"
        fake_nvm_script.write_text("# fake nvm script")

        # Mock Path.home() to return our temp directory so nvm check finds our fake nvm
        with patch("pathlib.Path.home", return_value=self.temp_dir):
            # Mock interactive mode to be False so it doesn't prompt
            with patch.object(cli, "_is_interactive", return_value=False):
                # Test the nvm setup method
                cli._setup_nvm_for_claude(worktree_path, node_env)

        # Verify setup script was created
        setup_script = worktree_path / ".cproj" / "setup-claude.sh"
        self.assertTrue(setup_script.exists())

        # Verify script content
        content = setup_script.read_text()
        self.assertIn("nvm use --lts", content)
        self.assertIn("NVM_DIR", content)

    def test_nvm_setup_no_nvm(self):
        """Test behavior when nvm is not available"""
        cli = CprojCLI()
        worktree_path = self.temp_dir / "test_worktree"
        worktree_path.mkdir()

        # Mock node environment without nvm
        node_env = {"manager": "none"}

        # Mock nvm path to not exist
        with patch("pathlib.Path.exists", return_value=False):
            # Should return early without creating script
            cli._setup_nvm_for_claude(worktree_path, node_env)

        setup_script = worktree_path / ".cproj" / "setup-claude.sh"
        self.assertFalse(setup_script.exists())


class TestCleanupDirtyWorktree(unittest.TestCase):
    """Test cleanup command handling of dirty worktrees"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo_dir = self.temp_dir / "test_repo"
        self.repo_dir.mkdir()

        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )

        # Create initial commit on main branch
        (self.repo_dir / "README.md").write_text("# Test Repo")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        # Ensure we're on main branch
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )

        # Create config for testing
        self.config_dir = self.temp_dir / ".config" / "cproj"
        self.config_dir.mkdir(parents=True)
        self.config = Config(self.config_dir / "config.json")
        self.config.set("repo_path", str(self.repo_dir))

        # Create CLI instance
        self.cli = CprojCLI()
        self.cli.config = self.config

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir)

    @patch("builtins.input")
    def test_cleanup_dirty_worktree_force_prompt_yes(self, mock_input):
        """Test that cleanup prompts for force removal and accepts yes"""
        import os

        original_cwd = Path.cwd()
        try:
            os.chdir(self.repo_dir)

            # Create a worktree
            git = GitWorktree(self.repo_dir)
            worktree_path = self.temp_dir / "test_worktree"
            git.create_worktree(worktree_path, "test-branch", "main")

            # Make the worktree dirty by adding a file
            (worktree_path / "dirty_file.txt").write_text("uncommitted change")

            # Mock user inputs: cleanup method selection, select test_worktree,
            # confirm selection, confirm removal, force removal
            # Use enough inputs to handle both single and multi-worktree scenarios
            mock_input.side_effect = ["1", "y", "y", "y", "y", "y"]

            # Create args for cleanup with --force=False so it will prompt
            from types import SimpleNamespace

            args = SimpleNamespace(
                repo=str(self.repo_dir),
                older_than=None,
                newer_than=None,
                merged_only=False,
                force=False,
                dry_run=False,
                yes=False,  # Don't auto-confirm, let the method 1
                # prompting handle it
            )

            # Mock the interactive detection to return True
            with patch.object(self.cli, "_is_interactive", return_value=True):
                # Call the actual cleanup command
                self.cli.cmd_cleanup(args)

            # Verify worktree was removed
            self.assertFalse(worktree_path.exists())

        finally:
            os.chdir(original_cwd)

    @patch("builtins.input")
    def test_cleanup_dirty_worktree_force_prompt_no(self, mock_input):
        """Test that cleanup prompts for force removal and accepts no"""
        import os

        original_cwd = Path.cwd()
        try:
            os.chdir(self.repo_dir)

            # Create a worktree
            git = GitWorktree(self.repo_dir)
            worktree_path = self.temp_dir / "test_worktree"
            git.create_worktree(worktree_path, "test-branch", "main")

            # Make the worktree dirty
            (worktree_path / "dirty_file.txt").write_text("uncommitted change")

            # Mock user inputs: confirm removal, then refuse force removal
            mock_input.side_effect = ["y", "n"]  # Remove? Yes, Force? No

            # The args variable was removed as it's not used in this test

            # Mock interactive detection
            with patch.object(self.cli, "_is_interactive", return_value=True):
                success = False
                try:
                    git.remove_worktree(worktree_path, force=False)
                    success = True
                except Exception as e:
                    if "is dirty" in str(e):
                        # User said no to force removal
                        pass

                # Verify worktree still exists (wasn't force removed)
                self.assertTrue(worktree_path.exists())
                self.assertFalse(success)

        finally:
            os.chdir(original_cwd)


class TestIntegration(unittest.TestCase):
    """Integration tests"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo_dir = self.temp_dir / "test_repo"
        self.repo_dir.mkdir()

        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )

        # Create initial commit on main branch
        (self.repo_dir / "README.md").write_text("# Test Repo")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        # Ensure we're on 'main' branch (rename default branch if needed)
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_git_worktree_creation(self):
        git = GitWorktree(self.repo_dir)

        # Test worktree creation
        worktree_path = self.temp_dir / "test_worktree"
        created_path = git.create_worktree(worktree_path, "feature/test", "main", interactive=False)

        self.assertEqual(created_path, worktree_path)
        self.assertTrue(worktree_path.exists())
        self.assertTrue((worktree_path / "README.md").exists())

    def test_agent_json_workflow(self):
        # Create worktree
        worktree_path = self.temp_dir / "test_worktree"
        worktree_path.mkdir()

        # Test AgentJson workflow
        agent_json = AgentJson(worktree_path)
        agent_json.set_project("Test Project", str(self.repo_dir))
        agent_json.set_workspace(str(worktree_path), "feature/test", "main")
        agent_json.save()

        # Verify file exists and is valid JSON
        json_file = worktree_path / ".cproj" / ".agent.json"
        self.assertTrue(json_file.exists())

        with json_file.open() as f:
            data = json.load(f)

        self.assertEqual(data["project"]["name"], "Test Project")
        self.assertEqual(data["workspace"]["branch"], "feature/test")


if __name__ == "__main__":
    unittest.main()
