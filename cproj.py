#!/usr/bin/env python3
"""
cproj - Multi-project CLI with git worktree + uv
A production-ready CLI tool for managing parallel project work using Git worktrees
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import tempfile
import getpass


class CprojError(Exception):
    """Base exception for cproj errors"""
    pass


class OnePasswordIntegration:
    """1Password CLI integration for secret management"""
    
    @staticmethod
    def is_available() -> bool:
        """Check if 1Password CLI is available and authenticated"""
        if not shutil.which('op'):
            return False
        
        try:
            # Check if authenticated
            subprocess.run(['op', 'account', 'list'], check=True, 
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
            result = subprocess.run(
                ['op', 'read', reference], 
                capture_output=True, text=True, check=True, timeout=10
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None
    
    @staticmethod 
    def store_secret(title: str, value: str, vault: str = None) -> Optional[str]:
        """Store secret in 1Password and return reference"""
        if not OnePasswordIntegration.is_available():
            return None
        
        try:
            cmd = ['op', 'item', 'create', '--category=password', f'--title={title}']
            if vault:
                cmd.append(f'--vault={vault}')
            cmd.append(f'password={value}')
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
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
        
        if OnePasswordIntegration.is_available() and store_choice == 'y':
            vault = input("1Password vault name (or press Enter for Private): ").strip() or None
            reference = OnePasswordIntegration.store_secret(f"cproj-{secret_name}", secret_value, vault)
            if reference:
                print(f"Stored in 1Password. Reference: {reference}")
                return reference
        
        return secret_value


class Config:
    """Configuration management"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path.home() / '.config' / 'cproj' / 'config.json'
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config = self._load_config()
    
    def _load_config(self) -> Dict:
        if self.config_path.exists():
            with open(self.config_path) as f:
                return json.load(f)
        return {}
    
    def save(self):
        with open(self.config_path, 'w') as f:
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
        self._run_git(['fetch', '--all', '--prune'])
    
    def ensure_base_branch(self, base_branch: str):
        """Ensure base branch exists and is up to date"""
        try:
            # Check if branch exists locally
            self._run_git(['show-ref', '--verify', '--quiet', f'refs/heads/{base_branch}'])
        except subprocess.CalledProcessError:
            # Create from origin if it doesn't exist
            try:
                self._run_git(['branch', base_branch, f'origin/{base_branch}'])
            except subprocess.CalledProcessError:
                raise CprojError(f"Base branch '{base_branch}' not found locally or on origin")
        
        # Fast-forward the base branch
        current_branch = self._get_current_branch()
        if current_branch != base_branch:
            self._run_git(['checkout', base_branch])
        
        try:
            self._run_git(['merge', '--ff-only', f'origin/{base_branch}'])
        except subprocess.CalledProcessError:
            print(f"Warning: Could not fast-forward {base_branch}")
        
        if current_branch and current_branch != base_branch:
            self._run_git(['checkout', current_branch])
    
    def create_worktree(self, worktree_path: Path, branch: str, base_branch: str) -> Path:
        """Create a new worktree"""
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if branch already exists
        try:
            self._run_git(['show-ref', '--verify', '--quiet', f'refs/heads/{branch}'])
            # Branch exists, use it
            self._run_git(['worktree', 'add', str(worktree_path), branch])
        except subprocess.CalledProcessError:
            # Branch doesn't exist, create it
            self._run_git(['worktree', 'add', '-b', branch, str(worktree_path), base_branch])
        
        return worktree_path
    
    def remove_worktree(self, worktree_path: Path, force: bool = False):
        """Remove a worktree"""
        cmd = ['worktree', 'remove']
        if force:
            cmd.append('--force')
        cmd.append(str(worktree_path))
        self._run_git(cmd)
    
    def list_worktrees(self) -> List[Dict]:
        """List all worktrees"""
        result = self._run_git(['worktree', 'list', '--porcelain'], capture_output=True, text=True)
        worktrees = []
        current_tree = {}
        
        for line in result.stdout.strip().split('\n'):
            if line.startswith('worktree '):
                if current_tree:
                    worktrees.append(current_tree)
                current_tree = {'path': line.split(' ', 1)[1]}
            elif line.startswith('HEAD '):
                current_tree['commit'] = line.split(' ', 1)[1]
            elif line.startswith('branch '):
                current_tree['branch'] = line.split('refs/heads/', 1)[1]
            elif line == 'bare':
                current_tree['bare'] = True
            elif line == 'detached':
                current_tree['detached'] = True
        
        if current_tree:
            worktrees.append(current_tree)
        
        return worktrees
    
    def get_status(self, worktree_path: Path) -> Dict:
        """Get status for a specific worktree"""
        try:
            # Get ahead/behind info
            result = self._run_git(['rev-list', '--left-right', '--count', 'HEAD...@{u}'], 
                                 cwd=worktree_path, capture_output=True, text=True)
            ahead, behind = map(int, result.stdout.strip().split())
            
            # Check if dirty
            result = self._run_git(['status', '--porcelain'], 
                                 cwd=worktree_path, capture_output=True, text=True)
            dirty = bool(result.stdout.strip())
            
            return {
                'ahead': ahead,
                'behind': behind,
                'dirty': dirty
            }
        except subprocess.CalledProcessError:
            return {'ahead': 0, 'behind': 0, 'dirty': False}
    
    def push_branch(self, branch: str, worktree_path: Path):
        """Push branch to origin"""
        self._run_git(['push', '-u', 'origin', branch], cwd=worktree_path)
    
    def is_branch_dirty(self, worktree_path: Path) -> bool:
        """Check if worktree has uncommitted changes"""
        try:
            result = self._run_git(['status', '--porcelain'], 
                                 cwd=worktree_path, capture_output=True, text=True)
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False
    
    def _get_current_branch(self) -> Optional[str]:
        """Get current branch name"""
        try:
            result = self._run_git(['branch', '--show-current'], capture_output=True, text=True)
            return result.stdout.strip() or None
        except subprocess.CalledProcessError:
            return None
    
    def _find_git_root(self, start_path: Path) -> Optional[Path]:
        """Find the git repository root from any subdirectory"""
        current = start_path.absolute()
        
        # Check if current directory is a git repository
        while current != current.parent:
            if (current / '.git').exists():
                return current
            current = current.parent
        
        # Check root directory
        if (current / '.git').exists():
            return current
        
        return None
    
    def _run_git(self, args: List[str], cwd: Optional[Path] = None, **kwargs) -> subprocess.CompletedProcess:
        """Run git command"""
        cmd = ['git', '-C', str(cwd or self.repo_path)] + args
        return subprocess.run(cmd, check=True, **kwargs)


class AgentJson:
    """Manage .agent.json metadata"""
    
    SCHEMA_VERSION = "1.0"
    
    def __init__(self, worktree_path: Path):
        self.path = worktree_path / '.agent.json'
        self.data = self._load() if self.path.exists() else self._default_data()
    
    def _default_data(self) -> Dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "agent": {
                "name": os.environ.get('USER', 'unknown'),
                "email": ""
            },
            "project": {
                "name": "",
                "repo_path": ""
            },
            "workspace": {
                "path": "",
                "branch": "",
                "base": "",
                "created_at": "",
                "created_by": f"cproj-{self._get_version()}"
            },
            "links": {
                "linear": "",
                "pr": ""
            },
            "env": {
                "python": {
                    "manager": "none",
                    "active": False,
                    "pyproject": False,
                    "requirements": False
                },
                "node": {
                    "manager": "none",
                    "node_version": ""
                },
                "java": {
                    "build": "none"
                }
            },
            "notes": ""
        }
    
    def _load(self) -> Dict:
        with open(self.path) as f:
            return json.load(f)
    
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def set_project(self, name: str, repo_path: str):
        self.data['project']['name'] = name
        self.data['project']['repo_path'] = repo_path
    
    def set_workspace(self, path: str, branch: str, base: str):
        self.data['workspace']['path'] = path
        self.data['workspace']['branch'] = branch
        self.data['workspace']['base'] = base
        self.data['workspace']['created_at'] = datetime.now(timezone.utc).isoformat()
    
    def set_link(self, link_type: str, url: str):
        if link_type in self.data['links']:
            self.data['links'][link_type] = url
    
    def set_env(self, env_type: str, env_data: Dict):
        if env_type in self.data['env']:
            self.data['env'][env_type].update(env_data)
    
    def close_workspace(self):
        self.data['workspace']['closed_at'] = datetime.now(timezone.utc).isoformat()
    
    @staticmethod
    def _get_version() -> str:
        return "1.0.0"


class EnvironmentSetup:
    """Environment setup for different languages"""
    
    def __init__(self, worktree_path: Path):
        self.worktree_path = worktree_path
    
    def setup_python(self, auto_install: bool = False) -> Dict:
        """Setup Python environment with uv or venv"""
        env_data = {
            "manager": "none",
            "active": False,
            "pyproject": False,
            "requirements": False
        }
        
        # Check for project files
        pyproject_exists = (self.worktree_path / 'pyproject.toml').exists()
        requirements_exists = (self.worktree_path / 'requirements.txt').exists()
        
        env_data['pyproject'] = pyproject_exists
        env_data['requirements'] = requirements_exists
        
        if not (pyproject_exists or requirements_exists):
            return env_data
        
        # Try uv first
        if shutil.which('uv'):
            try:
                subprocess.run(['uv', 'venv'], cwd=self.worktree_path, check=True, 
                             capture_output=True)
                env_data['manager'] = 'uv'
                env_data['active'] = True
                
                if auto_install and (pyproject_exists or requirements_exists):
                    subprocess.run(['uv', 'pip', 'sync'] if pyproject_exists else 
                                 ['uv', 'pip', 'install', '-r', 'requirements.txt'], 
                                 cwd=self.worktree_path, check=True, capture_output=True)
                
                return env_data
            except subprocess.CalledProcessError:
                pass
        
        # Fallback to venv
        try:
            subprocess.run([sys.executable, '-m', 'venv', '.venv'], 
                         cwd=self.worktree_path, check=True, capture_output=True)
            env_data['manager'] = 'venv'
            env_data['active'] = True
            
            if auto_install and requirements_exists:
                pip_cmd = str(self.worktree_path / '.venv' / 'bin' / 'pip')
                if platform.system() == 'Windows':
                    pip_cmd = str(self.worktree_path / '.venv' / 'Scripts' / 'pip.exe')
                
                subprocess.run([pip_cmd, 'install', '-r', 'requirements.txt'], 
                             cwd=self.worktree_path, check=True, capture_output=True)
        
        except subprocess.CalledProcessError:
            pass
        
        return env_data
    
    def setup_node(self, auto_install: bool = False) -> Dict:
        """Setup Node environment with nvm"""
        env_data = {
            "manager": "none",
            "node_version": ""
        }
        
        package_json = self.worktree_path / 'package.json'
        nvmrc = self.worktree_path / '.nvmrc'
        
        if not package_json.exists():
            return env_data
        
        # Check if nvm is available
        nvm_path = Path.home() / '.nvm' / 'nvm.sh'
        if not nvm_path.exists():
            return env_data
        
        env_data['manager'] = 'nvm'
        
        try:
            # Use node version from .nvmrc or LTS
            if nvmrc.exists():
                with open(nvmrc) as f:
                    node_version = f.read().strip()
            else:
                node_version = 'lts/*'
            
            # This would require shell integration in a real implementation
            # For now, just record what we would do
            env_data['node_version'] = node_version
            
        except Exception:
            pass
        
        return env_data
    
    def setup_java(self, auto_build: bool = False) -> Dict:
        """Setup Java environment"""
        env_data = {"build": "none"}
        
        if (self.worktree_path / 'pom.xml').exists():
            env_data['build'] = 'maven'
            if auto_build:
                try:
                    subprocess.run(['mvn', 'compile', '-DskipTests'], 
                                 cwd=self.worktree_path, check=True, capture_output=True)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass
        
        elif any((self.worktree_path / f).exists() for f in ['build.gradle', 'build.gradle.kts']):
            env_data['build'] = 'gradle'
            if auto_build:
                try:
                    subprocess.run(['./gradlew', 'compileJava'], 
                                 cwd=self.worktree_path, check=True, capture_output=True)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass
        
        return env_data


class TerminalAutomation:
    """Terminal and editor automation"""
    
    @staticmethod
    def open_terminal(path: Path, title: str, terminal_app: str = 'Terminal'):
        """Open terminal at path with title"""
        if platform.system() != 'Darwin':
            print(f"Terminal automation not supported on {platform.system()}")
            return
        
        if terminal_app.lower() == 'iterm':
            script = f'''
            tell application "iTerm"
                create window with default profile
                tell current session of current window
                    write text "cd '{path}'"
                    set name to "{title}"
                end tell
            end tell
            '''
        else:  # Terminal
            script = f'''
            tell application "Terminal"
                do script "cd '{path}'"
                set custom title of front window to "{title}"
            end tell
            '''
        
        try:
            subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
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
        return shutil.which('gh') is not None
    
    @staticmethod
    def ensure_auth() -> bool:
        """Ensure GitHub authentication, using 1Password if needed"""
        if not GitHubIntegration.is_available():
            return False
        
        try:
            # Check if already authenticated
            subprocess.run(['gh', 'auth', 'status'], check=True, capture_output=True)
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
                        env['GH_TOKEN'] = token
                        subprocess.run(['gh', 'auth', 'login', '--with-token'], 
                                     input=token, text=True, check=True, 
                                     capture_output=True, env=env)
                        return True
                    except subprocess.CalledProcessError:
                        print("Failed to authenticate with 1Password token")
            
            # Interactive login
            try:
                subprocess.run(['gh', 'auth', 'login'], check=True)
                return True
            except subprocess.CalledProcessError:
                print("GitHub authentication failed")
                return False
    
    @staticmethod
    def create_pr(title: str, body: str, draft: bool = True, assignees: Optional[List[str]] = None) -> Optional[str]:
        """Create a pull request"""
        if not GitHubIntegration.ensure_auth():
            return None
        
        cmd = ['gh', 'pr', 'create', '--title', title, '--body', body]
        
        if draft:
            cmd.append('--draft')
        
        if assignees:
            cmd.extend(['--assignee', ','.join(assignees)])
        
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
        
        cmd = ['gh', 'pr', 'merge']
        
        if squash:
            cmd.append('--squash')
        
        if delete_branch:
            cmd.append('--delete-branch')
        
        try:
            subprocess.run(cmd, check=True)
            return True
        except subprocess.CalledProcessError:
            return False


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
        config['project_name'] = project_name or "My Project"
        
        # Repository
        repo_input = input("Repository path or URL (. for current directory): ").strip()
        if repo_input == '.' or not repo_input:
            repo_path = Path.cwd()
            # If we're in a subdirectory of a git repo, find the root
            git_root = self._find_git_root(repo_path)
            if git_root:
                repo_path = git_root
                print(f"Found git repository root at: {repo_path}")
        elif repo_input.startswith('http'):
            # It's a URL, we'll clone it
            clone_to = input(f"Clone to directory [{Path.home() / 'dev' / project_name}]: ").strip()
            repo_path = Path(clone_to) if clone_to else (Path.home() / 'dev' / project_name)
            config['clone_url'] = repo_input
        else:
            repo_path = Path(repo_input).expanduser().absolute()
            # If the path exists and is inside a git repo, find the root
            if repo_path.exists():
                git_root = self._find_git_root(repo_path)
                if git_root:
                    repo_path = git_root
                    print(f"Found git repository root at: {repo_path}")
        
        config['repo_path'] = str(repo_path)
        
        base_branch = input("Default base branch [main]: ").strip()
        config['base_branch'] = base_branch or 'main'
        
        print()
        
        # Workspace policy
        print("🏗️  Workspace Policy")
        print("-" * 50)
        
        default_temp = str(Path.home() / '.cache' / 'cproj-workspaces')
        temp_root = input(f"Temp root for worktrees [{default_temp}]: ").strip()
        config['temp_root'] = temp_root or default_temp
        
        branch_scheme = input("Branch naming scheme [feature/{ticket}-{slug}]: ").strip()
        config['branch_scheme'] = branch_scheme or 'feature/{ticket}-{slug}'
        
        cleanup_days = input("Auto-cleanup age threshold (days) [14]: ").strip()
        try:
            config['cleanup_days'] = int(cleanup_days) if cleanup_days else 14
        except ValueError:
            config['cleanup_days'] = 14
        
        print()
        
        # Environment setup
        print("🐍 Environment Setup")
        print("-" * 50)
        
        use_uv = input("Prefer uv for Python? [Y/n]: ").strip().lower()
        config['python_prefer_uv'] = use_uv not in ['n', 'no']
        
        auto_install_python = input("Auto-install Python dependencies? [Y/n]: ").strip().lower()
        config['python_auto_install'] = auto_install_python not in ['n', 'no']
        
        use_nvm = input("Use nvm for Node? [Y/n]: ").strip().lower()
        config['node_use_nvm'] = use_nvm not in ['n', 'no']
        
        auto_install_node = input("Auto-install Node dependencies? [Y/n]: ").strip().lower()
        config['node_auto_install'] = auto_install_node not in ['n', 'no']
        
        auto_build_java = input("Auto-build Java projects? [y/N]: ").strip().lower()
        config['java_auto_build'] = auto_build_java in ['y', 'yes']
        
        print()
        
        # Tools
        print("🛠️  Tools & Automation")
        print("-" * 50)
        
        if platform.system() == 'Darwin':
            terminal = input("Terminal app [Terminal/iTerm/none]: ").strip()
            if terminal.lower() in ['iterm', 'iterm2']:
                config['terminal'] = 'iTerm'
            elif terminal.lower() == 'none':
                config['terminal'] = 'none'
            else:
                config['terminal'] = 'Terminal'
        else:
            config['terminal'] = 'none'
        
        editor = input("Editor command [code]: ").strip()
        config['editor'] = editor or 'code'
        
        print()
        
        # Integrations
        print("🔗 Integrations")
        print("-" * 50)
        
        linear_org = input("Linear organization URL (optional): ").strip()
        if linear_org:
            config['linear_org'] = linear_org
        
        github_default_reviewers = input("Default GitHub reviewers (comma-separated, optional): ").strip()
        if github_default_reviewers:
            config['github_reviewers'] = [r.strip() for r in github_default_reviewers.split(',')]
        
        draft_prs = input("Create draft PRs by default? [Y/n]: ").strip().lower()
        config['github_draft_default'] = draft_prs not in ['n', 'no']
        
        print()
        
        # 1Password integration
        if OnePasswordIntegration.is_available():
            print("🔐 1Password Integration")
            print("-" * 50)
            print("1Password CLI detected! You can store GitHub tokens and other secrets securely.")
            
            use_1password = input("Use 1Password for secrets? [Y/n]: ").strip().lower()
            config['use_1password'] = use_1password not in ['n', 'no']
            
            if config.get('use_1password'):
                vault = input("Default 1Password vault [Private]: ").strip()
                config['onepassword_vault'] = vault or 'Private'
            
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
        
        if config.get('linear_org'):
            print(f"Linear: {config['linear_org']}")
        if config.get('github_reviewers'):
            print(f"GitHub reviewers: {', '.join(config['github_reviewers'])}")
        if config.get('use_1password'):
            print(f"1Password: enabled (vault: {config.get('onepassword_vault')})")
        
        print()
        
        confirm = input("Save this configuration? [Y/n]: ").strip().lower()
        if confirm in ['n', 'no']:
            print("Configuration cancelled.")
            sys.exit(1)
        
        return config
        
    def create_parser(self) -> argparse.ArgumentParser:
        """Create argument parser"""
        parser = argparse.ArgumentParser(description='Multi-project CLI with git worktree + uv')
        parser.add_argument('--repo', help='Repository path')
        parser.add_argument('--base', help='Base branch')
        parser.add_argument('--temp-root', help='Temp root for worktrees')
        parser.add_argument('--terminal', choices=['Terminal', 'iTerm', 'none'], help='Terminal app')
        parser.add_argument('--editor', help='Editor command')
        parser.add_argument('--yes', action='store_true', help='Skip confirmations')
        parser.add_argument('--verbose', action='store_true', help='Verbose output')
        parser.add_argument('--json', action='store_true', help='JSON output')
        
        subparsers = parser.add_subparsers(dest='command', help='Commands')
        
        # init command
        init_parser = subparsers.add_parser('init', aliases=['new', 'start'], help='Initialize project')
        init_parser.add_argument('--name', help='Project name')
        init_parser.add_argument('--clone', help='Clone URL if repo not local')
        
        # worktree create command
        wt_create = subparsers.add_parser('worktree', help='Worktree commands')
        wt_sub = wt_create.add_subparsers(dest='worktree_command')
        
        create_parser = wt_sub.add_parser('create', help='Create worktree')
        create_parser.add_argument('--branch', required=True, help='Branch name')
        create_parser.add_argument('--linear', help='Linear issue URL')
        create_parser.add_argument('--python-install', action='store_true', help='Auto-install Python deps')
        create_parser.add_argument('--node-install', action='store_true', help='Auto-install Node deps')
        create_parser.add_argument('--java-build', action='store_true', help='Auto-build Java')
        create_parser.add_argument('--no-open', action='store_true', help='Don\'t open terminal/editor')
        
        # review command
        review_parser = subparsers.add_parser('review', help='Review commands')
        review_sub = review_parser.add_subparsers(dest='review_command')
        
        open_parser = review_sub.add_parser('open', help='Open review')
        open_parser.add_argument('--draft', action='store_true', help='Create draft PR')
        open_parser.add_argument('--ready', action='store_true', help='Create ready PR')
        open_parser.add_argument('--assign', help='Assignees (comma-separated)')
        open_parser.add_argument('--no-push', action='store_true', help='Don\'t push branch')
        
        # merge command
        merge_parser = subparsers.add_parser('merge', help='Merge and cleanup')
        merge_parser.add_argument('--squash', action='store_true', default=True, help='Squash merge')
        merge_parser.add_argument('--merge', dest='squash', action='store_false', help='Merge commit')
        merge_parser.add_argument('--delete-remote', action='store_true', help='Delete remote branch')
        merge_parser.add_argument('--keep-worktree', action='store_true', help='Keep worktree')
        merge_parser.add_argument('--force', action='store_true', help='Force merge even if dirty')
        
        # list command
        subparsers.add_parser('list', aliases=['ls'], help='List worktrees')
        
        # status command
        status_parser = subparsers.add_parser('status', aliases=['st'], help='Show status')
        status_parser.add_argument('path', nargs='?', help='Worktree path')
        
        # cleanup command
        cleanup_parser = subparsers.add_parser('cleanup', help='Cleanup worktrees')
        cleanup_parser.add_argument('--older-than', type=int, help='Days old')
        cleanup_parser.add_argument('--merged-only', action='store_true', help='Only merged branches')
        cleanup_parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
        
        # open command
        open_parser = subparsers.add_parser('open', help='Open workspace')
        open_parser.add_argument('path', nargs='?', help='Worktree path')
        
        # config command
        config_parser = subparsers.add_parser('config', help='Configuration')
        config_parser.add_argument('key', nargs='?', help='Config key')
        config_parser.add_argument('value', nargs='?', help='Config value')
        
        return parser
    
    def run(self, args: Optional[List[str]] = None):
        """Main entry point"""
        parser = self.create_parser()
        parsed_args = parser.parse_args(args)
        
        try:
            if parsed_args.command == 'init' or parsed_args.command in ['new', 'start']:
                self.cmd_init(parsed_args)
            elif parsed_args.command == 'worktree' and parsed_args.worktree_command == 'create':
                self.cmd_worktree_create(parsed_args)
            elif parsed_args.command == 'review' and parsed_args.review_command == 'open':
                self.cmd_review_open(parsed_args)
            elif parsed_args.command == 'merge':
                self.cmd_merge(parsed_args)
            elif parsed_args.command in ['list', 'ls']:
                self.cmd_list(parsed_args)
            elif parsed_args.command in ['status', 'st']:
                self.cmd_status(parsed_args)
            elif parsed_args.command == 'cleanup':
                self.cmd_cleanup(parsed_args)
            elif parsed_args.command == 'open':
                self.cmd_open(parsed_args)
            elif parsed_args.command == 'config':
                self.cmd_config(parsed_args)
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
            if (current / '.git').exists():
                return current
            current = current.parent
        
        # Check root directory
        if (current / '.git').exists():
            return current
        
        return None
    
    def cmd_init(self, args):
        """Initialize project"""
        # If no arguments provided, run interactive configuration
        if not any([args.repo, args.name, args.clone]) and not self.config.get('repo_path'):
            config_data = self._prompt_for_config()
            
            # Save all configuration
            for key, value in config_data.items():
                self.config.set(key, value)
            
            # Handle repository setup
            repo_path = Path(config_data['repo_path'])
            
            # Clone if URL provided
            if config_data.get('clone_url'):
                if not repo_path.parent.exists():
                    repo_path.parent.mkdir(parents=True, exist_ok=True)
                
                print(f"Cloning {config_data['clone_url']} to {repo_path}...")
                try:
                    subprocess.run(['git', 'clone', config_data['clone_url'], str(repo_path)], check=True)
                    print("Repository cloned successfully!")
                except subprocess.CalledProcessError as e:
                    raise CprojError(f"Failed to clone repository: {e}")
            
        else:
            # Handle command-line arguments (legacy mode)
            repo_path = Path(args.repo or self.config.get('repo_path', '.'))
            
            if args.clone and not repo_path.exists():
                subprocess.run(['git', 'clone', args.clone, str(repo_path)], check=True)
            else:
                # Find git root if we're in a subdirectory
                git_root = self._find_git_root(repo_path)
                if git_root:
                    repo_path = git_root
            
            project_name = args.name or repo_path.name
            base_branch = args.base or self.config.get('base_branch', 'main')
            
            self.config.set('repo_path', str(repo_path.absolute()))
            self.config.set('project_name', project_name)
            self.config.set('base_branch', base_branch)
        
        # Verify git repository and find root
        final_repo_path = Path(self.config.get('repo_path'))
        git_root = self._find_git_root(final_repo_path)
        if not git_root:
            raise CprojError(f"Not a git repository: {final_repo_path}")
        
        # Update config with the actual git root
        if git_root != final_repo_path:
            self.config.set('repo_path', str(git_root))
            final_repo_path = git_root
        
        print(f"✅ Initialized project '{self.config.get('project_name')}' at {final_repo_path}")
        
        # Create temp directory if it doesn't exist
        temp_root = Path(self.config.get('temp_root', str(Path.home() / '.cache' / 'cproj-workspaces')))
        temp_root.mkdir(parents=True, exist_ok=True)
        
        # Show next steps
        print()
        print("🎉 Ready to go! Try these commands:")
        print(f"  cproj worktree create --branch feature/awesome-feature")
        print(f"  cproj list")
        print(f"  cproj config")
        
        # Show tool availability
        missing_tools = []
        if not shutil.which('git'):
            missing_tools.append('git')
        if not shutil.which('uv') and self.config.get('python_prefer_uv'):
            print("💡 Note: uv not found, will use venv as fallback")
        if not shutil.which('gh'):
            missing_tools.append('gh (for GitHub integration)')
        if not OnePasswordIntegration.is_available() and self.config.get('use_1password'):
            missing_tools.append('op (1Password CLI)')
        
        if missing_tools:
            print(f"⚠️  Missing tools: {', '.join(missing_tools)}")
            print("   Install them for full functionality")
    
    def cmd_worktree_create(self, args):
        """Create worktree"""
        repo_path = Path(args.repo or self.config.get('repo_path', '.'))
        base_branch = args.base or self.config.get('base_branch', 'main')
        temp_root = Path(args.temp_root or self.config.get('temp_root', tempfile.gettempdir()) or tempfile.gettempdir())
        project_name = self.config.get('project_name', repo_path.name)
        
        git = GitWorktree(repo_path)
        
        # Fetch and ensure base branch
        git.fetch_all()
        git.ensure_base_branch(base_branch)
        
        # Create worktree path
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        worktree_name = f"{project_name}_{args.branch}_{timestamp}"
        worktree_path = temp_root / worktree_name
        
        # Create worktree
        git.create_worktree(worktree_path, args.branch, base_branch)
        
        # Setup environment
        env_setup = EnvironmentSetup(worktree_path)
        python_env = env_setup.setup_python(args.python_install)
        node_env = env_setup.setup_node(args.node_install)
        java_env = env_setup.setup_java(args.java_build)
        
        # Create .agent.json
        agent_json = AgentJson(worktree_path)
        agent_json.set_project(project_name, str(repo_path))
        agent_json.set_workspace(str(worktree_path), args.branch, base_branch)
        agent_json.set_env('python', python_env)
        agent_json.set_env('node', node_env)
        agent_json.set_env('java', java_env)
        
        if args.linear:
            agent_json.set_link('linear', args.linear)
        
        agent_json.save()
        
        print(f"Created worktree: {worktree_path}")
        print(f"Branch: {args.branch}")
        
        # Open terminal and editor
        if not args.no_open:
            terminal_app = args.terminal or self.config.get('terminal', 'Terminal')
            editor = args.editor or self.config.get('editor', 'code')
            
            if terminal_app != 'none':
                TerminalAutomation.open_terminal(worktree_path, f"{project_name}:{args.branch}", terminal_app)
            
            if editor:
                TerminalAutomation.open_editor(worktree_path, editor)
    
    def cmd_review_open(self, args):
        """Open review"""
        worktree_path = Path.cwd()
        agent_json_path = worktree_path / '.agent.json'
        
        if not agent_json_path.exists():
            raise CprojError("Not in a cproj worktree")
        
        agent_json = AgentJson(worktree_path)
        repo_path = Path(agent_json.data['project']['repo_path'])
        branch = agent_json.data['workspace']['branch']
        
        git = GitWorktree(repo_path)
        
        # Push branch
        if not args.no_push:
            git.push_branch(branch, worktree_path)
        
        # Create PR if GitHub available
        if GitHubIntegration.is_available():
            title = f"feat: {branch}"
            body = f"Branch: {branch}"
            
            if agent_json.data['links']['linear']:
                body += f"\n\nLinear: {agent_json.data['links']['linear']}"
            
            draft = not args.ready if args.ready else True
            assignees = args.assign.split(',') if args.assign else None
            
            pr_url = GitHubIntegration.create_pr(title, body, draft, assignees)
            if pr_url:
                agent_json.set_link('pr', pr_url)
                agent_json.save()
                print(f"Created PR: {pr_url}")
        
        print(f"Branch {branch} ready for review")
    
    def cmd_merge(self, args):
        """Merge and cleanup"""
        worktree_path = Path.cwd()
        agent_json_path = worktree_path / '.agent.json'
        
        if not agent_json_path.exists():
            raise CprojError("Not in a cproj worktree")
        
        agent_json = AgentJson(worktree_path)
        repo_path = Path(agent_json.data['project']['repo_path'])
        
        git = GitWorktree(repo_path)
        
        # Check if dirty
        if not args.force and git.is_branch_dirty(worktree_path):
            raise CprojError("Worktree has uncommitted changes. Use --force to override.")
        
        # Merge PR if GitHub available
        if GitHubIntegration.is_available():
            if GitHubIntegration.merge_pr(args.squash, args.delete_remote):
                print("PR merged successfully")
        
        # Close workspace
        agent_json.close_workspace()
        agent_json.save()
        
        # Remove worktree
        if not args.keep_worktree:
            git.remove_worktree(worktree_path, force=True)
            print(f"Removed worktree: {worktree_path}")
    
    def cmd_list(self, args):
        """List worktrees"""
        repo_path = Path(self.config.get('repo_path', '.'))
        
        if not repo_path.exists():
            print("No configured repository")
            return
        
        git = GitWorktree(repo_path)
        worktrees = git.list_worktrees()
        
        if args.json:
            print(json.dumps(worktrees, indent=2))
            return
        
        for wt in worktrees:
            path = Path(wt['path'])
            branch = wt.get('branch', 'N/A')
            
            # Try to load .agent.json for additional info
            agent_json_path = path / '.agent.json'
            if agent_json_path.exists():
                try:
                    agent_json = AgentJson(path)
                    linear = agent_json.data['links']['linear']
                    pr = agent_json.data['links']['pr']
                    
                    print(f"{path} [{branch}]")
                    if linear:
                        print(f"  Linear: {linear}")
                    if pr:
                        print(f"  PR: {pr}")
                except:
                    print(f"{path} [{branch}]")
            else:
                print(f"{path} [{branch}]")
    
    def cmd_status(self, args):
        """Show status"""
        if args.path:
            worktree_path = Path(args.path)
        else:
            worktree_path = Path.cwd()
        
        agent_json_path = worktree_path / '.agent.json'
        if not agent_json_path.exists():
            raise CprojError("Not in a cproj worktree")
        
        agent_json = AgentJson(worktree_path)
        
        if args.json:
            print(json.dumps(agent_json.data, indent=2))
            return
        
        print(f"Workspace: {worktree_path}")
        print(f"Project: {agent_json.data['project']['name']}")
        print(f"Branch: {agent_json.data['workspace']['branch']}")
        print(f"Base: {agent_json.data['workspace']['base']}")
        print(f"Created: {agent_json.data['workspace']['created_at']}")
        
        if agent_json.data['links']['linear']:
            print(f"Linear: {agent_json.data['links']['linear']}")
        if agent_json.data['links']['pr']:
            print(f"PR: {agent_json.data['links']['pr']}")
    
    def cmd_cleanup(self, args):
        """Cleanup worktrees"""
        repo_path = Path(self.config.get('repo_path', '.'))
        
        if not repo_path.exists():
            print("No configured repository")
            return
        
        git = GitWorktree(repo_path)
        worktrees = git.list_worktrees()
        
        to_remove = []
        for wt in worktrees:
            path = Path(wt['path'])
            if path == repo_path:  # Skip main worktree
                continue
            
            should_remove = False
            
            # Check age
            if args.older_than:
                agent_json_path = path / '.agent.json'
                if agent_json_path.exists():
                    try:
                        agent_json = AgentJson(path)
                        created_at = datetime.fromisoformat(
                            agent_json.data['workspace']['created_at'].replace('Z', '+00:00')
                        )
                        age_days = (datetime.now(timezone.utc) - created_at).days
                        if age_days > args.older_than:
                            should_remove = True
                    except:
                        pass
            
            # Check if merged (simplified check)
            if args.merged_only and 'closed_at' in agent_json_path.read_text() if agent_json_path.exists() else False:
                should_remove = True
            
            if should_remove:
                to_remove.append(wt)
        
        if not to_remove:
            print("No worktrees to cleanup")
            return
        
        for wt in to_remove:
            path = Path(wt['path'])
            print(f"Would remove: {path}")
            
            if not args.dry_run:
                if args.yes or input(f"Remove {path}? [y/N] ").lower() == 'y':
                    git.remove_worktree(path, force=True)
                    print(f"Removed: {path}")
    
    def cmd_open(self, args):
        """Open workspace"""
        if args.path:
            worktree_path = Path(args.path)
        else:
            worktree_path = Path.cwd()
        
        agent_json_path = worktree_path / '.agent.json'
        if not agent_json_path.exists():
            raise CprojError("Not in a cproj worktree")
        
        agent_json = AgentJson(worktree_path)
        project_name = agent_json.data['project']['name']
        branch = agent_json.data['workspace']['branch']
        
        terminal_app = args.terminal or self.config.get('terminal', 'Terminal')
        editor = args.editor or self.config.get('editor', 'code')
        
        # Open terminal
        if terminal_app != 'none':
            TerminalAutomation.open_terminal(worktree_path, f"{project_name}:{branch}", terminal_app)
        
        # Open editor
        if editor:
            TerminalAutomation.open_editor(worktree_path, editor)
        
        # Open browser links
        links = agent_json.data['links']
        if links['linear']:
            subprocess.run(['open', links['linear']], check=False)
        if links['pr']:
            subprocess.run(['open', links['pr']], check=False)
    
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


def main():
    """Entry point for CLI"""
    cli = CprojCLI()
    cli.run()


if __name__ == '__main__':
    main()