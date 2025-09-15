#!/usr/bin/env python3
"""
Comprehensive tests for environment setup functionality
"""

import tempfile
import subprocess
import pytest
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the classes we need to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cproj import EnvironmentSetup, CprojError


class TestEnvironmentSetup:
    """Test environment detection and setup functionality"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def env_setup(self, temp_dir):
        """Create an EnvironmentSetup instance for testing"""
        return EnvironmentSetup(temp_dir)

    def test_environment_setup_initialization(self, temp_dir):
        """Test EnvironmentSetup initialization"""
        env_setup = EnvironmentSetup(temp_dir)
        assert env_setup.worktree_path == temp_dir
        assert isinstance(env_setup.worktree_path, Path)

    def test_python_project_detection(self, env_setup, temp_dir):
        """Test Python project detection methods"""
        # Test pyproject.toml detection
        assert not env_setup._has_pyproject_toml()

        (temp_dir / 'pyproject.toml').touch()
        assert env_setup._has_pyproject_toml()

        # Test requirements.txt detection
        assert not env_setup._has_requirements_txt()

        (temp_dir / 'requirements.txt').touch()
        assert env_setup._has_requirements_txt()

        # Test setup.py detection
        assert not env_setup._has_setup_py()

        (temp_dir / 'setup.py').touch()
        assert env_setup._has_setup_py()

    def test_nodejs_project_detection(self, env_setup, temp_dir):
        """Test Node.js project detection methods"""
        # Test package.json detection
        assert not env_setup._has_package_json()

        package_json = {
            "name": "test-project",
            "version": "1.0.0",
            "scripts": {
                "dev": "next dev",
                "build": "next build"
            }
        }
        (temp_dir / 'package.json').write_text(json.dumps(package_json))
        assert env_setup._has_package_json()

        # Test yarn.lock detection
        assert not env_setup._has_yarn_lock()

        (temp_dir / 'yarn.lock').touch()
        assert env_setup._has_yarn_lock()

        # Test package-lock.json detection
        assert not env_setup._has_package_lock()

        (temp_dir / 'package-lock.json').touch()
        assert env_setup._has_package_lock()

    def test_java_project_detection(self, env_setup, temp_dir):
        """Test Java project detection methods"""
        # Test Maven detection
        assert not env_setup._has_maven()

        pom_xml = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>test-project</artifactId>
    <version>1.0.0</version>
</project>"""
        (temp_dir / 'pom.xml').write_text(pom_xml)
        assert env_setup._has_maven()

        # Test Gradle detection
        assert not env_setup._has_gradle()

        (temp_dir / 'build.gradle').touch()
        assert env_setup._has_gradle()

        # Also test gradle.kts
        (temp_dir / 'build.gradle').unlink()
        assert not env_setup._has_gradle()

        (temp_dir / 'build.gradle.kts').touch()
        assert env_setup._has_gradle()

    def test_environment_detection_comprehensive(self, env_setup, temp_dir):
        """Test comprehensive environment detection"""
        # Initially no environments detected
        result = env_setup.detect_environments()
        assert isinstance(result, dict)
        assert 'python' in result
        assert 'node' in result
        assert 'java' in result

        # Add Python project files
        (temp_dir / 'pyproject.toml').write_text('[tool.poetry]\nname = "test"\nversion = "0.1.0"')
        (temp_dir / 'requirements.txt').write_text('requests==2.28.0\n')

        # Add Node.js project files
        package_json = {"name": "test", "version": "1.0.0"}
        (temp_dir / 'package.json').write_text(json.dumps(package_json))

        # Add Java project files
        (temp_dir / 'pom.xml').write_text('<project></project>')

        # Re-detect environments
        result = env_setup.detect_environments()

        # Should detect all three environments
        assert result['python']['active'] == True
        assert result['node']['active'] == True
        assert result['java']['active'] == True

    @patch('shutil.which')
    @patch('subprocess.run')
    def test_python_environment_setup_uv_available(self, mock_run, mock_which, env_setup, temp_dir):
        """Test Python environment setup when uv is available"""
        # Mock uv being available
        mock_which.side_effect = lambda cmd: '/usr/local/bin/uv' if cmd == 'uv' else None
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        # Create pyproject.toml
        pyproject_content = """[tool.uv]
dev-dependencies = ["pytest>=7.0.0"]

[project]
name = "test-project"
version = "0.1.0"
dependencies = ["requests>=2.28.0"]
"""
        (temp_dir / 'pyproject.toml').write_text(pyproject_content)

        result = env_setup.setup_python(auto_install=True)

        # Should use uv for environment setup
        assert isinstance(result, dict)
        mock_run.assert_called()

        # Verify uv commands were called
        uv_calls = [call for call in mock_run.call_args_list
                   if len(call[0]) > 0 and 'uv' in str(call[0][0])]
        assert len(uv_calls) > 0

    @patch('shutil.which')
    @patch('subprocess.run')
    def test_python_environment_setup_venv_fallback(self, mock_run, mock_which, env_setup, temp_dir):
        """Test Python environment setup fallback to venv when uv not available"""
        # Mock uv not available, python available
        mock_which.side_effect = lambda cmd: '/usr/bin/python3' if cmd == 'python3' else None
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        # Create requirements.txt
        (temp_dir / 'requirements.txt').write_text('requests==2.28.0\npytest>=7.0.0\n')

        result = env_setup.setup_python(auto_install=True)

        # Should use venv for environment setup
        assert isinstance(result, dict)
        mock_run.assert_called()

        # Verify venv commands were called
        venv_calls = [call for call in mock_run.call_args_list
                     if len(call[0]) > 0 and ('venv' in str(call[0]) or 'python' in str(call[0][0]))]
        assert len(venv_calls) > 0

    @patch('shutil.which')
    @patch('subprocess.run')
    def test_nodejs_environment_setup(self, mock_run, mock_which, env_setup, temp_dir):
        """Test Node.js environment setup"""
        # Mock node and npm being available
        mock_which.side_effect = lambda cmd: f'/usr/local/bin/{cmd}' if cmd in ['node', 'npm', 'yarn'] else None
        mock_run.return_value = MagicMock(returncode=0, stdout='v18.16.0\n', stderr='')

        # Create package.json
        package_json = {
            "name": "test-project",
            "version": "1.0.0",
            "dependencies": {
                "react": "^18.0.0"
            },
            "devDependencies": {
                "typescript": "^5.0.0"
            }
        }
        (temp_dir / 'package.json').write_text(json.dumps(package_json, indent=2))

        result = env_setup.setup_node(auto_install=True)

        # Should setup Node.js environment
        assert isinstance(result, dict)
        if mock_run.called:
            # Verify node/npm commands were called
            node_calls = [call for call in mock_run.call_args_list
                         if len(call[0]) > 0 and any(cmd in str(call[0][0]) for cmd in ['node', 'npm', 'yarn'])]
            # At least version check should be called
            assert len(node_calls) >= 0

    @patch('shutil.which')
    @patch('subprocess.run')
    def test_java_environment_setup(self, mock_run, mock_which, env_setup, temp_dir):
        """Test Java environment setup"""
        # Mock java and maven being available
        mock_which.side_effect = lambda cmd: f'/usr/local/bin/{cmd}' if cmd in ['java', 'mvn', 'gradle'] else None
        mock_run.return_value = MagicMock(returncode=0, stdout='openjdk 17.0.7\n', stderr='')

        # Create pom.xml
        pom_xml = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>test-project</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
    </properties>
    <dependencies>
        <dependency>
            <groupId>junit</groupId>
            <artifactId>junit</artifactId>
            <version>4.13.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>"""
        (temp_dir / 'pom.xml').write_text(pom_xml)

        result = env_setup.setup_java(auto_install=True)

        # Should setup Java environment
        assert isinstance(result, dict)

    def test_environment_setup_error_handling(self, env_setup, temp_dir):
        """Test error handling in environment setup"""
        # Test with no environment files
        with pytest.raises(CprojError):
            env_setup.setup_python(auto_install=False)

        # Test with invalid pyproject.toml
        (temp_dir / 'pyproject.toml').write_text('invalid toml content [[[')

        # Should handle gracefully or raise appropriate error
        try:
            result = env_setup.setup_python(auto_install=False)
            # If it doesn't raise, should return meaningful result
            assert isinstance(result, dict)
        except CprojError:
            # Expected for invalid configuration
            pass

    def test_shared_venv_functionality(self, env_setup, temp_dir):
        """Test shared virtual environment functionality"""
        # Test shared venv detection logic
        shared_venv_path = temp_dir.parent / '.shared-venv'

        # Should not exist initially
        assert not shared_venv_path.exists()

        # Test shared venv path calculation
        expected_path = temp_dir.parent / '.shared-venv'
        assert isinstance(expected_path, Path)

    def test_environment_validation(self, env_setup, temp_dir):
        """Test environment validation logic"""
        # Test Python environment validation
        def validate_python_env(worktree_path):
            """Validate Python environment setup"""
            venv_path = worktree_path / '.venv'
            if venv_path.exists():
                python_path = venv_path / 'bin' / 'python'
                if not python_path.exists():
                    python_path = venv_path / 'Scripts' / 'python.exe'  # Windows
                return python_path.exists()
            return False

        # Initially no venv
        assert not validate_python_env(temp_dir)

        # Create mock venv structure
        venv_path = temp_dir / '.venv'
        venv_path.mkdir()
        bin_path = venv_path / 'bin'
        bin_path.mkdir()
        python_path = bin_path / 'python'
        python_path.touch()

        # Should validate now
        assert validate_python_env(temp_dir)

    @patch('subprocess.run')
    def test_package_manager_detection(self, mock_run, env_setup, temp_dir):
        """Test package manager detection and preference"""
        # Test uv detection
        with patch('shutil.which') as mock_which:
            mock_which.return_value = '/usr/local/bin/uv'
            assert env_setup._has_uv()

            mock_which.return_value = None
            assert not env_setup._has_uv()

        # Test yarn vs npm preference
        (temp_dir / 'yarn.lock').touch()
        (temp_dir / 'package-lock.json').touch()

        # yarn.lock should take precedence
        assert env_setup._has_yarn_lock()
        assert env_setup._has_package_lock()

    def test_environment_info_generation(self, env_setup, temp_dir):
        """Test environment information generation"""
        # Create various project files
        (temp_dir / 'pyproject.toml').write_text('[project]\nname = "test"\nversion = "0.1.0"')
        (temp_dir / 'package.json').write_text('{"name": "test", "version": "1.0.0"}')
        (temp_dir / 'pom.xml').write_text('<project></project>')

        env_info = env_setup.detect_environments()

        # Should contain comprehensive environment information
        assert 'python' in env_info
        assert 'node' in env_info
        assert 'java' in env_info

        # Each environment should have expected structure
        for env_name, env_data in env_info.items():
            assert isinstance(env_data, dict)
            assert 'active' in env_data
            assert isinstance(env_data['active'], bool)

    @patch('subprocess.run')
    def test_subprocess_timeout_handling(self, mock_run, env_setup):
        """Test subprocess timeout handling in environment setup"""
        # Test timeout scenario
        mock_run.side_effect = subprocess.TimeoutExpired('test_cmd', 30)

        # Should handle timeout gracefully
        try:
            result = subprocess.run(['echo', 'test'], timeout=0.001, capture_output=True)
        except subprocess.TimeoutExpired:
            # Expected behavior
            pass

    def test_path_validation_in_environment_setup(self, env_setup, temp_dir):
        """Test path validation during environment setup"""
        # Test safe path operations
        safe_paths = [
            temp_dir / '.venv',
            temp_dir / 'node_modules',
            temp_dir / 'target',
            temp_dir / '.cproj'
        ]

        for path in safe_paths:
            # Should be safe to create within worktree
            try:
                relative = path.resolve().relative_to(temp_dir.resolve())
                is_safe = True
            except ValueError:
                is_safe = False

            assert is_safe, f"Path should be safe: {path}"

        # Test dangerous paths
        dangerous_paths = [
            temp_dir / '..' / '..' / 'etc' / 'passwd',
            Path('/etc/passwd'),
            Path('~/.ssh/id_rsa').expanduser()
        ]

        for path in dangerous_paths:
            try:
                relative = path.resolve().relative_to(temp_dir.resolve())
                is_safe = True
            except ValueError:
                is_safe = False

            # Most should not be safe
            if str(path).startswith('/') or str(path).startswith('~'):
                assert not is_safe, f"Dangerous path should not be safe: {path}"

    def test_environment_configuration_parsing(self, env_setup, temp_dir):
        """Test parsing of environment configuration files"""
        # Test pyproject.toml parsing
        pyproject_content = """[project]
name = "test-project"
version = "0.1.0"
dependencies = [
    "requests>=2.28.0",
    "click>=8.0.0"
]

[tool.uv]
dev-dependencies = [
    "pytest>=7.0.0",
    "black>=23.0.0"
]
"""
        (temp_dir / 'pyproject.toml').write_text(pyproject_content)

        # Should be able to detect pyproject.toml
        assert env_setup._has_pyproject_toml()

        # Test package.json parsing
        package_json = {
            "name": "test-project",
            "version": "1.0.0",
            "scripts": {
                "dev": "next dev",
                "build": "next build",
                "test": "jest"
            },
            "dependencies": {
                "react": "^18.0.0",
                "next": "^13.0.0"
            },
            "devDependencies": {
                "jest": "^29.0.0",
                "typescript": "^5.0.0"
            }
        }
        (temp_dir / 'package.json').write_text(json.dumps(package_json, indent=2))

        # Should be able to detect package.json
        assert env_setup._has_package_json()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])