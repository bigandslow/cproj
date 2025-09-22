#!/usr/bin/env python3
"""
Security utilities for cproj - input validation and safe subprocess execution
"""

import re
import subprocess
from pathlib import Path
from typing import Any, List, Union


class SecurityError(Exception):
    """Security-related exceptions"""
    pass


def validate_branch_name(name: str) -> str:
    """
    Validate and sanitize git branch name

    Args:
        name: Branch name to validate

    Returns:
        Sanitized branch name

    Raises:
        SecurityError: If branch name is invalid or potentially dangerous
    """
    if not name or not isinstance(name, str):
        raise SecurityError("Branch name must be a non-empty string")

    name = name.strip()

    # Check length
    if len(name) > 250:
        raise SecurityError("Branch name too long (max 250 characters)")

    # Check for dangerous patterns
    dangerous_patterns = [
        r'\.\./',          # Path traversal
        r'^-',             # Starting with dash (command option)
        r'[;&|`$()]',      # Shell metacharacters
        r'[\x00-\x1f]',    # Control characters
        r'\\',             # Backslashes
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, name):
            raise SecurityError(f"Branch name contains invalid characters: {name}")

    # Git branch name restrictions
    if name.startswith('.') or name.endswith('.'):
        raise SecurityError("Branch name cannot start or end with a dot")

    if '//' in name or name.endswith('/') or name.startswith('/'):
        raise SecurityError("Invalid slash usage in branch name")

    if '@{' in name:
        raise SecurityError("Branch name cannot contain '@{'")

    return name


def validate_file_path(path: Union[str, Path], allow_relative: bool = False) -> Path:
    """
    Validate file path for security issues

    Args:
        path: File path to validate
        allow_relative: Whether to allow relative paths

    Returns:
        Validated Path object

    Raises:
        SecurityError: If path is potentially dangerous
    """
    if not path:
        raise SecurityError("Path cannot be empty")

    path_obj = Path(path)

    # Check for path traversal
    if '..' in path_obj.parts:
        raise SecurityError("Path traversal detected")

    # Check for absolute paths when not allowed
    if not allow_relative and not path_obj.is_absolute():
        raise SecurityError("Relative paths not allowed")

    # Check for dangerous characters
    path_str = str(path_obj)
    if re.search(r'[;&|`$()]', path_str):
        raise SecurityError("Path contains shell metacharacters")

    if re.search(r'[\x00-\x1f]', path_str):
        raise SecurityError("Path contains control characters")

    return path_obj


def validate_user_input(user_input: str, max_length: int = 1000,
                       allow_special_chars: bool = False) -> str:
    """
    Validate and sanitize user input

    Args:
        user_input: Input to validate
        max_length: Maximum allowed length
        allow_special_chars: Whether to allow special characters

    Returns:
        Sanitized input

    Raises:
        SecurityError: If input is potentially dangerous
    """
    if not isinstance(user_input, str):
        raise SecurityError("Input must be a string")

    if len(user_input) > max_length:
        raise SecurityError(f"Input too long (max {max_length} characters)")

    # Check for control characters
    if re.search(r'[\x00-\x08\x0b-\x1f\x7f]', user_input):
        raise SecurityError("Input contains control characters")

    # Check for dangerous patterns if special chars not allowed
    if not allow_special_chars:
        if re.search(r'[;&|`$()\\]', user_input):
            raise SecurityError("Input contains shell metacharacters")

    return user_input.strip()


def safe_file_write(file_path: Union[str, Path], content: str,
                    create_dirs: bool = True) -> None:
    """
    Safely write content to a file with validation

    Args:
        file_path: Path to write to
        content: Content to write
        create_dirs: Whether to create parent directories

    Raises:
        SecurityError: If path is invalid or operation is unsafe
    """
    validated_path = validate_file_path(file_path, allow_relative=False)

    # Check if we're writing to a safe location
    path_str = str(validated_path)
    unsafe_locations = ['/etc', '/usr', '/bin', '/sbin', '/var/log', '/root']
    for unsafe in unsafe_locations:
        if path_str.startswith(unsafe + '/') or path_str == unsafe:
            raise SecurityError(f"Cannot write to system location: {path_str}")

    if create_dirs:
        validated_path.parent.mkdir(parents=True, exist_ok=True)

    # Validate content
    if not isinstance(content, str):
        raise SecurityError("Content must be a string")

    # Check for suspiciously large content
    if len(content) > 10_000_000:  # 10MB limit
        raise SecurityError("Content too large")

    validated_path.write_text(content, encoding='utf-8')


def safe_file_read(file_path: Union[str, Path]) -> str:
    """
    Safely read file content with validation

    Args:
        file_path: Path to read from

    Returns:
        File content as string

    Raises:
        SecurityError: If path is invalid
    """
    validated_path = validate_file_path(file_path, allow_relative=False)

    if not validated_path.exists():
        raise SecurityError(f"File does not exist: {validated_path}")

    if not validated_path.is_file():
        raise SecurityError(f"Path is not a file: {validated_path}")

    # Check file size
    if validated_path.stat().st_size > 50_000_000:  # 50MB limit
        raise SecurityError("File too large to read safely")

    return validated_path.read_text(encoding='utf-8')


def safe_mkdir(dir_path: Union[str, Path], parents: bool = True,
                exist_ok: bool = True) -> None:
    """
    Safely create directory with validation

    Args:
        dir_path: Directory path to create
        parents: Whether to create parent directories
        exist_ok: Whether to ignore if directory exists

    Raises:
        SecurityError: If path is invalid
    """
    validated_path = validate_file_path(dir_path, allow_relative=False)

    # Check if we're creating in a safe location
    path_str = str(validated_path)
    unsafe_locations = ['/etc', '/usr', '/bin', '/sbin', '/var/log', '/root']
    for unsafe in unsafe_locations:
        if path_str.startswith(unsafe + '/') or path_str == unsafe:
            raise SecurityError(f"Cannot create directory in system location: {path_str}")

    validated_path.mkdir(parents=parents, exist_ok=exist_ok)


def safe_subprocess_run(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """
    Safely execute subprocess with enhanced error handling and validation

    Args:
        cmd: Command as list of strings
        **kwargs: Additional subprocess.run arguments

    Returns:
        CompletedProcess result

    Raises:
        SecurityError: If command is potentially dangerous
        subprocess.CalledProcessError: If command fails
    """
    if not cmd or not isinstance(cmd, list):
        raise SecurityError("Command must be a non-empty list")

    if not all(isinstance(arg, str) for arg in cmd):
        raise SecurityError("All command arguments must be strings")

    # Validate command executable
    executable = cmd[0]
    if not executable or not isinstance(executable, str):
        raise SecurityError("Command executable must be a non-empty string")

    # Check for dangerous patterns in command
    for arg in cmd:
        # Allow metacharacters in args but not in executable
        if re.search(r'[;&|`$()]', arg) and arg not in cmd[1:]:
            raise SecurityError(f"Command contains shell metacharacters: {arg}")

        if re.search(r'[\x00-\x1f]', arg):
            raise SecurityError(f"Command contains control characters: {arg}")

    # Set safe defaults
    safe_kwargs = {
        'shell': False,  # Never use shell=True
        'timeout': kwargs.get('timeout', 30),  # Default timeout
        'capture_output': kwargs.get('capture_output', True),
        'text': kwargs.get('text', True),
        'check': kwargs.get('check', True),
    }

    # Allow override of safe defaults only for specific keys
    allowed_overrides = {'timeout', 'capture_output', 'text', 'check', 'cwd', 'env'}
    for key, value in kwargs.items():
        if key in allowed_overrides:
            safe_kwargs[key] = value

    try:
        return subprocess.run(cmd, **safe_kwargs)
    except subprocess.TimeoutExpired:
        raise SecurityError(f"Command timed out: {' '.join(cmd[:2])}...")
    except subprocess.CalledProcessError as e:
        # Re-raise with more context but don't expose full command in error
        raise subprocess.CalledProcessError(
            e.returncode,
            cmd[0],  # Only show executable name
            e.output,
            e.stderr
        )
