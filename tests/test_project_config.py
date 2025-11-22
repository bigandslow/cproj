#!/usr/bin/env python3
"""
Tests for ProjectConfig class

Tests project-specific configuration management including base branch configuration.
"""

import sys
import tempfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cproj import ProjectConfig


class TestProjectConfig:
    """Test ProjectConfig class functionality"""

    @pytest.fixture
    def temp_repo_dir(self):
        """Create a temporary directory for repo tests"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "test_repo"
            repo_path.mkdir()
            yield repo_path

    def test_default_base_branch_is_main(self, temp_repo_dir):
        """Test that default base branch is 'main' when not configured"""
        # Arrange & Act
        config = ProjectConfig(temp_repo_dir)

        # Assert
        assert config.get_base_branch() == "main"

    def test_configured_base_branch_develop(self, temp_repo_dir):
        """Test that configured base branch is returned when set to 'develop'"""
        # Arrange
        config_dir = temp_repo_dir / ".cproj"
        config_dir.mkdir()
        config_file = config_dir / "project.yaml"

        with open(config_file, "w") as f:
            yaml.dump({"base_branch": "develop"}, f)

        # Act
        config = ProjectConfig(temp_repo_dir)

        # Assert
        assert config.get_base_branch() == "develop"

    def test_configured_base_branch_custom(self, temp_repo_dir):
        """Test that any custom base branch can be configured"""
        # Arrange
        config_dir = temp_repo_dir / ".cproj"
        config_dir.mkdir()
        config_file = config_dir / "project.yaml"

        with open(config_file, "w") as f:
            yaml.dump({"base_branch": "staging"}, f)

        # Act
        config = ProjectConfig(temp_repo_dir)

        # Assert
        assert config.get_base_branch() == "staging"

    def test_base_branch_persists_after_save(self, temp_repo_dir):
        """Test that base branch configuration persists after save"""
        # Arrange
        config = ProjectConfig(temp_repo_dir)

        # Act
        config.set_base_branch("develop")
        config.save()

        # Reload config
        reloaded_config = ProjectConfig(temp_repo_dir)

        # Assert
        assert reloaded_config.get_base_branch() == "develop"

    def test_set_base_branch_updates_config(self, temp_repo_dir):
        """Test that set_base_branch updates the configuration"""
        # Arrange
        config = ProjectConfig(temp_repo_dir)

        # Act
        config.set_base_branch("develop")

        # Assert
        assert config.get_base_branch() == "develop"
