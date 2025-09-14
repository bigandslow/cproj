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

```python
import subprocess
import json
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

# Ensure .cproj/.cproj_review.json exists
Path('.cproj').mkdir(exist_ok=True)
config_file = Path('.cproj/.cproj_review.json')
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
with open('.cproj/.cproj_review.json', 'r') as f:
    config = json.load(f)

# Execute review agents using cproj review system
if '--full' in args:
    print("📖 Reviewing entire codebase...")
else:
    print("📝 Reviewing changes since last commit...")

# Run the review agents via cproj command
review_args = ['python', 'cproj.py', 'review', 'agents']

if '--json' in args:
    review_args.append('--json')

print(f"🚀 Executing: {' '.join(review_args)}")
result = subprocess.run(review_args, cwd=git_root)

if result.returncode == 0:
    print("\n✅ Code review completed successfully!")
    print("📋 Review results have been generated.")
    print("💡 Check the output above for detailed feedback and recommendations.")
else:
    print(f"\n❌ Code review failed with exit code: {result.returncode}")
    print("💡 Try running 'review-code --setup' to reinitialize the review system.")
```

## Notes

- Requires git repository context
- Uses existing cproj review agent system
- Generates structured feedback with actionable recommendations
- Supports both incremental (changes only) and full codebase review
- Safe execution with proper error handling and validation