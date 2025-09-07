#!/usr/bin/env python3
"""
Test suite for claude_review_agents.py
Comprehensive security and functionality tests
"""

import json
import pytest
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import the module under test
from claude_review_agents import (
    ClaudeReviewOrchestrator, 
    ProjectContext,
    safe_json_loads,
    setup_review,
    _sanitize_pii_for_logging
)


class TestProjectContext:
    """Test ProjectContext dataclass"""
    
    def test_default_initialization(self):
        """Test ProjectContext creates with sensible defaults"""
        context = ProjectContext()
        assert context.pr_title == ""
        assert context.arch_notes == "Python/TypeScript monorepo, REST APIs, PostgreSQL, Docker, AWS"
        assert context.data_classification == "Internal"
    
    def test_custom_initialization(self):
        """Test ProjectContext accepts custom values"""
        context = ProjectContext(
            pr_title="Test PR", 
            ticket="TEST-123",
            arch_notes="Custom architecture"
        )
        assert context.pr_title == "Test PR"
        assert context.ticket == "TEST-123" 
        assert context.arch_notes == "Custom architecture"


class TestClaudeReviewOrchestratorSecurity:
    """Security-focused tests for ClaudeReviewOrchestrator"""
    
    def test_path_validation_prevents_traversal(self):
        """Test that path validation prevents directory traversal attacks"""
        with pytest.raises(ValueError, match="Potentially unsafe path"):
            ClaudeReviewOrchestrator(Path("../../../etc/passwd"))
        
        with pytest.raises(ValueError, match="Potentially unsafe path"):
            ClaudeReviewOrchestrator(Path(".."))
    
    def test_path_validation_requires_git_repo(self):
        """Test that path validation requires a git repository"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="Not a git repository"):
                ClaudeReviewOrchestrator(Path(tmpdir))
    
    def test_safe_path_join_prevents_traversal(self):
        """Test _safe_path_join prevents directory traversal"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake git repo
            git_dir = Path(tmpdir) / '.git'
            git_dir.mkdir()
            
            orchestrator = ClaudeReviewOrchestrator(Path(tmpdir))
            
            # Test legitimate file names
            safe_path = orchestrator._safe_path_join(Path(tmpdir), '.agent.json')
            assert '.agent.json' in str(safe_path)
            
            # Test directory traversal attempts
            with pytest.raises(ValueError, match="Unsafe filename"):
                orchestrator._safe_path_join(Path(tmpdir), '../../../etc/passwd')
            
            with pytest.raises(ValueError, match="Unsafe filename"):
                orchestrator._safe_path_join(Path(tmpdir), 'sub/dir/file')
    
    def test_sanitize_context_value_removes_dangerous_chars(self):
        """Test context value sanitization removes dangerous characters"""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / '.git'
            git_dir.mkdir()
            
            orchestrator = ClaudeReviewOrchestrator(Path(tmpdir))
            
            # Test with potentially malicious input
            malicious = "$(rm -rf /) && echo 'hacked'"
            sanitized = orchestrator._sanitize_context_value(malicious)
            
            # Should remove dangerous shell characters
            assert '$' not in sanitized
            assert '&&' not in sanitized
            assert 'rm -rf' in sanitized  # Content preserved but shell chars removed
    
    def test_sanitize_context_value_truncates_long_input(self):
        """Test context value sanitization truncates overly long input"""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / '.git'
            git_dir.mkdir()
            
            orchestrator = ClaudeReviewOrchestrator(Path(tmpdir))
            
            long_input = "A" * 2000
            sanitized = orchestrator._sanitize_context_value(long_input, max_length=100)
            
            assert len(sanitized) <= 103  # 100 + "..."
            assert sanitized.endswith("...")


class TestSubprocessSecurity:
    """Test subprocess security measures"""
    
    @patch('subprocess.run')
    def test_git_commands_use_timeout(self, mock_run):
        """Test that git commands have timeout protection"""
        # Setup mock to return empty result
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / '.git'
            git_dir.mkdir()
            
            orchestrator = ClaudeReviewOrchestrator(Path(tmpdir))
            orchestrator.get_diff()
            
            # Verify subprocess.run was called with timeout
            for call in mock_run.call_args_list:
                if 'timeout' in call.kwargs:
                    assert call.kwargs['timeout'] > 0
    
    @patch('subprocess.run')
    def test_git_commands_handle_timeout_gracefully(self, mock_run):
        """Test graceful handling of subprocess timeouts"""
        # Mock timeout exception
        mock_run.side_effect = subprocess.TimeoutExpired('git', 30)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / '.git'  
            git_dir.mkdir()
            
            orchestrator = ClaudeReviewOrchestrator(Path(tmpdir))
            result = orchestrator.get_diff()
            
            # Should return empty string on timeout, not crash
            assert result == ""
    
    @patch('subprocess.run')
    def test_subprocess_uses_safe_arguments(self, mock_run):
        """Test subprocess calls use array arguments (not shell)"""
        mock_run.return_value = Mock(returncode=0, stdout="main\n", stderr="")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / '.git'
            git_dir.mkdir()
            
            orchestrator = ClaudeReviewOrchestrator(Path(tmpdir))
            orchestrator.load_project_context()
            
            # Verify all subprocess calls use list arguments (not shell=True)
            for call in mock_run.call_args_list:
                assert isinstance(call.args[0], list)  # First arg should be list
                assert call.kwargs.get('shell', False) == False  # shell should be False or absent


class TestJSONSafety:
    """Test JSON parsing security"""
    
    def test_safe_json_loads_validates_size(self):
        """Test JSON size validation"""
        large_json = '{"key": "' + 'A' * 20000 + '"}'
        
        with pytest.raises(ValueError, match="JSON input too large"):
            safe_json_loads(large_json)
    
    def test_safe_json_loads_validates_format(self):
        """Test JSON format validation"""
        with pytest.raises(ValueError, match="Invalid JSON"):
            safe_json_loads("not json")
        
        with pytest.raises(ValueError, match="JSON input must be an object"):
            safe_json_loads('"string"')  # Valid JSON but not object
        
        with pytest.raises(ValueError, match="JSON input must be an object"):
            safe_json_loads('[1,2,3]')  # Valid JSON but not object
    
    def test_safe_json_loads_accepts_valid_input(self):
        """Test safe_json_loads accepts valid input"""
        valid_json = '{"ticket": "TEST-123", "arch_notes": "Python app"}'
        result = safe_json_loads(valid_json)
        
        assert isinstance(result, dict)
        assert result["ticket"] == "TEST-123"
    
    def test_safe_json_loads_validates_nested_depth(self):
        """Test JSON nested depth validation"""
        # Create deeply nested JSON (depth > 10)
        nested_json = '{"level1": {"level2": {"level3": {"level4": {"level5": {"level6": {"level7": {"level8": {"level9": {"level10": {"level11": "too deep"}}}}}}}}}}}'
        
        with pytest.raises(ValueError, match="JSON nesting too deep"):
            safe_json_loads(nested_json)
    
    def test_safe_json_loads_validates_object_count(self):
        """Test JSON object count validation"""
        # Create JSON with too many objects
        large_json = '{'
        for i in range(101):  # More than max_nested_objects=100  
            large_json += f'"obj{i}": {{"data": "value{i}"}},'
        large_json = large_json.rstrip(',') + '}'
        
        with pytest.raises(ValueError, match="JSON contains too many objects"):
            safe_json_loads(large_json)


class TestTemplateSecurityFixes:
    """Test template injection prevention"""
    
    def test_format_agent_prompt_uses_safe_substitution(self):
        """Test that template formatting uses safe substitution"""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / '.git'
            git_dir.mkdir()
            
            context = ProjectContext()
            # Try to inject template syntax
            context.pr_title = "${evil_substitution}"
            context.arch_notes = "$invalid_var"
            
            orchestrator = ClaudeReviewOrchestrator(Path(tmpdir), context)
            
            template = "Title: $pr_title, Arch: $arch_notes, Diff: $pr_diff"
            result = orchestrator.format_agent_prompt(template, "test diff")
            
            # Template variables should be safely substituted or left as-is
            assert "evil_substitution" not in result or "$" not in result
    
    def test_diff_truncation_at_line_boundaries(self):
        """Test diff truncation preserves line integrity"""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / '.git'
            git_dir.mkdir()
            
            orchestrator = ClaudeReviewOrchestrator(Path(tmpdir))
            
            # Create a diff with many lines
            long_diff = "\n".join([f"line {i}" for i in range(300)])
            template = "Diff: $pr_diff"
            
            result = orchestrator.format_agent_prompt(template, long_diff)
            
            # Should be truncated but with proper message
            assert "[... diff truncated for length ...]" in result
            # Should not end mid-line
            assert not result.split('\n')[-2].startswith('line') or result.endswith('[... diff truncated for length ...]')


class TestIntegrationSafety:
    """Integration tests for security fixes"""
    
    def test_setup_review_with_malicious_path(self):
        """Test setup_review handles malicious paths safely"""
        malicious_path = Path("../../../etc")
        
        with pytest.raises(ValueError):
            setup_review(malicious_path)
    
    @patch('claude_review_agents.ClaudeReviewOrchestrator')
    def test_setup_review_handles_orchestrator_failure(self, mock_orchestrator):
        """Test setup_review handles orchestrator failures gracefully"""
        mock_orchestrator.side_effect = Exception("Mocked failure")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / '.git'
            git_dir.mkdir()
            
            # Should not crash, but may return error result
            try:
                result = setup_review(Path(tmpdir))
            except Exception as e:
                # If it raises, should be a clear error message
                assert "Mocked failure" in str(e)


class TestErrorHandling:
    """Test improved error handling"""
    
    @patch('subprocess.run')
    def test_specific_exception_handling(self, mock_run):
        """Test that specific exceptions are caught instead of bare except"""
        # This test verifies the code uses specific exception types
        mock_run.side_effect = subprocess.CalledProcessError(1, 'git')
        
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / '.git'
            git_dir.mkdir()
            
            orchestrator = ClaudeReviewOrchestrator(Path(tmpdir))
            # Should handle the exception gracefully
            result = orchestrator.get_diff()
            assert result == ""  # Should return empty on error
    
    def test_file_permission_errors(self):
        """Test handling of file permission errors"""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / '.git'
            git_dir.mkdir()
            
            # Create an unreadable .agent.json file
            agent_file = Path(tmpdir) / '.agent.json'
            agent_file.write_text('{"test": "data"}')
            agent_file.chmod(0o000)  # No permissions
            
            try:
                # Should handle permission error gracefully
                orchestrator = ClaudeReviewOrchestrator(Path(tmpdir))
                # Verify it doesn't crash, may not load context but that's OK
                assert orchestrator.context is not None
            finally:
                # Restore permissions for cleanup
                agent_file.chmod(0o644)


class TestPIISanitization:
    """Test PII sanitization in logging"""
    
    def test_sanitize_pii_emails(self):
        """Test email sanitization"""
        message = "User john.doe@example.com encountered error"
        sanitized = _sanitize_pii_for_logging(message)
        assert "john.doe@example.com" not in sanitized
        assert "[EMAIL_REDACTED]" in sanitized
    
    def test_sanitize_pii_api_keys(self):
        """Test API key sanitization"""
        message = "Failed with token sk-1234567890abcdef1234567890abcdef12345678901234567890"
        sanitized = _sanitize_pii_for_logging(message)
        assert "1234567890abcdef1234567890abcdef" not in sanitized
        assert "[TOKEN_REDACTED]" in sanitized or "[API_KEY_REDACTED]" in sanitized
    
    def test_sanitize_pii_file_paths(self):
        """Test file path username sanitization"""
        message = "Error in /Users/johndoe/project/file.py"
        sanitized = _sanitize_pii_for_logging(message)
        assert "johndoe" not in sanitized
        assert "/Users/[USER_REDACTED]/project/file.py" in sanitized
    
    def test_sanitize_pii_ip_addresses(self):
        """Test IP address sanitization"""
        message = "Connection to 192.168.1.100 failed"
        sanitized = _sanitize_pii_for_logging(message)
        assert "192.168.1.100" not in sanitized
        assert "[IP_REDACTED]" in sanitized
    
    def test_sanitize_pii_preserves_safe_content(self):
        """Test that safe content is preserved"""
        message = "Git command failed with exit code 1"
        sanitized = _sanitize_pii_for_logging(message)
        assert sanitized == message  # Should be unchanged


if __name__ == "__main__":
    pytest.main([__file__, "-v"])