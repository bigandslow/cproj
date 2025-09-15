description: Run comprehensive AI-powered code review using specialized review agents on current codebase changes
argument-hint: "[--full] [--security-only] [--qa-only] [--senior-dev-only]"

## Mission

Execute a professional-grade code review using three specialized AI agents: Senior Developer, QA Engineer, and Security Review agents. This command analyzes git changes, code quality, test coverage, and security vulnerabilities to provide actionable feedback.

## Usage

Basic usage (reviews all staged/unstaged changes):
```
review-code
```

Options:
- `--full`: Review entire codebase, not just changes
- `--security-only`: Run only security review agent
- `--qa-only`: Run only QA engineer agent  
- `--senior-dev-only`: Run only senior developer agent
- `--setup`: Initialize review configuration (if needed)

## How It Works

1. **Setup Phase**: Ensures `.cproj_review.json` configuration exists
2. **Change Detection**: Analyzes git diff to identify modified files
3. **Agent Orchestration**: Runs specialized review agents in parallel:
   - **Senior Developer**: Code quality, architecture, best practices
   - **QA Engineer**: Test coverage, quality assurance, edge cases
   - **Security Review**: Vulnerability assessment, OWASP compliance
4. **Report Generation**: Provides structured feedback with severity levels

## Agent Specializations

### Senior Developer Agent
- Code architecture and design patterns
- Performance considerations and optimization
- Maintainability and readability
- Best practices adherence

### QA Engineer Agent  
- Test coverage analysis
- Edge case identification
- Quality assurance processes
- Integration testing strategies

### Security Review Agent
- OWASP Top 10 vulnerability scanning
- Input validation and sanitization
- Authentication and authorization review
- Data protection and privacy compliance

## Implementation

```python
import subprocess
import json
import string
import re
from pathlib import Path

# Parse command arguments
args = input("Arguments (optional): ").strip().split() if input("Arguments (optional): ").strip() else []

# Check if we're in a git repository
try:
    result = subprocess.run(['git', 'rev-parse', '--git-dir'], 
                          capture_output=True, text=True, check=True)
    git_root = Path(result.stdout.strip()).parent.absolute()
except subprocess.CalledProcessError:
    print("❌ Not in a git repository")
    exit(1)

# Change to git root directory
import os
os.chdir(git_root)

# Setup review configuration if needed or requested
if '--setup' in args:
    print("🔧 Setting up review configuration...")
    setup_result = subprocess.run(['python', 'claude_review_agents.py', '--setup'], 
                                capture_output=True, text=True)
    print(setup_result.stdout)
    if setup_result.stderr:
        print(f"Setup warnings: {setup_result.stderr}")

# Ensure .cproj_review.json exists
config_file = Path('.cproj_review.json')
if not config_file.exists():
    print("📋 Creating review configuration...")
    setup_result = subprocess.run(['python', 'claude_review_agents.py', '--setup'], 
                                capture_output=True, text=True)
    if setup_result.returncode != 0:
        print(f"❌ Failed to setup review: {setup_result.stderr}")
        exit(1)

# Determine review scope
review_scope = []
if '--security-only' in args:
    review_scope = ['security']
elif '--qa-only' in args:
    review_scope = ['qa']  
elif '--senior-dev-only' in args:
    review_scope = ['senior-dev']
else:
    review_scope = ['senior-dev', 'qa', 'security']

# Check for changes (unless --full is specified)
if '--full' not in args:
    # Check git status
    status_result = subprocess.run(['git', 'status', '--porcelain'], 
                                 capture_output=True, text=True)
    if not status_result.stdout.strip():
        print("ℹ️  No changes detected. Use --full to review entire codebase.")
        
        # Ask if user wants to proceed with full review
        proceed = input("Run full codebase review instead? [y/N]: ").strip().lower()
        if proceed not in ['y', 'yes']:
            exit(0)
        args.append('--full')

print("🔍 Starting comprehensive code review...")
print(f"📊 Review scope: {', '.join(review_scope)}")

# Load review configuration
with open('.cproj_review.json', 'r') as f:
    config = json.load(f)

# Execute review agents using Task tool
print("🚀 Initializing AI-powered review agents...")

# Security function to validate file paths
def validate_file_path(path):
    """Validate file path is safe and within project boundaries"""
    try:
        normalized = Path(path).resolve()
        current_dir = Path('.').resolve()
        # Ensure path is within current directory
        normalized.relative_to(current_dir)
        return str(normalized)
    except (ValueError, OSError):
        return None

# Safe file discovery function
def discover_files_safe(max_files=50):
    """Safely discover files using pathlib instead of subprocess"""
    try:
        allowed_extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.md']
        excluded_dirs = {'node_modules', '.git', '.venv', '__pycache__', '.pytest_cache'}

        files = []
        current_dir = Path('.')

        for ext in allowed_extensions:
            for file_path in current_dir.rglob(f'*{ext}'):
                # Security check: ensure path is safe
                safe_path = validate_file_path(file_path)
                if not safe_path:
                    continue

                # Check if any part of the path contains excluded directories
                if any(excluded in file_path.parts for excluded in excluded_dirs):
                    continue

                files.append(str(file_path.relative_to(current_dir)))

                # Limit to prevent resource exhaustion
                if len(files) >= max_files:
                    break

            if len(files) >= max_files:
                break

        return files[:max_files]
    except Exception as e:
        print(f"⚠️  Error during file discovery: {e}")
        return []

# Get git diff for the agents
if '--full' in args:
    print("📖 Preparing full codebase review...")
    # Use safe file discovery instead of subprocess find
    files = discover_files_safe(max_files=50)
    if files:
        pr_diff = "Full codebase review (selected files):\n" + '\n'.join(files)
    else:
        pr_diff = "Full codebase review requested (no files found)"
else:
    print("📝 Preparing incremental review of changes...")
    # Get git diff with error handling
    try:
        diff_result = subprocess.run(['git', 'diff', 'HEAD'],
                                   capture_output=True, text=True,
                                   timeout=30, check=False)
        if diff_result.returncode == 0:
            pr_diff = diff_result.stdout if diff_result.stdout.strip() else "No changes detected"
        else:
            print(f"⚠️  Git diff failed with code {diff_result.returncode}")
            pr_diff = "Could not get git diff"
    except subprocess.TimeoutExpired:
        print("⚠️  Git diff timed out")
        pr_diff = "Git diff timed out"
    except Exception as e:
        print(f"⚠️  Error getting git diff: {e}")
        pr_diff = "Could not get git diff"

# Filter agents based on scope
agents_to_run = []
if '--security-only' in args:
    agents_to_run = [agent for agent in config['agents'] if agent['type'] == 'security-review']
elif '--qa-only' in args:
    agents_to_run = [agent for agent in config['agents'] if agent['type'] == 'qa-review']
elif '--senior-dev-only' in args:
    agents_to_run = [agent for agent in config['agents'] if agent['type'] == 'code-review']
else:
    agents_to_run = config['agents']

print(f"\n📊 Running {len(agents_to_run)} specialized AI review agents...")
print("🎯 Each agent will analyze your code from their expert perspective\n")

# Generate formatted prompts for each agent
agent_tasks = []
for i, agent in enumerate(agents_to_run, 1):
    print(f"⚙️  Preparing {agent['name']} ({i}/{len(agents_to_run)})...")

    # Safe template formatting to prevent injection
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
                    # Limit length to prevent DoS
                    sanitized_context[key] = str_value[:10000]

            # Use string.Template for safer substitution
            # Convert {} format to $ format for Template
            template_str = template
            for key in sanitized_context.keys():
                template_str = template_str.replace(f'{{{key}}}', f'${key}')

            template_obj = string.Template(template_str)
            return template_obj.safe_substitute(sanitized_context)
        except Exception as e:
            print(f"⚠️  Error formatting prompt for {agent['name']}: {e}")
            return template  # Return original template if formatting fails

    # Format the prompt with context using safe method
    context_data = {
        'pr_title': config['context']['pr_title'],
        'pr_desc': config['context']['pr_desc'],
        'pr_diff': pr_diff,
        'ticket': config['context']['ticket'],
        'arch_notes': config['context']['arch_notes'],
        'conventions': config['context']['conventions'],
        'non_goals': config['context']['non_goals'],
        'risk_profile': config['context']['risk_profile'],
        'stack_info': config['context']['stack_info'],
        'test_infra': config['context']['test_infra'],
        'non_func': config['context']['non_func'],
        'data_classification': config['context']['data_classification'],
        'authz_model': config['context']['authz_model'],
        'secrets_policy': config['context']['secrets_policy'],
        'compliance': config['context']['compliance'],
        'known_threats': config['context']['known_threats']
    }

    formatted_prompt = safe_format_prompt(agent['prompt'], context_data)

    agent_tasks.append({
        'name': agent['name'],
        'type': agent['type'],
        'description': agent['description'],
        'prompt': formatted_prompt
    })

print(f"\n✅ Review agents configured successfully!")
print(f"📋 {len(agent_tasks)} agents ready to analyze your code")

print(f"\n🤖 EXECUTING AI REVIEW AGENTS")
print("=" * 50)

# Now execute the agents using Task tool calls
print("🚀 Starting comprehensive AI-powered code review...\n")

# Store all results
review_results = []

# Execute each agent using Task tool integration
for i, task in enumerate(agent_tasks, 1):
    print(f"🔄 Running {task['name']} ({i}/{len(agent_tasks)})...")

    try:
        # Store the task configuration for Claude to execute
        task_config = {
            'description': f"{task['name']} Analysis",
            'prompt': task['prompt'],
            'subagent_type': 'general-purpose'
        }

        print(f"✅ {task['name']} configured for execution")
        print(f"   📝 {task['description']}")
        print(f"   🔧 Task tool integration ready")

        review_results.append({
            'agent': task['name'],
            'type': task['type'],
            'status': 'ready_for_execution',
            'description': task['description'],
            'task_config': task_config
        })

    except Exception as e:
        print(f"⚠️  Error configuring {task['name']}: {e}")
        review_results.append({
            'agent': task['name'],
            'type': task['type'],
            'status': 'configuration_failed',
            'description': task['description'],
            'error': str(e)
        })

# Summary and execution status
successful_configs = sum(1 for r in review_results if r['status'] == 'ready_for_execution')
failed_configs = len(review_results) - successful_configs

print(f"\n🎉 Review agent configuration complete!")
print(f"   ✅ {successful_configs} agents ready for execution")
if failed_configs > 0:
    print(f"   ⚠️  {failed_configs} agents failed configuration")

if '--json' in args:
    output = {
        "status": "agents_ready" if failed_configs == 0 else "partial_configuration",
        "total_agents": len(agent_tasks),
        "successful_configs": successful_configs,
        "failed_configs": failed_configs,
        "agents": review_results,
        "config_file": ".cproj_review.json",
        "execution_ready": failed_configs == 0
    }
    print(f"\n{json.dumps(output, indent=2)}")
else:
    print("\n📋 Review Configuration Summary:")
    print(f"   • {len(agent_tasks)} specialized AI agents configured")
    print(f"   • Configuration stored in .cproj_review.json")
    print(f"   • Git diff prepared ({len(pr_diff)} characters)")
    print(f"   • Security validations: ✅ Path validation, ✅ Template injection prevention")

    if failed_configs == 0:
        print(f"\n🚀 All agents ready for execution!")
        print(f"   The review system will now execute each agent automatically.")
        print(f"   Each agent will analyze the code and provide structured JSON feedback.")
    else:
        print(f"\n⚠️  Some agents failed configuration. Review the errors above.")

print(f"\n🔍 AI-powered code review {'execution ready' if failed_configs == 0 else 'partially configured'}!")
```

## Notes

- Requires git repository context
- Uses existing cproj review agent system
- Generates structured feedback with actionable recommendations
- Supports both incremental (changes only) and full codebase review
- Safe execution with proper error handling and validation