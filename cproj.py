#!/usr/bin/env python3
"""
cproj - Multi-project CLI with git worktree + uv
A production-ready CLI tool for managing parallel project work using Git worktrees
"""

import argparse
import contextlib
import getpass
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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
                subprocess.run(["op", "account", "list"], check=True,
                            capture_output=True, timeout=5)
                return True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                return False

    @staticmethod
    def get_secret(reference: str) -> Optional[str]:
        """Get secret from 1Password using secret reference"""
        if not OnePasswordIntegration.is_available():
            return None

        try:
            result = subprocess.run(["op", "read", reference], capture_output=True, text=True, check=True, timeout=10)
            return result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None

    @staticmethod
    def _sanitize_op_argument(arg: str) -> str:
        """Sanitize arguments for 1Password CLI to prevent injection"""
        if not isinstance(arg, str):
            arg = str(arg)

        # Special handling for 1Password references (op://...)
        if arg.startswith("op://"):
            # For valid 1Password references, we can be more permissive
            # Remove only dangerous shell metacharacters while preserving the reference format
            dangerous_chars = [
                ";",
                "&",
                "|",
                "`",
                "$",
                "'",
                '"',
                "\\",
                "\n",
                "\r",
                "\t",
                "<",
                ">",
                "(",
                ")",
            ]
            result = arg
            for char in dangerous_chars:
                result = result.replace(char, "")
            return result

        # Handle path traversal patterns specifically for non-op:// arguments
        result = arg
        # Remove path traversal sequences
        result = result.replace("../", "").replace("..\\", "")
        # Remove any remaining double-dots that are part of path traversal
        # but preserve legitimate ellipsis (...) by checking context
        if "../" in arg or "..\\" in arg:
            result = result.replace("..", "")

        # Remove shell metacharacters and only allow safe characters for general arguments
        result = "".join(c for c in result if c.isalnum() or c in "-_. ")
        return result

    @staticmethod
    def store_secret(title: str, value: str, vault: Optional[str] = None) -> Optional[str]:
        """Store secret in 1Password and return reference"""
        if not OnePasswordIntegration.is_available():
            return None

        # Validate and sanitize inputs
        if not title or not value:
            return None

        safe_title = OnePasswordIntegration._sanitize_op_argument(title)
        safe_vault = OnePasswordIntegration._sanitize_op_argument(vault) if vault else None

        try:
            cmd = ["op", "item", "create", "--category=password", f"--title={safe_title}"]
            if safe_vault:
                cmd.append(f"--vault={safe_vault}")
            cmd.append(f"password={value}")  # Password value is passed as argument

            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            # Extract reference from output (simplified)
            return f"op://{safe_vault or 'Private'}/{safe_title}/password"
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
            reference = OnePasswordIntegration.store_secret(f"cproj-{secret_name}", secret_value, vault)
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
            self._run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{base_branch}"])
        except subprocess.CalledProcessError:
            # Create from origin if it doesn't exist
            try:
                self._run_git(["branch", base_branch, f"origin/{base_branch}"])
            except subprocess.CalledProcessError as e:
                msg = f"Base branch '{base_branch}' not found locally or on origin"
                raise CprojError(msg) from e

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
            result = self._run_git(["worktree", "list", "--porcelain"], capture_output=True, text=True)
            current_branch = None
            for line in result.stdout.strip().split("\n"):
                if line.startswith("branch "):
                    current_branch = line.split("refs/heads/", 1)[1] if "refs/heads/" in line else None
                    if current_branch == branch:
                        return True
            return False
        except subprocess.CalledProcessError:
            return False

    def create_worktree(self, worktree_path: Path, branch: str, base_branch: str, interactive: bool = True) -> Path:
        """Create a new worktree"""
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if branch already exists
        if self.branch_exists(branch):
            # Check if it's already checked out somewhere
            if self.is_branch_checked_out(branch):
                if interactive:
                    print(f"⚠️  Branch '{branch}' is already checked out in another worktree.")
                    print("\nOptions:")
                    print("  1. Create worktree with a different branch name")
                    print("  2. Switch to existing worktree (if you know where it is)")
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
                                f"Branch '{branch}' is checked out elsewhere. Use 'git worktree list' to find it."
                            )
                        elif choice == "3":
                            # Force create new worktree, detaching the branch from current location
                            try:
                                self._run_git(["worktree", "add", "--force", str(worktree_path), branch])
                                return worktree_path
                            except subprocess.CalledProcessError as e:
                                raise CprojError(f"Failed to force create worktree: {e}") from e
                        elif choice == "4":
                            raise CprojError("Worktree creation cancelled by user")
                        else:
                            print("❌ Please enter 1, 2, 3, or 4")
                            continue
                else:
                    raise CprojError(
                        f"Branch '{branch}' is already checked out. "
                        f"Use --force to override or choose a different branch name."
                    )

            # Branch exists but not checked out, use it
            try:
                self._run_git(["worktree", "add", str(worktree_path), branch])
            except subprocess.CalledProcessError as e:
                raise CprojError(f"Failed to create worktree with existing branch '{branch}': {e}") from e
        else:
            # Branch doesn't exist, create it
            try:
                self._run_git(["worktree", "add", "-b", branch, str(worktree_path), base_branch])
            except subprocess.CalledProcessError as e:
                raise CprojError(f"Failed to create new branch '{branch}': {e}") from e

        return worktree_path

    def remove_worktree(self, worktree_path: Path, force: bool = False):
        """Remove a worktree"""
        cmd = ["worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(worktree_path))
        try:
            self._run_git(cmd, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            error_msg = str(e.stderr) if e.stderr else str(e)
            if "is dirty" in error_msg or "contains modified" in error_msg:
                raise CprojError("Worktree is dirty. Use force=True to remove anyway") from e
            raise CprojError(f"Failed to remove worktree: {error_msg}") from e

    def list_worktrees(self) -> List[Dict]:
        """List all worktrees"""
        result = self._run_git(["worktree", "list", "--porcelain"], capture_output=True, text=True)
        worktrees = []
        current_tree = {}

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
                current_tree["bare"] = True
            elif line == "detached":
                current_tree["detached"] = True

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
            result = self._run_git(["status", "--porcelain"], cwd=worktree_path, capture_output=True, text=True)
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
            result = self._run_git(["status", "--porcelain"], cwd=worktree_path, capture_output=True, text=True)
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

    def _run_git(self, args: List[str], cwd: Optional[Path] = None, **kwargs) -> subprocess.CompletedProcess:
        """Run git command"""
        cmd = ["git", "-C", str(cwd or self.repo_path), *args]
        return subprocess.run(cmd, check=True, **kwargs)


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
        except (OSError, json.JSONDecodeError) as e:
            logger.debug(f"Error loading agent.json from {self.path}: {e}")
            # Return default data if file is corrupted
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

    def set(self, key: str, value: Any):
        """Set a value in the data"""
        self.data[key] = value

    def get(self, key: str, default=None):
        """Get a value from the data"""
        return self.data.get(key, default)

    def close_workspace(self):
        self.data["workspace"]["closed_at"] = datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _get_version() -> str:
        return "1.0.0"


class EnvironmentSetup:
    """Environment setup for different languages"""

    def __init__(self, worktree_path: Path):
        self.worktree_path = worktree_path

    # Detection methods
    def _has_pyproject_toml(self) -> bool:
        """Check if pyproject.toml exists"""
        return (self.worktree_path / "pyproject.toml").exists()

    def _has_requirements_txt(self) -> bool:
        """Check if requirements.txt exists"""
        return (self.worktree_path / "requirements.txt").exists()

    def _has_setup_py(self) -> bool:
        """Check if setup.py exists"""
        return (self.worktree_path / "setup.py").exists()

    def _has_package_json(self) -> bool:
        """Check if package.json exists"""
        return (self.worktree_path / "package.json").exists()

    def _has_yarn_lock(self) -> bool:
        """Check if yarn.lock exists"""
        return (self.worktree_path / "yarn.lock").exists()

    def _has_package_lock(self) -> bool:
        """Check if package-lock.json exists"""
        return (self.worktree_path / "package-lock.json").exists()

    def _has_maven(self) -> bool:
        """Check if Maven pom.xml exists"""
        return (self.worktree_path / "pom.xml").exists()

    def _has_gradle(self) -> bool:
        """Check if Gradle build files exist"""
        return (self.worktree_path / "build.gradle").exists() or (self.worktree_path / "build.gradle.kts").exists()

    def _has_uv(self) -> bool:
        """Check if uv is available"""
        try:
            subprocess.run(["uv", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def detect_environments(self) -> Dict[str, Any]:
        """Detect available environments"""
        python_files = self._has_pyproject_toml() or self._has_requirements_txt() or self._has_setup_py()
        node_files = self._has_package_json()
        java_files = self._has_maven() or self._has_gradle()

        return {
            "python": {
                "active": python_files,
                "pyproject": self._has_pyproject_toml(),
                "requirements": self._has_requirements_txt(),
                "setup_py": self._has_setup_py(),
                "uv_available": self._has_uv(),
            },
            "node": {
                "active": node_files,
                "package_json": self._has_package_json(),
                "yarn_lock": self._has_yarn_lock(),
                "package_lock": self._has_package_lock(),
            },
            "java": {
                "active": java_files,
                "maven": self._has_maven(),
                "gradle": self._has_gradle(),
            },
        }

    def _find_python_files(self):
        """Find Python project files in the worktree"""
        # Check for project files in root and common subdirectories
        pyproject_paths = list(self.worktree_path.glob("**/pyproject.toml"))
        requirements_paths = list(self.worktree_path.glob("**/requirements.txt"))

        # Filter out common non-project directories
        exclude_dirs = {".venv", "venv", "node_modules", ".git", "__pycache__", "dist", "build"}
        pyproject_paths = [p for p in pyproject_paths if not any(ex in p.parts for ex in exclude_dirs)]
        requirements_paths = [p for p in requirements_paths if not any(ex in p.parts for ex in exclude_dirs)]

        return pyproject_paths, requirements_paths

    def setup_python(
        self,
        auto_install: bool = False,
        shared_venv: bool = False,
        repo_path: Optional[Path] = None,
    ) -> Dict:
        """Setup Python environment with uv or venv"""
        env_data = {"manager": "none", "active": False, "pyproject": False, "requirements": False}

        # Find and validate Python project files
        pyproject_paths, requirements_paths = self._find_python_files()
        pyproject_exists = len(pyproject_paths) > 0
        requirements_exists = len(requirements_paths) > 0
        env_data["pyproject"] = pyproject_exists
        env_data["requirements"] = requirements_exists

        if not (pyproject_exists or requirements_exists):
            return env_data

        # Try shared venv first if requested
        if shared_venv and repo_path:
            shared_result = self._setup_shared_venv(repo_path, env_data)
            if shared_result:
                return shared_result

        # Try uv next
        uv_result = self._setup_uv_environment(env_data, auto_install, pyproject_exists, requirements_exists)
        if uv_result:
            return uv_result

        # Fallback to venv
        return self._setup_venv_environment(env_data, auto_install, requirements_exists)

    def _setup_shared_venv(self, repo_path, env_data):
        """Setup shared virtual environment symlink"""
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
            return self._create_venv_symlink(main_venv, repo_path, env_data)
        else:
            print("No .venv found in main repo to share")
            return None

    def _create_venv_symlink(self, main_venv, repo_path, env_data):
        """Create symlink to main repo's venv"""
        # Determine where to create the symlink in worktree
        if main_venv.parent != repo_path:
            subdir = main_venv.parent.name
            worktree_venv = self.worktree_path / subdir / ".venv"
            worktree_venv.parent.mkdir(parents=True, exist_ok=True)
        else:
            worktree_venv = self.worktree_path / ".venv"

        try:
            if worktree_venv.exists():
                if worktree_venv.is_symlink():
                    worktree_venv.unlink()
                else:
                    shutil.rmtree(worktree_venv)
            worktree_venv.symlink_to(main_venv, target_is_directory=True)
            env_data["manager"] = "shared"
            env_data["active"] = True
            print(f"Created shared venv link: {worktree_venv} -> {main_venv}")
            return env_data
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"Warning: Failed to create shared venv: {e}")
            return None

    def _setup_uv_environment(self, env_data, auto_install, pyproject_exists, requirements_exists):
        """Setup Python environment using uv"""
        if not shutil.which("uv"):
            return None
        try:
            subprocess.run(["uv", "venv"], cwd=self.worktree_path, check=True, capture_output=True)
            env_data["manager"] = "uv"
            env_data["active"] = True

            if auto_install and (pyproject_exists or requirements_exists):
                subprocess.run(
                    ["uv", "pip", "sync"]
                    if pyproject_exists
                    else ["uv", "pip", "install", "-r", "requirements.txt"],
                    cwd=self.worktree_path,
                    check=True,
                    capture_output=True,
                )
            return env_data
        except subprocess.CalledProcessError:
            return None

    def _setup_venv_environment(self, env_data, auto_install, requirements_exists):
        """Setup Python environment using venv"""
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
                self._install_requirements_with_venv()
        except subprocess.CalledProcessError:
            pass
        return env_data

    def _install_requirements_with_venv(self):
        """Install requirements using venv pip"""
        venv_path = self.worktree_path / ".venv"
        if not venv_path.exists() or not venv_path.is_dir():
            raise CprojError(f"Virtual environment not found at {venv_path}")

        if platform.system() == "Windows":
            pip_cmd = venv_path / "Scripts" / "pip.exe"
        else:
            pip_cmd = venv_path / "bin" / "pip"

        # Validate pip executable exists and is within expected path
        if not pip_cmd.exists():
            raise CprojError(f"pip executable not found at {pip_cmd}")
        if not str(pip_cmd).startswith(str(self.worktree_path)):
            raise CprojError(f"pip path {pip_cmd} is outside worktree {self.worktree_path}")

        subprocess.run(
            [str(pip_cmd), "install", "-r", "requirements.txt"],
            cwd=self.worktree_path,
            check=True,
            capture_output=True,
        )

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

        except (subprocess.CalledProcessError, OSError) as e:
            logger.debug(f"Error setting up Node environment: {e}")
            pass

        return env_data

    def setup_java(self, auto_install: bool = False, auto_build: bool = False) -> Dict:
        """Setup Java environment"""
        env_data = {"build": "none"}

        if (self.worktree_path / "pom.xml").exists():
            env_data["build"] = "maven"
            if auto_build:
                with contextlib.suppress(subprocess.CalledProcessError, FileNotFoundError):
                    subprocess.run(
                        ["mvn", "compile", "-DskipTests"],
                        cwd=self.worktree_path,
                        check=True,
                        capture_output=True,
                    )

        elif any((self.worktree_path / f).exists() for f in ["build.gradle", "build.gradle.kts"]):
            env_data["build"] = "gradle"
            if auto_build:
                with contextlib.suppress(subprocess.CalledProcessError, FileNotFoundError):
                    subprocess.run(
                        ["./gradlew", "compileJava"],
                        cwd=self.worktree_path,
                        check=True,
                        capture_output=True,
                    )

        return env_data

    def copy_env_files(self, repo_path: Path):
        """Copy .env files from main repo to worktree, searching subdirectories"""

        # Find all .env* files in the repo (including subdirectories)
        env_patterns = ["**/.env", "**/.env.*"]
        found_files = []

        for pattern in env_patterns:
            found_files.extend(repo_path.glob(pattern))

        if not found_files:
            print("No .env files found in main repo")
            return

        # Copy files, preserving directory structure
        for source_file in found_files:
            # Skip hidden directories and common build/cache dirs
            allowed_env_files = [
                ".env",
                ".env.local",
                ".env.development",
                ".env.test",
                ".env.production",
                ".env.example",
            ]
            if any(
                part.startswith(".") and part not in allowed_env_files
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


class TerminalAutomation:
    """Terminal and editor automation"""

    @staticmethod
    def _is_test_environment() -> bool:
        """Check if we're running in a test environment"""
        return (
            "pytest" in sys.modules
            or "PYTEST_CURRENT_TEST" in os.environ
            or os.environ.get("CI") == "true"
            or "unittest" in sys.modules
        )

    @staticmethod
    def open_terminal(path: Path, title: str, terminal_app: str = "Terminal"):
        """Open terminal at path with title"""
        if TerminalAutomation._is_test_environment():
            print(f"[TEST MODE] Would open terminal: {terminal_app} at {path} with title '{title}'")
            return

        if platform.system() != "Darwin":
            print(f"Terminal automation not supported on {platform.system()}")
            return

        # Check if setup-claude.sh exists in .cproj directory and build the command
        setup_script = path / ".cproj" / "setup-claude.sh"
        base_command = f"cd '{path}' && source .cproj/setup-claude.sh" if setup_script.exists() else f"cd '{path}'"

        if terminal_app.lower() == "iterm":
            script = f'''
            tell application "iTerm"
                create window with default profile
                tell current session of current window
                    write text "{base_command}"
                    set name to "{title}"
                end tell
            end tell
            '''
        else:  # Terminal
            script = f'''
            tell application "Terminal"
                do script "{base_command}"
                set custom title of front window to "{title}"
            end tell
            '''

        try:
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to open terminal: {e}")

    @staticmethod
    def open_editor(path: Path, editor: str):
        """Open editor at path"""
        if TerminalAutomation._is_test_environment():
            print(f"[TEST MODE] Would open editor: {editor} at {path}")
            return

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
            token_ref = input("1Password GitHub token reference (or press Enter to login interactively): ").strip()

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
    def create_pr(title: str, body: str, draft: bool = True, assignees: Optional[List[str]] = None) -> Optional[str]:
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


class CprojCLI:
    """Main CLI application"""

    def __init__(self):
        self.config = Config()

    def _prompt_project_identity(self, config: Dict) -> None:
        """Prompt for project identity configuration"""
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
            clone_to = input(f"Clone to directory [{Path.home() / 'dev' / config['project_name']}]: ").strip()
            repo_path = Path(clone_to) if clone_to else (Path.home() / "dev" / config['project_name'])
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

    def _prompt_workspace_policy(self, config: Dict) -> None:
        """Prompt for workspace policy configuration"""
        print("🏗️  Workspace Policy")
        print("-" * 50)

        default_temp = str(Path.home() / ".cache" / "cproj-workspaces")
        temp_root = input(f"Temp root for worktrees [{default_temp}]: ").strip()
        config["temp_root"] = temp_root or default_temp

        branch_scheme = input("Branch naming scheme [feature/{ticket}-{slug}]: ").strip()
        config["branch_scheme"] = branch_scheme or "feature/{ticket}-{slug}"

        cleanup_days = input("Auto-cleanup age threshold (days) [14]: ").strip()
        try:
            config["cleanup_days"] = int(cleanup_days) if cleanup_days else 14
        except ValueError:
            config["cleanup_days"] = 14

        print()

    def _prompt_environment_setup(self, config: Dict) -> None:
        """Prompt for environment setup configuration"""
        print("🐍 Environment Setup")
        print("-" * 50)

        use_uv = input("Prefer uv for Python? [Y/n]: ").strip().lower()
        config["python_prefer_uv"] = use_uv not in ["n", "no"]

        auto_install_python = input("Auto-install Python dependencies? [Y/n]: ").strip().lower()
        config["python_auto_install"] = auto_install_python not in ["n", "no"]

        use_nvm = input("Use nvm for Node? [Y/n]: ").strip().lower()
        config["node_use_nvm"] = use_nvm not in ["n", "no"]

        auto_install_node = input("Auto-install Node dependencies? [Y/n]: ").strip().lower()
        config["node_auto_install"] = auto_install_node not in ["n", "no"]

        auto_build_java = input("Auto-build Java projects? [y/N]: ").strip().lower()
        config["java_auto_build"] = auto_build_java in ["y", "yes"]

        print()

    def _prompt_tools_automation(self, config: Dict) -> None:
        """Prompt for tools and automation configuration"""
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

    def _prompt_integrations(self, config: Dict) -> None:
        """Prompt for integrations configuration"""
        print("🔗 Integrations")
        print("-" * 50)

        # Linear Integration (Enhanced)
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

            # Ask about API key setup
            setup_api_key = input("Setup Linear API key now? [y/N]: ").strip().lower()
            if setup_api_key in ["y", "yes"]:
                print("\n📝 Linear API Key Setup:")
                print("1. Go to https://linear.app/settings/api")
                print("2. Create a new Personal API Key")
                print("3. Copy the key (it starts with 'lin_api_')")
                print("4. Paste it here (it will be stored securely)")

                api_key = input("\nLinear API Key: ").strip()
                if api_key:
                    # Store API key securely
                    self._store_linear_api_key(api_key)
                    print("✅ API key stored securely in .env.linear")
                    print("💡 This file is automatically added to .gitignore")

        github_default_reviewers = input("Default GitHub reviewers (comma-separated, optional): ").strip()
        if github_default_reviewers:
            config["github_reviewers"] = [r.strip() for r in github_default_reviewers.split(",")]

        draft_prs = input("Create draft PRs by default? [y/N]: ").strip().lower()
        config["github_draft_default"] = draft_prs in ["y", "yes"]

        print()

    def _prompt_claude_integration(self, config: Dict) -> None:
        """Prompt for Claude IDE integration configuration"""
        print("🤖 Claude IDE Integration")
        print("-" * 50)

        claude_symlink = input("Auto-create CLAUDE.md/.cursorrules symlinks in worktrees? [Y/n]: ").strip().lower()
        config["claude_symlink_default"] = "no" if claude_symlink in ["n", "no"] else "yes"

        claude_nvm = input("Auto-create nvm setup scripts for Claude CLI in worktrees? [Y/n]: ").strip().lower()
        config["claude_nvm_default"] = "no" if claude_nvm in ["n", "no"] else "yes"

        claude_workspace = (
            input("Auto-setup Claude workspace with commands and agents in worktrees? [Y/n]: ").strip().lower()
        )
        config["claude_workspace_default"] = "no" if claude_workspace in ["n", "no"] else "yes"

        print()

    def _prompt_onepassword_integration(self, config: Dict) -> None:
        """Prompt for 1Password integration configuration"""
        if OnePasswordIntegration.is_available():
            print("🔐 1Password Integration")
            print("-" * 50)
            print("1Password CLI detected! You can store GitHub tokens and other secrets securely.")

            use_1password = input("Use 1Password for secrets? [Y/n]: ").strip().lower()
            config["use_1password"] = use_1password not in ["n", "no"]

            if config.get("use_1password"):
                vault = input("Default 1Password vault [Private]: ").strip()
                config["onepassword_vault"] = vault or "Private"

            print()

    def _show_config_summary(self, config: Dict) -> None:
        """Show configuration summary"""
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
            print(f"1Password: enabled (vault: {config.get('onepassword_vault')})")

        print()

    def _prompt_for_config(self) -> Dict:
        """Interactive configuration prompting"""
        print("🚀 Welcome to cproj! Let's set up your configuration.")
        print()

        config = {}

        # Call helper methods for each section
        self._prompt_project_identity(config)
        self._prompt_workspace_policy(config)
        self._prompt_environment_setup(config)
        self._prompt_tools_automation(config)
        self._prompt_integrations(config)
        self._prompt_claude_integration(config)
        self._prompt_onepassword_integration(config)

        # Summary and confirmation
        self._show_config_summary(config)

        confirm = input("Save this configuration? [Y/n]: ").strip().lower()
        if confirm in ["n", "no"]:
            print("Configuration cancelled.")
            sys.exit(1)

        return config

    def create_parser(self) -> argparse.ArgumentParser:
        """Create argument parser"""
        parser = argparse.ArgumentParser(description="Multi-project CLI with git worktree + uv")

        # Add global arguments
        self._add_global_arguments(parser)

        # Create subparsers and add commands
        subparsers = parser.add_subparsers(dest="command", help="Commands")
        self._add_init_command(subparsers)
        self._add_worktree_commands(subparsers)
        self._add_review_commands(subparsers)
        self._add_merge_command(subparsers)
        self._add_basic_commands(subparsers)
        self._add_config_commands(subparsers)
        self._add_linear_commands(subparsers)

        return parser

    def _add_global_arguments(self, parser: argparse.ArgumentParser):
        """Add global command-line arguments"""
        parser.add_argument("--repo", help="Repository path")
        parser.add_argument("--base", help="Base branch")
        parser.add_argument("--temp-root", help="Temp root for worktrees")
        parser.add_argument("--terminal", choices=["Terminal", "iTerm", "none"], help="Terminal app")
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

    def _add_init_command(self, subparsers):
        """Add init command"""
        init_parser = subparsers.add_parser("init", aliases=["new", "start"], help="Initialize project")
        init_parser.add_argument("--name", help="Project name")
        init_parser.add_argument("--clone", help="Clone URL if repo not local")

    def _add_worktree_commands(self, subparsers):
        """Add worktree commands"""
        wt_create = subparsers.add_parser("worktree", aliases=["w"], help="Worktree commands")
        wt_sub = wt_create.add_subparsers(dest="worktree_command")

        create_parser = wt_sub.add_parser("create", help="Create worktree")
        create_parser.add_argument("--branch", help="Branch name")
        create_parser.add_argument("--linear", help="Linear issue URL")
        create_parser.add_argument("--python-install", action="store_true", help="Auto-install Python deps")
        create_parser.add_argument(
            "--shared-venv",
            action="store_true",
            help="Link to main repo venv instead of creating new one",
        )
        create_parser.add_argument("--copy-env", action="store_true", help="Copy .env files from main repo")
        create_parser.add_argument("--node-install", action="store_true", help="Auto-install Node deps")
        create_parser.add_argument("--java-build", action="store_true", help="Auto-build Java")
        create_parser.add_argument("--open-editor", action="store_true", help="Open editor after creating worktree")
        create_parser.add_argument(
            "--no-terminal",
            action="store_true",
            help="Do not open terminal after creating worktree",
        )
        create_parser.add_argument("--setup-claude", action="store_true", help="Force setup Claude workspace")
        create_parser.add_argument("--no-claude", action="store_true", help="Skip Claude workspace setup")

    def _add_review_commands(self, subparsers):
        """Add review commands"""
        review_parser = subparsers.add_parser("review", help="Review commands")
        review_sub = review_parser.add_subparsers(dest="review_command")

        open_parser = review_sub.add_parser("open", help="Open review")
        open_parser.add_argument("--draft", action="store_true", help="Create draft PR (default is ready for review)")
        open_parser.add_argument("--ready", action="store_true", help="[Deprecated] Create ready PR (now default)")
        open_parser.add_argument("--assign", help="Assignees (comma-separated)")
        open_parser.add_argument("--no-push", action="store_true", help="Don't push branch")
        open_parser.add_argument("--no-agents", action="store_true", help="Skip automated review agents")

    def _add_merge_command(self, subparsers):
        """Add merge command"""
        merge_parser = subparsers.add_parser("merge", help="Merge and cleanup")
        merge_parser.add_argument("--squash", action="store_true", default=True, help="Squash merge")
        merge_parser.add_argument("--merge", dest="squash", action="store_false", help="Merge commit")
        merge_parser.add_argument("--delete-remote", action="store_true", help="Delete remote branch")
        merge_parser.add_argument("--keep-worktree", action="store_true", help="Keep worktree")
        merge_parser.add_argument("--force", action="store_true", help="Force merge even if dirty")

    def _add_basic_commands(self, subparsers):
        """Add basic commands (list, status, cleanup, open)"""
        # list command
        subparsers.add_parser("list", aliases=["ls"], help="List worktrees")

        # status command
        status_parser = subparsers.add_parser("status", aliases=["st"], help="Show status")
        status_parser.add_argument("path", nargs="?", help="Worktree path")

        # cleanup command
        cleanup_parser = subparsers.add_parser("cleanup", help="Cleanup worktrees")
        cleanup_parser.add_argument("--older-than", type=int, help="Days old")
        cleanup_parser.add_argument("--merged-only", action="store_true", help="Only merged branches")
        cleanup_parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
        cleanup_parser.add_argument("--force", action="store_true", help="Force removal of dirty worktrees")

        # open command
        open_parser = subparsers.add_parser("open", help="Open workspace")
        open_parser.add_argument("path", nargs="?", help="Worktree path")

        # setup-claude command
        setup_claude_parser = subparsers.add_parser("setup-claude",
                                                   help="Setup workspace in current directory")
        setup_claude_parser.add_argument("--force", action="store_true",
                                        help="Force setup even if directory exists")

    def _add_config_commands(self, subparsers):
        """Add config command"""
        config_parser = subparsers.add_parser("config", help="Configuration")
        config_parser.add_argument("key", nargs="?", help="Config key")
        config_parser.add_argument("value", nargs="?", help="Config value")

    def _add_linear_commands(self, subparsers):
        """Add Linear integration commands"""
        linear_parser = subparsers.add_parser("linear", help="Linear integration management")
        linear_sub = linear_parser.add_subparsers(dest="linear_command")

        linear_setup = linear_sub.add_parser("setup", help="Setup Linear integration")
        linear_setup.add_argument("--api-key", help="Linear API key")
        linear_setup.add_argument(
            "--from-1password",
            action="store_true",
            help="Configure Linear API key from 1Password reference",
        )
        linear_setup.add_argument("--team", help="Default team ID/key")
        linear_setup.add_argument("--project", help="Default project ID")
        linear_setup.add_argument("--org", help="Linear organization URL")

        linear_sub.add_parser("test", help="Test Linear integration")
        linear_sub.add_parser("status", help="Show Linear configuration status")

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
            if parsed_args.command == "init" or parsed_args.command in ["new", "start"]:
                self.cmd_init(parsed_args)
            elif parsed_args.command in {"worktree", "w"}:
                if parsed_args.worktree_command == "create":
                    self.cmd_worktree_create(parsed_args)
                else:
                    # Show worktree help when no subcommand given
                    parser.parse_args(["worktree", "--help"])
            elif parsed_args.command == "review":
                if parsed_args.review_command == "open":
                    self.cmd_review_open(parsed_args)
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
            elif parsed_args.command == "config":
                self.cmd_config(parsed_args)
            elif parsed_args.command == "linear":
                self.cmd_linear(parsed_args)
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
        print("Projects are now automatically detected from your current working directory.")
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
        print(f"  GitHub reviewers: {', '.join(self.config.get('github_reviewers', []))}")

    def _prompt_for_system_config(self) -> Dict:
        """Prompt for system-level configuration"""
        config = {}

        print("🛠️ System Configuration")
        print("-" * 50)

        # Use defaults in non-interactive mode
        if not self._is_interactive():
            default_temp = str(Path.home() / ".cache" / "cproj-workspaces")
            default_terminal = "Terminal" if sys.platform == "darwin" else "none"
            config["temp_root"] = default_temp
            config["terminal"] = default_terminal
            config["editor"] = "code"
            config["python_prefer_uv"] = True
            config["node_use_nvm"] = True
            config["linear_org"] = ""
            config["linear_default_team"] = ""
            config["linear_default_project"] = ""
            config["github_user"] = ""
            print("Non-interactive mode: Using defaults")
            print(f"  Temp directory: {default_temp}")
            print(f"  Terminal: {default_terminal}")
            print("  Editor: code")
            print("  Python: Prefer uv")
            print("  Node: Use nvm")
            return config

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
        config["python_prefer_uv"] = python_uv != "n"

        # Node preferences
        node_nvm = input("Use nvm for Node.js? [Y/n]: ").strip().lower()
        config["node_use_nvm"] = node_nvm != "n"

        # Optional integrations
        print()
        print("📱 Optional Integrations")
        print("-" * 50)

        # Linear
        linear_org = input("Linear organization (optional): ").strip()
        if linear_org:
            config["linear_org"] = linear_org

        # GitHub reviewers
        github_reviewers = input("GitHub default reviewers (comma-separated, optional): ").strip()
        if github_reviewers:
            config["github_reviewers"] = [r.strip() for r in github_reviewers.split(",")]

        return config

    def _is_interactive(self) -> bool:
        """Check if we're running in an interactive terminal"""
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
            print(f"Found CLAUDE.md symlinked as .cursorrules in {repo_path.name}")

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
                    shutil.copy2(claude_md, worktree_claude)
                    print("✅ Copied CLAUDE.md to worktree")

                # Create relative symlink to CLAUDE.md
                worktree_cursorrules.symlink_to("CLAUDE.md")
                print("✅ Created .cursorrules -> CLAUDE.md symlink")
            except OSError as e:
                print(f"⚠️  Failed to create .cursorrules symlink: {e}")

    def _setup_nvm_for_claude(self, worktree_path: Path, node_env: Dict, args=None):
        """Setup nvm and create a script to automatically use LTS for Claude CLI"""
        # Skip if no_env is set
        if args and hasattr(args, "no_env") and args.no_env:
            return

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
                response = input("Create nvm setup script for this worktree? [Y/n]: ").strip().lower()
                setup_nvm = response in ("", "y", "yes")
            else:
                response = input("Create nvm setup script for this worktree? [y/N]: ").strip().lower()
                setup_nvm = response in ("y", "yes")

        if setup_nvm:
            try:
                # Create .cproj directory for cproj-specific files
                cproj_dir = worktree_path / ".cproj"
                cproj_dir.mkdir(exist_ok=True)

                # Create a setup script that sources nvm and uses LTS
                setup_script = cproj_dir / "setup-claude.sh"
                script_content = """#!/bin/bash
# Auto-generated script to setup Node.js for Claude CLI
# Run: source .cproj/setup-claude.sh

echo "🚀 Setting up Node.js environment for Claude CLI..."

# Source nvm
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \\. "$NVM_DIR/nvm.sh"

# Use LTS Node
nvm use --lts

echo "✅ Node.js LTS activated. You can now run 'claude' command."
echo "💡 Tip: Run 'source .cproj/setup-claude.sh' whenever you open a new terminal in this directory"
"""
                setup_script.write_text(script_content)
                setup_script.chmod(0o755)

                print("✅ Created .cproj/setup-claude.sh script")
                print("💡 Run 'source .cproj/setup-claude.sh' in your terminal to activate Node.js LTS")

            except OSError as e:
                print(f"⚠️  Failed to create nvm setup script: {e}")

    def _setup_claude_workspace(self, worktree_path: Path, repo_path: Path, args=None):
        """Setup Claude workspace configuration with commands and agents"""
        # Validate setup requirements and get paths
        cproj_claude_dir, project_claude_dir = self._validate_claude_setup(repo_path, args)
        if not cproj_claude_dir:
            return

        # Determine if workspace should be set up
        setup_workspace = self._should_setup_claude_workspace(args)

        if setup_workspace:
            self._execute_claude_workspace_setup(worktree_path, repo_path, cproj_claude_dir, project_claude_dir)

    def _validate_claude_setup(self, repo_path: Path, args):
        """Validate Claude setup requirements and return directory paths"""
        # Get cproj's Claude templates
        cproj_root = Path(__file__).parent
        cproj_claude_dir = cproj_root / ".claude"
        project_claude_dir = repo_path / ".claude"

        # Need at least cproj templates to proceed
        if not cproj_claude_dir.exists():
            return None, None

        # Handle explicit command-line flags
        if args and hasattr(args, "no_claude") and args.no_claude:
            return None, None

        # Skip if no_env is set (as Claude setup is part of environment setup)
        if args and hasattr(args, "no_env") and args.no_env:
            return None, None

        return cproj_claude_dir, project_claude_dir

    def _should_setup_claude_workspace(self, args):
        """Determine if Claude workspace should be set up"""
        # Check if we should set up Claude workspace
        default_action = self.config.get("claude_workspace_default", "yes")
        setup_workspace = default_action == "yes"

        # Override with explicit --setup-claude flag
        if args and hasattr(args, "setup_claude") and args.setup_claude:
            setup_workspace = True

        # Interactive prompting
        if self._is_interactive() and not (args and hasattr(args, "no_env") and args.no_env):
            print("\n🤖 Claude Workspace Setup")
            print("Found Claude commands and agents configuration.")

            if default_action == "yes":
                response = input("Setup Claude workspace in worktree? [Y/n]: ").strip().lower()
                setup_workspace = response in ("", "y", "yes")
            else:
                response = input("Setup Claude workspace in worktree? [y/N]: ").strip().lower()
                setup_workspace = response in ("y", "yes")

        return setup_workspace

    def _execute_claude_workspace_setup(self, worktree_path: Path, repo_path: Path, cproj_claude_dir: Path, project_claude_dir: Path):
        """Execute the Claude workspace setup process"""
        print(f"🔧 Setting up Claude workspace in {worktree_path}")
        try:
            # Create .claude directory in worktree
            worktree_claude_dir = worktree_path / ".claude"
            worktree_claude_dir.mkdir(exist_ok=True)
            print(f"Created .claude directory: {worktree_claude_dir}")

            # Copy and merge Claude configurations
            self._copy_claude_configurations(cproj_claude_dir, project_claude_dir, worktree_claude_dir)

            # Copy MCP configuration
            self._copy_mcp_configuration(cproj_claude_dir, project_claude_dir, worktree_claude_dir)

            # Create workspace configuration
            self._create_workspace_configuration(worktree_claude_dir, repo_path, worktree_path)

            print("✅ Setup Claude workspace configuration")
            print("💡 Available commands: add-ticket, review-code")
            print("💡 Available agents: product-manager, ux-designer, senior-software-engineer, code-reviewer")

        except (OSError, shutil.Error) as e:
            print(f"⚠️  Failed to setup Claude workspace: {e}")

    def _copy_claude_configurations(self, cproj_claude_dir: Path, project_claude_dir: Path, worktree_claude_dir: Path):
        """Copy and merge Claude commands and agents configurations"""
        for subdir in ["commands", "agents"]:
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
                    # Copy project files, potentially overwriting templates
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

    def _copy_mcp_configuration(self, cproj_claude_dir: Path, project_claude_dir: Path, worktree_claude_dir: Path):
        """Copy MCP configuration (prefer project over cproj template)"""
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

    def _create_workspace_configuration(self, worktree_claude_dir: Path, repo_path: Path, worktree_path: Path):
        """Create workspace-specific configuration file"""
        # Load Linear configuration
        self._load_linear_config()

        # Create workspace-specific configuration
        workspace_config = {
            "project_root": str(repo_path),
            "worktree_path": str(worktree_path),
            "linear": {
                "org": self.config.get("linear_org"),
                "default_team": self.config.get("linear_default_team"),
                "default_project": self.config.get("linear_default_project"),
                "api_key_file": ".env.linear",
            },
            "commands": {
                "add-ticket": {
                    "description": "Create comprehensive Linear tickets using AI agents",
                    "agents": [
                        "product-manager",
                        "ux-designer",
                        "senior-software-engineer",
                    ],
                    "requires_mcp": ["linear"],
                },
                "review-code": {
                    "description": "Run comprehensive AI-powered code review using specialized review agents",
                    "agents": ["senior-developer", "qa-engineer", "security-reviewer"],
                    "requires_git": True,
                },
            },
            "agents": {
                "product-manager": "Turn high-level asks into crisp PRDs",
                "ux-designer": "Create clear, accessible, user-centric designs",
                "senior-software-engineer": "Plan implementation with tests and docs",
                "code-reviewer": "Review code for correctness and maintainability",
            },
        }

        config_file = worktree_claude_dir / "workspace.json"
        with config_file.open("w") as f:
            json.dump(workspace_config, f, indent=2)

    def _store_linear_api_key(self, api_key: str):
        """Store Linear API key securely in .env.linear file"""
        try:
            # Find git repository root
            git_root = self._find_git_root(Path.cwd())
            if not git_root:
                raise ValueError("Not in a git repository")

            # Create .env.linear file
            env_file = git_root / ".env.linear"
            with env_file.open("w") as f:
                f.write("# Linear API Key - DO NOT COMMIT TO GIT\n")
                f.write("# This file is automatically added to .gitignore\n")
                f.write(f"LINEAR_API_KEY={api_key}\n")

            # Set restrictive permissions (owner read/write only)
            env_file.chmod(0o600)

            # Add to .gitignore if not already present
            self._add_to_gitignore(git_root, ".env.linear")

        except (OSError, ValueError) as e:
            raise ValueError(f"Failed to store API key: {e}")

    def _store_linear_1password_ref(self, reference: str):
        """Store Linear API key 1Password reference in .cproj directory"""
        try:
            # Find git repository root
            git_root = self._find_git_root(Path.cwd())
            if not git_root:
                raise ValueError("Not in a git repository")

            # Ensure .cproj directory exists
            cproj_dir = git_root / ".cproj"
            cproj_dir.mkdir(exist_ok=True)

            # Store reference
            ref_file = cproj_dir / ".linear-1password-ref"
            with ref_file.open("w") as f:
                f.write(reference)

            # Set restrictive permissions
            ref_file.chmod(0o600)

            logger.info("Stored 1Password reference for Linear API key")

        except (OSError, ValueError) as e:
            raise ValueError(f"Failed to store 1Password reference: {e}")

    def _setup_api_key_from_1password(self):
        """Interactive setup for API key from 1Password"""
        # Check if 1Password is available
        if not OnePasswordIntegration.is_available():
            print("❌ 1Password CLI not available or not authenticated")
            print("💡 Install 1Password CLI and run 'op account add' to set up")
            return False

        # Prompt for 1Password reference
        print("\n📝 To get your Linear API key reference from 1Password:")
        print("   1. Open the Linear API key item in 1Password")
        print("   2. Right-click on the password/secret field")
        print("   3. Select 'Copy Secret Reference'")
        print()
        reference = input("Enter 1Password reference (e.g., op://Private/linear-api-key/password): ").strip()
        if reference:
            # Strip quotes that 1Password includes in "Copy Secret Reference"
            reference = reference.strip("\"'")

            # Test the reference
            api_key = OnePasswordIntegration.get_secret(reference)
            if api_key:
                try:
                    self._store_linear_1password_ref(reference)
                    print("✅ 1Password reference stored and validated")
                    return True
                except ValueError as e:
                    print(f"❌ Failed to store reference: {e}")
                    return False
            else:
                print("❌ Could not retrieve API key from 1Password reference")
                print("💡 Check that the reference is correct and you're authenticated")
                return False
        else:
            print("❌ No reference provided")
            return False

    def _add_to_gitignore(self, repo_path: Path, pattern: str):
        """Add pattern to .gitignore if not already present"""
        gitignore_path = repo_path / ".gitignore"

        # Check if pattern already exists
        content = ""
        if gitignore_path.exists():
            with gitignore_path.open() as f:
                content = f.read()
                if pattern in content:
                    return

        # Add pattern to .gitignore
        with gitignore_path.open("a") as f:
            if gitignore_path.exists() and content and not content.endswith("\n"):
                f.write("\n")
            f.write("# Linear API key (added by cproj)\n")
            f.write(f"{pattern}\n")

    def _load_linear_config(self) -> Dict[str, str]:
        """Load Linear configuration from .env.linear file or 1Password"""
        git_root = self._find_git_root(Path.cwd())
        if not git_root:
            return {}

        config = {}

        # First check for .env.linear file
        env_file = git_root / ".env.linear"
        if env_file.exists():
            try:
                with env_file.open() as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            config[key.strip()] = value.strip()
            except OSError:
                pass

        # Check for 1Password reference if API key not found
        if "LINEAR_API_KEY" not in config:
            cproj_dir = git_root / ".cproj"
            onepass_ref_file = cproj_dir / ".linear-1password-ref"
            if onepass_ref_file.exists():
                try:
                    with onepass_ref_file.open() as f:
                        reference = f.read().strip()
                        if reference and OnePasswordIntegration.is_available():
                            api_key = OnePasswordIntegration.get_secret(reference)
                            if api_key:
                                config["LINEAR_API_KEY"] = api_key
                                config["LINEAR_API_KEY_SOURCE"] = "1Password"
                except (OSError, ValueError):
                    pass

        return config

    def _generate_branch_suggestions(self) -> List[str]:
        """Generate reasonable branch name suggestions"""
        # Use datetime that's already imported at top level

        # Get configured branch scheme
        branch_scheme = self.config.get("branch_scheme", "feature/{ticket}-{slug}")

        suggestions = []
        timestamp = datetime.now().strftime("%m%d")

        # Parse the scheme to generate suggestions
        if "{ticket}" in branch_scheme and "{slug}" in branch_scheme:
            suggestions.extend(
                [
                    branch_scheme.replace("{ticket}", "TICKET-123").replace("{slug}", "description"),
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
                        ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
                        cwd=repo_path,
                        capture_output=True,
                        check=True,
                    )
                    return branch
                except subprocess.CalledProcessError:
                    continue
        return None

    def _resolve_repository_path(self, args):
        """Resolve repository path from args or current directory"""
        if hasattr(args, "repo") and args.repo:
            return Path(args.repo)
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
                print("  cproj w create --repo /path/to/project --branch feature/name")
                return None
            return repo_path

    def _prompt_for_branch_name(self, args):
        """Handle interactive branch name prompting if needed"""
        if not hasattr(args, "branch") or not args.branch:
            if not self._is_interactive():
                raise CprojError("Branch name is required. Use --branch BRANCH_NAME or run in interactive mode.")

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
                            print(f"❌ Please enter a number between 1 and {len(suggestions)}")
                            continue
                    except (ValueError, IndexError):
                        print("❌ Invalid selection")
                        continue
                else:
                    args.branch = branch_input
                    break

            print(f"✅ Using branch: {args.branch}")
            print()

    def _prompt_for_linear_integration(self, args):
        """Handle Linear integration prompting if configured"""
        if not (hasattr(args, "linear") and args.linear) and self.config.get("linear_org") and self._is_interactive():
            print("🔗 Linear Integration (optional)")
            print("-" * 50)
            print(f"Linear organization: {self.config.get('linear_org')}")
            linear_input = input("Linear issue URL (optional, press Enter to skip): ").strip()
            if linear_input:
                args.linear = linear_input
                print(f"✅ Using Linear URL: {args.linear}")
            print()

    def _prompt_for_environment_setup(self, args, repo_path):
        """Handle environment setup prompting if not specified"""
        if (
            not any(
                [
                    hasattr(args, "python_install") and args.python_install,
                    hasattr(args, "node_install") and args.node_install,
                    hasattr(args, "java_build") and args.java_build,
                ]
            )
            and self._is_interactive()
            and not (hasattr(args, "no_env") and args.no_env)
        ):
            print("⚙️  Environment Setup (optional)")
            print("-" * 50)

            # Check what environments are available in the repo
            repo_path_obj = Path(repo_path)
            has_python = any((repo_path_obj / f).exists() for f in ["pyproject.toml", "requirements.txt", "setup.py"])
            has_node = (repo_path_obj / "package.json").exists()
            has_java = any((repo_path_obj / f).exists() for f in ["pom.xml", "build.gradle", "build.gradle.kts"])

            if has_python:
                python_install = input("Auto-install Python dependencies? [y/N]: ").strip().lower()
                args.python_install = python_install in ["y", "yes"]

                if not args.python_install:
                    shared_venv = input("Use shared venv from main repo? [y/N]: ").strip().lower()
                    args.shared_venv = shared_venv in ["y", "yes"]

            if has_node:
                node_install = input("Auto-install Node dependencies? [y/N]: ").strip().lower()
                args.node_install = node_install in ["y", "yes"]

            if has_java:
                java_build = input("Auto-build Java project? [y/N]: ").strip().lower()
                args.java_build = java_build in ["y", "yes"]

            # Ask about .env files
            copy_env = input("Copy .env files from main repo? [y/N]: ").strip().lower()
            args.copy_env = copy_env in ["y", "yes"]

            if has_python or has_node or has_java:
                print()

    def _setup_worktree_environment(self, worktree_path, repo_path, args):
        """Setup environment for the new worktree"""
        env_setup = EnvironmentSetup(worktree_path)
        python_install = hasattr(args, "python_install") and args.python_install
        shared_venv = hasattr(args, "shared_venv") and args.shared_venv
        node_install = hasattr(args, "node_install") and args.node_install
        java_build = hasattr(args, "java_build") and args.java_build
        copy_env = hasattr(args, "copy_env") and args.copy_env

        python_env = env_setup.setup_python(python_install, shared_venv, repo_path)
        node_env = env_setup.setup_node(node_install)
        java_env = env_setup.setup_java(java_build)

        # Copy .env files if requested
        if copy_env:
            env_setup.copy_env_files(repo_path)

        return python_env, node_env, java_env

    def _create_agent_json(self, worktree_path, repo_path, project_name, args, python_env, node_env, java_env, base_branch):
        """Create and configure .agent.json file"""
        agent_json = AgentJson(worktree_path)
        agent_json.set_project(project_name, str(repo_path))
        agent_json.set_workspace(str(worktree_path), args.branch, base_branch)
        agent_json.set_env("python", python_env)
        agent_json.set_env("node", node_env)
        agent_json.set_env("java", java_env)

        if hasattr(args, "linear") and args.linear:
            agent_json.set_link("linear", args.linear)

        agent_json.save()

    def _handle_terminal_and_editor(self, worktree_path, args):
        """Handle terminal and editor opening"""
        # Open terminal by default (unless --no-terminal is specified)
        terminal_app = (hasattr(args, "terminal") and args.terminal) or self.config.get("terminal", "Terminal")
        no_terminal = hasattr(args, "no_terminal") and args.no_terminal
        if not no_terminal and terminal_app != "none":
            # Strip branch prefix (everything before /) for cleaner window title
            branch_display = re.sub(r"^\S+/", "", args.branch)
            TerminalAutomation.open_terminal(worktree_path, branch_display, terminal_app)

        # Open editor only if --open-editor is specified
        if hasattr(args, "open_editor") and args.open_editor:
            editor = (hasattr(args, "editor") and args.editor) or self.config.get("editor", "code")
            if editor:
                TerminalAutomation.open_editor(worktree_path, editor)

    def cmd_worktree_create(self, args):
        """Create worktree"""
        # Resolve repository path
        repo_path = self._resolve_repository_path(args)
        if not repo_path:
            return

        # Derive project settings from repository
        project_name = repo_path.name
        base_branch = (hasattr(args, "base") and args.base) or self._detect_default_branch(repo_path) or "main"
        temp_root = Path(
            (hasattr(args, "temp_root") and args.temp_root)
            or self.config.get("temp_root", tempfile.gettempdir())
            or tempfile.gettempdir()
        )

        logger.debug(f"Using repository: {repo_path} (project: {project_name})")

        # Handle interactive prompts
        self._prompt_for_branch_name(args)
        self._prompt_for_linear_integration(args)
        self._prompt_for_environment_setup(args, repo_path)

        # Create git worktree
        git = GitWorktree(repo_path)
        git.fetch_all()
        git.ensure_base_branch(base_branch)

        # Create worktree path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        worktree_name = f"{project_name}_{args.branch}_{timestamp}"
        worktree_path = temp_root / worktree_name

        # Create worktree
        git.create_worktree(worktree_path, args.branch, base_branch, interactive=self._is_interactive())

        # Setup environment
        python_env, node_env, java_env = self._setup_worktree_environment(worktree_path, repo_path, args)

        # Create .agent.json
        self._create_agent_json(worktree_path, repo_path, project_name, args, python_env, node_env, java_env, base_branch)

        # Setup Claude integration
        self._setup_claude_symlink(worktree_path, repo_path)
        self._setup_nvm_for_claude(worktree_path, node_env, args)
        self._setup_claude_workspace(worktree_path, repo_path, args)

        print(f"Created worktree: {worktree_path}")
        print(f"Branch: {args.branch}")

        # Handle terminal and editor opening
        self._handle_terminal_and_editor(worktree_path, args)

    def cmd_review_open(self, args):
        """Open review"""
        worktree_path = Path.cwd()
        agent_json_path = worktree_path / ".cproj" / ".agent.json"

        if not agent_json_path.exists():
            raise CprojError(
                "Not in a cproj worktree (no .agent.json found in .cproj directory). Run from worktree root directory."
            )

        agent_json = AgentJson(worktree_path)
        repo_path = Path(agent_json.data["project"]["repo_path"])
        branch = agent_json.data["workspace"]["branch"]

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
                print(f"✅ Review configuration created: {result['config_path']}")
                print("📋 Ready for Claude review! Run:")
                print("   cproj review agents")
            except ImportError:
                print("⚠️  Review agents not available (claude_review_agents.py not found)")
            except Exception as e:
                print(f"⚠️  Could not setup review agents: {e}")

        print(f"\n🎉 Branch {branch} ready for review")

    # Legacy cmd_review_agents method removed for security and maintainability
    # The old implementation had potential security vulnerabilities in:
    # - Template string formatting without proper sanitization
    # - Subprocess execution without adequate input validation
    # - Complex orchestrator dependencies that increased attack surface
    #
    # Migration Path:
    # - Use 'review-code' command instead of 'cproj review agents'
    # - New implementation provides enhanced security controls:
    #   - Safe file path validation and sanitization
    #   - Template injection prevention with string.Template
    #   - Bounded resource usage and timeout handling
    #   - Better error handling and user feedback

    def cmd_merge(self, args):
        """Merge and cleanup"""
        worktree_path = Path.cwd()
        agent_json_path = worktree_path / ".cproj" / ".agent.json"

        if not agent_json_path.exists():
            raise CprojError(
                "Not in a cproj worktree (no .agent.json found in .cproj directory). Run from worktree root directory."
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
                print("❌ PR merge failed. Keeping worktree for you to continue working.")
                print("Common reasons:")
                print("  - PR is still in draft mode (use 'gh pr ready' or mark ready in GitHub)")
                print("  - PR needs approval from reviewers")
                print("  - PR has merge conflicts")
                print("  - Branch protection rules not satisfied")
                return
        else:
            print("⚠️  GitHub CLI not available. Please merge manually in GitHub.")
            print("After merging, you can clean up with:")
            print(f"  git worktree remove --force {worktree_path}")
            return

        # Only proceed with cleanup if merge was successful
        if merge_successful:
            # Close workspace
            agent_json.close_workspace()
            agent_json.save()

            # Remove worktree
            if not args.keep_worktree:
                git.remove_worktree(worktree_path, force=True)
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
                except (OSError, json.JSONDecodeError, KeyError) as e:
                    logger.debug(f"Error reading agent.json for {path}: {e}")
                    print(f"{path} [{branch}]")
            else:
                print(f"{path} [{branch}]")

    def cmd_status(self, args):
        """Show status"""
        worktree_path = Path(args.path) if hasattr(args, "path") and args.path else Path.cwd()

        agent_json_path = worktree_path / ".cproj" / ".agent.json"
        if not agent_json_path.exists():
            # For testing and basic git status, provide basic information
            print(f"Directory: {worktree_path}")

            # Try to get git status if we're in a git repository
            try:
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                if result.stdout.strip():
                    print("Git Status:")
                    for line in result.stdout.strip().split("\n"):
                        print(f"  {line}")
                else:
                    print("Git Status: Clean working directory")
            except (subprocess.CalledProcessError, OSError):
                print("Not in a git repository or cproj worktree")
            return

        agent_json = AgentJson(worktree_path)

        if hasattr(args, "json") and args.json:
            print(json.dumps(agent_json.data, indent=2))
            return

        print(f"Workspace: {worktree_path}")
        print(f"Project: {agent_json.data['project']['name']}")
        print(f"Branch: {agent_json.data['workspace']['branch']}")
        print(f"Base: {agent_json.data['workspace']['base']}")
        print(f"Created: {agent_json.data['workspace']['created_at']}")

        if agent_json.data["links"]["linear"]:
            print(f"Linear: {agent_json.data['links']['linear']}")
        if agent_json.data["links"]["pr"]:
            print(f"PR: {agent_json.data['links']['pr']}")

    def _get_worktree_age_info(self, path: Path) -> str:
        """Get age information for a worktree"""
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
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.debug(f"Error parsing date for {path}: {e}")
        return age_info

    def _show_cleanup_menu(self, active_worktrees: list, force_enabled: bool) -> None:
        """Display cleanup menu and worktree list"""
        print("🧹 Cleanup Worktrees")
        print("-" * 50)

        print(f"Found {len(active_worktrees)} active worktree(s):")
        for wt in active_worktrees:
            path = Path(wt["path"])
            branch = wt.get("branch", "N/A")
            age_info = self._get_worktree_age_info(path)
            print(f"  - {path.name} [{branch}]{age_info}")

        print()
        print("Cleanup options:")
        print("  1. Interactive selection")
        print("  2. Remove worktrees newer than X days")
        print("  3. Remove worktrees older than X days")
        print("  4. Remove merged worktrees only")
        print("  5. Cancel")
        if force_enabled:
            print("💪 Force mode enabled - will remove dirty worktrees")

    def _handle_interactive_selection(self, active_worktrees: list, git: GitWorktree, force: bool) -> None:
        """Handle interactive worktree selection for removal"""
        current_worktree = Path.cwd()
        selected_for_removal = []

        print("📋 Select worktrees to remove:")
        print("   [y/n] for each worktree, Enter to confirm selection")
        print()

        for wt in active_worktrees:
            path = Path(wt["path"])
            branch = wt.get("branch", "N/A")
            age_info = self._get_worktree_age_info(path)

            # Check if this is the current worktree
            is_current = current_worktree == path or current_worktree.resolve() == path.resolve()
            status_info = " [CURRENT]" if is_current else ""

            while True:
                response = input(f"Remove {path.name} [{branch}]{age_info}{status_info}? [y/N]: ").strip().lower()
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

        self._execute_worktree_removal(selected_for_removal, git, force)

    def _execute_worktree_removal(self, selected_worktrees: list, git: GitWorktree, force: bool) -> None:
        """Execute removal of selected worktrees"""
        if not selected_worktrees:
            print("No worktrees selected for removal")
            return

        print(f"\n📋 Selected {len(selected_worktrees)} worktrees for removal")
        for wt in selected_worktrees:
            print(f"  - {Path(wt['path']).name} [{wt.get('branch', 'N/A')}]")

        confirm = input("\nConfirm removal? [y/N]: ").strip().lower()
        if confirm not in ["y", "yes"]:
            print("Cleanup cancelled")
            return

        for wt in selected_worktrees:
            self._remove_single_worktree(Path(wt["path"]), git, force)

    def _remove_single_worktree(self, path: Path, git: GitWorktree, force: bool) -> None:
        """Remove a single worktree with error handling"""
        try:
            git.remove_worktree(path, force=force)
            print(f"✅ Removed {path.name}")
        except Exception as e:
            error_msg = str(e)
            if "is dirty" in error_msg and not force:
                print(f"❌ Failed to remove {path.name}: Worktree is dirty (has uncommitted changes)")
                if self._is_interactive():
                    force_choice = input(f"Force removal of dirty worktree {path.name}? [y/N]: ").strip().lower()
                    if force_choice in ["y", "yes"]:
                        try:
                            git.remove_worktree(path, force=True)
                            print(f"✅ Force removed {path.name}")
                        except Exception as force_e:
                            print(f"❌ Failed to force remove {path.name}: {force_e}")
                    else:
                        print(f"⏭️  Skipped {path.name}")
                else:
                    print("💡 Use --force to remove dirty worktrees")
            else:
                print(f"❌ Failed to remove {path.name}: {e}")

    def _get_worktree_age_info(self, path):
        """Get age information for a worktree"""
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
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.debug(f"Error parsing date for {path}: {e}")
        return age_info

    def _show_cleanup_menu(self, active_worktrees, args):
        """Show cleanup menu and get user selection"""
        print("🧹 Cleanup Worktrees")
        print("-" * 50)

        print(f"Found {len(active_worktrees)} active worktree(s):")
        for wt in active_worktrees:
            path = Path(wt["path"])
            branch = wt.get("branch", "N/A")
            age_info = self._get_worktree_age_info(path)
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
            if choice in ["1", "2", "3", "4", "5"]:
                return choice
            print("❌ Please enter 1-5")

    def _handle_interactive_selection(self, active_worktrees, git, args):
        """Handle interactive worktree selection for cleanup"""
        current_worktree = Path.cwd()
        selected_for_removal = []

        print("📋 Select worktrees to remove:")
        print("   [y/n] for each worktree, Enter to confirm selection")
        print()

        for wt in active_worktrees:
            path = Path(wt["path"])
            branch = wt.get("branch", "N/A")
            age_info = self._get_worktree_age_info(path)

            # Check if this is the current worktree
            is_current = current_worktree == path or current_worktree.resolve() == path.resolve()
            status_info = " [CURRENT]" if is_current else ""

            while True:
                response = input(f"Remove {path.name} [{branch}]{age_info}{status_info}? [y/N]: ").strip().lower()
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
            print(f"\n📋 Selected {len(selected_for_removal)} worktrees for removal")
            for wt in selected_for_removal:
                print(f"  - {Path(wt['path']).name} [{wt.get('branch', 'N/A')}]")

            confirm = input("\nConfirm removal? [y/N]: ").strip().lower()
            if confirm in ["y", "yes"]:
                for wt in selected_for_removal:
                    self._remove_single_worktree(git, Path(wt["path"]), args.force)
            else:
                print("Cleanup cancelled")
        else:
            print("No worktrees selected for removal")

    def _remove_single_worktree(self, git, path, force_removal):
        """Remove a single worktree with error handling"""
        try:
            git.remove_worktree(path, force=force_removal)
            print(f"✅ Removed {path.name}")
        except Exception as e:
            error_msg = str(e)
            if "is dirty" in error_msg and not force_removal:
                print(f"❌ Failed to remove {path.name}: Worktree is dirty (has uncommitted changes)")
                if self._is_interactive():
                    force_choice = input(f"Force removal of dirty worktree {path.name}? [y/N]: ").strip().lower()
                    if force_choice in ["y", "yes"]:
                        try:
                            git.remove_worktree(path, force=True)
                            print(f"✅ Force removed {path.name}")
                        except Exception as force_e:
                            print(f"❌ Failed to force remove {path.name}: {force_e}")
                    else:
                        print(f"⏭️  Skipped {path.name}")
                else:
                    print("💡 Use --force to remove dirty worktrees")
            else:
                print(f"❌ Failed to remove {path.name}: {e}")

    def _execute_worktree_removal(self, to_remove, git, args):
        """Execute the removal of selected worktrees"""
        if not to_remove:
            print("No worktrees to cleanup")
            return

        for wt in to_remove:
            path = Path(wt["path"])
            print(f"Would remove: {path}")

            if not args.dry_run and (args.yes or input(f"Remove {path}? [y/N] ").lower() == "y"):
                self._remove_single_worktree(git, path, args.force)

    def cmd_cleanup(self, args):
        """Cleanup worktrees"""
        repo_path = Path(self.config.get("repo_path", "."))
        if not repo_path.exists():
            print("No configured repository")
            return

        git = GitWorktree(repo_path)
        worktrees = git.list_worktrees()

        # Handle interactive prompts if no criteria specified
        if not self._has_cleanup_criteria(args) and self._is_interactive():
            active_worktrees = [wt for wt in worktrees if Path(wt["path"]) != repo_path]
            if not active_worktrees:
                print("No worktrees to clean up.")
                return
            if not self._handle_interactive_cleanup(active_worktrees, git, args):
                return

        logger.debug(
            f"Processing cleanup with filters - older_than: {args.older_than}, newer_than: "
            f"{getattr(args, 'newer_than', None)}, merged_only: {args.merged_only}"
        )

        to_remove = self._find_worktrees_to_remove(worktrees, repo_path, args)
        self._execute_worktree_removal(to_remove, git, args)

    def _has_cleanup_criteria(self, args):
        """Check if any cleanup criteria are specified"""
        return any([args.older_than, getattr(args, "newer_than", None), args.merged_only])

    def _handle_interactive_cleanup(self, active_worktrees, git, args):
        """Handle interactive cleanup menu and return True to continue"""
        choice = self._show_cleanup_menu(active_worktrees, args)

        if choice == "1":
            self._handle_interactive_selection(active_worktrees, git, args)
            return False
        elif choice == "2":
            return self._set_newer_than_criteria(args)
        elif choice == "3":
            return self._set_older_than_criteria(args)
        elif choice == "4":
            args.merged_only = True
            print()
            return True
        elif choice == "5":
            print("Cleanup cancelled")
            return False
        return True

    def _set_newer_than_criteria(self, args):
        """Set newer_than criteria from user input"""
        default_days = 7
        days_input = input(f"Remove worktrees newer than how many days? [{default_days}]: ").strip()
        try:
            newer_days = int(days_input) if days_input else default_days
            args.newer_than = newer_days
            logger.debug(f"Set args.newer_than to {args.newer_than}")
            print()
            return True
        except ValueError:
            print("❌ Please enter a valid number")
            return False

    def _set_older_than_criteria(self, args):
        """Set older_than criteria from user input"""
        default_days = self.config.get("cleanup_days", 14)
        days_input = input(f"Remove worktrees older than how many days? [{default_days}]: ").strip()
        try:
            args.older_than = int(days_input) if days_input else default_days
            print()
            return True
        except ValueError:
            print("❌ Please enter a valid number")
            return False

    def _find_worktrees_to_remove(self, worktrees, repo_path, args):
        """Find worktrees that match removal criteria"""
        to_remove = []
        for wt in worktrees:
            path = Path(wt["path"])
            if path == repo_path:  # Skip main worktree
                continue

            logger.debug(f"Evaluating worktree: {path.name}")
            if self._should_remove_worktree(path, args):
                logger.debug(f"Adding {path.name} to removal list")
                to_remove.append(wt)
            else:
                logger.debug(f"Keeping {path.name}")
        return to_remove

    def _should_remove_worktree(self, path, args):
        """Check if a worktree should be removed based on criteria"""
        agent_json_path = path / ".cproj" / ".agent.json"

        # Track individual criteria results for AND logic
        age_matches = True  # Default to true if no age criteria
        merged_matches = True  # Default to true if no merged criteria

        # Check age criteria
        if args.older_than:
            age_matches = self._check_older_than(agent_json_path, path, args.older_than)

        # Check for newer than (opposite logic)
        if hasattr(args, "newer_than") and args.newer_than:
            age_matches = self._check_newer_than(agent_json_path, path, args.newer_than)

        # Check if merged
        if args.merged_only:
            merged_matches = self._check_merged_status(agent_json_path, path)

        # Use AND logic - all specified criteria must be met
        return age_matches and merged_matches

    def _check_older_than(self, agent_json_path, path, older_than_days):
        """Check if worktree is older than specified days"""
        if not agent_json_path.exists():
            return False
        try:
            agent_json = AgentJson(path)
            created_at = datetime.fromisoformat(
                agent_json.data["workspace"]["created_at"].replace("Z", "+00:00")
            )
            age_days = (datetime.now(timezone.utc) - created_at).days
            return age_days > older_than_days
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug(f"Error parsing date for {path}: {e}")
            return False

    def _check_newer_than(self, agent_json_path, path, newer_than_days):
        """Check if worktree is newer than specified days"""
        logger.debug(f"Checking newer_than condition for {path.name}")
        if not agent_json_path.exists():
            return False
        try:
            agent_json = AgentJson(path)
            created_at = datetime.fromisoformat(
                agent_json.data["workspace"]["created_at"].replace("Z", "+00:00")
            )
            age_days = (datetime.now(timezone.utc) - created_at).days
            logger.debug(f"{path.name} is {age_days} days old, newer_than={newer_than_days}")
            if age_days <= newer_than_days:
                logger.debug(f"Marking {path.name} for removal (newer than {newer_than_days} days)")
                return True
            return False
        except (OSError, ValueError) as e:
            logger.debug(f"Error processing {path.name}: {e}")
            return False

    def _check_merged_status(self, agent_json_path, path):
        """Check if worktree is marked as merged/closed"""
        if not agent_json_path.exists():
            return False
        try:
            agent_data = json.loads(agent_json_path.read_text())
            if "closed_at" in agent_data.get("workspace", {}):
                logger.debug(f"Marking {path.name} for removal (marked as closed)")
                return True
            return False
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Error parsing agent.json for merged check in {path.name}: {e}")
            return False

    def cmd_open(self, args):
        """Open workspace"""
        if args.path:
            # Check if user might be trying to use 'open review' instead of 'review open'
            if args.path == "review":
                raise CprojError("Did you mean 'cproj review open'? The correct syntax is: cproj review open")
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
                        f"Found .agent.json in parent directory: {parent}/.cproj\n"
                        f"Run command from worktree root or specify path with 'cproj open {parent}'"
                    )
                parent = parent.parent
            raise CprojError("Not in a cproj worktree (no .agent.json found in .cproj directory)")

        agent_json = AgentJson(worktree_path)
        agent_json.data["project"]["name"]
        branch = agent_json.data["workspace"]["branch"]

        terminal_app = args.terminal or self.config.get("terminal", "Terminal")
        editor = args.editor or self.config.get("editor", "code")

        # Open terminal
        if terminal_app != "none":
            # Strip branch prefix (everything before /) for cleaner window title
            branch_display = re.sub(r"^\S+/", "", branch)
            TerminalAutomation.open_terminal(worktree_path, branch_display, terminal_app)

        # Open editor
        if editor:
            TerminalAutomation.open_editor(worktree_path, editor)

        # Open browser links safely
        links = agent_json.data["links"]
        if links["linear"]:
            self._safe_open_url(links["linear"])
        if links["pr"]:
            self._safe_open_url(links["pr"])

    def _safe_open_url(self, url: str):
        """Safely open a URL, validating it first to prevent command injection"""
        if url is None:
            logger.warning("Cannot open None URL")
            return

        try:
            # Check for shell metacharacters that could be used for injection
            dangerous_chars = [";", "&", "|", "`", "$", "'", '"', "\\", "\n", "\r"]
            if any(char in url for char in dangerous_chars):
                logger.warning(f"Refusing to open URL with dangerous characters: {url}")
                return

            parsed = urllib.parse.urlparse(url)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                subprocess.run(["open", url], check=False)
            else:
                logger.warning(f"Refusing to open potentially unsafe URL: {url}")
        except Exception:
            logger.exception(f"Error opening URL {url}")

    def cmd_setup_claude(self, args):
        """Setup workspace in current directory"""
        current_dir = Path.cwd()

        # Check if we're in a git repository
        try:
            git_root = self._find_git_root(current_dir)
        except CprojError:
            raise CprojError("Not in a git repository")

        # Get cproj's directory (template files)
        cproj_dir = Path(__file__).parent
        cproj_claude_dir = cproj_dir / ".claude"
        if not cproj_claude_dir.exists():
            raise CprojError(f"cproj template directory not found: {cproj_claude_dir}")

        # Check if directory exists in current location
        claude_dir = current_dir / ".claude"

        if claude_dir.exists():
            print(f"🔍 Found existing directory in {current_dir}")
            print("🔀 Merging cproj's template files with existing configuration...")
            self._merge_claude_config_files(cproj_claude_dir, claude_dir)
        else:
            print(f"📂 Creating new directory in {current_dir}")

            # Load project configuration to check if we should copy from main repo
            try:
                config = self._load_config()
                main_repo_path = Path(config.get("repo_path", ""))

                # If this is a worktree and main repo has directory, copy from there first
                if (str(git_root) != str(main_repo_path) and
                    main_repo_path.exists() and
                    (main_repo_path / ".claude").exists()):

                    print(f"📂 Copying project config from {main_repo_path}")
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

        print(f"✅ Workspace setup complete in {current_dir}")
        print("💡 cproj commands and agents are now available")

    def _merge_claude_config_files(self, cproj_claude_dir, target_claude_dir):
        """Intelligently merge cproj's template files with existing project files"""

        # Files that need special JSON merging
        json_merge_files = {
            "settings.local.json": self._merge_settings_json,
            "mcp_config.json": self._merge_mcp_config_json
        }

        # Process each file in cproj's directory
        for cproj_file in cproj_claude_dir.rglob("*"):
            if cproj_file.is_file():
                # Get relative path from directory
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
                            print(f"⚠️  Could not merge {rel_path}, copying cproj version: {e}")
                            shutil.copy2(cproj_file, target_file)
                    else:
                        # Just copy the cproj version
                        shutil.copy2(cproj_file, target_file)
                        print(f"📋 Copied {rel_path}")
                else:
                    # For non-JSON files, copy with potential overwrite
                    if target_file.exists():
                        print(f"📝 Updating {rel_path}")
                    else:
                        print(f"📋 Copied {rel_path}")
                    shutil.copy2(cproj_file, target_file)

    def _merge_settings_json(self, cproj_file, target_file):
        """Merge settings.local.json files"""
        # Load both files
        with open(cproj_file) as f:
            cproj_config = json.load(f)
        with open(target_file) as f:
            target_config = json.load(f)

        # Merge cproj settings into target, preserving existing settings
        for key, value in cproj_config.items():
            if key not in target_config:
                target_config[key] = value

        # Write merged config
        with open(target_file, "w") as f:
            json.dump(target_config, f, indent=2)

    def _merge_mcp_config_json(self, cproj_file, target_file):
        """Merge mcp_config.json files"""
        # Load both files
        with open(cproj_file) as f:
            cproj_config = json.load(f)
        with open(target_file) as f:
            target_config = json.load(f)

        # Merge MCP servers, preserving existing ones
        if "mcpServers" in cproj_config and "mcpServers" in target_config:
            for server_name, server_config in cproj_config["mcpServers"].items():
                if server_name not in target_config["mcpServers"]:
                    target_config["mcpServers"][server_name] = server_config
        elif "mcpServers" in cproj_config:
            target_config["mcpServers"] = cproj_config["mcpServers"]

        # Write merged config
        with open(target_file, "w") as f:
            json.dump(target_config, f, indent=2)

    def cmd_config(self, args):
        """Configuration management"""
        if not hasattr(args, "key") or not args.key:
            # Show all config
            if hasattr(args, "json") and args.json:
                print(json.dumps(self.config._config, indent=2))
            else:
                for key, value in self.config._config.items():
                    print(f"{key}: {value}")
        elif not hasattr(args, "value") or not args.value:
            # Show specific key
            value = self.config.get(args.key)
            if value is not None:
                print(value)
        else:
            # Set key-value
            self.config.set(args.key, args.value)
            print(f"Set {args.key} = {args.value}")

    def cmd_linear(self, args):
        """Linear integration management"""
        if args.linear_command == "setup":
            self.cmd_linear_setup(args)
        elif args.linear_command == "test":
            self.cmd_linear_test(args)
        elif args.linear_command == "status":
            self.cmd_linear_status(args)
        else:
            print("Available subcommands: setup, test, status")

    def cmd_linear_setup(self, args):
        """Setup Linear integration"""
        print("🔗 Linear Integration Setup")
        print("-" * 40)

        # Check if any arguments were provided
        has_args = any([args.org, args.team, args.project, args.api_key, args.from_1password])

        # If no arguments, run interactive setup
        if not has_args:
            self._interactive_linear_setup()
        else:
            self._handle_linear_command_line_args(args)

        # Handle API key setup from command-line flags
        self._handle_linear_api_key_args(args)

        print("\n💡 Configuration updated! Test with: cproj linear test")

    def _interactive_linear_setup(self):
        """Handle interactive Linear setup prompting"""
        print("\n📝 Interactive Linear Setup")
        print("Configure your Linear integration step by step:")
        print()

        # Prompt for organization, team, and project
        self._prompt_linear_organization()
        self._prompt_linear_team()
        self._prompt_linear_project()

        # Handle API key configuration
        self._prompt_linear_api_key_setup()

    def _prompt_linear_organization(self):
        """Prompt for Linear organization configuration"""
        current_org = self.config.get("linear_org", "")
        org_prompt = f"Linear organization [{current_org}]: " if current_org else "Linear organization: "
        org = input(org_prompt).strip()
        if org:
            self.config.set("linear_org", org)
            print(f"✅ Set organization: {org}")
        elif current_org:
            print(f"✅ Using existing organization: {current_org}")

    def _prompt_linear_team(self):
        """Prompt for Linear default team configuration"""
        current_team = self.config.get("linear_default_team", "")
        team_prompt = f"Default team [{current_team}]: " if current_team else "Default team (optional): "
        team = input(team_prompt).strip()
        if team:
            self.config.set("linear_default_team", team)
            print(f"✅ Set default team: {team}")
        elif current_team:
            print(f"✅ Using existing team: {current_team}")

    def _prompt_linear_project(self):
        """Prompt for Linear default project configuration"""
        current_project = self.config.get("linear_default_project", "")
        project_prompt = (
            f"Default project [{current_project}]: " if current_project else "Default project (optional): "
        )
        project = input(project_prompt).strip()
        if project:
            self.config.set("linear_default_project", project)
            print(f"✅ Set default project: {project}")
        elif current_project:
            print(f"✅ Using existing project: {current_project}")

    def _prompt_linear_api_key_setup(self):
        """Prompt for Linear API key setup if not already configured"""
        linear_config = self._load_linear_config()
        if linear_config.get("LINEAR_API_KEY"):
            source = linear_config.get("LINEAR_API_KEY_SOURCE", "File")
            print(f"✅ API key already configured (source: {source})")
        else:
            print("\n🔑 API Key Configuration")
            print("Choose how to configure your Linear API key:")
            print("  1. From 1Password (recommended)")
            print("  2. Enter directly")
            print("  3. Skip for now")

            choice = input("Choose option [1]: ").strip() or "1"

            if choice == "1":
                self._setup_api_key_from_1password()
            elif choice == "2":
                api_key = input("Enter your Linear API key: ").strip()
                if api_key:
                    try:
                        self._store_linear_api_key(api_key)
                        print("✅ API key stored securely")
                    except ValueError as e:
                        print(f"❌ Failed to store API key: {e}")
            elif choice == "3":
                print("⏭️  Skipping API key configuration")
                print("💡 You can set it later with: cproj linear setup --from-1password")

    def _handle_linear_command_line_args(self, args):
        """Handle Linear setup from command-line arguments"""
        if args.org:
            self.config.set("linear_org", args.org)
            print(f"✅ Set organization: {args.org}")

        if args.team:
            self.config.set("linear_default_team", args.team)
            print(f"✅ Set default team: {args.team}")

        if args.project:
            self.config.set("linear_default_project", args.project)
            print(f"✅ Set default project: {args.project}")

    def _handle_linear_api_key_args(self, args):
        """Handle Linear API key setup from command-line arguments"""
        if args.api_key:
            try:
                self._store_linear_api_key(args.api_key)
                print("✅ API key stored securely")
            except ValueError as e:
                print(f"❌ Failed to store API key: {e}")
                return
        elif args.from_1password:
            self._setup_linear_1password_integration()

    def _setup_linear_1password_integration(self):
        """Setup Linear API key from 1Password"""
        # Check if 1Password is available
        if not OnePasswordIntegration.is_available():
            print("❌ 1Password CLI not available or not authenticated")
            print("💡 Install 1Password CLI and run 'op account add' to set up")
            return

        # Prompt for 1Password reference
        print("\n📝 To get your Linear API key reference from 1Password:")
        print("   1. Open the Linear API key item in 1Password")
        print("   2. Right-click on the password/secret field")
        print("   3. Select 'Copy Secret Reference'")
        print()
        reference = input("Enter 1Password reference (e.g., op://Private/linear-api-key/password): ").strip()
        if reference:
            # Strip quotes that 1Password includes in "Copy Secret Reference"
            reference = reference.strip("\"'")

            # Test the reference
            api_key = OnePasswordIntegration.get_secret(reference)
            if api_key:
                try:
                    self._store_linear_1password_ref(reference)
                    print("✅ 1Password reference stored and validated")
                except ValueError as e:
                    print(f"❌ Failed to store reference: {e}")
                    return
            else:
                print("❌ Could not retrieve API key from 1Password reference")
                print("💡 Check that the reference is correct and you're authenticated")
                return
        else:
            print("❌ No reference provided")
            return

    def cmd_linear_test(self, args):  # noqa: ARG002
        """Test Linear integration"""
        print("🧪 Testing Linear Integration")
        print("-" * 40)

        # Check configuration
        linear_config = self._load_linear_config()
        if not linear_config.get("LINEAR_API_KEY"):
            print("❌ No API key found. Run: cproj linear setup --api-key YOUR_KEY")
            return

        org = self.config.get("linear_org")
        team = self.config.get("linear_default_team")

        print(f"Organization: {org or 'Not configured'}")
        print(f"Default Team: {team or 'Not configured'}")
        print(f"API Key: {'✅ Found' if linear_config.get('LINEAR_API_KEY') else '❌ Missing'}")
        print(
            f"MCP Config: {'✅ Available' if (Path.cwd() / '.claude' / 'mcp_config.json').exists() else '❌ Missing'}"
        )

        # TODO: Add actual API test when Linear MCP is available
        print("\n💡 Basic configuration looks good!")
        print("📝 To fully test, try: add-ticket 'test ticket creation'")

    def cmd_linear_status(self, args):  # noqa: ARG002
        """Show Linear configuration status"""
        print("📊 Linear Integration Status")
        print("-" * 40)

        # Load configurations
        linear_config = self._load_linear_config()

        # Show cproj config
        print("\n🔧 cproj Configuration:")
        print(f"  Organization: {self.config.get('linear_org', 'Not configured')}")
        print(f"  Default Team: {self.config.get('linear_default_team', 'Not configured')}")
        print(f"  Default Project: {self.config.get('linear_default_project', 'Not configured')}")

        # Show secure config
        print("\n🔐 Secure Configuration:")
        print(f"  API Key: {'✅ Configured' if linear_config.get('LINEAR_API_KEY') else '❌ Not configured'}")
        if linear_config.get("LINEAR_API_KEY"):
            key = linear_config["LINEAR_API_KEY"]
            source = linear_config.get("LINEAR_API_KEY_SOURCE", "File")
            print(f"  Key Source: {source}")
            min_key_length = 12
            print(f"  Key Preview: {key[:8]}...{key[-4:] if len(key) > min_key_length else ''}")

        # Show file status
        git_root = self._find_git_root(Path.cwd())
        if git_root:
            env_file = git_root / ".env.linear"
            gitignore_file = git_root / ".gitignore"

            print("\n📁 File Status:")
            print(f"  .env.linear: {'✅ Exists' if env_file.exists() else '❌ Missing'}")
            if env_file.exists():
                print(f"  File permissions: {oct(env_file.stat().st_mode)[-3:]}")

            if gitignore_file.exists():
                with gitignore_file.open() as f:
                    content = f.read()
                    is_ignored = ".env.linear" in content
                    status = "✅ Protected" if is_ignored else "⚠️  Not protected"
                    print(print(f"  .gitignore entry: {status}"))
            else:
                print("  .gitignore: ❌ Missing")

        # Show workspace status
        claude_dir = Path.cwd() / ".claude"
        print("\n🤖 Workspace Status:")
        commands_available = "✅ Yes" if (claude_dir / "commands").exists() else "❌ No"
        agents_available = "✅ Yes" if (claude_dir / "agents").exists() else "❌ No"
        mcp_config_available = "✅ Yes" if (claude_dir / "mcp_config.json").exists() else "❌ No"

        print(f"  Commands available: {commands_available}")
        print(f"  Agents available: {agents_available}")
        print(f"  MCP config: {mcp_config_available}")

    # Alias methods for integration tests compatibility
    def cmd_setup(self, args):
        """Alias for cmd_init"""
        return self.cmd_init(args)

    def cmd_create(self, args):
        """Alias for cmd_worktree_create"""
        return self.cmd_worktree_create(args)


def main():
    """Entry point for CLI"""
    cli = CprojCLI()
    cli.run()


if __name__ == "__main__":
    main()
