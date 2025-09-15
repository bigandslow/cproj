#!/usr/bin/env python3
"""
Integration tests for environment setup with real tools and dependencies
"""

import tempfile
import subprocess
import pytest
import os
import json
import shutil
from pathlib import Path
from unittest.mock import patch

# Import the classes we need to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cproj import EnvironmentSetup, CprojError


@pytest.mark.integration
class TestEnvironmentIntegration:
    """Integration tests for environment setup with real tools"""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'test_project'
            project_dir.mkdir()
            yield project_dir

    @pytest.fixture
    def env_setup(self, temp_project):
        """Create an EnvironmentSetup instance"""
        return EnvironmentSetup(temp_project)

    def test_python_environment_real_detection(self, temp_project, env_setup):
        """Test Python environment detection with real project files"""
        # Test with pyproject.toml
        pyproject_content = '''[project]
name = "integration-test"
version = "0.1.0"
description = "Integration test project"
dependencies = [
    "requests>=2.28.0",
    "click>=8.0.0"
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "black>=23.0.0"
]

[tool.uv]
dev-dependencies = [
    "mypy>=1.0.0"
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
'''
        (temp_project / 'pyproject.toml').write_text(pyproject_content)

        # Test detection
        environments = env_setup.detect_environments()
        assert environments['python']['active'] == True
        assert environments['python']['pyproject'] == True

        # Test with requirements.txt
        requirements_content = '''requests==2.28.2
click==8.1.3
pytest>=7.0.0
black>=23.0.0
mypy>=1.0.0
'''
        (temp_project / 'requirements.txt').write_text(requirements_content)

        environments = env_setup.detect_environments()
        assert environments['python']['requirements'] == True

    @pytest.mark.skipif(not shutil.which('python3'), reason="Python 3 not available")
    def test_python_venv_creation_integration(self, temp_project, env_setup):
        """Test real Python virtual environment creation"""
        # Create requirements.txt
        requirements_content = '''requests>=2.28.0
pytest>=7.0.0
'''
        (temp_project / 'requirements.txt').write_text(requirements_content)

        # Create venv (if Python is available)
        result = env_setup.setup_python(auto_install=True)

        # Should return environment info
        assert isinstance(result, dict)
        assert 'python' in result

        # Check if venv was created
        venv_path = temp_project / '.venv'
        if venv_path.exists():
            # Verify venv structure
            if os.name == 'nt':  # Windows
                python_path = venv_path / 'Scripts' / 'python.exe'
                pip_path = venv_path / 'Scripts' / 'pip.exe'
            else:  # Unix-like
                python_path = venv_path / 'bin' / 'python'
                pip_path = venv_path / 'bin' / 'pip'

            # At least one should exist
            assert python_path.exists() or pip_path.exists()

    @pytest.mark.skipif(not shutil.which('uv'), reason="uv not available")
    def test_python_uv_integration(self, temp_project, env_setup):
        """Test integration with uv package manager"""
        # Create pyproject.toml for uv
        pyproject_content = '''[project]
name = "uv-test"
version = "0.1.0"
dependencies = [
    "requests>=2.28.0"
]

[tool.uv]
dev-dependencies = [
    "pytest>=7.0.0"
]
'''
        (temp_project / 'pyproject.toml').write_text(pyproject_content)

        # Test uv environment setup
        result = env_setup.setup_python(auto_install=True)

        assert isinstance(result, dict)
        assert result['manager'] == 'uv'

    def test_nodejs_environment_real_detection(self, temp_project, env_setup):
        """Test Node.js environment detection with real project files"""
        # Create package.json
        package_json = {
            "name": "integration-test-node",
            "version": "1.0.0",
            "description": "Integration test Node.js project",
            "main": "index.js",
            "scripts": {
                "start": "node index.js",
                "dev": "nodemon index.js",
                "test": "jest",
                "build": "webpack --mode production"
            },
            "dependencies": {
                "express": "^4.18.2",
                "lodash": "^4.17.21"
            },
            "devDependencies": {
                "jest": "^29.5.0",
                "nodemon": "^2.0.22",
                "webpack": "^5.88.0"
            }
        }
        (temp_project / 'package.json').write_text(json.dumps(package_json, indent=2))

        # Test detection
        environments = env_setup.detect_environments()
        assert environments['node']['active'] == True
        assert environments['node']['package_json'] == True

        # Test with package-lock.json
        package_lock = {
            "name": "integration-test-node",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "requires": True,
            "packages": {}
        }
        (temp_project / 'package-lock.json').write_text(json.dumps(package_lock, indent=2))

        environments = env_setup.detect_environments()
        assert environments['node']['package_lock'] == True

        # Test with yarn.lock
        yarn_lock_content = '''# THIS IS AN AUTOGENERATED FILE. DO NOT EDIT THIS FILE DIRECTLY.
# yarn lockfile v1

express@^4.18.2:
  version "4.18.2"
  resolved "https://registry.yarnpkg.com/express/-/express-4.18.2.tgz"
'''
        (temp_project / 'yarn.lock').write_text(yarn_lock_content)

        environments = env_setup.detect_environments()
        assert environments['node']['yarn_lock'] == True

    @pytest.mark.skipif(not shutil.which('node'), reason="Node.js not available")
    def test_nodejs_npm_integration(self, temp_project, env_setup):
        """Test real Node.js/npm integration"""
        # Create simple package.json
        package_json = {
            "name": "test-integration",
            "version": "1.0.0",
            "dependencies": {}
        }
        (temp_project / 'package.json').write_text(json.dumps(package_json, indent=2))

        # Test Node.js setup
        result = env_setup.setup_node(auto_install=True)

        assert isinstance(result, dict)
        assert 'node' in result

        # Check if node_modules was created (if npm install ran)
        node_modules = temp_project / 'node_modules'
        # node_modules might not be created for empty dependencies

    def test_java_environment_real_detection(self, temp_project, env_setup):
        """Test Java environment detection with real project files"""
        # Create pom.xml for Maven
        pom_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>integration-test</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>junit</groupId>
            <artifactId>junit</artifactId>
            <version>4.13.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>'''
        (temp_project / 'pom.xml').write_text(pom_xml)

        # Test detection
        environments = env_setup.detect_environments()
        assert environments['java']['active'] == True
        assert environments['java']['build'] == 'maven'

        # Test with Gradle
        (temp_project / 'pom.xml').unlink()
        build_gradle = '''plugins {
    id 'java'
    id 'application'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'junit:junit:4.13.2'
    implementation 'com.google.guava:guava:31.1-jre'
}

application {
    mainClass = 'com.example.App'
}
'''
        (temp_project / 'build.gradle').write_text(build_gradle)

        environments = env_setup.detect_environments()
        assert environments['java']['active'] == True
        assert environments['java']['build'] == 'gradle'

    @pytest.mark.skipif(not shutil.which('java'), reason="Java not available")
    def test_java_maven_integration(self, temp_project, env_setup):
        """Test real Java/Maven integration"""
        # Create Maven project structure
        (temp_project / 'src' / 'main' / 'java').mkdir(parents=True)
        (temp_project / 'src' / 'test' / 'java').mkdir(parents=True)

        # Create pom.xml
        pom_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>test-project</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.source>11</maven.compiler.source>
        <maven.compiler.target>11</maven.compiler.target>
    </properties>
</project>'''
        (temp_project / 'pom.xml').write_text(pom_xml)

        # Test Java setup
        result = env_setup.setup_java(auto_install=True)

        assert isinstance(result, dict)
        assert 'java' in result

    def test_multi_language_project_integration(self, temp_project, env_setup):
        """Test project with multiple language environments"""
        # Create Python files
        pyproject_content = '''[project]
name = "multi-lang-project"
version = "0.1.0"
dependencies = ["requests>=2.28.0"]
'''
        (temp_project / 'pyproject.toml').write_text(pyproject_content)

        # Create Node.js files
        package_json = {
            "name": "multi-lang-project",
            "version": "1.0.0",
            "dependencies": {"express": "^4.18.0"}
        }
        (temp_project / 'package.json').write_text(json.dumps(package_json, indent=2))

        # Create Java files
        pom_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>multi-lang-project</artifactId>
    <version>1.0.0</version>
</project>'''
        (temp_project / 'pom.xml').write_text(pom_xml)

        # Test detection of all environments
        environments = env_setup.detect_environments()

        assert environments['python']['active'] == True
        assert environments['node']['active'] == True
        assert environments['java']['active'] == True

        # Each should have correct configuration files detected
        assert environments['python']['pyproject'] == True
        assert environments['node']['package_json'] == True
        assert environments['java']['build'] == 'maven'

    def test_environment_setup_with_real_files(self, temp_project, env_setup):
        """Test environment setup with realistic project structure"""
        # Create a realistic project structure
        (temp_project / 'src').mkdir()
        (temp_project / 'tests').mkdir()
        (temp_project / 'docs').mkdir()

        # Python source files
        (temp_project / 'src' / '__init__.py').touch()
        (temp_project / 'src' / 'main.py').write_text('''#!/usr/bin/env python3
"""Main application module."""

import requests

def main():
    """Main function."""
    response = requests.get("https://httpbin.org/get")
    print(f"Status: {response.status_code}")

if __name__ == "__main__":
    main()
''')

        # Test files
        (temp_project / 'tests' / '__init__.py').touch()
        (temp_project / 'tests' / 'test_main.py').write_text('''import unittest
from src.main import main

class TestMain(unittest.TestCase):
    def test_main(self):
        # Test that main function exists
        self.assertTrue(callable(main))

if __name__ == "__main__":
    unittest.main()
''')

        # Configuration files
        pyproject_content = '''[project]
name = "realistic-project"
version = "0.1.0"
description = "A realistic test project"
dependencies = [
    "requests>=2.28.0"
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "black>=23.0.0",
    "mypy>=1.0.0"
]

[tool.black]
line-length = 88

[tool.mypy]
python_version = "3.8"
warn_return_any = true
'''
        (temp_project / 'pyproject.toml').write_text(pyproject_content)

        (temp_project / 'README.md').write_text('''# Realistic Project

This is a realistic test project for integration testing.

## Installation

```bash
pip install -e .
```

## Usage

```bash
python src/main.py
```

## Testing

```bash
pytest tests/
```
''')

        # Test comprehensive environment detection
        environments = env_setup.detect_environments()

        assert environments['python']['active'] == True
        assert environments['python']['pyproject'] == True

        # Test that files are properly detected
        pyproject_path = temp_project / 'pyproject.toml'
        assert pyproject_path.exists()

        src_files = list((temp_project / 'src').glob('*.py'))
        assert len(src_files) >= 1

        test_files = list((temp_project / 'tests').glob('*.py'))
        assert len(test_files) >= 1

    def test_environment_error_handling_integration(self, temp_project, env_setup):
        """Test error handling with real error conditions"""
        # Test with corrupted pyproject.toml
        (temp_project / 'pyproject.toml').write_text('invalid toml content [[[')

        # Should handle gracefully
        environments = env_setup.detect_environments()
        # Should still detect presence of file, even if corrupted
        assert isinstance(environments, dict)

        # Test with invalid package.json
        (temp_project / 'package.json').write_text('{"invalid": json content}')

        environments = env_setup.detect_environments()
        assert isinstance(environments, dict)

    def test_environment_setup_permissions(self, temp_project, env_setup):
        """Test environment setup with permission considerations"""
        # Create files with different permissions
        pyproject_file = temp_project / 'pyproject.toml'
        pyproject_file.write_text('[project]\nname = "test"\nversion = "0.1.0"')

        # Test that we can read the file
        environments = env_setup.detect_environments()
        assert environments['python']['active'] == True

        # Test setup in read-only directory (simulate CI environment)
        if os.name != 'nt':  # Skip on Windows due to permission differences
            # Make directory read-only
            temp_project.chmod(0o555)

            try:
                # Detection should still work
                environments = env_setup.detect_environments()
                assert isinstance(environments, dict)
            finally:
                # Restore permissions
                temp_project.chmod(0o755)

    def test_tool_availability_integration(self, env_setup):
        """Test real tool availability detection"""
        # Test common tools
        tools_to_test = [
            ('python3', 'Python 3'),
            ('python', 'Python'),
            ('node', 'Node.js'),
            ('npm', 'npm'),
            ('java', 'Java'),
            ('git', 'Git'),
        ]

        for tool_cmd, tool_name in tools_to_test:
            is_available = shutil.which(tool_cmd) is not None
            print(f"{tool_name}: {'Available' if is_available else 'Not available'}")

        # Test that we can detect uv specifically
        uv_available = shutil.which('uv') is not None
        print(f"uv: {'Available' if uv_available else 'Not available'}")

    def test_subprocess_integration_with_timeout(self, temp_project, env_setup):
        """Test subprocess operations with timeout handling"""
        # Test git operations that might hang
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_project)

            # Initialize git repo
            subprocess.run(['git', 'init'], check=True, capture_output=True, timeout=30)
            subprocess.run(['git', 'config', 'user.email', 'test@example.com'],
                          check=True, capture_output=True, timeout=10)
            subprocess.run(['git', 'config', 'user.name', 'Test User'],
                          check=True, capture_output=True, timeout=10)

            # Test git status with timeout
            result = subprocess.run(['git', 'status', '--porcelain'],
                                   capture_output=True, text=True, timeout=10)
            assert result.returncode == 0

        finally:
            os.chdir(original_cwd)

    def test_large_project_performance(self, temp_project, env_setup):
        """Test environment detection performance with larger projects"""
        # Create a larger project structure
        for i in range(50):
            (temp_project / f'file_{i}.py').write_text(f'# File {i}\nprint("File {i}")\n')

        for i in range(10):
            subdir = temp_project / f'subdir_{i}'
            subdir.mkdir()
            for j in range(10):
                (subdir / f'nested_{j}.py').write_text(f'# Nested file {i}-{j}\n')

        # Create pyproject.toml
        (temp_project / 'pyproject.toml').write_text('[project]\nname = "large-test"\nversion = "0.1.0"')

        # Test that detection still works efficiently
        import time
        start_time = time.time()

        environments = env_setup.detect_environments()

        end_time = time.time()
        detection_time = end_time - start_time

        assert environments['python']['active'] == True
        assert detection_time < 5.0  # Should complete within 5 seconds

    def test_concurrent_environment_operations(self, temp_project, env_setup):
        """Test concurrent environment operations"""
        # Create multiple environment files
        (temp_project / 'pyproject.toml').write_text('[project]\nname = "concurrent"\nversion = "0.1.0"')
        (temp_project / 'package.json').write_text('{"name": "concurrent", "version": "1.0.0"}')
        (temp_project / 'pom.xml').write_text('<project></project>')

        # Test multiple detections in sequence (simulating concurrent access)
        results = []
        for i in range(5):
            env = env_setup.detect_environments()
            results.append(env)

        # All results should be consistent
        for result in results:
            assert result['python']['active'] == True
            assert result['node']['active'] == True
            assert result['java']['active'] == True


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'integration'])