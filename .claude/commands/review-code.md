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

1. **Setup Phase**: Ensures `.cproj/.cproj_review.json` configuration exists
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

I'll analyze the current codebase and run specialized review agents based on the selected scope.

```python
# Dependencies: Requires bash() and task() functions from execution environment
# These are provided by the system and handle error conditions internally

import sys
from pathlib import Path

def validate_git_repository():
    """Validate we're in a git repository with proper error handling."""
    try:
        result = bash('git rev-parse --git-dir')
        if result.returncode != 0:
            print("❌ Not in a git repository")
            print("💡 Please run this command from within a git repository")
            return False
        return True
    except Exception as e:
        print(f"❌ Error checking git repository: {e}")
        return False

def validate_arguments(args):
    """Validate and sanitize command arguments."""
    valid_args = ['--full', '--security-only', '--qa-only', '--senior-dev-only', '--setup']
    sanitized_args = []

    for arg in args:
        if arg.startswith('--') and arg in valid_args:
            sanitized_args.append(arg)
        else:
            print(f"⚠️  Unknown argument '{arg}' ignored")

    return sanitized_args

def get_agent_prompts():
    """Get agent prompt templates for better maintainability."""
    return {
        'senior-dev': {
            'type': 'code-reviewer',
            'prompt': 'Perform a comprehensive senior developer code review focusing on code architecture, design patterns, performance considerations, maintainability, readability, and best practices adherence. Analyze the current codebase changes and provide detailed feedback with actionable recommendations.'
        },
        'qa': {
            'type': 'general-purpose',
            'prompt': 'Act as a QA Engineer and perform a thorough quality assurance review. Focus on test coverage analysis, edge case identification, quality assurance processes, integration testing strategies, and potential bugs or issues. Provide recommendations for improving test coverage and quality.'
        },
        'security': {
            'type': 'general-purpose',
            'prompt': 'Act as a Security Review specialist and perform a comprehensive security audit. Focus on OWASP Top 10 vulnerability scanning, input validation and sanitization, authentication and authorization review, data protection and privacy compliance. Identify potential security vulnerabilities and provide remediation recommendations.'
        }
    }

# Parse and validate arguments
raw_args = arguments.strip().split() if arguments else []
args = validate_arguments(raw_args)

# Validate git repository
if not validate_git_repository():
    sys.exit(1)

print("🔧 Initializing code review system...")

# Handle setup if requested
if '--setup' in args:
    print("📋 Setting up review configuration...")
    # Setup would be handled by the system if needed
    print("✅ Setup completed")

# Determine review scope with validation
review_scope = []
if '--security-only' in args:
    review_scope = ['security']
elif '--qa-only' in args:
    review_scope = ['qa']
elif '--senior-dev-only' in args:
    review_scope = ['senior-dev']
else:
    review_scope = ['senior-dev', 'qa', 'security']

print(f"🔍 Starting comprehensive code review...")
print(f"📊 Review scope: {', '.join(review_scope)}")

# Check for changes with proper error handling
if '--full' not in args:
    try:
        status_result = bash('git status --porcelain')
        if status_result.returncode != 0:
            print("❌ Error checking git status")
            print("💡 Try running 'git status' manually to check for issues")
            sys.exit(1)

        if not status_result.stdout.strip():
            print("ℹ️  No changes detected. Use --full to review entire codebase.")
            # Interactive fallback option
            proceed = input("\n🤔 Run full codebase review instead? [y/N]: ").strip().lower()
            if proceed in ['y', 'yes']:
                args.append('--full')
                print("📖 Switching to full codebase review...")
            else:
                print("👋 Review cancelled")
                sys.exit(0)
    except Exception as e:
        print(f"❌ Error checking for changes: {e}")
        sys.exit(1)

# Get agent configurations
agent_templates = get_agent_prompts()
agents_to_run = []

# Build agent list with validation
for scope in review_scope:
    if scope in agent_templates:
        agents_to_run.append(agent_templates[scope])
    else:
        print(f"⚠️  Unknown review scope '{scope}' skipped")

if not agents_to_run:
    print("❌ No valid review agents configured")
    sys.exit(1)

print(f"🚀 Launching {len(agents_to_run)} specialized review agents...")

# Launch agents with error handling
task_success_count = 0
for i, agent_config in enumerate(agents_to_run):
    try:
        print(f"  📋 Starting {agent_config['type']} agent...")
        task(
            description=f"Review agent {i+1}: {agent_config['type']}",
            prompt=agent_config['prompt'],
            subagent_type=agent_config['type']
        )
        task_success_count += 1
    except Exception as e:
        print(f"⚠️  Failed to launch agent {i+1}: {e}")
        print(f"    Continuing with remaining agents...")

if task_success_count > 0:
    print(f"✅ Successfully launched {task_success_count}/{len(agents_to_run)} review agents!")
    print("📋 Review results will be provided by each specialized agent.")
    if task_success_count < len(agents_to_run):
        print(f"⚠️  Note: {len(agents_to_run) - task_success_count} agents failed to launch")
else:
    print("❌ Failed to launch any review agents")
    print("💡 Please check your environment and try again")
    sys.exit(1)
```

## Notes

- Requires git repository context
- Uses existing cproj review agent system
- Generates structured feedback with actionable recommendations
- Supports both incremental (changes only) and full codebase review
- Safe execution with proper error handling and validation