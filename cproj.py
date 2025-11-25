#!/usr/bin/env python3
"""
cproj - Multi-project CLI with git worktree + uv
A production-ready CLI tool for managing parallel project work using Git
worktrees
"""

import argparse
import getpass
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

# Setup logging
logger = logging.getLogger("cproj")
handler = logging.StreamHandler()
formatter = logging.Formatter("%(levelname)s: %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


class CprojError(Exception):
    """Base exception for cproj errors"""

    pass


class OnePasswordIntegration:
    """1Password CLI integration for secret management"""

    @staticmethod
    def is_available() -> bool:
        """Check if 1Password CLI is available and authenticated"""
        if not shutil.which("op"):
            return False

        else:
            try:
                # Check if authenticated
                subprocess.run(
                    ["op", "account", "list"],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
                return True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                return False

    @staticmethod
    def get_secret(reference: str) -> Optional[str]:
        """Get secret from 1Password using secret reference"""
        if not OnePasswordIntegration.is_available():
            return None

        try:
            result = subprocess.run(
                ["op", "read", reference],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None

    @staticmethod
    def store_secret(title: str, value: str, vault: Optional[str] = None) -> Optional[str]:
        """Store secret in 1Password and return reference"""
        if not OnePasswordIntegration.is_available():
            return None

        try:
            cmd = [
                "op",
                "item",
                "create",
                "--category=password",
                f"--title={title}",
            ]
            if vault:
                cmd.append(f"--vault={vault}")
            cmd.append(f"password={value}")

            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            # Extract reference from output (simplified)
            return f"op://{vault or 'Private'}/{title}/password"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None

    @staticmethod
    def prompt_for_secret(prompt_text: str, secret_name: str) -> Optional[str]:
        """Prompt user for secret and optionally store in 1Password"""
        if OnePasswordIntegration.is_available():
            store_choice = input(f"Store {secret_name} in 1Password? [y/N]: ").lower().strip()

        secret_value = getpass.getpass(f"{prompt_text}: ")

        if OnePasswordIntegration.is_available() and store_choice == "y":
            vault = input("1Password vault name (or press Enter for Private): ").strip() or None
            reference = OnePasswordIntegration.store_secret(
                f"cproj-{secret_name}", secret_value, vault or "Private"
            )
            if reference:
                print(f"Stored in 1Password. Reference: {reference}")
                return reference

        return secret_value


class Config:
    """Configuration management"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path.home() / ".config" / "cproj" / "config.json"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config = self._load_config()

    def _load_config(self) -> Dict:
        if self.config_path.exists():
            with self.config_path.open() as f:
                return json.load(f)
        return {}

    def save(self):
        with self.config_path.open("w") as f:
            json.dump(self._config, f, indent=2)

    def get(self, key: str, default=None):
        return self._config.get(key, default)

    def set(self, key: str, value):
        self._config[key] = value
        self.save()


class PortRegistry:
    """Manage port offset allocations across worktrees"""

    def __init__(self):
        self.registry_path = Path.home() / ".config" / "cproj" / "ports.json"
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._registry: Dict[str, Dict[str, int]] = self._load_registry()

    def _load_registry(self) -> Dict[str, Dict[str, int]]:
        """Load port registry from disk"""
        if not self.registry_path.exists():
            return {}
        try:
            with open(self.registry_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load port registry: {e}")
            return {}

    def _save_registry(self):
        """Save port registry to disk"""
        try:
            with open(self.registry_path, "w") as f:
                json.dump(self._registry, f, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save port registry: {e}")

    def get_next_available_offset(self, project_name: str, max_slots: int = 99) -> Optional[int]:
        """Get next available port offset for a project"""
        if project_name not in self._registry:
            self._registry[project_name] = {}

        allocated_offsets = set(self._registry[project_name].values())

        # Find first available offset
        for offset in range(max_slots + 1):
            if offset not in allocated_offsets:
                return offset

        return None  # All slots taken

    def allocate(self, project_name: str, worktree_path: Path, offset: int) -> bool:
        """Allocate a port offset for a worktree"""
        if project_name not in self._registry:
            self._registry[project_name] = {}

        worktree_key = str(worktree_path.resolve())

        # Check if offset is already taken by another worktree
        for path, existing_offset in self._registry[project_name].items():
            if existing_offset == offset and path != worktree_key:
                logger.warning(f"Offset {offset} already allocated to {path}")
                return False

        self._registry[project_name][worktree_key] = offset
        self._save_registry()
        return True

    def deallocate(self, project_name: str, worktree_path: Path) -> bool:
        """Deallocate port offset for a worktree"""
        if project_name not in self._registry:
            return False

        worktree_key = str(worktree_path.resolve())

        if worktree_key in self._registry[project_name]:
            del self._registry[project_name][worktree_key]
            self._save_registry()
            return True

        return False

    def get_offset(self, project_name: str, worktree_path: Path) -> Optional[int]:
        """Get port offset for a worktree"""
        if project_name not in self._registry:
            return None

        worktree_key = str(worktree_path.resolve())
        return self._registry[project_name].get(worktree_key)

    def list_allocations(self, project_name: str) -> Dict[str, int]:
        """List all port allocations for a project"""
        return self._registry.get(project_name, {})


class ProjectConfig:
    """Project-specific configuration management"""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.config_path = repo_path / ".cproj" / "project.yaml"
        self._config: Dict[str, Any] = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load project configuration from project.yaml"""
        if not self.config_path.exists():
            return self._get_default_config()

        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f) or {}
        except (yaml.YAMLError, IOError) as e:
            logger.warning(f"Failed to load project config: {e}")
            return self._get_default_config()

        # Merge with defaults
        default_config = self._get_default_config()
        features = default_config["features"].copy()
        features.update(config.get("features", {}))

        custom_actions = default_config.get("custom_actions", [])
        custom_actions.extend(config.get("custom_actions", []))

        return {
            "name": config.get("name", self.repo_path.name),
            "type": config.get("type", "generic"),
            "features": features,
            "custom_actions": custom_actions,
            "mcp_servers": config.get("mcp_servers", []),
            "port_config": config.get("port_config", {}),
            "base_branch": config.get("base_branch", "main"),
        }

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration for projects without config"""
        return {
            "name": self.repo_path.name,
            "type": "generic",
            "features": {
                "claude_workspace": False,
                "claude_symlink": False,
                "review_agents": False,
                "nvm_setup": False,
                "env_sync_check": False,
            },
            "custom_actions": [],
            "base_branch": "main",
        }

    def save(self):
        """Save configuration to project.yaml"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_path, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        return self._config.get("features", {}).get(feature, False)

    def get_project_name(self) -> str:
        """Get project name"""
        return self._config.get("name", self.repo_path.name)

    def get_project_type(self) -> str:
        """Get project type"""
        return self._config.get("type", "generic")

    def enable_feature(self, feature: str, enabled: bool = True):
        """Enable or disable a feature"""
        if "features" not in self._config:
            self._config["features"] = {}
        self._config["features"][feature] = enabled

    def set_project_info(self, name: str, project_type: str):
        """Set project name and type"""
        self._config["name"] = name
        self._config["type"] = project_type

    def get_port_config(self) -> Dict[str, Any]:
        """Get port allocation configuration"""
        return self._config.get("port_config", {})

    def get_base_port(self) -> int:
        """Get base port for port allocation"""
        return self.get_port_config().get("base_port", 3000)

    def get_max_slots(self) -> int:
        """Get maximum port slots"""
        return self.get_port_config().get("max_slots", 99)

    def get_base_branch(self) -> str:
        """Get the default base branch for creating new branches"""
        return self._config.get("base_branch", "main")

    def set_base_branch(self, branch: str):
        """Set the default base branch for creating new branches"""
        self._config["base_branch"] = branch

    def get_custom_actions(self) -> List[Dict[str, Any]]:
        """Get list of custom actions"""
        return self._config.get("custom_actions", [])

    def add_custom_action(self, action: Dict[str, Any]):
        """Add a custom action"""
        if "custom_actions" not in self._config:
            self._config["custom_actions"] = []
        self._config["custom_actions"].append(action)

    def get_mcp_servers(self) -> List[Dict[str, Any]]:
        """Get list of MCP servers to configure"""
        return self._config.get("mcp_servers", [])

    def add_mcp_server(self, server: Dict[str, Any]):
        """Add an MCP server configuration"""
        if "mcp_servers" not in self._config:
            self._config["mcp_servers"] = []
        self._config["mcp_servers"].append(server)


class GitWorktree:
    """Git worktree management"""

    def __init__(self, repo_path: Path):
        self.repo_path = self._find_git_root(Path(repo_path))
        if not self.repo_path:
            raise CprojError(f"Not a git repository: {repo_path}")

    def fetch_all(self):
        """Fetch all remotes"""
        self._run_git(["fetch", "--all", "--prune"])

    def ensure_base_branch(self, base_branch: str):
        """Ensure base branch exists and is up to date"""
        try:
            # Check if branch exists locally
            self._run_git(
                [
                    "show-ref",
                    "--verify",
                    "--quiet",
                    f"refs/heads/{base_branch}",
                ]
            )
        except subprocess.CalledProcessError:
            # Create from origin if it doesn't exist
            try:
                self._run_git(["branch", base_branch, f"origin/{base_branch}"])
            except subprocess.CalledProcessError:
                raise CprojError(f"Base branch '{base_branch}' not found locally or on " f"origin")

        # Fast-forward the base branch
        current_branch = self._get_current_branch()
        if current_branch != base_branch:
            self._run_git(["checkout", base_branch])

        try:
            self._run_git(["merge", "--ff-only", f"origin/{base_branch}"])
        except subprocess.CalledProcessError:
            print(f"Warning: Could not fast-forward {base_branch}")

        if current_branch and current_branch != base_branch:
            self._run_git(["checkout", current_branch])

    def branch_exists(self, branch: str) -> bool:
        """Check if a branch exists"""
        try:
            self._run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"])
            return True
        except subprocess.CalledProcessError:
            return False

    def is_branch_checked_out(self, branch: str) -> bool:
        """Check if a branch is already checked out in a worktree"""
        try:
            # List all worktrees and check if any have this branch checked out
            result = self._run_git(
                ["worktree", "list", "--porcelain"],
                capture_output=True,
                text=True,
            )
            current_branch = None
            for line in result.stdout.strip().split("\n"):
                if line.startswith("branch "):
                    current_branch = (
                        line.split("refs/heads/", 1)[1] if "refs/heads/" in line else None
                    )
                    if current_branch == branch:
                        return True
            return False
        except subprocess.CalledProcessError:
            return False

    def create_worktree(
        self,
        worktree_path: Path,
        branch: str,
        base_branch: str,
        interactive: bool = True,
    ) -> Path:
        """Create a new worktree"""
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if branch already exists
        if self.branch_exists(branch):
            # Check if it's already checked out somewhere
            if self.is_branch_checked_out(branch):
                if interactive:
                    print(f"⚠️  Branch '{branch}' is already checked out in " f"another worktree.")
                    print("\nOptions:")
                    print("  1. Create worktree with a different branch name")
                    print("  2. Switch to existing worktree (if you know where " "it is)")
                    print("  3. Force create worktree (may cause issues)")
                    print("  4. Cancel")

                    while True:
                        choice = input("Choose option [1-4]: ").strip()
                        if choice == "1":
                            new_branch = input("Enter new branch name: ").strip()
                            if new_branch:
                                branch = new_branch
                                break
                            else:
                                print("❌ Branch name cannot be empty")
                                continue
                        elif choice == "2":
                            raise CprojError(
                                f"Branch '{branch}' is checked out elsewhere. "
                                f"Use 'git worktree list' to find it."
                            )
                        elif choice == "3":
                            # Force create new worktree, detaching the branch
                            # from current location
                            try:
                                self._run_git(
                                    [
                                        "worktree",
                                        "add",
                                        "--force",
                                        str(worktree_path),
                                        branch,
                                    ]
                                )
                                return worktree_path
                            except subprocess.CalledProcessError as e:
                                raise CprojError(f"Failed to force create worktree: {e}")
                        elif choice == "4":
                            raise CprojError("Worktree creation cancelled by user")
                        else:
                            print("❌ Please enter 1, 2, 3, or 4")
                            continue
                else:
                    raise CprojError(
                        f"Branch '{branch}' is already checked out. "
                        "Use --force to override or choose a different branch "
                        "name."
                    )

            # Branch exists but not checked out, use it
            try:
                self._run_git(["worktree", "add", str(worktree_path), branch])
            except subprocess.CalledProcessError as e:
                raise CprojError(
                    f"Failed to create worktree with existing branch " f"'{branch}': {e}"
                )
        else:
            # Branch doesn't exist, create it
            try:
                self._run_git(
                    [
                        "worktree",
                        "add",
                        "-b",
                        branch,
                        str(worktree_path),
                        base_branch,
                    ]
                )
            except subprocess.CalledProcessError as e:
                raise CprojError(f"Failed to create new branch '{branch}': {e}")

        return worktree_path

    def remove_worktree(self, worktree_path: Path, force: bool = False):
        """Remove a worktree"""
        cmd = ["worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(worktree_path))
        self._run_git(cmd)

    def delete_branch(self, branch_name: str, force: bool = False):
        """Delete a branch"""
        cmd = ["branch"]
        if force:
            cmd.append("-D")  # Force delete
        else:
            cmd.append("-d")  # Safe delete (only if merged)
        cmd.append(branch_name)
        self._run_git(cmd)

    def remove_worktree_and_branch(self, worktree_path: Path, force: bool = False):
        """Remove a worktree and its associated branch"""
        # First, get the branch name for this worktree
        worktrees = self.list_worktrees()
        branch_name = None

        for wt in worktrees:
            if Path(wt["path"]) == worktree_path:
                branch_name = wt.get("branch")
                break

        # Remove the worktree first
        self.remove_worktree(worktree_path, force=force)

        # Then delete the branch if we found one and it's not a main/master branch
        if branch_name and branch_name not in ["main", "master", "develop"]:
            try:
                self.delete_branch(branch_name, force=force)
            except subprocess.CalledProcessError as e:
                # Don't fail the whole operation if branch deletion fails
                logger.debug(f"Failed to delete branch {branch_name}: {e}")
                print(f"⚠️  Warning: Could not delete branch '{branch_name}': {e}")

        return branch_name

    def list_worktrees(self) -> List[Dict]:
        """List all worktrees"""
        result = self._run_git(["worktree", "list", "--porcelain"], capture_output=True, text=True)
        worktrees = []
        current_tree: Dict[str, str] = {}

        for line in result.stdout.strip().split("\n"):
            if line.startswith("worktree "):
                if current_tree:
                    worktrees.append(current_tree)
                current_tree = {"path": line.split(" ", 1)[1]}
            elif line.startswith("HEAD "):
                current_tree["commit"] = line.split(" ", 1)[1]
            elif line.startswith("branch "):
                current_tree["branch"] = line.split("refs/heads/", 1)[1]
            elif line == "bare":
                current_tree["bare"] = "True"
            elif line == "detached":
                current_tree["detached"] = "True"

        if current_tree:
            worktrees.append(current_tree)

        return worktrees

    def get_status(self, worktree_path: Path) -> Dict:
        """Get status for a specific worktree"""
        try:
            # Get ahead/behind info
            result = self._run_git(
                ["rev-list", "--left-right", "--count", "HEAD...@{u}"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
            )
            ahead, behind = map(int, result.stdout.strip().split())

            # Check if dirty
            result = self._run_git(
                ["status", "--porcelain"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
            )
            dirty = bool(result.stdout.strip())

            return {"ahead": ahead, "behind": behind, "dirty": dirty}
        except subprocess.CalledProcessError:
            return {"ahead": 0, "behind": 0, "dirty": False}

    def push_branch(self, branch: str, worktree_path: Path):
        """Push branch to origin"""
        self._run_git(["push", "-u", "origin", branch], cwd=worktree_path)

    def is_branch_dirty(self, worktree_path: Path) -> bool:
        """Check if worktree has uncommitted changes"""
        try:
            result = self._run_git(
                ["status", "--porcelain"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
            )
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False

    def _get_current_branch(self) -> Optional[str]:
        """Get current branch name"""
        try:
            result = self._run_git(["branch", "--show-current"], capture_output=True, text=True)
            return result.stdout.strip() or None
        except subprocess.CalledProcessError:
            return None

    def _find_git_root(self, start_path: Path) -> Optional[Path]:
        """Find the git repository root from any subdirectory"""
        current = start_path.absolute()

        # Check if current directory is a git repository
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent

        # Check root directory
        if (current / ".git").exists():
            return current

        return None

    def get_local_status(self, worktree_path: Path) -> Dict[str, Any]:
        """Get local git status information"""
        try:
            # Check working directory status
            result = self._run_git(
                ["status", "--porcelain"], cwd=worktree_path, capture_output=True, text=True
            )

            lines = result.stdout.strip().split("\n") if result.stdout.strip() else []

            staged = []
            modified = []
            untracked = []

            for line in lines:
                if line.startswith("A ") or line.startswith("M ") or line.startswith("D "):
                    staged.append(line[3:])
                elif line.startswith(" M") or line.startswith(" D"):
                    modified.append(line[3:])
                elif line.startswith("??"):
                    untracked.append(line[3:])
                elif line.startswith("AM") or line.startswith("MM"):
                    staged.append(line[3:])
                    modified.append(line[3:])

            return {
                "staged": staged,
                "modified": modified,
                "untracked": untracked,
                "is_clean": len(lines) == 0,
            }
        except subprocess.CalledProcessError:
            return {"staged": [], "modified": [], "untracked": [], "is_clean": True}

    def get_branch_comparison(
        self, worktree_path: Path, branch: str, base_branch: str = "main"
    ) -> Dict[str, Any]:
        """Compare branch with main and remote"""
        try:
            # Get current branch if not specified
            if not branch:
                result = self._run_git(
                    ["branch", "--show-current"], cwd=worktree_path, capture_output=True, text=True
                )
                branch = result.stdout.strip()

            # Fetch to ensure we have latest info
            try:
                self._run_git(["fetch", "origin"], cwd=worktree_path, capture_output=True)
            except subprocess.CalledProcessError:
                pass  # Fetch may fail, continue anyway

            # Check if remote branch exists
            remote_branch = f"origin/{branch}"
            try:
                self._run_git(
                    ["rev-parse", "--verify", remote_branch], cwd=worktree_path, capture_output=True
                )
                has_remote = True
            except subprocess.CalledProcessError:
                has_remote = False

            # Compare with main branch
            try:
                ahead_main_result = self._run_git(
                    ["rev-list", "--count", f"{base_branch}..{branch}"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                )
                ahead_main = int(ahead_main_result.stdout.strip())
            except (subprocess.CalledProcessError, ValueError):
                ahead_main = 0

            try:
                behind_main_result = self._run_git(
                    ["rev-list", "--count", f"{branch}..{base_branch}"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                )
                behind_main = int(behind_main_result.stdout.strip())
            except (subprocess.CalledProcessError, ValueError):
                behind_main = 0

            # Compare with remote branch if it exists
            ahead_remote = 0
            behind_remote = 0
            if has_remote:
                try:
                    ahead_remote_result = self._run_git(
                        ["rev-list", "--count", f"{remote_branch}..{branch}"],
                        cwd=worktree_path,
                        capture_output=True,
                        text=True,
                    )
                    ahead_remote = int(ahead_remote_result.stdout.strip())
                except (subprocess.CalledProcessError, ValueError):
                    ahead_remote = 0

                try:
                    behind_remote_result = self._run_git(
                        ["rev-list", "--count", f"{branch}..{remote_branch}"],
                        cwd=worktree_path,
                        capture_output=True,
                        text=True,
                    )
                    behind_remote = int(behind_remote_result.stdout.strip())
                except (subprocess.CalledProcessError, ValueError):
                    behind_remote = 0

            return {
                "branch": branch,
                "base_branch": base_branch,
                "has_remote": has_remote,
                "ahead_main": ahead_main,
                "behind_main": behind_main,
                "ahead_remote": ahead_remote,
                "behind_remote": behind_remote,
                "is_synced_with_main": ahead_main == 0 and behind_main == 0,
                "is_synced_with_remote": ahead_remote == 0 and behind_remote == 0,
            }
        except subprocess.CalledProcessError:
            return {
                "branch": branch,
                "base_branch": base_branch,
                "has_remote": False,
                "ahead_main": 0,
                "behind_main": 0,
                "ahead_remote": 0,
                "behind_remote": 0,
                "is_synced_with_main": True,
                "is_synced_with_remote": True,
            }

    def _run_git(
        self, args: List[str], cwd: Optional[Path] = None, **kwargs
    ) -> subprocess.CompletedProcess:
        """Run git command"""
        cmd = ["git", "-C", str(cwd or self.repo_path)] + args
        return subprocess.run(cmd, check=True, **kwargs)


class WorktreeStatus:
    """Comprehensive status information for a worktree"""

    def __init__(self, worktree_path: Path, agent_json: Optional["AgentJson"] = None):
        self.worktree_path = worktree_path
        self.agent_json = agent_json
        self._local_status = None
        self._branch_comparison = None
        self._pr_status = None

    def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get all status information"""
        if not self.agent_json:
            return {"error": "Not a cproj worktree"}

        repo_path = Path(self.agent_json.data["project"]["repo_path"])
        branch = self.agent_json.data["workspace"]["branch"]
        base_branch = self.agent_json.data["workspace"]["base"]

        git = GitWorktree(repo_path)

        # Get local status
        local_status = git.get_local_status(self.worktree_path)

        # Get branch comparison
        branch_comparison = git.get_branch_comparison(self.worktree_path, branch, base_branch)

        # Get PR status if available
        pr_status = None
        pr_url = self.agent_json.data["links"].get("pr")
        if pr_url and GitHubIntegration.is_available():
            pr_status = GitHubIntegration.get_pr_status_from_url(pr_url)

        return {
            "worktree_path": str(self.worktree_path),
            "project_name": self.agent_json.data["project"]["name"],
            "branch": branch,
            "base_branch": base_branch,
            "created_at": self.agent_json.data["workspace"]["created_at"],
            "local_status": local_status,
            "branch_comparison": branch_comparison,
            "pr_status": pr_status,
            "links": self.agent_json.data["links"],
            "overall_status": self._determine_overall_status(
                local_status, branch_comparison, pr_status
            ),
        }

    def _determine_overall_status(
        self, local_status: Dict, branch_comparison: Dict, pr_status: Optional[Dict]
    ) -> str:
        """Determine overall status description"""
        # Check if PR was merged and branch is behind main - needs cleanup or pull
        if pr_status and pr_status.get("state") == "merged":
            if branch_comparison["behind_main"] > 0:
                return "cleanup"  # Merged PR, behind main - likely needs cleanup
            else:
                return "merged"

        if not local_status["is_clean"]:
            return "has_local_changes"
        elif branch_comparison["ahead_remote"] > 0:
            return "needs_push"
        elif branch_comparison["behind_remote"] > 0:
            return "needs_pull"
        elif branch_comparison["ahead_main"] > 0:
            if pr_status:
                if pr_status.get("state") == "open":
                    return "under_review"
                else:
                    return "ready_for_pr"
            else:
                return "ready_for_pr"
        elif branch_comparison["behind_main"] > 0:
            # Behind main with no local changes and no PR activity
            if branch_comparison["ahead_main"] == 0 and local_status["is_clean"]:
                return "cleanup"  # No work done, behind main - likely needs cleanup
            else:
                return "needs_pull"
        elif branch_comparison["is_synced_with_main"]:
            return "synced"
        else:
            return "unknown"

    def format_status(self, detailed: bool = True) -> str:
        """Format status for human reading"""
        try:
            status = self.get_comprehensive_status()

            if "error" in status:
                return f"❌ {status['error']}"

            lines = []

            # Header
            lines.append(f"📁 {status['worktree_path']}")

            # Branch info
            branch_comp = status["branch_comparison"]
            branch_line = f"🌿 {status['branch']} → {status['base_branch']}"

            if branch_comp["ahead_main"] > 0 or branch_comp["behind_main"] > 0:
                branch_line += (
                    f" (ahead {branch_comp['ahead_main']}, " f"behind {branch_comp['behind_main']})"
                )

            lines.append(branch_line)

            # Local status
            local = status["local_status"]
            if not local["is_clean"]:
                local_parts = []
                if local["modified"]:
                    local_parts.append(f"{len(local['modified'])} modified")
                if local["staged"]:
                    local_parts.append(f"{len(local['staged'])} staged")
                if local["untracked"]:
                    local_parts.append(f"{len(local['untracked'])} untracked")
                lines.append(f"📝 Local: {', '.join(local_parts)}")

            # Remote status
            if branch_comp["has_remote"]:
                if branch_comp["ahead_remote"] > 0:
                    lines.append(f"🔄 Remote: ↑ {branch_comp['ahead_remote']} commits to push")
                elif branch_comp["behind_remote"] > 0:
                    lines.append(f"🔄 Remote: ↓ {branch_comp['behind_remote']} commits to pull")

            # PR status
            pr_status = status["pr_status"]
            if pr_status:
                state = pr_status.get("state", "unknown")
                pr_line = f"📋 PR: {pr_status.get('title', 'Unknown')} ({state}"

                if state == "open":
                    reviews = pr_status.get("reviews", {})
                    if reviews:
                        approved = reviews.get("approved", 0)
                        total = reviews.get("total", 0)
                        pr_line += f", {approved}/{total} approvals"

                    ci_status = pr_status.get("ci_status")
                    if ci_status:
                        pr_line += f", {ci_status}"

                pr_line += ")"
                lines.append(pr_line)

            # Overall status
            overall = status["overall_status"]
            status_icons = {
                "synced": "✅ Status: In sync with main",
                "has_local_changes": "📝 Status: Has local changes",
                "needs_push": "⬆️ Status: Ready to push",
                "needs_pull": "⬇️ Status: Needs pull",
                "ready_for_pr": "🚀 Status: Ready for PR",
                "under_review": "👀 Status: Under review",
                "merged": "✅ Status: Merged",
                "cleanup": "🧹 Status: Ready for cleanup",
                "unknown": "❓ Status: Unknown",
            }
            lines.append(status_icons.get(overall, f"Status: {overall}"))

            if detailed and status["links"]["linear"]:
                lines.append(f"🔗 Linear: {status['links']['linear']}")

            return "\n".join(lines)

        except Exception as e:
            return f"❌ Error getting status: {e}"

    def format_terse(self) -> str:
        """Format status in a terse, action-focused format for --all view"""
        try:
            status = self.get_comprehensive_status()

            if "error" in status:
                return f"ERROR {status['worktree_path']}: {status['error']}"

            # Build a concise, action-oriented line
            path_name = Path(status["worktree_path"]).name
            branch = status["branch"]
            overall = status["overall_status"]

            # Action-focused status messages
            action_map = {
                "has_local_changes": "COMMIT",
                "needs_push": "PUSH",
                "needs_pull": "PULL",
                "ready_for_pr": "CREATE PR",
                "under_review": "REVIEW",
                "merged": "MERGED",
                "synced": "SYNCED",
                "cleanup": "CLEANUP",
                "unknown": "CHECK",
            }

            action = action_map.get(overall, overall.upper())

            # Build compact info
            parts = [f"{action} {path_name} [{branch}]"]

            # Add specific action details
            local = status["local_status"]
            branch_comp = status["branch_comparison"]

            if overall == "has_local_changes":
                changes = []
                if local["staged"]:
                    changes.append(f"{len(local['staged'])}staged")
                if local["modified"]:
                    changes.append(f"{len(local['modified'])}mod")
                if local["untracked"]:
                    changes.append(f"{len(local['untracked'])}new")
                if changes:
                    parts.append(f"({', '.join(changes)})")
            elif overall == "needs_push":
                parts.append(f"({branch_comp['ahead_remote']} commits)")
            elif overall == "needs_pull":
                parts.append(f"({branch_comp['behind_remote']} commits)")
            elif overall == "ready_for_pr":
                if branch_comp["ahead_main"] > 0:
                    parts.append(f"({branch_comp['ahead_main']} commits ahead)")

            return " ".join(parts)

        except Exception as e:
            return f"ERROR {self.worktree_path}: {e}"


class AgentJson:
    """Manage .agent.json metadata"""

    SCHEMA_VERSION = "1.0"

    def __init__(self, worktree_path: Path):
        # Create .cproj directory if it doesn't exist
        cproj_dir = worktree_path / ".cproj"
        cproj_dir.mkdir(exist_ok=True)

        self.path = cproj_dir / ".agent.json"
        self.data = self._load() if self.path.exists() else self._default_data()

    def _default_data(self) -> Dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "agent": {"name": os.environ.get("USER", "unknown"), "email": ""},
            "project": {"name": "", "repo_path": ""},
            "workspace": {
                "path": "",
                "branch": "",
                "base": "",
                "created_at": "",
                "created_by": f"cproj-{self._get_version()}",
            },
            "links": {"linear": "", "pr": ""},
            "env": {
                "python": {
                    "manager": "none",
                    "active": False,
                    "pyproject": False,
                    "requirements": False,
                },
                "node": {"manager": "none", "node_version": ""},
                "java": {"build": "none"},
            },
            "notes": "",
        }

    def _load(self) -> Dict:
        try:
            with self.path.open() as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            # Return default data if JSON is corrupted
            return self._default_data()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w") as f:
            json.dump(self.data, f, indent=2)

    def set_project(self, name: str, repo_path: str):
        self.data["project"]["name"] = name
        self.data["project"]["repo_path"] = repo_path

    def set_workspace(self, path: str, branch: str, base: str):
        self.data["workspace"]["path"] = path
        self.data["workspace"]["branch"] = branch
        self.data["workspace"]["base"] = base
        self.data["workspace"]["created_at"] = datetime.now(timezone.utc).isoformat()

    def set_link(self, link_type: str, url: str):
        if link_type in self.data["links"]:
            self.data["links"][link_type] = url

    def set_env(self, env_type: str, env_data: Dict):
        if env_type in self.data["env"]:
            self.data["env"][env_type].update(env_data)

    def close_workspace(self):
        self.data["workspace"]["closed_at"] = datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _get_version() -> str:
        return "1.0.0"


class EnvironmentSetup:
    """Environment setup for different languages"""

    def __init__(self, worktree_path: Path):
        self.worktree_path = worktree_path

    def write_ports_env(self, offset: int, base_port: int):
        """Write ports.env file with port offset configuration"""
        cproj_dir = self.worktree_path / ".cproj"
        cproj_dir.mkdir(exist_ok=True)

        ports_env_path = cproj_dir / "ports.env"
        content = f"""# Port offset configuration for this worktree
# Auto-generated by cproj - do not edit manually
export CPROJ_PORT_OFFSET={offset}
export CPROJ_BASE_PORT={base_port}
"""
        ports_env_path.write_text(content)
        print(f"📡 Port offset {offset} allocated (base port: {base_port})")

    def setup_python(
        self,
        auto_install: bool = False,
        shared_venv: bool = False,
        repo_path: Optional[Path] = None,
        project_config: Optional["ProjectConfig"] = None,
    ) -> Dict:
        """Setup Python environment with uv or venv"""
        env_data = {
            "manager": "none",
            "active": False,
            "pyproject": False,
            "requirements": False,
        }

        # Check for project files in root and common subdirectories
        pyproject_paths = list(self.worktree_path.glob("**/pyproject.toml"))
        requirements_paths = list(self.worktree_path.glob("**/requirements.txt"))

        # Filter out common non-project directories
        exclude_dirs = {
            ".venv",
            "venv",
            "node_modules",
            ".git",
            "__pycache__",
            "dist",
            "build",
        }
        pyproject_paths = [
            p for p in pyproject_paths if not any(ex in p.parts for ex in exclude_dirs)
        ]
        requirements_paths = [
            p for p in requirements_paths if not any(ex in p.parts for ex in exclude_dirs)
        ]

        pyproject_exists = len(pyproject_paths) > 0
        requirements_exists = len(requirements_paths) > 0

        env_data["pyproject"] = pyproject_exists
        env_data["requirements"] = requirements_exists

        if not (pyproject_exists or requirements_exists):
            return env_data

        # Handle shared venv option
        if shared_venv and repo_path:
            # Search for .venv in repo root and common subdirectories
            venv_search_paths = [
                repo_path / ".venv",
                repo_path / "bankrec" / ".venv",  # Common pattern in your repos
                *list(repo_path.glob("*/.venv")),  # Any direct subdirectory
            ]

            main_venv = None
            for venv_path in venv_search_paths:
                if venv_path.exists() and venv_path.is_dir():
                    main_venv = venv_path
                    break

            if main_venv:
                # Determine where to create the symlink in worktree
                # If venv is in a subdirectory, preserve that structure
                if main_venv.parent != repo_path:
                    subdir = main_venv.parent.name
                    worktree_venv = self.worktree_path / subdir / ".venv"
                    worktree_venv.parent.mkdir(parents=True, exist_ok=True)
                else:
                    worktree_venv = self.worktree_path / ".venv"

                try:
                    # Create symlink to main repo's venv
                    if worktree_venv.exists():
                        if worktree_venv.is_symlink():
                            worktree_venv.unlink()
                        else:
                            shutil.rmtree(worktree_venv)
                    worktree_venv.symlink_to(main_venv, target_is_directory=True)
                    env_data["manager"] = "shared"
                    env_data["active"] = True
                    print(f"Created shared venv link: {worktree_venv} -> " f"{main_venv}")
                    return env_data
                except (OSError, subprocess.CalledProcessError) as e:
                    print(f"Warning: Failed to create shared venv: {e}")
            else:
                print("No .venv found in main repo to share")

        # Check for Poetry first (unless disabled in project config)
        poetry_enabled = (
            project_config.is_feature_enabled("poetry_auto_setup")
            if project_config
            else True  # Default to enabled if no config
        )

        if poetry_enabled:
            poetry_lock_paths = list(self.worktree_path.glob("**/poetry.lock"))
            poetry_lock_paths = [
                p for p in poetry_lock_paths if not any(ex in p.parts for ex in exclude_dirs)
            ]
            uses_poetry = len(poetry_lock_paths) > 0
        else:
            uses_poetry = False

        if uses_poetry and shutil.which("poetry"):
            # Configure Poetry to use in-project virtualenvs
            # This prevents shared virtualenv conflicts across worktrees
            env = os.environ.copy()
            env["POETRY_VIRTUALENVS_IN_PROJECT"] = "true"

            env_data["manager"] = "poetry"
            env_data["active"] = True
            success_count = 0

            # Process each poetry.lock location separately
            for poetry_lock in poetry_lock_paths:
                poetry_dir = poetry_lock.parent
                try:
                    # Set local config for this specific Poetry project
                    subprocess.run(
                        ["poetry", "config", "virtualenvs.in-project", "true", "--local"],
                        cwd=poetry_dir,
                        check=True,
                        capture_output=True,
                        env=env,
                    )

                    if auto_install:
                        # Install dependencies with in-project virtualenv
                        subprocess.run(
                            ["poetry", "install"],
                            cwd=poetry_dir,
                            check=True,
                            capture_output=True,
                            env=env,
                        )
                        success_count += 1
                        rel_path = poetry_dir.relative_to(self.worktree_path)
                        print(f"✅ Poetry dependencies installed in {rel_path}/.venv")

                except subprocess.CalledProcessError as e:
                    rel_path = poetry_dir.relative_to(self.worktree_path)
                    print(f"⚠️  Warning: Poetry setup failed for {rel_path}: {e}")

            # Only return poetry manager if at least one succeeded
            if success_count > 0 or not auto_install:
                return env_data
            # Fall through to try other methods if all failed

        # Try uv next
        if shutil.which("uv"):
            try:
                subprocess.run(
                    ["uv", "venv"],
                    cwd=self.worktree_path,
                    check=True,
                    capture_output=True,
                )
                env_data["manager"] = "uv"
                env_data["active"] = True

                if auto_install and (pyproject_exists or requirements_exists):
                    subprocess.run(
                        (
                            ["uv", "pip", "sync"]
                            if pyproject_exists
                            else [
                                "uv",
                                "pip",
                                "install",
                                "-r",
                                "requirements.txt",
                            ]
                        ),
                        cwd=self.worktree_path,
                        check=True,
                        capture_output=True,
                    )

                return env_data
            except subprocess.CalledProcessError:
                pass

        # Fallback to venv
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", ".venv"],
                cwd=self.worktree_path,
                check=True,
                capture_output=True,
            )
            env_data["manager"] = "venv"
            env_data["active"] = True

            if auto_install and requirements_exists:
                pip_cmd = str(self.worktree_path / ".venv" / "bin" / "pip")
                if platform.system() == "Windows":
                    pip_cmd = str(self.worktree_path / ".venv" / "Scripts" / "pip.exe")

                subprocess.run(
                    [pip_cmd, "install", "-r", "requirements.txt"],
                    cwd=self.worktree_path,
                    check=True,
                    capture_output=True,
                )

        except subprocess.CalledProcessError:
            pass

        return env_data

    def setup_node(self, auto_install: bool = False) -> Dict:
        """Setup Node environment with nvm"""
        env_data = {"manager": "none", "node_version": ""}

        package_json = self.worktree_path / "package.json"
        nvmrc = self.worktree_path / ".nvmrc"

        if not package_json.exists():
            return env_data

        # Check if nvm is available
        nvm_path = Path.home() / ".nvm" / "nvm.sh"
        if not nvm_path.exists():
            return env_data

        env_data["manager"] = "nvm"

        try:
            # Use node version from .nvmrc or LTS
            if nvmrc.exists():
                with nvmrc.open() as f:
                    node_version = f.read().strip()
            else:
                node_version = "lts/*"

            # This would require shell integration in a real implementation
            # For now, just record what we would do
            env_data["node_version"] = node_version

        except Exception:
            pass

        return env_data

    def setup_java(self, auto_build: bool = False) -> Dict:
        """Setup Java environment"""
        env_data = {"build": "none"}

        if (self.worktree_path / "pom.xml").exists():
            env_data["build"] = "maven"
            if auto_build:
                try:
                    subprocess.run(
                        ["mvn", "compile", "-DskipTests"],
                        cwd=self.worktree_path,
                        check=True,
                        capture_output=True,
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

        elif any((self.worktree_path / f).exists() for f in ["build.gradle", "build.gradle.kts"]):
            env_data["build"] = "gradle"
            if auto_build:
                try:
                    subprocess.run(
                        ["./gradlew", "compileJava"],
                        cwd=self.worktree_path,
                        check=True,
                        capture_output=True,
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

        return env_data

    def copy_env_files(self, repo_path: Path):
        """Copy .env files from main repo to worktree, searching
        subdirectories"""

        # Find all .env* files in the repo (including subdirectories)
        env_patterns = ["**/.env", "**/.env.*"]
        found_files: List[Path] = []

        for pattern in env_patterns:
            found_files.extend(repo_path.glob(pattern))

        if not found_files:
            print("No .env files found in main repo")
            return

        # Copy files, preserving directory structure
        for source_file in found_files:
            # Skip hidden directories and common build/cache dirs
            if any(
                part.startswith(".")
                and part
                not in [
                    ".env",
                    ".env.local",
                    ".env.development",
                    ".env.test",
                    ".env.production",
                    ".env.example",
                ]
                for part in source_file.relative_to(repo_path).parts[:-1]
            ):
                continue

            # Calculate relative path from repo root
            rel_path = source_file.relative_to(repo_path)
            dest_file = self.worktree_path / rel_path

            if not dest_file.exists():
                try:
                    # Create parent directories if needed
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, dest_file)
                    print(f"Copied {rel_path} to worktree")
                except OSError as e:
                    print(f"Warning: Failed to copy {rel_path}: {e}")

    def check_env_differences(self, main_repo_path: Path) -> List[Path]:
        """Check for differences in .env files between worktree and main repo"""
        # Find all .env* files in the current worktree
        env_patterns = ["**/.env", "**/.env.*"]
        found_files: List[Path] = []
        different_files: List[Path] = []

        for pattern in env_patterns:
            found_files.extend(self.worktree_path.glob(pattern))

        for source_file in found_files:
            # Skip hidden directories and common build/cache dirs
            if any(
                part.startswith(".")
                and part
                not in [
                    ".env",
                    ".env.local",
                    ".env.development",
                    ".env.test",
                    ".env.production",
                    ".env.example",
                ]
                for part in source_file.relative_to(self.worktree_path).parts[:-1]
            ):
                continue

            # Calculate relative path and destination
            rel_path = source_file.relative_to(self.worktree_path)
            dest_file = main_repo_path / rel_path

            # Check if files differ
            if dest_file.exists():
                try:
                    with open(source_file, "r") as sf, open(dest_file, "r") as df:
                        source_content = sf.read()
                        dest_content = df.read()

                    if source_content != dest_content:
                        different_files.append(rel_path)
                except (IOError, UnicodeDecodeError):
                    continue
            else:
                # New file in worktree
                different_files.append(rel_path)

        return different_files

    def sync_env_files(
        self,
        main_repo_path: Path,
        specific_file: Optional[str] = None,
        dry_run: bool = False,
        backup: bool = False,
    ):
        """Sync .env files from current worktree back to main repo"""
        from datetime import datetime
        import difflib

        # Find all .env* files in the current worktree
        env_patterns = ["**/.env", "**/.env.*"]
        found_files: List[Path] = []

        for pattern in env_patterns:
            found_files.extend(self.worktree_path.glob(pattern))

        if not found_files:
            print("No .env files found in current worktree")
            return

        # Filter to specific file if requested
        if specific_file:
            found_files = [f for f in found_files if f.name == specific_file]
            if not found_files:
                print(f"File {specific_file} not found in worktree")
                return

        synced_count = 0
        for source_file in found_files:
            # Skip hidden directories and common build/cache dirs
            if any(
                part.startswith(".")
                and part
                not in [
                    ".env",
                    ".env.local",
                    ".env.development",
                    ".env.test",
                    ".env.production",
                    ".env.example",
                ]
                for part in source_file.relative_to(self.worktree_path).parts[:-1]
            ):
                continue

            # Calculate relative path and destination
            rel_path = source_file.relative_to(self.worktree_path)
            dest_file = main_repo_path / rel_path

            # Skip if source and destination are identical
            if source_file.samefile(dest_file) if dest_file.exists() else False:
                continue

            # Show diff if files differ
            if dest_file.exists():
                try:
                    with open(source_file, "r") as sf, open(dest_file, "r") as df:
                        source_lines = sf.readlines()
                        dest_lines = df.readlines()

                    diff = list(
                        difflib.unified_diff(
                            dest_lines,
                            source_lines,
                            fromfile=f"main/{rel_path}",
                            tofile=f"worktree/{rel_path}",
                            lineterm="",
                        )
                    )

                    if diff:
                        print(f"\n📝 Changes in {rel_path}:")
                        for line in diff[:20]:  # Limit diff output
                            print(line)
                        if len(diff) > 20:
                            print(f"... ({len(diff) - 20} more lines)")
                    else:
                        print(f"⏭️  No changes in {rel_path}")
                        continue

                except (IOError, UnicodeDecodeError) as e:
                    print(f"Warning: Could not read {rel_path}: {e}")
                    continue
            else:
                print(f"➕ New file: {rel_path}")

            if dry_run:
                print(f"[DRY RUN] Would sync {rel_path}")
                synced_count += 1
                continue

            try:
                # Create backup if requested
                if backup and dest_file.exists():
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_file = dest_file.with_suffix(f"{dest_file.suffix}.backup_{timestamp}")
                    shutil.copy2(dest_file, backup_file)
                    print(f"📁 Backup created: {backup_file.name}")

                # Create parent directories if needed
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, dest_file)
                print(f"✅ Synced {rel_path}")
                synced_count += 1

            except OSError as e:
                print(f"❌ Failed to sync {rel_path}: {e}")

        if not dry_run:
            print(f"\n🎉 Synced {synced_count} file(s) to main repo")
        else:
            print(f"\n[DRY RUN] Would sync {synced_count} file(s)")


class TerminalAutomation:
    """Terminal and editor automation"""

    @staticmethod
    def open_terminal(path: Path, title: str, terminal_app: str = "Terminal"):
        """Open terminal at path with title"""
        if platform.system() != "Darwin":
            print(f"Terminal automation not supported on {platform.system()}")
            return

        # Check if setup-claude.sh exists in .cproj directory and build the
        # command
        setup_script = path / ".cproj" / "setup-claude.sh"
        if setup_script.exists():
            base_command = f"cd '{path}' && source .cproj/setup-claude.sh"
        else:
            base_command = f"cd '{path}'"

        if terminal_app.lower() == "iterm":
            script = f"""
            tell application "iTerm"
                create window with default profile
                tell current session of current window
                    write text "{base_command}"
                    set name to "{title}"
                end tell
            end tell
            """
        else:  # Terminal
            script = f"""
            tell application "Terminal"
                do script "{base_command}"
                set custom title of front window to "{title}"
            end tell
            """

        try:
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to open terminal: {e}")

    @staticmethod
    def open_editor(path: Path, editor: str):
        """Open editor at path"""
        if not editor or not shutil.which(editor):
            return

        try:
            subprocess.run([editor, str(path)], check=False)
        except Exception as e:
            print(f"Failed to open editor: {e}")


class GitHubIntegration:
    """GitHub integration using gh CLI with 1Password support"""

    @staticmethod
    def is_available() -> bool:
        return shutil.which("gh") is not None

    @staticmethod
    def ensure_auth() -> bool:
        """Ensure GitHub authentication, using 1Password if needed"""
        if not GitHubIntegration.is_available():
            return False

        try:
            # Check if already authenticated
            subprocess.run(["gh", "auth", "status"], check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            # Not authenticated, try to auth
            print("GitHub authentication required.")

            # Check if token available in 1Password
            token_ref = input(
                "1Password GitHub token reference (or press Enter to login " "interactively): "
            ).strip()

            if token_ref and OnePasswordIntegration.is_available():
                token = OnePasswordIntegration.get_secret(token_ref)
                if token:
                    try:
                        # Login with token
                        env = os.environ.copy()
                        env["GH_TOKEN"] = token
                        subprocess.run(
                            ["gh", "auth", "login", "--with-token"],
                            input=token,
                            text=True,
                            check=True,
                            capture_output=True,
                            env=env,
                        )
                        return True
                    except subprocess.CalledProcessError:
                        print("Failed to authenticate with 1Password token")

            # Interactive login
            try:
                subprocess.run(["gh", "auth", "login"], check=True)
                return True
            except subprocess.CalledProcessError:
                print("GitHub authentication failed")
                return False

    @staticmethod
    def create_pr(
        title: str,
        body: str,
        draft: bool = True,
        assignees: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Create a pull request"""
        if not GitHubIntegration.ensure_auth():
            return None

        cmd = ["gh", "pr", "create", "--title", title, "--body", body]

        if draft:
            cmd.append("--draft")

        if assignees:
            cmd.extend(["--assignee", ",".join(assignees)])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    @staticmethod
    def merge_pr(squash: bool = True, delete_branch: bool = False) -> bool:
        """Merge current PR"""
        if not GitHubIntegration.ensure_auth():
            return False

        cmd = ["gh", "pr", "merge"]

        if squash:
            cmd.append("--squash")

        if delete_branch:
            cmd.append("--delete-branch")

        try:
            subprocess.run(cmd, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def get_pr_status_from_url(pr_url: str) -> Optional[Dict[str, Any]]:
        """Get PR status information from GitHub URL"""
        if not GitHubIntegration.is_available():
            return None

        try:
            # Extract owner/repo/number from URL
            import re

            match = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
            if not match:
                return None

            owner, repo, pr_number = match.groups()

            # Get PR info using gh CLI
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    pr_number,
                    "--repo",
                    f"{owner}/{repo}",
                    "--json",
                    "state,title,author,reviewDecision,statusCheckRollup,reviews,mergedAt,mergedBy",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            pr_data = json.loads(result.stdout)

            # Process review information
            reviews_info = {"approved": 0, "total": 0}
            if "reviews" in pr_data and pr_data["reviews"]:
                reviews_info["total"] = len(pr_data["reviews"])
                for review in pr_data["reviews"]:
                    if review.get("state") == "APPROVED":
                        reviews_info["approved"] += 1

            # Determine CI status
            ci_status = None
            status_checks = pr_data.get("statusCheckRollup", [])
            if status_checks:
                # Analyze status checks - look for any failures
                failed_checks = []
                pending_checks = []
                success_checks = []

                for check in status_checks:
                    conclusion = check.get("conclusion")
                    status = check.get("status")
                    state = check.get("state")  # For StatusContext objects

                    if conclusion == "FAILURE" or state == "FAILURE":
                        failed_checks.append(check.get("name", "Unknown"))
                    elif conclusion == "PENDING" or status == "IN_PROGRESS" or state == "PENDING":
                        pending_checks.append(check.get("name", "Unknown"))
                    elif conclusion == "SUCCESS" or state == "SUCCESS":
                        success_checks.append(check.get("name", "Unknown"))

                if failed_checks:
                    ci_status = f"❌ CI failing ({len(failed_checks)} checks)"
                elif pending_checks:
                    ci_status = f"🟡 CI pending ({len(pending_checks)} checks)"
                elif success_checks:
                    ci_status = f"✅ CI passing ({len(success_checks)} checks)"

            return {
                "state": pr_data.get("state", "unknown").lower(),
                "title": pr_data.get("title", "Unknown"),
                "author": pr_data.get("author", {}).get("login", "Unknown"),
                "review_decision": pr_data.get("reviewDecision"),
                "reviews": reviews_info,
                "ci_status": ci_status,
                "merged_at": pr_data.get("mergedAt"),
                "merged_by": (
                    pr_data.get("mergedBy", {}).get("login") if pr_data.get("mergedBy") else None
                ),
                "url": pr_url,
            }

        except (subprocess.CalledProcessError, json.JSONDecodeError, Exception):
            return None


class CprojCLI:
    """Main CLI application"""

    def __init__(self):
        self.config = Config()

    def _prompt_for_config(self) -> Dict:
        """Interactive configuration prompting"""
        print("🚀 Welcome to cproj! Let's set up your configuration.")
        print()

        config = {}

        # Project identity
        print("📁 Project Identity")
        print("-" * 50)

        project_name = input("Project name (display name): ").strip()
        config["project_name"] = project_name or "My Project"

        # Repository
        repo_input = input("Repository path or URL (. for current directory): ").strip()
        if repo_input == "." or not repo_input:
            repo_path = Path.cwd()
            # If we're in a subdirectory of a git repo, find the root
            git_root = self._find_git_root(repo_path)
            if git_root:
                repo_path = git_root
                print(f"Found git repository root at: {repo_path}")
        elif repo_input.startswith("http"):
            # It's a URL, we'll clone it
            clone_to = input(f"Clone to directory [{Path.home() / 'dev' / project_name}]: ").strip()
            repo_path = Path(clone_to) if clone_to else (Path.home() / "dev" / project_name)
            config["clone_url"] = repo_input
        else:
            repo_path = Path(repo_input).expanduser().absolute()
            # If the path exists and is inside a git repo, find the root
            if repo_path.exists():
                git_root = self._find_git_root(repo_path)
                if git_root:
                    repo_path = git_root
                    print(f"Found git repository root at: {repo_path}")

        config["repo_path"] = str(repo_path)

        base_branch = input("Default base branch [main]: ").strip()
        config["base_branch"] = base_branch or "main"

        print()

        # Workspace policy
        print("🏗️  Workspace Policy")
        print("-" * 50)

        default_temp = str(Path.home() / ".cache" / "cproj-workspaces")
        temp_root = input(f"Temp root for worktrees [{default_temp}]: ").strip()
        config["temp_root"] = temp_root or default_temp

        branch_scheme = input("Branch naming scheme [feature/{ticket}-{slug}]: ").strip()
        config["branch_scheme"] = branch_scheme or "feature/{ticket}-{slug}"

        cleanup_days = input("Auto-cleanup age threshold (days) [14]: ").strip()
        try:
            config["cleanup_days"] = str(int(cleanup_days) if cleanup_days else 14)
        except ValueError:
            config["cleanup_days"] = "14"

        print()

        # Environment setup
        print("🐍 Environment Setup")
        print("-" * 50)

        use_uv = input("Prefer uv for Python? [Y/n]: ").strip().lower()
        config["python_prefer_uv"] = str(use_uv not in ["n", "no"])

        auto_install_python = input("Auto-install Python dependencies? [Y/n]: ").strip().lower()
        config["python_auto_install"] = str(auto_install_python not in ["n", "no"])

        use_nvm = input("Use nvm for Node? [Y/n]: ").strip().lower()
        config["node_use_nvm"] = str(use_nvm not in ["n", "no"])

        auto_install_node = input("Auto-install Node dependencies? [Y/n]: ").strip().lower()
        config["node_auto_install"] = str(auto_install_node not in ["n", "no"])

        auto_build_java = input("Auto-build Java projects? [y/N]: ").strip().lower()
        config["java_auto_build"] = str(auto_build_java in ["y", "yes"])

        print()

        # Tools
        print("🛠️  Tools & Automation")
        print("-" * 50)

        if platform.system() == "Darwin":
            terminal = input("Terminal app [Terminal/iTerm/none]: ").strip()
            if terminal.lower() in ["iterm", "iterm2"]:
                config["terminal"] = "iTerm"
            elif terminal.lower() == "none":
                config["terminal"] = "none"
            else:
                config["terminal"] = "Terminal"
        else:
            config["terminal"] = "none"

        editor = input("Editor command [code]: ").strip()
        config["editor"] = editor or "code"

        print()

        # Integrations
        print("🔗 Integrations")
        print("-" * 50)

        # Linear Integration (for MCP)
        print("Configure Linear integration for ticket creation:")
        linear_org = input("Linear organization URL (optional): ").strip()
        if linear_org:
            config["linear_org"] = linear_org

            # Get Linear team and project info
            linear_team = input("Default Linear team ID/key (optional): ").strip()
            if linear_team:
                config["linear_default_team"] = linear_team

            linear_project = input("Default Linear project ID (optional): ").strip()
            if linear_project:
                config["linear_default_project"] = linear_project

        github_default_reviewers = input(
            "Default GitHub reviewers (comma-separated, optional): "
        ).strip()
        if github_default_reviewers:
            config["github_reviewers"] = ",".join(
                [r.strip() for r in github_default_reviewers.split(",")]
            )

        draft_prs = input("Create draft PRs by default? [y/N]: ").strip().lower()
        config["github_draft_default"] = str(draft_prs in ["y", "yes"])

        print()

        # Claude IDE integration
        print("🤖 Claude IDE Integration")
        print("-" * 50)

        claude_symlink = (
            input("Auto-create CLAUDE.md/.cursorrules symlinks in worktrees? " "[Y/n]: ")
            .strip()
            .lower()
        )
        config["claude_symlink_default"] = "no" if claude_symlink in ["n", "no"] else "yes"

        claude_nvm = (
            input("Auto-create nvm setup scripts for Claude CLI in " "worktrees? [Y/n]: ")
            .strip()
            .lower()
        )
        config["claude_nvm_default"] = "no" if claude_nvm in ["n", "no"] else "yes"

        claude_workspace = (
            input("Auto-setup Claude workspace with commands and agents in " "worktrees? [Y/n]: ")
            .strip()
            .lower()
        )
        config["claude_workspace_default"] = "no" if claude_workspace in ["n", "no"] else "yes"

        print()

        # 1Password integration
        if OnePasswordIntegration.is_available():
            print("🔐 1Password Integration")
            print("-" * 50)
            print(
                "1Password CLI detected! You can store GitHub tokens and " "other secrets securely."
            )

            use_1password = input("Use 1Password for secrets? [Y/n]: ").strip().lower()
            config["use_1password"] = str(use_1password not in ["n", "no"])

            if config.get("use_1password"):
                vault = input("Default 1Password vault [Private]: ").strip()
                config["onepassword_vault"] = vault or "Private"

            print()

        # Summary
        print("✅ Configuration Summary")
        print("-" * 50)
        print(f"Project: {config['project_name']}")
        print(f"Repository: {config['repo_path']}")
        print(f"Base branch: {config['base_branch']}")
        print(f"Temp root: {config['temp_root']}")
        print(f"Terminal: {config.get('terminal', 'none')}")
        print(f"Editor: {config.get('editor', 'none')}")

        if config.get("linear_org"):
            print(f"Linear: {config['linear_org']}")
        if config.get("github_reviewers"):
            print(f"GitHub reviewers: {', '.join(config['github_reviewers'])}")
        if config.get("use_1password"):
            print(f"1Password: enabled (vault: " f"{config.get('onepassword_vault')})")

        print()

        confirm = input("Save this configuration? [Y/n]: ").strip().lower()
        if confirm in ["n", "no"]:
            print("Configuration cancelled.")
            sys.exit(1)

        return config

    def create_parser(self) -> argparse.ArgumentParser:
        """Create argument parser"""
        parser = argparse.ArgumentParser(description="Multi-project CLI with git worktree + uv")
        parser.add_argument("--repo", help="Repository path")
        parser.add_argument("--base", help="Base branch")
        parser.add_argument("--temp-root", help="Temp root for worktrees")
        parser.add_argument(
            "--terminal",
            choices=["Terminal", "iTerm", "none"],
            help="Terminal app",
        )
        parser.add_argument("--editor", help="Editor command")
        parser.add_argument("--yes", action="store_true", help="Skip confirmations")
        parser.add_argument("--verbose", action="store_true", help="Verbose output")
        parser.add_argument("--json", action="store_true", help="JSON output")
        parser.add_argument(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            default="INFO",
            help="Set logging level (default: INFO)",
        )

        subparsers = parser.add_subparsers(dest="command", help="Commands")

        # init command
        init_parser = subparsers.add_parser(
            "init", aliases=["new", "start"], help="Initialize project"
        )
        init_parser.add_argument("--name", help="Project name")
        init_parser.add_argument("--clone", help="Clone URL if repo not local")

        # init-project command
        init_project_parser = subparsers.add_parser(
            "init-project", help="Initialize project configuration"
        )
        init_project_parser.add_argument("--name", help="Project name")
        init_project_parser.add_argument(
            "--type", help="Project type", choices=["tool", "web-app", "library", "generic"]
        )
        init_project_parser.add_argument(
            "--template",
            help="Configuration template",
            choices=["cproj", "web-app", "trivalley", "minimal"],
        )

        # worktree create command
        wt_create = subparsers.add_parser("worktree", aliases=["w"], help="Worktree commands")
        wt_sub = wt_create.add_subparsers(dest="worktree_command")

        create_parser = wt_sub.add_parser("create", help="Create worktree")
        create_parser.add_argument("--branch", help="Branch name")
        create_parser.add_argument("--linear", help="Linear issue URL")
        create_parser.add_argument(
            "--python-install",
            action="store_true",
            help="Auto-install Python deps",
        )
        create_parser.add_argument(
            "--shared-venv",
            action="store_true",
            help="Link to main repo venv instead of creating new one",
        )
        create_parser.add_argument(
            "--copy-env",
            action="store_true",
            help="Copy .env files from main repo",
        )
        create_parser.add_argument(
            "--node-install",
            action="store_true",
            help="Auto-install Node deps",
        )
        create_parser.add_argument("--java-build", action="store_true", help="Auto-build Java")
        create_parser.add_argument(
            "--open-editor",
            action="store_true",
            help="Open editor after creating worktree",
        )
        create_parser.add_argument(
            "--no-terminal",
            action="store_true",
            help="Do not open terminal after creating worktree",
        )
        create_parser.add_argument(
            "--setup-claude",
            action="store_true",
            help="Force setup Claude workspace",
        )
        create_parser.add_argument(
            "--no-claude",
            action="store_true",
            help="Skip Claude workspace setup",
        )

        # review command
        review_parser = subparsers.add_parser("review", help="Review commands")
        review_sub = review_parser.add_subparsers(dest="review_command")

        open_parser = review_sub.add_parser("open", help="Open review")
        open_parser.add_argument(
            "--draft",
            action="store_true",
            help="Create draft PR (default is ready for review)",
        )
        open_parser.add_argument(
            "--ready",
            action="store_true",
            help="[Deprecated] Create ready PR (now default)",
        )
        open_parser.add_argument("--assign", help="Assignees (comma-separated)")
        open_parser.add_argument("--no-push", action="store_true", help="Don't push branch")
        open_parser.add_argument(
            "--no-agents",
            action="store_true",
            help="Skip automated review agents",
        )
        open_parser.add_argument(
            "--skip-env-sync",
            action="store_true",
            help="Skip .env file sync prompt",
        )

        agents_parser = review_sub.add_parser("agents", help="Run automated review agents")
        agents_parser.add_argument(
            "--setup",
            action="store_true",
            help="Setup review configuration only",
        )
        agents_parser.add_argument("--json", action="store_true", help="Output as JSON")

        # merge command
        merge_parser = subparsers.add_parser("merge", help="Merge and cleanup")
        merge_parser.add_argument(
            "--squash", action="store_true", default=True, help="Squash merge"
        )
        merge_parser.add_argument(
            "--merge", dest="squash", action="store_false", help="Merge commit"
        )
        merge_parser.add_argument(
            "--delete-remote", action="store_true", help="Delete remote branch"
        )
        merge_parser.add_argument("--keep-worktree", action="store_true", help="Keep worktree")
        merge_parser.add_argument("--force", action="store_true", help="Force merge even if dirty")

        # list command
        subparsers.add_parser("list", aliases=["ls"], help="List worktrees")

        # status command
        status_parser = subparsers.add_parser("status", aliases=["st"], help="Show status")
        status_parser.add_argument("path", nargs="?", help="Worktree path")
        status_parser.add_argument(
            "--all", action="store_true", help="Show status of all worktrees"
        )
        status_parser.add_argument(
            "--detailed", action="store_true", help="Show detailed status information"
        )

        # cleanup command
        cleanup_parser = subparsers.add_parser("cleanup", help="Cleanup worktrees")
        cleanup_parser.add_argument("--older-than", type=int, help="Days old")
        cleanup_parser.add_argument(
            "--merged-only", action="store_true", help="Only merged branches"
        )
        cleanup_parser.add_argument(
            "--dry-run", action="store_true", help="Show what would be done"
        )
        cleanup_parser.add_argument(
            "--force",
            action="store_true",
            help="Force removal of dirty worktrees",
        )

        # open command
        open_parser = subparsers.add_parser("open", help="Open workspace")
        open_parser.add_argument("path", nargs="?", help="Worktree path")

        # setup-claude command
        setup_claude_parser = subparsers.add_parser(
            "setup-claude", help="Setup Claude workspace in current directory"
        )
        setup_claude_parser.add_argument(
            "--force",
            action="store_true",
            help="Force setup even if .claude directory exists",
        )

        # sync-env command
        sync_env_parser = subparsers.add_parser(
            "sync-env", help="Sync .env files from worktree to main repo"
        )
        sync_env_parser.add_argument(
            "--file",
            help="Specific .env file to sync (e.g., .env.local)",
        )
        sync_env_parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without copying files",
        )
        sync_env_parser.add_argument(
            "--backup",
            action="store_true",
            help="Create backup of existing files before overwriting",
        )

        # config command
        config_parser = subparsers.add_parser("config", help="Configuration")
        config_parser.add_argument("key", nargs="?", help="Config key")
        config_parser.add_argument("value", nargs="?", help="Config value")

        # ports command
        ports_parser = subparsers.add_parser("ports", help="Port allocation management")
        ports_sub = ports_parser.add_subparsers(dest="ports_command")

        # ports list
        list_ports_parser = ports_sub.add_parser("list", help="List port allocations")
        list_ports_parser.add_argument(
            "--project",
            help="Filter by project name (default: current project)",
        )

        # ports allocate
        allocate_parser = ports_sub.add_parser(
            "allocate", help="Allocate port offset for a worktree"
        )
        allocate_parser.add_argument(
            "--path",
            type=Path,
            help="Worktree path (default: current directory)",
        )
        allocate_parser.add_argument(
            "--offset",
            type=int,
            help="Specific offset to allocate (default: next available)",
        )

        # ports free
        free_parser = ports_sub.add_parser("free", help="Free a port offset")
        free_parser.add_argument(
            "offset",
            type=int,
            help="Port offset to free",
        )
        free_parser.add_argument(
            "--project",
            help="Project name (default: current project)",
        )

        return parser

    def run(self, args: Optional[List[str]] = None):
        """Main entry point"""
        parser = self.create_parser()
        parsed_args = parser.parse_args(args)

        # Set logging level based on command-line argument
        log_level = getattr(logging, parsed_args.log_level)
        logger.setLevel(log_level)

        # Also enable debug if --verbose is used
        if parsed_args.verbose:
            logger.setLevel(logging.DEBUG)

        try:
            if parsed_args.command == "init" or parsed_args.command in [
                "new",
                "start",
            ]:
                self.cmd_init(parsed_args)
            elif parsed_args.command == "init-project":
                self.cmd_init_project(parsed_args)
            elif parsed_args.command == "worktree" or parsed_args.command == "w":
                if parsed_args.worktree_command == "create":
                    self.cmd_worktree_create(parsed_args)
                else:
                    # Show worktree help when no subcommand given
                    parser.parse_args(["worktree", "--help"])
            elif parsed_args.command == "review":
                if parsed_args.review_command == "open":
                    self.cmd_review_open(parsed_args)
                elif parsed_args.review_command == "agents":
                    self.cmd_review_agents(parsed_args)
                else:
                    # Show review help when no subcommand given
                    parser.parse_args(["review", "--help"])
            elif parsed_args.command == "merge":
                self.cmd_merge(parsed_args)
            elif parsed_args.command in ["list", "ls"]:
                self.cmd_list(parsed_args)
            elif parsed_args.command in ["status", "st"]:
                self.cmd_status(parsed_args)
            elif parsed_args.command == "cleanup":
                self.cmd_cleanup(parsed_args)
            elif parsed_args.command == "open":
                self.cmd_open(parsed_args)
            elif parsed_args.command == "setup-claude":
                self.cmd_setup_claude(parsed_args)
            elif parsed_args.command == "sync-env":
                self.cmd_sync_env(parsed_args)
            elif parsed_args.command == "config":
                self.cmd_config(parsed_args)
            elif parsed_args.command == "ports":
                if parsed_args.ports_command == "list":
                    self.cmd_ports_list(parsed_args)
                elif parsed_args.ports_command == "allocate":
                    self.cmd_ports_allocate(parsed_args)
                elif parsed_args.ports_command == "free":
                    self.cmd_ports_free(parsed_args)
                else:
                    # Show ports help when no subcommand given
                    parser.parse_args(["ports", "--help"])
            else:
                parser.print_help()

        except CprojError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except KeyboardInterrupt:
            print("\nAborted by user", file=sys.stderr)
            sys.exit(1)

    def _find_git_root(self, start_path: Path) -> Optional[Path]:
        """Find the git repository root from any subdirectory"""
        current = start_path.absolute()

        # Check if current directory is a git repository
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent

        # Check root directory
        if (current / ".git").exists():
            return current

        return None

    def cmd_init(self, args):
        """Initialize system-level cproj configuration"""
        print("🚀 Welcome to cproj!")
        print()
        print("This will configure system-level settings.")
        print("Projects are now automatically detected from your current " "working directory.")
        print()

        # Check if we already have system config
        if self.config.get("temp_root"):
            print("✅ cproj is already configured!")
            print()
            print("Current system settings:")
            self._show_system_config()
            print()
            proceed = input("Reconfigure system settings? [y/N]: ").strip().lower()
            if proceed not in ["y", "yes"]:
                return

        # Run system configuration
        config_data = self._prompt_for_system_config()

        # Save system configuration
        for key, value in config_data.items():
            self.config.set(key, value)

        print()
        print("✅ System configuration saved!")
        print()
        print("🎉 Ready to go! Now you can use cproj in any git repository:")
        print("  cd /path/to/your/project")
        print("  cproj w create --branch feature/awesome-feature")
        print("  cproj list")
        print("  cproj config")

    def _show_system_config(self):
        """Show current system configuration"""
        print(f"  Temp root: {self.config.get('temp_root', 'Not set')}")
        print(f"  Terminal: {self.config.get('terminal', 'Not set')}")
        print(f"  Editor: {self.config.get('editor', 'Not set')}")
        print(f"  Python prefer uv: {self.config.get('python_prefer_uv', False)}")
        print(f"  Node use nvm: {self.config.get('node_use_nvm', False)}")
        print(f"  Linear org: {self.config.get('linear_org', 'Not set')}")
        print(f"  GitHub reviewers: " f"{', '.join(self.config.get('github_reviewers', []))}")

    def _prompt_for_system_config(self) -> Dict:
        """Prompt for system-level configuration"""
        config = {}

        print("🛠️ System Configuration")
        print("-" * 50)

        # Temp directory for worktrees
        default_temp = str(Path.home() / ".cache" / "cproj-workspaces")
        temp_root = input(f"Temp directory for worktrees [{default_temp}]: ").strip()
        config["temp_root"] = temp_root or default_temp

        # Terminal preference
        default_terminal = "Terminal" if sys.platform == "darwin" else "none"
        terminal = input(f"Terminal app (Terminal, iTerm, none) [{default_terminal}]: ").strip()
        config["terminal"] = terminal or default_terminal

        # Editor preference
        editor = input("Editor command (code, cursor, vim, etc.) [code]: ").strip()
        config["editor"] = editor or "code"

        # Python preferences
        python_uv = input("Prefer uv for Python environments? [Y/n]: ").strip().lower()
        config["python_prefer_uv"] = str(python_uv != "n")

        # Node preferences
        node_nvm = input("Use nvm for Node.js? [Y/n]: ").strip().lower()
        config["node_use_nvm"] = str(node_nvm != "n")

        # Optional integrations
        print()
        print("📱 Optional Integrations")
        print("-" * 50)

        # Linear (for MCP)
        linear_org = input("Linear organization (optional): ").strip()
        if linear_org:
            config["linear_org"] = linear_org

        # GitHub reviewers
        github_reviewers = input("GitHub default reviewers (comma-separated, optional): ").strip()
        if github_reviewers:
            config["github_reviewers"] = ",".join([r.strip() for r in github_reviewers.split(",")])

        return config

    def _is_interactive(self) -> bool:
        """Check if we're running in an interactive terminal"""
        import sys

        return sys.stdin.isatty() and sys.stdout.isatty()

    def _setup_claude_symlink(self, worktree_path: Path, repo_path: Path):
        """Setup CLAUDE.md/.cursorrules symlink in new worktree"""
        # Check if repo has CLAUDE.md
        claude_md = repo_path / "CLAUDE.md"
        if not claude_md.exists():
            return

        # Check if repo has .cursorrules symlinked to CLAUDE.md
        cursorrules = repo_path / ".cursorrules"
        if not cursorrules.is_symlink():
            return

        # Verify the symlink points to CLAUDE.md
        try:
            if cursorrules.resolve() != claude_md.resolve():
                return
        except (OSError, FileNotFoundError):
            return

        # Check if worktree already has .cursorrules
        worktree_cursorrules = worktree_path / ".cursorrules"
        if worktree_cursorrules.exists():
            return

        # Get default action from config
        default_action = self.config.get("claude_symlink_default", "yes")

        # Prompt user if interactive
        if self._is_interactive():
            print("\n🔗 CLAUDE.md Configuration")
            print(f"Found CLAUDE.md symlinked as .cursorrules in " f"{repo_path.name}")

            if default_action == "yes":
                response = input("Create .cursorrules symlink in worktree? [Y/n]: ").strip().lower()
                create_link = response in ("", "y", "yes")
            else:
                response = input("Create .cursorrules symlink in worktree? [y/N]: ").strip().lower()
                create_link = response in ("y", "yes")
        else:
            # Non-interactive: use default
            create_link = default_action == "yes"

        if create_link:
            try:
                # First copy CLAUDE.md to worktree if it doesn't exist
                worktree_claude = worktree_path / "CLAUDE.md"
                if not worktree_claude.exists():
                    import shutil

                    shutil.copy2(claude_md, worktree_claude)
                    print("✅ Copied CLAUDE.md to worktree")

                # Create relative symlink to CLAUDE.md
                worktree_cursorrules.symlink_to("CLAUDE.md")
                print("✅ Created .cursorrules -> CLAUDE.md symlink")
            except OSError as e:
                print(f"⚠️  Failed to create .cursorrules symlink: {e}")

    def _setup_nvm_for_claude(
        self, worktree_path: Path, node_env: Dict, project_config: Optional[ProjectConfig] = None
    ):
        """Setup nvm and create a script to automatically use LTS for Claude
        CLI"""
        # Check if nvm is available on the system (regardless of project setup)
        nvm_path = Path.home() / ".nvm" / "nvm.sh"
        if not nvm_path.exists():
            return

        # Get default action from config
        default_action = self.config.get("claude_nvm_default", "yes")

        # Check if we should set up nvm automation
        setup_nvm = default_action == "yes"

        if self._is_interactive():
            print("\n🚀 Node.js Setup for Claude CLI")
            print("Claude CLI requires Node.js LTS to run properly.")

            if default_action == "yes":
                response = (
                    input("Create nvm setup script for this worktree? [Y/n]: ").strip().lower()
                )
                setup_nvm = response in ("", "y", "yes")
            else:
                response = (
                    input("Create nvm setup script for this worktree? [y/N]: ").strip().lower()
                )
                setup_nvm = response in ("y", "yes")

        if setup_nvm:
            try:
                # Create .cproj directory for cproj-specific files
                cproj_dir = worktree_path / ".cproj"
                cproj_dir.mkdir(exist_ok=True)

                # Create a setup script that sources nvm and uses LTS
                setup_script = cproj_dir / "setup-claude.sh"

                # Build base script
                script_content = """#!/bin/bash
# Auto-generated script to setup Node.js for Claude CLI
# Run: source .cproj/setup-claude.sh

echo "🚀 Setting up Node.js environment for Claude CLI..."

# Source port configuration if it exists
if [ -f ".cproj/ports.env" ]; then
    source .cproj/ports.env
    echo "📡 Port offset loaded: CPROJ_PORT_OFFSET=$CPROJ_PORT_OFFSET"
fi

# Source nvm
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \\. "$NVM_DIR/nvm.sh"

# Use LTS Node
nvm use --lts

echo "✅ Node.js LTS activated. You can now run 'claude' command."
"""

                # Add MCP server setup if configured
                if project_config:
                    mcp_servers = project_config.get_mcp_servers()
                    if mcp_servers:
                        script_content += "\n# Setup MCP servers\n"
                        for server in mcp_servers:
                            name = server.get("name", "unknown")
                            transport = server.get("transport")
                            url = server.get("url")
                            command = server.get("command")

                            script_content += f'echo "🔗 Setting up {name} MCP..."\n'

                            if transport and url:
                                # SSE transport
                                script_content += (
                                    f"claude mcp add --transport {transport} {name} {url}\n"
                                )
                            elif command:
                                # Command-based (like npx)
                                script_content += f"claude mcp add {name} {command}\n"
                            else:
                                script_content += (
                                    f'echo "⚠️  Skipping {name}: '
                                    'missing transport/url or command"\n'
                                )
                                continue

                            script_content += f'echo "✅ {name} MCP configured."\n'

                script_content += (
                    "\necho \"💡 Tip: Run 'source .cproj/setup-claude.sh' "
                    'whenever you open a new terminal in this directory"\n'
                )

                setup_script.write_text(script_content)
                setup_script.chmod(0o755)

                print("✅ Created .cproj/setup-claude.sh script")
                print(
                    "💡 Run 'source .cproj/setup-claude.sh' in your terminal "
                    "to activate Node.js LTS"
                )

            except OSError as e:
                print(f"⚠️  Failed to create nvm setup script: {e}")

    def _setup_claude_workspace(self, worktree_path: Path, repo_path: Path, args=None):
        """Setup Claude workspace configuration with commands and agents"""
        # Get cproj's Claude templates
        cproj_root = Path(__file__).parent
        cproj_claude_dir = cproj_root / ".claude"

        logger.debug(f"Looking for cproj .claude directory at: {cproj_claude_dir}")
        logger.debug(f"cproj .claude directory exists: {cproj_claude_dir.exists()}")

        # Check target project's .claude directory
        project_claude_dir = repo_path / ".claude"
        logger.debug(f"Project .claude directory: {project_claude_dir}")
        logger.debug(f"Project .claude directory exists: {project_claude_dir.exists()}")

        # Need at least cproj templates to proceed
        if not cproj_claude_dir.exists():
            logger.debug("No cproj .claude directory found, skipping setup")
            return

        # Handle explicit command-line flags
        if args and hasattr(args, "no_claude") and args.no_claude:
            logger.debug("--no-claude flag detected, skipping setup")
            return

        # Check if we should set up Claude workspace
        default_action = self.config.get("claude_workspace_default", "yes")
        setup_workspace = default_action == "yes"
        logger.debug(f"Default action: {default_action}, " f"setup_workspace: {setup_workspace}")

        # Override with explicit --setup-claude flag
        if args and hasattr(args, "setup_claude") and args.setup_claude:
            setup_workspace = True

        if self._is_interactive():
            print("\n🤖 Claude Workspace Setup")
            print("Found Claude commands and agents configuration.")

            if default_action == "yes":
                response = input("Setup Claude workspace in worktree? [Y/n]: ").strip().lower()
                setup_workspace = response in ("", "y", "yes")
            else:
                response = input("Setup Claude workspace in worktree? [y/N]: ").strip().lower()
                setup_workspace = response in ("y", "yes")

            logger.debug(
                f"Interactive response: '{response}', " f"final setup_workspace: {setup_workspace}"
            )

        logger.debug(f"Final decision - setup_workspace: {setup_workspace}")

        if setup_workspace:
            print(f"🔧 Setting up Claude workspace in {worktree_path}")
            try:
                import shutil

                # Create .claude directory in worktree
                worktree_claude_dir = worktree_path / ".claude"
                worktree_claude_dir.mkdir(exist_ok=True)
                print(f"Created .claude directory: {worktree_claude_dir}")

                # Start with cproj templates as base,
                # then merge project configs
                for subdir in ["commands", "agents", "skills"]:
                    cproj_source_dir = cproj_claude_dir / subdir
                    target_dir = worktree_claude_dir / subdir

                    # Copy cproj templates first
                    if cproj_source_dir.exists():
                        if target_dir.exists():
                            shutil.rmtree(target_dir)
                        shutil.copytree(cproj_source_dir, target_dir)
                        print(f"  ✅ Copied cproj {subdir} templates")

                    # Merge project-specific configs if they exist
                    if project_claude_dir.exists():
                        project_source_dir = project_claude_dir / subdir
                        if project_source_dir.exists():
                            # Ensure target directory exists
                            target_dir.mkdir(exist_ok=True)
                            # Copy project files, potentially
                            # overwriting templates
                            for item in project_source_dir.iterdir():
                                target_file = target_dir / item.name
                                if item.is_file():
                                    shutil.copy2(item, target_file)
                                    print(f"  ✅ Merged project {item.name}")
                                elif item.is_dir():
                                    if target_file.exists():
                                        shutil.rmtree(target_file)
                                    shutil.copytree(item, target_file)
                                    print(f"  ✅ Merged project {item.name}/")

                # Copy standalone files from both cproj and
                # project .claude directories
                # Start with cproj standalone files
                for item in cproj_claude_dir.iterdir():
                    if item.is_file() and item.name not in [
                        "mcp_config.json"
                    ]:  # mcp_config.json handled separately
                        target_file = worktree_claude_dir / item.name
                        shutil.copy2(item, target_file)
                        # Make shell scripts executable
                        if item.suffix == ".sh":
                            target_file.chmod(target_file.stat().st_mode | 0o111)
                        print(f"  ✅ Copied cproj {item.name}")

                # Copy standalone files from project
                # (will overwrite cproj versions)
                if project_claude_dir.exists():
                    for item in project_claude_dir.iterdir():
                        if item.is_file() and item.name not in [
                            "mcp_config.json"
                        ]:  # mcp_config.json handled separately
                            target_file = worktree_claude_dir / item.name
                            shutil.copy2(item, target_file)
                            # Make shell scripts executable
                            if item.suffix == ".sh":
                                target_file.chmod(target_file.stat().st_mode | 0o111)
                            print(f"  ✅ Merged project {item.name}")

                # Copy MCP config (prefer project over cproj template)
                mcp_source = None
                if project_claude_dir.exists():
                    project_mcp = project_claude_dir / "mcp_config.json"
                    if project_mcp.exists():
                        mcp_source = project_mcp
                        print("  ✅ Using project mcp_config.json")

                if not mcp_source:
                    cproj_mcp = cproj_claude_dir / "mcp_config.json"
                    if cproj_mcp.exists():
                        mcp_source = cproj_mcp
                        print("  ✅ Using cproj mcp_config.json")

                if mcp_source:
                    shutil.copy2(mcp_source, worktree_claude_dir / "mcp_config.json")

                # Create workspace-specific configuration
                workspace_config = {
                    "project_root": str(repo_path),
                    "worktree_path": str(worktree_path),
                    "linear": {
                        "org": self.config.get("linear_org"),
                        "default_team": self.config.get("linear_default_team"),
                        "default_project": self.config.get("linear_default_project"),
                    },
                    "commands": {
                        "add-ticket": {
                            "description": (
                                "Create comprehensive Linear tickets using " "AI agents"
                            ),
                            "agents": [
                                "product-manager",
                                "ux-designer",
                                "senior-software-engineer",
                            ],
                            "requires_mcp": ["linear"],
                        },
                        "review-code": {
                            "description": (
                                "Run comprehensive AI-powered code review "
                                "using specialized review agents"
                            ),
                            "agents": [
                                "senior-developer",
                                "qa-engineer",
                                "security-reviewer",
                            ],
                            "requires_git": True,
                        },
                    },
                    "agents": {
                        "product-manager": ("Turn high-level asks into crisp PRDs"),
                        "ux-designer": ("Create clear, accessible, user-centric designs"),
                        "senior-software-engineer": ("Plan implementation with tests and docs"),
                        "code-reviewer": ("Review code for correctness and maintainability"),
                    },
                }

                config_file = worktree_claude_dir / "workspace.json"
                with config_file.open("w") as f:
                    json.dump(workspace_config, f, indent=2)

                print("✅ Setup Claude workspace configuration")
                print("💡 Available commands: add-ticket, review-code")
                print(
                    "💡 Available agents: product-manager, ux-designer, "
                    "senior-software-engineer, code-reviewer"
                )

            except (OSError, shutil.Error) as e:
                print(f"⚠️  Failed to setup Claude workspace: {e}")

    def _add_to_gitignore(self, repo_path: Path, pattern: str):
        """Add pattern to .gitignore if not already present"""
        gitignore_path = repo_path / ".gitignore"

        # Check if pattern already exists
        if gitignore_path.exists():
            with gitignore_path.open() as f:
                content = f.read()
                if pattern in content:
                    return

        # Add pattern to .gitignore
        with gitignore_path.open("a") as f:
            if gitignore_path.exists() and not content.endswith("\n"):
                f.write("\n")
            f.write("# Linear API key (added by cproj)\n")
            f.write(f"{pattern}\n")

    def _generate_branch_suggestions(self) -> List[str]:
        """Generate reasonable branch name suggestions"""
        from datetime import datetime

        # Get configured branch scheme
        branch_scheme = self.config.get("branch_scheme", "feature/{ticket}-{slug}")

        suggestions = []
        timestamp = datetime.now().strftime("%m%d")

        # Parse the scheme to generate suggestions
        if "{ticket}" in branch_scheme and "{slug}" in branch_scheme:
            suggestions.extend(
                [
                    branch_scheme.replace("{ticket}", "TICKET-123").replace(
                        "{slug}", "description"
                    ),
                    branch_scheme.replace("{ticket}", "ABC-456").replace("{slug}", "feature-name"),
                ]
            )
        elif "{ticket}" in branch_scheme:
            suggestions.extend(
                [
                    branch_scheme.replace("{ticket}", "TICKET-123"),
                    branch_scheme.replace("{ticket}", "ABC-456"),
                ]
            )
        elif "{slug}" in branch_scheme:
            suggestions.extend(
                [
                    branch_scheme.replace("{slug}", "new-feature"),
                    branch_scheme.replace("{slug}", "bug-fix"),
                ]
            )
        # Generic suggestions based on common patterns
        elif branch_scheme.startswith("feature/"):
            suggestions.extend(
                [
                    f"feature/new-feature-{timestamp}",
                    f"feature/improvement-{timestamp}",
                ]
            )
        else:
            suggestions.extend(
                [
                    f"feature/new-feature-{timestamp}",
                    f"fix/bug-fix-{timestamp}",
                    f"dev/experiment-{timestamp}",
                ]
            )

        return suggestions[:3]  # Limit to 3 suggestions

    def _detect_default_branch(self, repo_path: Path) -> Optional[str]:
        """Detect the default branch for a repository"""
        try:
            # Try to get the default branch from origin
            result = subprocess.run(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            # Extract branch name from refs/remotes/origin/branch_name
            return result.stdout.strip().split("/")[-1]
        except subprocess.CalledProcessError:
            # Fall back to common default branches
            for branch in ["main", "master", "develop"]:
                try:
                    subprocess.run(
                        [
                            "git",
                            "show-ref",
                            "--verify",
                            f"refs/heads/{branch}",
                        ],
                        cwd=repo_path,
                        capture_output=True,
                        check=True,
                    )
                    return branch
                except subprocess.CalledProcessError:
                    continue
        return None

    def cmd_init_project(self, args):
        """Initialize project configuration"""
        current_dir = Path.cwd()

        # Check if we're in a git repository
        try:
            repo_path = self._find_git_root(current_dir)
            if not repo_path:
                raise CprojError("Not in a git repository")
        except Exception:
            raise CprojError("Not in a git repository")

        # Load existing project config or create new one
        project_config = ProjectConfig(repo_path)

        print(f"🔧 Initializing project configuration for {repo_path.name}")
        print()

        # Check if config already exists
        if project_config.config_path.exists():
            print("✅ Project configuration already exists!")
            print(f"   Location: {project_config.config_path}")
            print()
            print("Current configuration:")
            print(f"   Name: {project_config.get_project_name()}")
            print(f"   Type: {project_config.get_project_type()}")
            print(f"   Base branch: {project_config.get_base_branch()}")
            print("   Features:")
            for feature in [
                "claude_workspace",
                "claude_symlink",
                "review_agents",
                "nvm_setup",
                "env_sync_check",
            ]:
                enabled = "✅" if project_config.is_feature_enabled(feature) else "❌"
                print(f"     {enabled} {feature}")
            print()

            if not args.template:
                proceed = input("Reconfigure project? [y/N]: ").strip().lower()
                if proceed not in ["y", "yes"]:
                    return

        # Get project info
        project_name = (
            args.name or input(f"Project name [{repo_path.name}]: ").strip() or repo_path.name
        )

        if args.type:
            project_type = args.type
        else:
            print("\nSelect project type:")
            print("1. tool - CLI tool or development utility")
            print("2. web-app - Web application")
            print("3. library - Reusable library/package")
            print("4. generic - Generic project")

            while True:
                choice = input("Project type [1-4]: ").strip()
                if choice == "1" or choice.lower() == "tool":
                    project_type = "tool"
                    break
                elif choice == "2" or choice.lower() == "web-app":
                    project_type = "web-app"
                    break
                elif choice == "3" or choice.lower() == "library":
                    project_type = "library"
                    break
                elif choice == "4" or choice.lower() == "generic":
                    project_type = "generic"
                    break
                else:
                    print("Please enter 1, 2, 3, or 4")

        # Apply template or prompt for features
        if args.template == "cproj":
            self._apply_cproj_template(project_config)
        elif args.template in ["web-app", "trivalley"]:
            # trivalley is an alias for web-app (backward compatibility)
            self._apply_web_app_template(project_config, repo_path)
        elif args.template == "minimal":
            self._apply_minimal_template(project_config)
        else:
            self._prompt_for_features(project_config)

        # Set project info
        project_config.set_project_info(project_name, project_type)

        # Prompt for base branch
        print()
        current_base = project_config.get_base_branch()
        base_branch_input = input(f"Default base branch [{current_base}]: ").strip()
        if base_branch_input:
            project_config.set_base_branch(base_branch_input)

        # Save configuration
        project_config.save()

        print()
        print("✅ Project configuration saved!")
        print(f"   Location: {project_config.config_path}")
        print()
        print("🎉 Project is now configured for cproj!")

    def _apply_cproj_template(self, config: ProjectConfig):
        """Apply cproj project template"""
        config.enable_feature("claude_workspace", True)
        config.enable_feature("claude_symlink", True)
        config.enable_feature("review_agents", True)
        config.enable_feature("nvm_setup", True)
        config.enable_feature("env_sync_check", True)

    def _apply_web_app_template(self, config: ProjectConfig, repo_path: Path):
        """Apply web-app project template (formerly trivalley)"""
        config.enable_feature("claude_workspace", True)
        config.enable_feature("claude_symlink", False)
        config.enable_feature("review_agents", True)
        config.enable_feature("nvm_setup", True)
        config.enable_feature("env_sync_check", True)

        # Auto-detect and add workspace file if it exists
        workspace_files = list(repo_path.glob("*.code-workspace"))
        if workspace_files:
            source_file = workspace_files[0].name
            # Extract project name from workspace file (remove .code-workspace)
            project_name_from_file = source_file.replace(".code-workspace", "")

            config.add_custom_action(
                {
                    "type": "copy_workspace_file",
                    "description": f"Copy {source_file} with worktree-specific name",
                    "source": source_file,
                    "destination_pattern": (
                        f"{{worktree_dir}}_{project_name_from_file}.code-workspace"
                    ),
                }
            )

        # Add MCP servers commonly used in web apps
        config.add_mcp_server(
            {
                "name": "linear-server",
                "transport": "sse",
                "url": "https://mcp.linear.app/sse",
            }
        )
        config.add_mcp_server(
            {
                "name": "playwright",
                "command": "npx @playwright/mcp@latest",
            }
        )

    def _apply_minimal_template(self, config: ProjectConfig):
        """Apply minimal project template"""
        config.enable_feature("claude_workspace", False)
        config.enable_feature("claude_symlink", False)
        config.enable_feature("review_agents", False)
        config.enable_feature("nvm_setup", False)
        config.enable_feature("env_sync_check", False)

    def _prompt_for_features(self, config: ProjectConfig):
        """Prompt user for feature configuration"""
        print("\n⚙️ Feature Configuration")
        print("-" * 30)

        features = [
            ("claude_workspace", "Setup Claude workspace with commands/agents"),
            ("claude_symlink", "Create .cursorrules symlink to CLAUDE.md"),
            ("review_agents", "Enable automated review agents"),
            ("nvm_setup", "Setup NVM integration for Node projects"),
            ("env_sync_check", "Check for env file changes during review"),
        ]

        for feature, description in features:
            current = config.is_feature_enabled(feature)
            default = "Y" if current else "N"
            prompt = f"Enable {feature}? ({description}) [{default}]: "

            response = input(prompt).strip().lower()
            if not response:
                enabled = current
            else:
                enabled = response in ["y", "yes"]

            config.enable_feature(feature, enabled)

    def _execute_custom_actions(
        self, project_config: ProjectConfig, worktree_path: Path, repo_path: Path
    ):
        """Execute custom actions defined in project configuration"""
        actions = project_config.get_custom_actions()

        for action in actions:
            action_type = action.get("type")

            if action_type == "copy_workspace_file":
                self._execute_copy_workspace_file(action, worktree_path, repo_path)
            elif action_type == "copy_directory":
                self._execute_copy_directory(action, worktree_path, repo_path)
            elif action_type == "run_command":
                self._execute_run_command(action, worktree_path, repo_path)
            elif action_type == "copy_env_files":
                self._execute_copy_env_files(action, worktree_path, repo_path)
            elif action_type == "allocate_port":
                self._execute_allocate_port(action, worktree_path, repo_path, project_config)
            else:
                logger.warning(f"Unknown custom action type: {action_type}")

    def _execute_copy_workspace_file(
        self, action: Dict[str, Any], worktree_path: Path, repo_path: Path
    ):
        """Execute copy workspace file action"""
        source = action.get("source")
        destination_pattern = action.get("destination_pattern")

        if not source or not destination_pattern:
            logger.warning("copy_workspace_file action missing source or destination_pattern")
            return

        source_file = repo_path / source
        if not source_file.exists():
            logger.warning(f"Source workspace file not found: {source_file}")
            return

        # Replace template variables
        worktree_dir = worktree_path.name
        destination_name = destination_pattern.format(worktree_dir=worktree_dir)
        destination_file = worktree_path / destination_name

        try:
            import shutil

            shutil.copy2(source_file, destination_file)
            print(f"📁 Copied workspace file: {destination_name}")
        except OSError as e:
            logger.warning(f"Failed to copy workspace file: {e}")

    def _execute_copy_directory(self, action: Dict[str, Any], worktree_path: Path, repo_path: Path):
        """Execute copy directory action"""
        source = action.get("source")
        destination = action.get("destination")

        if not source:
            logger.warning("copy_directory action missing source")
            return

        source_dir = repo_path / source
        if not source_dir.exists():
            logger.warning(f"Source directory not found: {source_dir}")
            return

        if not source_dir.is_dir():
            logger.warning(f"Source is not a directory: {source_dir}")
            return

        # Use source name as destination if not specified
        if not destination:
            destination = source

        destination_dir = worktree_path / destination

        try:
            import shutil

            # Remove destination if it exists
            if destination_dir.exists():
                shutil.rmtree(destination_dir)

            # Copy the entire directory
            shutil.copytree(source_dir, destination_dir)
            print(f"📁 Copied directory: {destination}")
        except OSError as e:
            logger.warning(f"Failed to copy directory: {e}")

    def _execute_run_command(self, action: Dict[str, Any], worktree_path: Path, repo_path: Path):
        """Execute shell command action"""
        command = action.get("command")
        description = action.get("description", "Running custom command")

        if not command:
            logger.warning("run_command action missing command")
            return

        print(f"🔧 {description}")

        try:
            # Run command in the worktree directory
            result = subprocess.run(
                command,
                cwd=worktree_path,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                print(result.stdout.strip())
            print("✅ Command completed successfully")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            print(f"⚠️  Command failed: {error_msg}")
            logger.warning(f"Failed to run command '{command}': {error_msg}")

    def _execute_copy_env_files(self, action: Dict[str, Any], worktree_path: Path, repo_path: Path):
        """Execute copy_env_files action"""
        description = action.get("description", "Copying .env files")
        print(f"📄 {description}")

        env_setup = EnvironmentSetup(worktree_path)
        env_setup.copy_env_files(repo_path)

    def _execute_allocate_port(
        self,
        action: Dict[str, Any],
        worktree_path: Path,
        repo_path: Path,
        project_config: ProjectConfig,
    ):
        """Execute allocate_port action"""
        description = action.get("description", "Allocating port offset")
        print(f"📡 {description}")

        project_name = project_config.get_project_name()
        port_registry = PortRegistry()
        max_slots = project_config.get_max_slots()
        base_port = project_config.get_base_port()

        # Get next available offset
        offset = port_registry.get_next_available_offset(project_name, max_slots)

        if offset is None:
            print(f"⚠️  Warning: All port slots (0-{max_slots}) are allocated!")
            print("   Run 'cproj cleanup' to free up unused worktrees")
        else:
            # Allocate port offset
            if port_registry.allocate(project_name, worktree_path, offset):
                env_setup = EnvironmentSetup(worktree_path)
                env_setup.write_ports_env(offset, base_port)

    def cmd_worktree_create(self, args):
        """Create worktree"""
        # Derive project context from current working directory
        if args.repo:
            repo_path = Path(args.repo)
        else:
            # Find git repository root from current working directory
            repo_path = self._find_git_root(Path.cwd())
            if not repo_path:
                print("❌ Not in a git repository!")
                print()
                print("You need to be in a git repository or specify --repo:")
                print("  cd /path/to/your/project")
                print("  cproj w create --branch feature/name")
                print()
                print("Or:")
                print("  cproj w create --repo /path/to/project " "--branch feature/name")
                return

        # Derive project settings from repository
        project_name = repo_path.name
        temp_root = Path(
            args.temp_root
            or self.config.get("temp_root", tempfile.gettempdir())
            or tempfile.gettempdir()
        )

        logger.debug(f"Using repository: {repo_path} (project: {project_name})")

        # Load project configuration
        project_config = ProjectConfig(repo_path)

        # Get base branch from args, project config, or auto-detect
        if args.base:
            base_branch = args.base
        elif project_config.config_path.exists():
            base_branch = project_config.get_base_branch()
        else:
            base_branch = self._detect_default_branch(repo_path) or "main"
        if not project_config.config_path.exists():
            print(f"⚠️  No project configuration found for {project_name}")
            print("   Consider running 'cproj init-project' to configure project-specific features")
            print()

        # Interactive prompt for branch name if not provided and
        # in interactive mode
        if not args.branch:
            if not self._is_interactive():
                raise CprojError(
                    "Branch name is required. Use --branch BRANCH_NAME or run "
                    "in interactive mode."
                )

            print("🌿 Create New Branch")
            print("-" * 50)

            suggestions = self._generate_branch_suggestions()
            print("Branch name suggestions:")
            for i, suggestion in enumerate(suggestions, 1):
                print(f"  {i}. {suggestion}")
            print()

            while True:
                branch_input = input("Enter branch name (or number for suggestion): ").strip()

                if not branch_input:
                    print("❌ Branch name is required")
                    continue

                # Check if user entered a number for suggestion
                if branch_input.isdigit():
                    try:
                        suggestion_idx = int(branch_input) - 1
                        if 0 <= suggestion_idx < len(suggestions):
                            args.branch = suggestions[suggestion_idx]
                            break
                        else:
                            print(f"❌ Please enter a number between 1 and " f"{len(suggestions)}")
                            continue
                    except (ValueError, IndexError):
                        print("❌ Invalid selection")
                        continue
                else:
                    args.branch = branch_input
                    break

            print(f"✅ Using branch: {args.branch}")
            print()

        # Interactive prompt for Linear URL if not provided and
        # Linear is configured
        if not args.linear and self.config.get("linear_org") and self._is_interactive():
            print("🔗 Linear Integration (optional)")
            print("-" * 50)
            print(f"Linear organization: {self.config.get('linear_org')}")
            linear_input = input("Linear issue URL (optional, press Enter to skip): ").strip()
            if linear_input:
                args.linear = linear_input
                print(f"✅ Using Linear URL: {args.linear}")
            print()

        # Interactive prompt for environment setup options if not specified and
        # in interactive mode
        if (
            not any([args.python_install, args.node_install, args.java_build])
            and self._is_interactive()
        ):
            print("⚙️  Environment Setup (optional)")
            print("-" * 50)

            # Check what environments are available in the repo
            repo_path_obj = Path(repo_path)
            has_python = any(
                (repo_path_obj / f).exists()
                for f in ["pyproject.toml", "requirements.txt", "setup.py"]
            )
            has_node = (repo_path_obj / "package.json").exists()
            has_java = any(
                (repo_path_obj / f).exists()
                for f in ["pom.xml", "build.gradle", "build.gradle.kts"]
            )

            if has_python:
                python_install = input("Auto-install Python dependencies? [Y/n]: ").strip().lower()
                args.python_install = python_install not in ["n", "no"]

                if not args.python_install:
                    shared_venv = input("Use shared venv from main repo? [Y/n]: ").strip().lower()
                    args.shared_venv = shared_venv not in ["n", "no"]

            if has_node:
                node_install = input("Auto-install Node dependencies? [Y/n]: ").strip().lower()
                args.node_install = node_install not in ["n", "no"]

            if has_java:
                java_build = input("Auto-build Java project? [Y/n]: ").strip().lower()
                args.java_build = java_build not in ["n", "no"]

            # Ask about .env files
            copy_env = input("Copy .env files from main repo? [Y/n]: ").strip().lower()
            args.copy_env = copy_env not in ["n", "no"]

            if has_python or has_node or has_java:
                print()

        git = GitWorktree(repo_path)

        # Fetch and ensure base branch
        git.fetch_all()
        git.ensure_base_branch(base_branch)

        # Create worktree path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        worktree_name = f"{project_name}_{args.branch}_{timestamp}"
        worktree_path = temp_root / worktree_name

        # Create worktree
        git.create_worktree(
            worktree_path,
            args.branch,
            base_branch,
            interactive=self._is_interactive(),
        )

        # Setup environment
        env_setup = EnvironmentSetup(worktree_path)
        python_env = env_setup.setup_python(
            args.python_install, args.shared_venv, repo_path, project_config
        )
        node_env = env_setup.setup_node(args.node_install)
        java_env = env_setup.setup_java(args.java_build)

        # Note: .env file copying is now handled by custom_actions in project.yaml
        # Use action type: copy_env_files

        # Create .agent.json
        agent_json = AgentJson(worktree_path)
        agent_json.set_project(project_name, str(repo_path))
        agent_json.set_workspace(str(worktree_path), args.branch, base_branch)
        agent_json.set_env("python", python_env)
        agent_json.set_env("node", node_env)
        agent_json.set_env("java", java_env)

        if args.linear:
            agent_json.set_link("linear", args.linear)

        agent_json.save()

        # Project-specific actions based on configuration
        if project_config.is_feature_enabled("claude_symlink"):
            self._setup_claude_symlink(worktree_path, repo_path)

        if project_config.is_feature_enabled("nvm_setup"):
            self._setup_nvm_for_claude(worktree_path, node_env, project_config)

        if project_config.is_feature_enabled("claude_workspace"):
            self._setup_claude_workspace(worktree_path, repo_path, args)

        # Execute custom actions (including .env copy and port allocation)
        # Custom actions are executed in the order specified in project.yaml
        # This allows projects to control when .env files are copied, when ports
        # are allocated, and when project-specific scripts (like update-env-ports.sh) run
        self._execute_custom_actions(project_config, worktree_path, repo_path)

        print(f"Created worktree: {worktree_path}")
        print(f"Branch: {args.branch}")

        # Open terminal by default (unless --no-terminal is specified)
        terminal_app = args.terminal or self.config.get("terminal", "Terminal")
        if not args.no_terminal and terminal_app != "none":
            # Strip branch prefix (everything before /) for cleaner
            # window title
            import re

            branch_display = re.sub(r"^\S+/", "", args.branch)
            TerminalAutomation.open_terminal(worktree_path, branch_display, terminal_app)

        # Open editor only if --open-editor is specified
        if args.open_editor:
            editor = args.editor or self.config.get("editor", "code")
            if editor:
                TerminalAutomation.open_editor(worktree_path, editor)

    def cmd_review_open(self, args):
        """Open review"""
        worktree_path = Path.cwd()
        agent_json_path = worktree_path / ".cproj" / ".agent.json"

        if not agent_json_path.exists():
            raise CprojError(
                "Not in a cproj worktree (no .agent.json found in .cproj "
                "directory). Run from worktree root directory."
            )

        agent_json = AgentJson(worktree_path)
        repo_path = Path(agent_json.data["project"]["repo_path"])
        branch = agent_json.data["workspace"]["branch"]

        # Load project configuration to check if env sync is enabled
        project_config = ProjectConfig(repo_path)

        # Check for env file differences if feature is enabled and not skipped
        if project_config.is_feature_enabled("env_sync_check") and not getattr(
            args, "skip_env_sync", False
        ):
            env_setup = EnvironmentSetup(worktree_path)
            different_env_files = env_setup.check_env_differences(repo_path)

            if different_env_files:
                print("\n⚠️  Found differences in .env files:")
                for file in different_env_files:
                    print(f"   • {file}")

                # Check if we can prompt for input
                if self._is_interactive():
                    try:
                        sync_response = (
                            input(
                                "\nDo you want to sync these .env files to the main repo? [y/N]: "
                            )
                            .strip()
                            .lower()
                        )
                    except (EOFError, KeyboardInterrupt):
                        sync_response = "n"
                        print("\n⏭️  Skipping .env file sync (no input available)")
                else:
                    sync_response = "n"
                    print("\n⏭️  Skipping .env file sync (non-interactive mode)")

                if sync_response == "y":
                    print("\n🔄 Syncing .env files...")
                    env_setup.sync_env_files(repo_path, backup=True)
                else:
                    if sync_response != "n" or self._is_interactive():
                        print("⏭️  Skipping .env file sync")
        elif getattr(args, "skip_env_sync", False):
            print("⏭️  Skipping .env file sync (--skip-env-sync flag)")

        git = GitWorktree(repo_path)

        # Push branch
        if not args.no_push:
            git.push_branch(branch, worktree_path)

        # Create PR if GitHub available
        if GitHubIntegration.is_available():
            title = f"feat: {branch}"
            body = f"Branch: {branch}"

            if agent_json.data["links"]["linear"]:
                body += f"\n\nLinear: {agent_json.data['links']['linear']}"

            # Default to ready (not draft), unless explicitly set to draft
            draft = args.draft if hasattr(args, "draft") else False
            assignees = args.assign.split(",") if args.assign else None

            pr_url = GitHubIntegration.create_pr(title, body, draft, assignees)
            if pr_url:
                agent_json.set_link("pr", pr_url)
                agent_json.save()
                print(f"Created PR: {pr_url}")

        # Run automated review agents unless disabled
        if not args.no_agents:
            print("\n🤖 Running automated review agents...")
            try:
                # Import and run agents
                from claude_review_agents import ProjectContext, setup_review

                context = ProjectContext()
                context.ticket = agent_json.data["links"].get("linear", "")
                context.pr_title = branch

                result = setup_review(worktree_path, context)
                print(f"✅ Review configuration created: " f"{result['config_path']}")
                print("📋 Ready for Claude review! Run:")
                print("   cproj review agents")
            except ImportError:
                print("⚠️  Review agents not available " "(claude_review_agents.py not found)")
            except Exception as e:
                print(f"⚠️  Could not setup review agents: {e}")

        print(f"\n🎉 Branch {branch} ready for review")

    def cmd_review_agents(self, args):
        """Run automated review agents with security validation"""
        try:
            from claude_review_agents import (
                ClaudeReviewOrchestrator,
                ProjectContext,
                setup_review,
            )
        except ImportError as e:
            raise CprojError(f"Review agents module not available: {e}")

        worktree_path = Path.cwd()
        agent_json_path = worktree_path / ".cproj" / ".agent.json"

        if not agent_json_path.exists():
            raise CprojError(
                "Not in a cproj worktree (no .agent.json found in .cproj "
                "directory). Run from worktree root directory."
            )

        try:
            # Load agent data for context
            agent_json = AgentJson(worktree_path)

            # Create project context with safe values
            context = ProjectContext()
            if "links" in agent_json.data and agent_json.data["links"].get("linear"):
                # Sanitize Linear URL
                linear_url = str(agent_json.data["links"]["linear"])[:200]  # Limit length
                context.ticket = f"Linear: {linear_url}"

            if "workspace" in agent_json.data and agent_json.data["workspace"].get("branch"):
                # Sanitize branch name
                branch = str(agent_json.data["workspace"]["branch"])[:100]  # Limit length
                safe_branch = "".join(c for c in branch if c.isalnum() or c in "-_.")
                context.pr_title = safe_branch

            if args.setup:
                # Just setup configuration
                result = setup_review(worktree_path, context)
                print(f"✅ Review configuration saved: {result['config_path']}")
                print(f"🤖 Configured {result['agents']} agents")
                print(f"📊 Diff size: {result['diff_size']} bytes")
                print("\n🎯 To run the review:")
                print("1. Open the configuration file in Claude")
                print("2. Use the Task tool to run each agent")
                print("3. Aggregate results")
                return

            # Setup and run review with error handling
            orchestrator = ClaudeReviewOrchestrator(worktree_path, context)
            config_path = orchestrator.save_review_config()

            if args.json:
                with config_path.open(encoding="utf-8") as f:
                    config = json.load(f)
                    print(json.dumps(config, indent=2))
            else:
                print("📋 Review agents configured!")
                print(f"Configuration: {config_path}")
                print("\n" + "=" * 60)
                print("READY FOR CLAUDE REVIEW")
                print("=" * 60)
                print("\nNext steps:")
                print("1. Copy the following prompt to Claude:")
                print("\n" + "-" * 40)
                print("Please run a comprehensive PR review using the Task tool.")
                print("The review configuration is in .cproj/.cproj_review.json")
                print("\nRun these three agents in sequence:")
                print("1. Senior Developer Code Review (general-purpose agent)")
                print("2. QA Engineer Review (general-purpose agent)")
                print("3. Security Review (general-purpose agent)")
                print("\nFor each agent, use the prompt from the " "configuration file.")
                print("Parse the JSON responses and provide a consolidated " "report.")
                print("-" * 40)
                print(f"\n2. The configuration file is: {config_path}")
                print("3. Each agent has a specific prompt and JSON output " "contract")
                print("4. Aggregate all findings and determine if PR should be " "blocked")

        except ValueError as e:
            raise CprojError(f"Security validation failed: {e}")
        except Exception as e:
            raise CprojError(f"Review setup failed: {e}")

    def cmd_merge(self, args):
        """Merge and cleanup"""
        worktree_path = Path.cwd()
        agent_json_path = worktree_path / ".cproj" / ".agent.json"

        if not agent_json_path.exists():
            raise CprojError(
                "Not in a cproj worktree (no .agent.json found in .cproj "
                "directory). Run from worktree root directory."
            )

        agent_json = AgentJson(worktree_path)
        repo_path = Path(agent_json.data["project"]["repo_path"])

        git = GitWorktree(repo_path)

        # Check if dirty
        if not args.force and git.is_branch_dirty(worktree_path):
            raise CprojError("Worktree has uncommitted changes. Use --force to override.")

        # Merge PR if GitHub available
        merge_successful = False
        if GitHubIntegration.is_available():
            merge_successful = GitHubIntegration.merge_pr(args.squash, args.delete_remote)
            if merge_successful:
                print("PR merged successfully")
            else:
                print("❌ PR merge failed. Keeping worktree for you to " "continue working.")
                print("Common reasons:")
                print(
                    "  - PR is still in draft mode (use 'gh pr ready' or " "mark ready in GitHub)"
                )
                print("  - PR needs approval from reviewers")
                print("  - PR has merge conflicts")
                print("  - Branch protection rules not satisfied")
                return
        else:
            print("⚠️  GitHub CLI not available. Please merge manually " "in GitHub.")
            print("After merging, you can clean up with:")
            print(f"  git worktree remove --force {worktree_path}")
            return

        # Only proceed with cleanup if merge was successful
        if merge_successful:
            # Close workspace
            agent_json.close_workspace()
            agent_json.save()

            # Remove worktree and branch
            if not args.keep_worktree:
                branch_name = git.remove_worktree_and_branch(worktree_path, force=True)

                # Deallocate port if port allocation is enabled
                project_config = ProjectConfig(repo_path)
                if project_config.is_feature_enabled("port_allocation"):
                    port_registry = PortRegistry()
                    project_name = project_config.get_project_name()
                    if port_registry.deallocate(project_name, worktree_path):
                        print("📡 Port offset deallocated")

                if branch_name:
                    print(f"Removed worktree and branch '{branch_name}': {worktree_path}")
                else:
                    print(f"Removed worktree: {worktree_path}")
            else:
                print(f"Keeping worktree: {worktree_path}")

    def cmd_list(self, args):
        """List worktrees"""
        repo_path = Path(self.config.get("repo_path", "."))

        if not repo_path.exists():
            print("No configured repository")
            return

        git = GitWorktree(repo_path)
        worktrees = git.list_worktrees()

        if args.json:
            print(json.dumps(worktrees, indent=2))
            return

        for wt in worktrees:
            path = Path(wt["path"])
            branch = wt.get("branch", "N/A")

            # Try to load .agent.json for additional info
            agent_json_path = path / ".cproj" / ".agent.json"
            if agent_json_path.exists():
                try:
                    agent_json = AgentJson(path)
                    linear = agent_json.data["links"]["linear"]
                    pr = agent_json.data["links"]["pr"]

                    print(f"{path} [{branch}]")
                    if linear:
                        print(f"  Linear: {linear}")
                    if pr:
                        print(f"  PR: {pr}")
                except Exception:
                    print(f"{path} [{branch}]")
            else:
                print(f"{path} [{branch}]")

    def cmd_status(self, args):
        """Show status"""
        # Check if we're in a cproj worktree or should default to --all
        if args.path:
            worktree_path = Path(args.path)
        else:
            worktree_path = Path.cwd()

        agent_json_path = worktree_path / ".cproj" / ".agent.json"

        # If not in a cproj worktree and --all not explicitly set, default to --all
        if not agent_json_path.exists() and not args.all:
            args.all = True

        if args.all:
            # Show status for all worktrees
            repo_path = self._find_git_root(Path.cwd())
            if not repo_path:
                raise CprojError("Not in a git repository")

            git = GitWorktree(repo_path)
            worktrees = git.list_worktrees()

            # Collect worktree statuses and filter based on --detailed flag
            actionable_worktrees = []
            all_worktrees = []

            for wt in worktrees:
                wt_path = Path(wt["path"])
                # Skip main repo unless it has .cproj/.agent.json
                agent_json_path = wt_path / ".cproj" / ".agent.json"
                if wt_path == repo_path and not agent_json_path.exists():
                    continue

                try:
                    if agent_json_path.exists():
                        agent_json = AgentJson(wt_path)
                        status = WorktreeStatus(wt_path, agent_json)
                        comprehensive_status = status.get_comprehensive_status()
                        overall_status = comprehensive_status.get("overall_status")

                        # Determine if this worktree needs action
                        needs_action = overall_status in [
                            "has_local_changes",
                            "needs_push",
                            "needs_pull",
                            "ready_for_pr",
                            "under_review",
                            "cleanup",
                            "unknown",
                        ]

                        worktree_info = {
                            "path": wt_path,
                            "status_obj": status,
                            "needs_action": needs_action,
                            "type": "cproj",
                        }
                    else:
                        # Plain worktree without cproj metadata
                        branch = wt.get("branch", "unknown")
                        local_status = git.get_local_status(wt_path)
                        needs_action = not local_status["is_clean"]

                        worktree_info = {
                            "path": wt_path,
                            "branch": branch,
                            "local_status": local_status,
                            "needs_action": needs_action,
                            "type": "plain",
                        }

                    all_worktrees.append(worktree_info)
                    if needs_action:
                        actionable_worktrees.append(worktree_info)

                except Exception as e:
                    # Always show errored worktrees
                    error_info = {
                        "path": wt_path,
                        "error": str(e),
                        "needs_action": True,
                        "type": "error",
                    }
                    all_worktrees.append(error_info)
                    actionable_worktrees.append(error_info)

            # Choose which worktrees to display
            if args.detailed:
                display_worktrees = all_worktrees
                print(f"Repository: {repo_path}")
                print(f"Found {len(all_worktrees)} worktree(s):\n")
            else:
                display_worktrees = actionable_worktrees
                print(f"Repository: {repo_path}")
                if len(actionable_worktrees) == 0:
                    print("All worktrees are up to date! (Use --detailed to see all)")
                    return
                else:
                    print(f"Found {len(actionable_worktrees)} worktree(s) needing attention:")
                    print(f"(Use --detailed to see all {len(all_worktrees)} worktrees)\n")

            # Sort worktrees by action priority
            action_priority = {
                "has_local_changes": 1,  # COMMIT
                "needs_push": 2,  # PUSH
                "ready_for_pr": 3,  # CREATE PR
                "under_review": 4,  # REVIEW
                "needs_pull": 5,  # PULL
                "unknown": 6,  # CHECK
                "cleanup": 7,  # CLEANUP
            }

            def get_sort_key(wt_info):
                if wt_info["type"] == "cproj":
                    status = wt_info["status_obj"].get_comprehensive_status()
                    overall_status = status.get("overall_status", "unknown")
                    return action_priority.get(overall_status, 999)
                elif wt_info["type"] == "plain":
                    # Plain worktrees with changes get priority 1 (COMMIT)
                    return 1 if wt_info["needs_action"] else 999
                else:
                    return 999  # Errors last

            display_worktrees.sort(key=get_sort_key)

            # Display the selected worktrees
            for wt_info in display_worktrees:
                try:
                    if wt_info["type"] == "cproj":
                        if args.detailed:
                            # Full detailed format
                            print(wt_info["status_obj"].format_status(args.detailed))
                        else:
                            # Terse action-focused format
                            print(wt_info["status_obj"].format_terse())
                    elif wt_info["type"] == "plain":
                        # Plain worktree formatting
                        path_name = wt_info["path"].name
                        branch = wt_info["branch"]
                        local = wt_info["local_status"]

                        if args.detailed:
                            print(f"📁 {path_name} [{branch}]")
                            if local["is_clean"]:
                                print("   ✅ Clean")
                            else:
                                changes = []
                                if local["staged"]:
                                    changes.append(f"staged: {len(local['staged'])}")
                                if local["modified"]:
                                    changes.append(f"modified: {len(local['modified'])}")
                                if local["untracked"]:
                                    changes.append(f"untracked: {len(local['untracked'])}")
                                print(f"   📝 Changes: {', '.join(changes)}")
                            print()
                        else:
                            # Terse format for plain worktrees
                            if not local["is_clean"]:
                                changes = []
                                if local["staged"]:
                                    changes.append(f"{len(local['staged'])}staged")
                                if local["modified"]:
                                    changes.append(f"{len(local['modified'])}mod")
                                if local["untracked"]:
                                    changes.append(f"{len(local['untracked'])}new")
                                change_detail = f" ({', '.join(changes)})" if changes else ""
                                print(f"COMMIT {path_name} [{branch}]{change_detail}")
                            else:
                                print(f"SYNCED {path_name} [{branch}]")
                    elif wt_info["type"] == "error":
                        print(f"ERROR {wt_info['path'].name}: {wt_info['error']}")
                except Exception as e:
                    print(f"ERROR {wt_info['path'].name}: {e}")
            return

        # Single worktree status - we know .agent.json exists at this point
        agent_json = AgentJson(worktree_path)

        if args.json:
            print(json.dumps(agent_json.data, indent=2))
            return

        # Enhanced status using WorktreeStatus
        repo_path = self._find_git_root(worktree_path)
        if not repo_path:
            raise CprojError("Not in a git repository")

        git = GitWorktree(repo_path)
        status = WorktreeStatus(worktree_path, agent_json)
        print(status.format_status(args.detailed))

    def cmd_cleanup(self, args):
        """Cleanup worktrees"""
        # Use CWD-based detection like other commands
        if args.repo:
            repo_path = Path(args.repo)
        else:
            # Find git repository root from current working directory
            repo_path = self._find_git_root(Path.cwd())
            if not repo_path:
                print("❌ Not in a git repository!")
                print("You need to be in a git repository or specify --repo")
                return

        if not repo_path.exists():
            print("No configured repository")
            return

        git = GitWorktree(repo_path)
        worktrees = git.list_worktrees()

        # Interactive prompt for cleanup criteria if not specified and
        # in interactive mode
        if (
            not any(
                [
                    args.older_than,
                    getattr(args, "newer_than", None),
                    args.merged_only,
                ]
            )
            and self._is_interactive()
        ):
            print("🧹 Cleanup Worktrees")
            print("-" * 50)

            # Show current worktrees with ages
            active_worktrees = [wt for wt in worktrees if Path(wt["path"]) != repo_path]
            if not active_worktrees:
                print("No worktrees to clean up.")
                return

            print(f"Found {len(active_worktrees)} active worktree(s):")
            for wt in active_worktrees:
                path = Path(wt["path"])
                branch = wt.get("branch", "N/A")

                # Try to get age
                age_info = ""
                agent_json_path = path / ".cproj" / ".agent.json"
                if agent_json_path.exists():
                    try:
                        agent_json = AgentJson(path)
                        created_at = datetime.fromisoformat(
                            agent_json.data["workspace"]["created_at"].replace("Z", "+00:00")
                        )
                        age_days = (datetime.now(timezone.utc) - created_at).days
                        age_info = f" ({age_days} days old)"
                    except Exception:
                        pass

                print(f"  - {path.name} [{branch}]{age_info}")

            print()
            print("Cleanup options:")
            print("  1. Interactive selection")
            print("  2. Remove worktrees newer than X days")
            print("  3. Remove worktrees older than X days")
            print("  4. Remove merged worktrees only")
            print("  5. Cancel")
            if args.force:
                print("💪 Force mode enabled - will remove dirty worktrees")

            while True:
                choice = input("Select cleanup method [1-5]: ").strip()

                if choice == "1":
                    # Interactive selection mode (moved to option 1)
                    current_worktree = Path.cwd()
                    selected_for_removal = []

                    print("📋 Select worktrees to remove:")
                    print("   [y/n] for each worktree, Enter to confirm " "selection")
                    print()

                    for i, wt in enumerate(active_worktrees):
                        path = Path(wt["path"])
                        branch = wt.get("branch", "N/A")

                        # Get age info
                        age_info = ""
                        agent_json_path = path / ".cproj" / ".agent.json"
                        if agent_json_path.exists():
                            try:
                                agent_json = AgentJson(path)
                                created_at = datetime.fromisoformat(
                                    agent_json.data["workspace"]["created_at"].replace(
                                        "Z", "+00:00"
                                    )
                                )
                                age_days = (datetime.now(timezone.utc) - created_at).days
                                age_info = f" ({age_days} days old)"
                            except Exception:
                                pass

                        # Check if this is the current worktree
                        is_current = (
                            current_worktree == path or current_worktree.resolve() == path.resolve()
                        )
                        status_info = " [CURRENT]" if is_current else ""

                        while True:
                            response = (
                                input(
                                    f"Remove {path.name} [{branch}]{age_info}"
                                    f"{status_info}? [y/N]: "
                                )
                                .strip()
                                .lower()
                            )
                            if response in ["", "n", "no"]:
                                break
                            elif response in ["y", "yes"]:
                                if not is_current:  # Don't allow removing current worktree
                                    selected_for_removal.append(wt)
                                else:
                                    print("❌ Cannot remove current worktree")
                                break
                            else:
                                print("Please enter 'y' or 'n'")

                    if selected_for_removal:
                        print(
                            f"\n📋 Selected {len(selected_for_removal)} " f"worktrees for removal"
                        )
                        for wt in selected_for_removal:
                            print(f"  - {Path(wt['path']).name} " f"[{wt.get('branch', 'N/A')}]")

                        confirm = input("\nConfirm removal? [y/N]: ").strip().lower()
                        if confirm in ["y", "yes"]:
                            for wt in selected_for_removal:
                                try:
                                    wt_path = Path(wt["path"])
                                    branch_name = git.remove_worktree_and_branch(
                                        wt_path, force=args.force
                                    )

                                    # Deallocate port if enabled
                                    project_config = ProjectConfig(repo_path)
                                    if project_config.is_feature_enabled("port_allocation"):
                                        port_registry = PortRegistry()
                                        project_name = project_config.get_project_name()
                                        port_registry.deallocate(project_name, wt_path)

                                    if branch_name:
                                        print(
                                            f"✅ Removed {wt_path.name} "
                                            f"and branch '{branch_name}'"
                                        )
                                    else:
                                        print(f"✅ Removed {wt_path.name}")
                                except subprocess.CalledProcessError as e:
                                    # Capture stderr to get the actual git
                                    # error message
                                    try:
                                        result = subprocess.run(
                                            [
                                                "git",
                                                "-C",
                                                str(repo_path),
                                                "worktree",
                                                "remove",
                                                str(wt["path"]),
                                            ],
                                            capture_output=True,
                                            text=True,
                                            check=False,
                                        )
                                        error_msg = (
                                            result.stderr.strip() if result.stderr else str(e)
                                        )
                                    except Exception:
                                        error_msg = str(e)

                                    logger.debug(f"Cleanup error message: '{error_msg}'")
                                    logger.debug(
                                        f"Contains 'is dirty': " f"{'is dirty' in error_msg}"
                                    )
                                    logger.debug(
                                        f"Contains '--force': " f"{'--force' in error_msg}"
                                    )
                                    logger.debug(f"args.force: {args.force}")
                                    logger.debug(f"Interactive mode: " f"{self._is_interactive()}")

                                    if (
                                        "is dirty" in error_msg or "--force" in error_msg
                                    ) and not args.force:
                                        print(
                                            f"❌ Failed to remove "
                                            f"{Path(wt['path']).name}: "
                                            f"Worktree is "
                                            f"dirty (has uncommitted changes)"
                                        )
                                        if self._is_interactive():
                                            force_choice = (
                                                input(
                                                    f"Force removal of dirty worktree "
                                                    f"{Path(wt['path']).name}? [y/N]: "
                                                )
                                                .strip()
                                                .lower()
                                            )
                                            if force_choice in ["y", "yes"]:
                                                try:
                                                    wt_path = Path(wt["path"])
                                                    branch_name = git.remove_worktree_and_branch(
                                                        wt_path,
                                                        force=True,
                                                    )

                                                    # Deallocate port if enabled
                                                    project_config = ProjectConfig(repo_path)
                                                    if project_config.is_feature_enabled(
                                                        "port_allocation"
                                                    ):
                                                        port_registry = PortRegistry()
                                                        project_name = (
                                                            project_config.get_project_name()
                                                        )
                                                        port_registry.deallocate(
                                                            project_name, wt_path
                                                        )

                                                    if branch_name:
                                                        print(
                                                            f"✅ Force removed "
                                                            f"{wt_path.name} "
                                                            f"and branch '{branch_name}'"
                                                        )
                                                    else:
                                                        print(
                                                            f"✅ Force removed " f"{wt_path.name}"
                                                        )
                                                except Exception as force_e:
                                                    print(
                                                        f"❌ Failed to force remove "
                                                        f"{Path(wt['path']).name}: {force_e}"
                                                    )
                                            else:
                                                print(f"⏭️  Skipped {Path(wt['path']).name}")
                                        else:
                                            print("💡 Use --force to remove dirty " "worktrees")
                                    else:
                                        print(
                                            f"❌ Failed to remove "
                                            f"{Path(wt['path']).name}: {error_msg}"
                                        )
                                except Exception as e:
                                    print(f"❌ Failed to remove " f"{Path(wt['path']).name}: {e}")
                        else:
                            print("Cleanup cancelled")
                    else:
                        print("No worktrees selected for removal")
                    return

                elif choice == "2":
                    # New option: Remove worktrees newer than X days
                    default_days = 7
                    days_input = input(
                        f"Remove worktrees newer than how many days? " f"[{default_days}]: "
                    ).strip()
                    try:
                        newer_days = int(days_input) if days_input else default_days
                        args.newer_than = newer_days
                        logger.debug(f"Set args.newer_than to {args.newer_than}")
                        break
                    except ValueError:
                        print("❌ Please enter a valid number")
                        continue

                elif choice == "3":
                    default_days = self.config.get("cleanup_days", 14)
                    days_input = input(
                        f"Remove worktrees older than how many days? " f"[{default_days}]: "
                    ).strip()
                    try:
                        args.older_than = int(days_input) if days_input else default_days
                        break
                    except ValueError:
                        print("❌ Please enter a valid number")
                        continue

                elif choice == "4":
                    args.merged_only = True
                    break

                elif choice == "5":
                    print("Cleanup cancelled")
                    return

                else:
                    print("❌ Please enter 1-5")
                    continue

            print()

        logger.debug(
            f"Processing cleanup with filters - older_than: {args.older_than}, "
            f"newer_than: {getattr(args, 'newer_than', None)}, "
            f"merged_only: {args.merged_only}"
        )

        to_remove = []
        for wt in worktrees:
            path = Path(wt["path"])
            if path == repo_path:  # Skip main worktree
                continue

            should_remove = False
            logger.debug(f"Evaluating worktree: {path.name}")

            # Check age
            if args.older_than:
                agent_json_path = path / ".cproj" / ".agent.json"
                if agent_json_path.exists():
                    try:
                        agent_json = AgentJson(path)
                        created_at = datetime.fromisoformat(
                            agent_json.data["workspace"]["created_at"].replace("Z", "+00:00")
                        )
                        age_days = (datetime.now(timezone.utc) - created_at).days
                        if age_days > args.older_than:
                            should_remove = True
                    except Exception:
                        pass

            # Check for newer than (opposite logic)
            if hasattr(args, "newer_than") and args.newer_than:
                logger.debug(f"Checking newer_than condition for {path.name}")
                agent_json_path = path / ".cproj" / ".agent.json"
                if agent_json_path.exists():
                    try:
                        agent_json = AgentJson(path)
                        created_at = datetime.fromisoformat(
                            agent_json.data["workspace"]["created_at"].replace("Z", "+00:00")
                        )
                        age_days = (datetime.now(timezone.utc) - created_at).days
                        logger.debug(
                            f"{path.name} is {age_days} days old, " f"newer_than={args.newer_than}"
                        )
                        if age_days <= args.newer_than:
                            should_remove = True
                            logger.debug(
                                f"Marking {path.name} for removal "
                                f"(newer than {args.newer_than} days)"
                            )
                    except Exception as e:
                        logger.debug(f"Error processing {path.name}: {e}")
                        pass

            # Check if merged (simplified check)
            if (
                args.merged_only and "closed_at" in agent_json_path.read_text()
                if agent_json_path.exists()
                else False
            ):
                should_remove = True

            if should_remove:
                logger.debug(f"Adding {path.name} to removal list")
                to_remove.append(wt)
            else:
                logger.debug(f"Keeping {path.name}")

        if not to_remove:
            print("No worktrees to cleanup")
            return

        for wt in to_remove:
            path = Path(wt["path"])
            print(f"Would remove: {path}")

            if not args.dry_run:
                if args.yes or input(f"Remove {path}? [y/N] ").lower() == "y":
                    try:
                        branch_name = git.remove_worktree_and_branch(path, force=args.force)

                        # Deallocate port if enabled
                        project_config = ProjectConfig(repo_path)
                        if project_config.is_feature_enabled("port_allocation"):
                            port_registry = PortRegistry()
                            project_name = project_config.get_project_name()
                            port_registry.deallocate(project_name, path)

                        if branch_name:
                            print(f"Removed: {path} and branch '{branch_name}'")
                        else:
                            print(f"Removed: {path}")
                    except subprocess.CalledProcessError as e:
                        # Capture stderr to get the actual git error message
                        try:
                            result = subprocess.run(
                                [
                                    "git",
                                    "-C",
                                    str(repo_path),
                                    "worktree",
                                    "remove",
                                    str(path),
                                ],
                                capture_output=True,
                                text=True,
                                check=False,
                            )
                            error_msg = result.stderr.strip() if result.stderr else str(e)
                        except Exception:
                            error_msg = str(e)

                        if ("is dirty" in error_msg or "--force" in error_msg) and not args.force:
                            print(
                                f"❌ Failed to remove {path.name}: Worktree is "
                                f"dirty (has uncommitted changes)"
                            )
                            if self._is_interactive():
                                force_choice = (
                                    input(
                                        f"Force removal of dirty worktree " f"{path.name}? [y/N]: "
                                    )
                                    .strip()
                                    .lower()
                                )
                                if force_choice in ["y", "yes"]:
                                    try:
                                        branch_name = git.remove_worktree_and_branch(
                                            path, force=True
                                        )

                                        # Deallocate port if enabled
                                        project_config = ProjectConfig(repo_path)
                                        if project_config.is_feature_enabled("port_allocation"):
                                            port_registry = PortRegistry()
                                            project_name = project_config.get_project_name()
                                            port_registry.deallocate(project_name, path)

                                        if branch_name:
                                            print(
                                                f"✅ Force removed {path.name} "
                                                f"and branch '{branch_name}'"
                                            )
                                        else:
                                            print(f"✅ Force removed {path.name}")
                                    except Exception as force_e:
                                        print(f"❌ Failed to force remove {path.name}: {force_e}")
                                else:
                                    print(f"⏭️  Skipped {path.name}")
                            else:
                                print("💡 Use --force to remove dirty worktrees")
                        else:
                            print(f"❌ Failed to remove {path.name}: {error_msg}")
                    except Exception as e:
                        print(f"❌ Failed to remove {path.name}: {e}")

    def _merge_claude_config_files(self, cproj_claude_dir, target_claude_dir):
        """Intelligently merge cproj's template files with existing
        project files"""

        # Files that need special JSON merging
        json_merge_files = {
            "settings.local.json": self._merge_settings_json,
            "mcp_config.json": self._merge_mcp_config_json,
        }

        # Process each file in cproj's .claude directory
        for cproj_file in cproj_claude_dir.rglob("*"):
            if cproj_file.is_file():
                # Get relative path from .claude directory
                rel_path = cproj_file.relative_to(cproj_claude_dir)
                target_file = target_claude_dir / rel_path

                # Ensure target directory exists
                target_file.parent.mkdir(parents=True, exist_ok=True)

                # Check if this file needs special merging
                if rel_path.name in json_merge_files:
                    if target_file.exists():
                        # Merge the files
                        try:
                            merge_func = json_merge_files[rel_path.name]
                            merge_func(cproj_file, target_file)
                            print(f"🔀 Merged {rel_path}")
                        except Exception as e:
                            print(f"⚠️  Could not merge {rel_path}, copying " f"cproj version: {e}")
                            shutil.copy2(cproj_file, target_file)
                    else:
                        # Copy new file
                        shutil.copy2(cproj_file, target_file)
                        print(f"📋 Added {rel_path}")
                # For non-JSON files, copy if not exists, otherwise skip
                # to preserve project customizations
                elif not target_file.exists():
                    shutil.copy2(cproj_file, target_file)
                    # Make shell scripts executable
                    if rel_path.suffix == ".sh":
                        target_file.chmod(target_file.stat().st_mode | 0o111)
                    print(f"📋 Added {rel_path}")
                else:
                    print(f"⏭️  Kept existing {rel_path}")

    def _merge_settings_json(self, cproj_file, target_file):
        """Merge settings.local.json files, combining permissions"""
        with cproj_file.open() as f:
            cproj_settings = json.load(f)

        with target_file.open() as f:
            target_settings = json.load(f)

        # Merge permissions
        if "permissions" in cproj_settings and "permissions" in target_settings:
            # Combine allow lists (remove duplicates)
            combined_allow = list(
                set(
                    cproj_settings["permissions"].get("allow", [])
                    + target_settings["permissions"].get("allow", [])
                )
            )

            # Keep existing deny and ask lists, add cproj's if they don't exist
            merged_permissions = {
                "allow": sorted(combined_allow),
                "deny": target_settings["permissions"].get(
                    "deny", cproj_settings["permissions"].get("deny", [])
                ),
                "ask": target_settings["permissions"].get(
                    "ask", cproj_settings["permissions"].get("ask", [])
                ),
            }

            target_settings["permissions"] = merged_permissions
        elif "permissions" in cproj_settings:
            target_settings["permissions"] = cproj_settings["permissions"]

        # Write merged settings
        with target_file.open("w") as f:
            json.dump(target_settings, f, indent=2)

    def _merge_mcp_config_json(self, cproj_file, target_file):
        """Merge mcp_config.json files, combining MCP servers"""
        with cproj_file.open() as f:
            cproj_config = json.load(f)

        with target_file.open() as f:
            target_config = json.load(f)

        # Merge mcpServers
        if "mcpServers" in cproj_config:
            if "mcpServers" not in target_config:
                target_config["mcpServers"] = {}

            # Add cproj's MCP servers, preserving existing ones
            for server_name, server_config in cproj_config["mcpServers"].items():
                if server_name not in target_config["mcpServers"]:
                    target_config["mcpServers"][server_name] = server_config

        # Write merged config
        with target_file.open("w") as f:
            json.dump(target_config, f, indent=2)

    def cmd_setup_claude(self, args):
        """Setup Claude workspace in current directory"""
        current_dir = Path.cwd()

        # Check if we're in a git repository
        try:
            git_root = self._find_git_root(current_dir)
        except CprojError:
            raise CprojError("Not in a git repository")

        # Get cproj's .claude directory (template files)
        cproj_dir = Path(__file__).parent
        cproj_claude_dir = cproj_dir / ".claude"
        if not cproj_claude_dir.exists():
            raise CprojError(f"cproj template .claude directory not found: " f"{cproj_claude_dir}")

        # Check if .claude directory exists in current location
        claude_dir = current_dir / ".claude"

        if claude_dir.exists():
            print(f"🔍 Found existing .claude directory in {current_dir}")
            print("🔀 Merging cproj's template files with existing " "configuration...")
            self._merge_claude_config_files(cproj_claude_dir, claude_dir)
        else:
            print(f"📂 Creating new .claude directory in {current_dir}")

            # Load project configuration to
            # check if we should copy from main repo
            try:
                config = self._load_config()
                main_repo_path = Path(config.get("repo_path", ""))

                # If this is a worktree and main repo has .claude,
                # copy from there first
                if (
                    str(git_root) != str(main_repo_path)
                    and main_repo_path.exists()
                    and (main_repo_path / ".claude").exists()
                ):
                    print(f"📂 Copying project .claude from {main_repo_path}")
                    shutil.copytree(main_repo_path / ".claude", claude_dir)
                    print("🔀 Merging cproj's template files...")
                    self._merge_claude_config_files(cproj_claude_dir, claude_dir)
                else:
                    # Copy cproj template directly
                    shutil.copytree(cproj_claude_dir, claude_dir)
                    print("📋 Copied cproj template files")

            except CprojError:
                # No cproj config, just copy template
                shutil.copytree(cproj_claude_dir, claude_dir)
                print("📋 Copied cproj template files")

        print(f"✅ Claude workspace setup complete in {current_dir}")
        print("💡 cproj commands and agents are now available")

    def cmd_open(self, args):
        """Open workspace"""
        if args.path:
            # Check if user might be trying to
            # use 'open review' instead of 'review open'
            if args.path == "review":
                raise CprojError(
                    "Did you mean 'cproj review open'? The correct syntax " "is: cproj review open"
                )
            worktree_path = Path(args.path)
            if not worktree_path.exists():
                raise CprojError(f"Path does not exist: {args.path}")
        else:
            worktree_path = Path.cwd()

        agent_json_path = worktree_path / ".cproj" / ".agent.json"
        if not agent_json_path.exists():
            # Check if we're in a subdirectory of a worktree
            parent = worktree_path.parent
            while parent != parent.parent:
                if (parent / ".cproj" / ".agent.json").exists():
                    raise CprojError(
                        f"Found .agent.json in parent directory: "
                        f"{parent}/.cproj\nRun command from worktree root or "
                        f"specify path with 'cproj open {parent}'"
                    )
                parent = parent.parent
            raise CprojError(
                "Not in a cproj worktree (no .agent.json found in .cproj " "directory)"
            )

        agent_json = AgentJson(worktree_path)
        branch = agent_json.data["workspace"]["branch"]

        terminal_app = args.terminal or self.config.get("terminal", "Terminal")
        editor = args.editor or self.config.get("editor", "code")

        # Open terminal
        if terminal_app != "none":
            # Strip branch prefix (everything before /) for cleaner window title
            import re

            branch_display = re.sub(r"^\S+/", "", branch)
            TerminalAutomation.open_terminal(worktree_path, branch_display, terminal_app)

        # Open editor
        if editor:
            TerminalAutomation.open_editor(worktree_path, editor)

        # Open browser links
        links = agent_json.data["links"]
        if links["linear"]:
            subprocess.run(["open", links["linear"]], check=False)
        if links["pr"]:
            subprocess.run(["open", links["pr"]], check=False)

    def cmd_sync_env(self, args):
        """Sync .env files from worktree to main repo"""
        # Validate we're in a worktree
        current_path = Path.cwd()
        agent_json_path = current_path / ".cproj" / ".agent.json"

        if not agent_json_path.exists():
            # Check if we're in a subdirectory of a worktree
            parent = current_path.parent
            while parent != parent.parent:
                if (parent / ".cproj" / ".agent.json").exists():
                    current_path = parent
                    agent_json_path = parent / ".cproj" / ".agent.json"
                    break
                parent = parent.parent
            else:
                raise CprojError(
                    "Not in a cproj worktree. Run this command from a worktree directory."
                )

        # Load agent.json to get main repo path
        try:
            with open(agent_json_path, "r") as f:
                agent_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            raise CprojError(f"Failed to read .agent.json: {e}")

        main_repo_path = Path(agent_data["project"]["repo_path"])
        if not main_repo_path.exists():
            raise CprojError(f"Main repo path not found: {main_repo_path}")

        # Set up environment and sync
        env_setup = EnvironmentSetup(current_path)
        env_setup.sync_env_files(
            main_repo_path=main_repo_path,
            specific_file=args.file,
            dry_run=args.dry_run,
            backup=args.backup,
        )

        # Run post-sync scripts if configured (e.g., update-env-ports.sh)
        if not args.dry_run:
            self._run_post_sync_hooks(current_path, main_repo_path)

    def _run_post_sync_hooks(self, worktree_path: Path, repo_path: Path):
        """Run project-specific post-sync hooks"""
        # Load project config to check for post-sync actions
        project_config = ProjectConfig(repo_path)
        post_sync_actions = project_config._config.get("post_sync_actions", [])

        if not post_sync_actions:
            return

        print("\n🔧 Running post-sync hooks...")
        for action in post_sync_actions:
            action_type = action.get("type")

            if action_type == "run_command":
                command = action.get("command")
                description = action.get("description", "Running post-sync command")

                if not command:
                    continue

                print(f"  {description}")
                try:
                    result = subprocess.run(
                        command,
                        cwd=worktree_path,
                        shell=True,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    if result.stdout:
                        print(f"  {result.stdout.strip()}")
                    print("  ✅ Completed")
                except subprocess.CalledProcessError as e:
                    error_msg = e.stderr.strip() if e.stderr else str(e)
                    print(f"  ⚠️  Failed: {error_msg}")
                    logger.warning(f"Post-sync hook failed: {error_msg}")

    def cmd_config(self, args):
        """Configuration management"""
        if not args.key:
            # Show all config
            if args.json:
                print(json.dumps(self.config._config, indent=2))
            else:
                for key, value in self.config._config.items():
                    print(f"{key}: {value}")
        elif not args.value:
            # Show specific key
            value = self.config.get(args.key)
            if value is not None:
                print(value)
        else:
            # Set key-value
            self.config.set(args.key, args.value)
            print(f"Set {args.key} = {args.value}")

    def cmd_ports_list(self, args):
        """List port allocations"""
        port_registry = PortRegistry()

        # Determine project name
        project_name = args.project
        if not project_name:
            # Try to get from current directory
            repo_path = self._find_git_root(Path.cwd())
            if repo_path:
                project_config = ProjectConfig(repo_path)
                project_name = project_config.get_project_name()

        # Get allocations
        allocations = port_registry.list_allocations(project_name)

        if not allocations:
            if project_name:
                print(f"No port allocations found for project: {project_name}")
            else:
                print("No port allocations found")
            return

        # Display allocations
        if project_name:
            print(f"Port allocations for {project_name}:")
        else:
            print("All port allocations:")

        print()

        if project_name:
            # Show single project allocations
            for worktree_path, offset in sorted(allocations.items(), key=lambda x: x[1]):
                # Check if worktree still exists
                exists = "✓" if Path(worktree_path).exists() else "✗"
                print(f"  {exists} Offset {offset:2d}: {worktree_path}")
        else:
            # Show all projects
            for proj_name, proj_allocations in sorted(allocations.items()):
                print(f"  {proj_name}:")
                for worktree_path, offset in sorted(proj_allocations.items(), key=lambda x: x[1]):
                    exists = "✓" if Path(worktree_path).exists() else "✗"
                    print(f"    {exists} Offset {offset:2d}: {worktree_path}")
                print()

    def cmd_ports_allocate(self, args):
        """Allocate a port offset for a worktree"""
        # Determine worktree path
        worktree_path = args.path if args.path else Path.cwd()
        worktree_path = worktree_path.absolute()

        # Find git root
        repo_path = self._find_git_root(worktree_path)
        if not repo_path:
            raise CprojError(f"Not in a git repository: {worktree_path}")

        # Check if we're in a worktree - if so, get main repo path from .agent.json
        agent_json_path = repo_path / ".cproj" / ".agent.json"
        if agent_json_path.exists():
            agent_json = AgentJson(repo_path)
            repo_path = Path(agent_json.data["project"]["repo_path"])

        # Get project config (from main repo if we're in a worktree)
        project_config = ProjectConfig(repo_path)
        project_name = project_config.get_project_name()

        if not project_config.is_feature_enabled("port_allocation"):
            print(f"⚠️  Port allocation is not enabled for project '{project_name}'")
            print()
            response = input("Enable port allocation for this project? [Y/n]: ").strip().lower()

            if response in ("", "y", "yes"):
                # Enable the feature
                project_config.enable_feature("port_allocation", True)

                # Set default port config if not present
                if not project_config.get_port_config():
                    print()
                    print("📊 Port Configuration")
                    base_port_input = input("Base port [3000]: ").strip()
                    base_port = int(base_port_input) if base_port_input else 3000

                    max_slots_input = input("Maximum concurrent worktrees [99]: ").strip()
                    max_slots = int(max_slots_input) if max_slots_input else 99

                    # Update config with port settings
                    project_config._config["port_config"] = {
                        "base_port": base_port,
                        "max_slots": max_slots,
                    }

                project_config.save()
                print()
                print("✅ Port allocation enabled!")
                print(f"   Configuration saved to: {project_config.config_path}")
                print()
            else:
                print("Port allocation not enabled. Exiting.")
                return

        # Get port configuration
        max_slots = project_config.get_max_slots()
        base_port = project_config.get_base_port()

        # Initialize port registry
        port_registry = PortRegistry()

        # Check if already allocated
        existing_offset = port_registry.get_offset(project_name, worktree_path)
        if existing_offset is not None:
            print(f"⚠️  Worktree already has port offset {existing_offset}")
            print(f"   Path: {worktree_path}")
            print(f"   Base port: {base_port}")
            return

        # Determine offset to allocate
        if args.offset is not None:
            # Use specific offset if provided
            offset = args.offset
            if offset < 0 or offset > max_slots:
                raise CprojError(f"Offset must be between 0 and {max_slots}")

            # Check if offset is already allocated
            allocations = port_registry.list_allocations(project_name)
            if allocations and offset in allocations.values():
                # Find which worktree has this offset
                for path, off in allocations.items():
                    if off == offset:
                        raise CprojError(f"Offset {offset} is already allocated to: {path}")
        else:
            # Auto-assign next available
            offset = port_registry.get_next_available_offset(project_name, max_slots)
            if offset is None:
                raise CprojError(
                    f"All port slots (0-{max_slots}) are allocated! "
                    "Run 'cproj cleanup' to free up unused worktrees"
                )

        # Allocate the port
        if not port_registry.allocate(project_name, worktree_path, offset):
            raise CprojError(f"Failed to allocate port offset {offset}")

        # Write ports.env file
        env_setup = EnvironmentSetup(worktree_path)
        env_setup.write_ports_env(offset, base_port)

        print(f"✅ Port offset {offset} allocated successfully")
        print(f"   Path: {worktree_path}")
        print(f"   Base port: {base_port}")

    def cmd_ports_free(self, args):
        """Free a port offset"""
        # Determine project name
        project_name = args.project
        if not project_name:
            # Try to get from current directory
            repo_path = self._find_git_root(Path.cwd())
            if repo_path:
                project_config = ProjectConfig(repo_path)
                project_name = project_config.get_project_name()
            else:
                raise CprojError(
                    "Could not determine project. Use --project or run from a git repository"
                )

        # Initialize port registry
        port_registry = PortRegistry()

        # Find worktree with this offset
        allocations = port_registry.list_allocations(project_name)
        if not allocations:
            raise CprojError(f"No port allocations found for project: {project_name}")

        worktree_path = None
        for path, offset in allocations.items():
            if offset == args.offset:
                worktree_path = Path(path)
                break

        if not worktree_path:
            raise CprojError(
                f"No allocation found for offset {args.offset} in project {project_name}"
            )

        # Deallocate
        if port_registry.deallocate(project_name, worktree_path):
            print(f"✅ Port offset {args.offset} freed successfully")
            print(f"   Was allocated to: {worktree_path}")

            # Remove ports.env file if it exists
            ports_env_path = worktree_path / ".cproj" / "ports.env"
            if ports_env_path.exists():
                ports_env_path.unlink()
                print("   Removed ports.env file")
        else:
            raise CprojError(f"Failed to free port offset {args.offset}")


def main():
    """Entry point for CLI"""
    cli = CprojCLI()
    cli.run()


if __name__ == "__main__":
    main()
