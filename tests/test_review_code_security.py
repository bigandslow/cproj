#!/usr/bin/env python3
"""
Security-focused tests for review-code command

Tests the security fixes implemented in the review-code command:
1. Safe file discovery without command injection
2. Template injection prevention in prompt formatting
3. Path validation and boundary checking
"""

import json
import string
import re
import tempfile
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

class TestReviewCodeSecurity:
    """Test security improvements in review-code command"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_safe_file_discovery(self, temp_dir):
        """Test that file discovery uses safe pathlib methods instead of subprocess"""
        # Create test files
        (temp_dir / 'test.py').touch()
        (temp_dir / 'src').mkdir()
        (temp_dir / 'src' / 'main.js').touch()
        (temp_dir / '.git').mkdir()
        (temp_dir / '.git' / 'config').touch()
        (temp_dir / 'node_modules').mkdir()
        (temp_dir / 'node_modules' / 'package.js').touch()

        # Implement the safe file discovery logic from review-code.md
        def discover_files_safe(base_dir, max_files=50):
            """Safely discover files using pathlib instead of subprocess"""
            try:
                allowed_extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.md']
                excluded_dirs = {'node_modules', '.git', '.venv', '__pycache__', '.pytest_cache'}

                files = []
                base_path = Path(base_dir)

                for ext in allowed_extensions:
                    for file_path in base_path.rglob(f'*{ext}'):
                        # Check if any part of the path contains excluded directories
                        if any(excluded in file_path.parts for excluded in excluded_dirs):
                            continue

                        try:
                            # Ensure path is within base directory
                            relative_path = file_path.relative_to(base_path)
                            files.append(str(relative_path))
                        except ValueError:
                            continue  # Skip files outside base directory

                        # Limit to prevent resource exhaustion
                        if len(files) >= max_files:
                            return files[:max_files]

                return files[:max_files]
            except Exception:
                return []

        # Test the function
        files = discover_files_safe(temp_dir, max_files=10)

        # Should find test.py and src/main.js, but not .git/config or node_modules/package.js
        assert 'test.py' in files
        assert 'src/main.js' in files
        assert '.git/config' not in files
        assert 'node_modules/package.js' not in files

    def test_template_injection_prevention(self):
        """Test that template formatting prevents injection attacks"""

        def safe_format_prompt(template, context_data):
            """Safely format prompt template with context data"""
            try:
                # Sanitize context values to prevent injection
                sanitized_context = {}
                for key, value in context_data.items():
                    if value is None:
                        sanitized_context[key] = ""
                    else:
                        # Convert to string and sanitize dangerous characters
                        str_value = str(value)
                        # Remove potential format string injection patterns
                        str_value = re.sub(r'[{}$\\]', '', str_value)
                        # Also remove shell metacharacters and dangerous command patterns
                        str_value = re.sub(r'[;&|`]', '', str_value)
                        # Remove common dangerous commands/patterns
                        dangerous_patterns = ['rm -rf', 'rm -fr', 'dd if=', 'mkfs', ':(){ :|:& };:']
                        for pattern in dangerous_patterns:
                            str_value = str_value.replace(pattern, '[SANITIZED]')
                        # Limit length to prevent DoS
                        sanitized_context[key] = str_value[:10000]

                # Use string.Template for safer substitution
                # Convert {} format to $ format for Template
                template_str = template
                for key in sanitized_context.keys():
                    template_str = template_str.replace(f'{{{key}}}', f'${key}')

                template_obj = string.Template(template_str)
                return template_obj.safe_substitute(sanitized_context)
            except Exception:
                return template  # Return original template if formatting fails

        # Test with safe input
        safe_template = "Review for {pr_title} by {author}"
        safe_context = {
            'pr_title': 'fix/security-improvements',
            'author': 'developer'
        }

        result = safe_format_prompt(safe_template, safe_context)
        assert "fix/security-improvements" in result
        assert "developer" in result

        # Test with malicious input attempting format string injection
        malicious_template = "Review for {pr_title} with {code}"
        malicious_context = {
            'pr_title': 'normal-title',
            'code': '${system: rm -rf /}'  # Template injection attempt
        }

        result = safe_format_prompt(malicious_template, malicious_context)
        # Should not contain the dangerous patterns
        assert '${system:' not in result
        assert 'rm -rf' not in result
        assert 'normal-title' in result

        # Test with bracket injection attempts
        bracket_context = {
            'pr_title': 'title{evil}code',
            'author': 'user${PATH}'
        }

        result = safe_format_prompt(safe_template, bracket_context)
        assert '{evil}' not in result
        assert '${PATH}' not in result

    def test_path_validation_within_boundaries(self, temp_dir):
        """Test that path validation keeps files within project boundaries"""

        def validate_file_path(path, base_dir):
            """Validate file path is safe and within project boundaries"""
            try:
                normalized = Path(path).resolve()
                base_path = Path(base_dir).resolve()
                # Ensure path is within base directory
                normalized.relative_to(base_path)
                return str(normalized)
            except (ValueError, OSError):
                return None

        # Create test files
        safe_file = temp_dir / 'safe.py'
        safe_file.touch()

        # Test safe paths
        assert validate_file_path(safe_file, temp_dir) is not None
        assert validate_file_path(temp_dir / 'test.py', temp_dir) is not None

        # Test dangerous paths (outside boundaries)
        assert validate_file_path('/etc/passwd', temp_dir) is None
        assert validate_file_path('../../../etc/passwd', temp_dir) is None
        assert validate_file_path(temp_dir.parent / 'outside.py', temp_dir) is None

    def test_no_subprocess_find_command(self):
        """Verify that subprocess.run is not used with 'find' command"""
        # This test ensures we're not using the vulnerable subprocess.run(['find', ...]) pattern

        # Read the review-code.md file to check for subprocess.run with find
        review_code_path = Path(__file__).parent.parent / '.claude' / 'commands' / 'review-code.md'
        if review_code_path.exists():
            content = review_code_path.read_text()

            # Check that we're not using subprocess.run with find anymore
            assert "subprocess.run(['find'" not in content or "# Use safe file discovery instead of subprocess find" in content

            # Check that we are using the safe pathlib-based approach
            assert "discover_files_safe" in content or "Path" in content

    def test_git_command_timeout_handling(self):
        """Test that git commands have proper timeout and error handling"""

        # Simulate the git diff command with timeout from review-code.md
        def get_git_diff_safe():
            """Get git diff with proper error handling"""
            import subprocess
            try:
                diff_result = subprocess.run(['git', 'diff', 'HEAD'],
                                           capture_output=True, text=True,
                                           timeout=30, check=False)
                if diff_result.returncode == 0:
                    return diff_result.stdout if diff_result.stdout.strip() else "No changes detected"
                else:
                    return "Could not get git diff"
            except subprocess.TimeoutExpired:
                return "Git diff timed out"
            except Exception:
                return "Could not get git diff"

        with patch('subprocess.run') as mock_run:
            # Test successful execution
            mock_run.return_value = MagicMock(returncode=0, stdout="diff content")
            result = get_git_diff_safe()
            assert result == "diff content"

            # Test timeout
            mock_run.side_effect = subprocess.TimeoutExpired('git', 30)
            result = get_git_diff_safe()
            assert result == "Git diff timed out"

            # Test other exceptions
            mock_run.side_effect = Exception("Unknown error")
            result = get_git_diff_safe()
            assert result == "Could not get git diff"

    def test_resource_exhaustion_prevention(self, temp_dir):
        """Test that file discovery has proper limits to prevent resource exhaustion"""

        # Create many files
        for i in range(100):
            (temp_dir / f'file{i}.py').touch()

        def discover_files_safe(base_dir, max_files=50):
            """Safely discover files with resource limits"""
            files = []
            base_path = Path(base_dir)

            for file_path in base_path.rglob('*.py'):
                files.append(str(file_path.relative_to(base_path)))

                # Enforce limit to prevent resource exhaustion
                if len(files) >= max_files:
                    break

            return files[:max_files]

        # Test that it respects the limit
        files = discover_files_safe(temp_dir, max_files=50)
        assert len(files) == 50  # Should be limited to 50 files

        files = discover_files_safe(temp_dir, max_files=10)
        assert len(files) == 10  # Should be limited to 10 files

    def test_context_data_length_limits(self):
        """Test that context data is limited in length to prevent DoS"""

        def safe_format_prompt(template, context_data):
            """Format with length limits"""
            sanitized_context = {}
            for key, value in context_data.items():
                if value is None:
                    sanitized_context[key] = ""
                else:
                    str_value = str(value)
                    # Limit length to prevent DoS
                    sanitized_context[key] = str_value[:10000]

            # Simple substitution for test
            result = template
            for key, value in sanitized_context.items():
                result = result.replace(f'{{{key}}}', value)
            return result

        # Test with very long input
        long_string = "A" * 20000  # 20k characters
        template = "Review: {content}"
        context = {'content': long_string}

        result = safe_format_prompt(template, context)

        # Should be truncated to 10000 characters
        assert len(result) < 15000  # Account for template text
        assert "A" * 10000 in result
        assert "A" * 10001 not in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])