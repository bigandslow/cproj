#!/usr/bin/env python3
"""
External integrations for cproj (1Password, GitHub)
"""

import getpass
import shutil
import subprocess
from typing import Optional

from cproj_security import SecurityError, safe_subprocess_run, validate_user_input


class OnePasswordIntegration:
    """1Password CLI integration for secret management"""

    @staticmethod
    def is_available() -> bool:
        """Check if 1Password CLI is available and authenticated"""
        if not shutil.which("op"):
            return False

        try:
            # Check if authenticated
            safe_subprocess_run(["op", "account", "list"], timeout=5)
            return True
        except (subprocess.CalledProcessError, SecurityError):
            return False

    @staticmethod
    def get_secret(reference: str) -> Optional[str]:
        """Get secret from 1Password using secret reference"""
        if not OnePasswordIntegration.is_available():
            return None

        try:
            # Validate the reference parameter
            validated_reference = validate_user_input(
                reference, max_length=500, allow_special_chars=True
            )
            result = safe_subprocess_run(["op", "read", validated_reference], timeout=10)
            return result.stdout.strip()
        except (subprocess.CalledProcessError, SecurityError):
            return None

    @staticmethod
    def store_secret(title: str, value: str, vault: Optional[str] = None) -> Optional[str]:
        """Store secret in 1Password and return reference"""
        if not OnePasswordIntegration.is_available():
            return None

        try:
            # Validate inputs
            validated_title = validate_user_input(title, max_length=100)
            validated_value = validate_user_input(
                value, max_length=1000, allow_special_chars=True
            )
            validated_vault = None
            if vault:
                validated_vault = validate_user_input(vault, max_length=100)

            cmd = [
                "op",
                "item",
                "create",
                "--category=password",
                f"--title={validated_title}",
            ]
            if validated_vault:
                cmd.append(f"--vault={validated_vault}")
            cmd.append(f"password={validated_value}")

            safe_subprocess_run(cmd, timeout=10)
            # Extract reference from output (simplified)
            return f"op://{validated_vault or 'Private'}/{validated_title}/password"
        except (subprocess.CalledProcessError, SecurityError):
            return None

    @staticmethod
    def prompt_for_secret(prompt_text: str, secret_name: str) -> Optional[str]:
        """Prompt user for secret and optionally store in 1Password"""
        available = OnePasswordIntegration.is_available()

        if available:
            try:
                store_choice = validate_user_input(
                    input(f"Store {secret_name} in 1Password? [y/N]: "), max_length=10
                ).lower()
            except SecurityError:
                store_choice = "n"

        secret_value = getpass.getpass(f"{prompt_text}: ")

        if available and store_choice == "y":
            try:
                vault = validate_user_input(
                    input("1Password vault name (or press Enter for Private): "),
                    max_length=100
                ).strip() or None
            except SecurityError:
                vault = None

            return OnePasswordIntegration.store_secret(secret_name, secret_value, vault)

        return secret_value


class GitHubIntegration:
    """GitHub CLI integration"""

    @staticmethod
    def is_available() -> bool:
        """Check if GitHub CLI is available and authenticated"""
        if not shutil.which("gh"):
            return False

        try:
            safe_subprocess_run(["gh", "auth", "status"], timeout=5)
            return True
        except (subprocess.CalledProcessError, SecurityError):
            return False

    @staticmethod
    def authenticate() -> bool:
        """Authenticate with GitHub CLI"""
        if GitHubIntegration.is_available():
            return True

        try:
            safe_subprocess_run(["gh", "auth", "login"], timeout=60)
            return True
        except (subprocess.CalledProcessError, SecurityError):
            return False

    @staticmethod
    def create_pr(title: str, body: str, base: str = "main", draft: bool = False) -> bool:
        """Create a pull request"""
        if not GitHubIntegration.is_available():
            return False

        try:
            # Validate inputs
            validated_title = validate_user_input(title, max_length=200)
            validated_body = validate_user_input(
                body, max_length=5000, allow_special_chars=True
            )
            validated_base = validate_user_input(base, max_length=100)

            cmd = ["gh", "pr", "create", "--title", validated_title, "--body", validated_body]
            if validated_base != "main":
                cmd.extend(["--base", validated_base])
            if draft:
                cmd.append("--draft")

            safe_subprocess_run(cmd, timeout=30)
            return True
        except (subprocess.CalledProcessError, SecurityError):
            return False