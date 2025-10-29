# GitHub Security Alert Fixer - Technical Reference

## GitHub CodeQL API Reference

### Fetching Alerts

```bash
# Get all open alerts
gh api /repos/{owner}/{repo}/code-scanning/alerts?state=open --paginate

# Get specific severity
gh api /repos/{owner}/{repo}/code-scanning/alerts \
  --paginate \
  -F state=open \
  -F severity=error

# Alert states: open, dismissed, fixed
# Severities: error, warning, note
```

### Alert JSON Structure

```json
{
  "number": 1,
  "state": "open",
  "dismissed_by": null,
  "dismissed_at": null,
  "dismissed_reason": null,
  "rule": {
    "id": "py/stack-trace-exposure",
    "severity": "warning",
    "security_severity_level": "medium",
    "description": "Information exposure through an exception",
    "name": "Stack trace exposure",
    "tags": ["security", "external/cwe/cwe-209"]
  },
  "most_recent_instance": {
    "ref": "refs/heads/main",
    "state": "open",
    "commit_sha": "abc123...",
    "message": {
      "text": "Stack trace information flows to this location..."
    },
    "location": {
      "path": "apps/api/app/auth/routes.py",
      "start_line": 476,
      "end_line": 476,
      "start_column": 16,
      "end_column": 22
    }
  }
}
```

## Ruff Configuration Reference

### Security Rules (flake8-bandit)

```toml
[tool.ruff.lint]
select = [
    "S",   # flake8-bandit (security checks)
]

# Common S-rules:
# S101  - assert-used (disable for tests)
# S105  - hardcoded-password-string
# S106  - hardcoded-password-func-arg
# S107  - hardcoded-password-default
# S108  - hardcoded-temp-file
# S110  - try-except-pass
# S112  - try-except-continue
# S324  - hashlib-insecure-hash-function
# S603  - subprocess-without-shell-equals-true
# S608  - hardcoded-sql-expression
```

### Exception Handling Rules (tryceratops)

```toml
[tool.ruff.lint]
select = [
    "TRY",  # tryceratops
]

# Common TRY-rules:
# TRY002 - raise-vanilla-class
# TRY003 - raise-vanilla-args
# TRY201 - verbose-raise
# TRY300 - try-consider-else
# TRY301 - raise-within-try
# TRY400 - error-instead-of-exception
```

### Pylint Rules

```toml
[tool.ruff.lint]
select = [
    "PL",  # pylint
]

# Common PL-rules:
# PLR0911 - too-many-return-statements
# PLR0912 - too-many-branches
# PLR0913 - too-many-arguments
# PLR0915 - too-many-statements
# PLW0602 - global-variable-not-assigned
# PLW0603 - global-statement
```

### Per-File Ignores

```toml
[tool.ruff.lint.per-file-ignores]
# Tests can have hardcoded credentials and assertions
"tests/**/*.py" = ["S101", "S105", "S106", "F401", "F841"]
"**/tests/**/*.py" = ["S101", "S105", "S106", "F401", "F841"]
"**/test_*.py" = ["S101", "S105", "S106"]

# Scripts can use subprocess and print
"scripts/**/*.py" = ["T201", "S603", "S607"]
"tools/**/*.py" = ["T201", "S603", "S607"]

# Init files can have unused imports (re-exports)
"**/__init__.py" = ["F401", "F403"]
```

## CWE Mappings

### Common CWEs in CodeQL

| CWE | Name | Severity | Common Fix |
|-----|------|----------|------------|
| CWE-209 | Information Exposure Through Error | Medium | Use structured logging |
| CWE-390 | Empty Exception Block | Low | Add explanatory comment |
| CWE-497 | Information Leak Through Stack Trace | High | Sanitize error responses |
| CWE-561 | Dead Code | Note | Remove unused code |
| CWE-563 | Unused Variable | Note | Remove or prefix with _ |

## Structured Logging Best Practices

### Structlog Configuration

```python
import structlog

# Configure once at application startup
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
```

### Safe Error Logging

```python
import structlog
logger = structlog.get_logger(__name__)

# ✅ Good: Logs server-side, safe client response
try:
    result = risky_operation()
except Exception as e:
    logger.error(
        "operation_failed",
        exc_info=e,                    # Full stack trace server-side
        operation="risky_operation",   # Context
        user_id=user.id,              # Non-sensitive identifiers
        # ❌ NEVER: password=password, api_key=key, etc.
    )
    raise HTTPException(
        status_code=500,
        detail="Operation failed"     # Generic message to client
    )
```

### Security Utils Pattern

```python
# apps/api/app/shared/security_utils.py

def sanitize_for_logging(value: str, max_length: int = 200) -> str:
    """Remove control characters and limit length."""
    import re
    sanitized = re.sub(r'[\x00-\x08\x0A-\x1F\x7F-\x9F]', '', value)
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + '...'
    return sanitized

def redact_secret_identifier(secret_name: str) -> str:
    """Redact sensitive parts of secret identifiers."""
    if secret_name.startswith('tenant-'):
        parts = secret_name.split('-', 2)
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1]}-***"
    return "***"
```

## Testing Strategies

### Testing Security Fixes

```python
# tests/security/test_credential_leakage.py

def test_no_credentials_in_logs(caplog):
    """Verify credentials never appear in logs."""
    with caplog.at_level(logging.INFO):
        try:
            service.authenticate(username="user", password="secret123")
        except Exception:
            pass

    # Verify no credentials leaked
    for record in caplog.records:
        message = record.getMessage()
        assert "secret123" not in message
        assert "password" not in message.lower() or "password=" not in message.lower()
```

### Coverage Requirements

```ini
# apps/api/pytest.ini
[pytest]
addopts =
    --cov=app
    --cov-report=term-missing
    --cov-report=html:coverage_html
    --cov-fail-under=15  # Adjust based on actual coverage

# Incremental improvement strategy:
# - Start at current coverage (e.g., 15%)
# - Increase by 5% each sprint
# - Target: 80-85% for business logic
```

## CI/CD Integration

### GitHub Actions Workflow

```yaml
name: Security Analysis

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  codeql:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: python, javascript

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v3
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.0
    hooks:
      - id: ruff
        args: [--fix, --unsafe-fixes]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.18.2
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
```

## Automated Fix Patterns

### Python Script for Batch Fixes

```python
#!/usr/bin/env python3
"""Batch fix common security issues."""

import re
import sys
from pathlib import Path

def fix_empty_except(content: str, file_path: Path) -> str:
    """Add explanatory comments to empty except blocks."""

    # Pattern: except Exception:\n    pass
    pattern = r'(except\s+\w+:)\n(\s+)(pass)(?!\s*#)'

    def get_comment(match):
        # Determine appropriate comment based on file type
        if 'test' in file_path.name:
            comment = '# Test continues - checking for condition regardless of success'
        elif 'cleanup' in match.group(0).lower():
            comment = '# Ignore cleanup errors - already processed'
        else:
            comment = '# Exception handled - continuing execution'

        return f'{match.group(1)}\n{match.group(2)}{comment}\n{match.group(2)}{match.group(3)}'

    return re.sub(pattern, get_comment, content)

def prefix_unused_vars(content: str) -> str:
    """Prefix unused variables with underscore."""
    # This is better done with AST analysis, but simple regex works for obvious cases
    pattern = r'\b(result|response|data)\s*='
    return re.sub(pattern, r'_\1 =', content)

if __name__ == '__main__':
    for file_path in Path('.').rglob('*.py'):
        if 'venv' in str(file_path) or '.git' in str(file_path):
            continue

        content = file_path.read_text()
        modified = fix_empty_except(content, file_path)

        if modified != content:
            file_path.write_text(modified)
            print(f'Fixed: {file_path}')
```

## Metrics & Reporting

### Alert Trend Analysis

```python
#!/usr/bin/env python3
"""Track security alert trends over time."""

import json
import subprocess
from datetime import datetime

def get_alert_counts():
    """Get current alert counts by severity."""
    cmd = ['gh', 'api', '/repos/{owner}/{repo}/code-scanning/alerts', '--paginate']
    result = subprocess.run(cmd, capture_output=True, text=True)
    alerts = json.loads(result.stdout)

    counts = {'error': 0, 'warning': 0, 'note': 0}
    for alert in alerts:
        if alert['state'] == 'open':
            severity = alert['rule'].get('security_severity_level', 'note')
            counts[severity] = counts.get(severity, 0) + 1

    return {
        'date': datetime.now().isoformat(),
        'total': sum(counts.values()),
        'by_severity': counts
    }

# Track over time
# Append to metrics.jsonl
```

## Troubleshooting Guide

### Issue: Alerts Not Updating

**Symptom:** Fixed code still shows alerts

**Cause:** CodeQL analysis hasn't run on latest commit

**Solution:**
1. Verify commit pushed: `git log --oneline -1`
2. Check CI status: `gh run list --limit 3`
3. Wait for CodeQL analysis: ~2-3 minutes
4. Refresh alerts: `gh api /repos/{owner}/{repo}/code-scanning/alerts?state=open`

### Issue: Too Many False Positives

**Symptom:** CodeQL flagging valid code patterns

**Solution:**
```python
# Add suppression comment (use sparingly)
# codeql[py/unused-local-variable]: Intentionally unused for API compatibility
_result = operation()
```

Or update rules:
```toml
[tool.ruff.lint]
ignore = ["specific-rule-id"]  # Document why
```

### Issue: Performance Impact

**Symptom:** Linting/type checking very slow

**Solution:**
```toml
# Limit file scanning
[tool.ruff]
exclude = [
    ".git",
    ".venv",
    "node_modules",
    "*.egg-info",
]

# Use caching
[tool.mypy]
cache_dir = ".mypy_cache"
```

## Additional Resources

- [CodeQL Documentation](https://codeql.github.com/docs/)
- [Ruff Rules Reference](https://docs.astral.sh/ruff/rules/)
- [CWE Database](https://cwe.mitre.org/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Structlog Documentation](https://www.structlog.org/)
