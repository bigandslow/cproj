#!/usr/bin/env python3
"""
Claude-based review agents for cproj
Professional-grade code review system using Claude's Task tool

This module provides three specialized AI agents for comprehensive PR review:
1. Senior Developer Agent - Code quality, architecture, best practices  
2. QA Engineer Agent - Test coverage, quality assurance, edge cases
3. Security Review Agent - Vulnerability assessment, OWASP compliance

Security Features:
- Input validation and sanitization for all user-provided data
- Path traversal protection for file operations  
- Subprocess timeout and safe argument passing
- Template injection prevention using safe substitution
- JSON deserialization with size limits

Usage:
    python claude_review_agents.py --setup
    # Creates .cproj_review.json with agent configurations
    
    cproj review agents
    # Ready for Claude Task tool execution
"""

import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from string import Template
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime


def _sanitize_pii_for_logging(message: str) -> str:
    """Sanitize potentially sensitive information from log messages.
    
    Args:
        message: Log message that may contain PII
        
    Returns:
        Sanitized message with PII redacted
    """
    if not isinstance(message, str):
        message = str(message)
    
    # Email addresses
    message = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]', message)
    
    # API keys/tokens (common patterns)
    message = re.sub(r'\b[A-Za-z0-9]{32,}\b', '[TOKEN_REDACTED]', message)
    message = re.sub(r'\bsk-[A-Za-z0-9]{48,}\b', '[API_KEY_REDACTED]', message)
    message = re.sub(r'\bghp_[A-Za-z0-9]{36}\b', '[GITHUB_TOKEN_REDACTED]', message)
    
    # URLs with potential sensitive tokens
    message = re.sub(r'https?://[^\s]*token=[^\s&]*', 'https://[URL_WITH_TOKEN_REDACTED]', message)
    
    # File paths that might contain usernames
    message = re.sub(r'/Users/[^/\s]+', '/Users/[USER_REDACTED]', message)
    message = re.sub(r'/home/[^/\s]+', '/home/[USER_REDACTED]', message)
    
    # IP addresses (basic pattern)
    message = re.sub(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', '[IP_REDACTED]', message)
    
    return message


# Professional Senior Developer Code Review Agent Prompt
CODE_REVIEW_AGENT_PROMPT = """
You are a **Senior Software Engineer** performing a pragmatic code review. Your goals:
* Ensure correctness, clarity, maintainability, performance, and alignment with architecture.
* Minimize churn: propose the **smallest effective change** that resolves each issue.
* Communicate crisply and respectfully. Offer examples/diffs the author can paste in.

## Inputs
* PR_TITLE: {pr_title}
* PR_DESC: {pr_desc}
* PR_DIFF: See below
* TICKET: {ticket}
* ARCH_NOTES: {arch_notes}
* CONVENTIONS: {conventions}
* NON_GOALS: {non_goals}

## Review checklist (apply quickly, cite evidence)

1. **Correctness & Behavior**
   * Aligns with TICKET acceptance criteria?
   * Edge cases & error paths handled? Idempotency where relevant?
   * Async behavior / retries / cancellation / timeouts sane?

2. **API & Contracts**
   * Types/interfaces stable, backward compatible?
   * Input validation and clear error messages?
   * Public surfaces documented (JSDoc/OpenAPI)?

3. **Readability & Maintainability**
   * Cohesive functions, clear naming, small modules?
   * Dead code, TODOs, commented-out blocks removed or ticketed?
   * Tests placed near code; avoids duplication; follows patterns?

4. **Performance & Resource Use**
   * Obvious N+1 queries, unnecessary data copies, hot-path allocations?
   * Streaming/pagination/batching where needed?

5. **Observability & Ops**
   * Logging levels appropriate; no PII secrets; structured logs?
   * Metrics/traces for critical paths?
   * Feature flagging, rollout/rollback plan indicated?

6. **Multi-Tenancy & Data Boundaries**
   * Tenant scoping on reads/writes; no cross-tenant leakage.
   * Row-level security or filters consistently applied.

7. **Dependencies**
   * New deps justified; license ok; no abandoned packages.

## Output contract (strict)
Return **only** this JSON object (no prose outside). Use empty arrays if none.

```json
{{
  "summary": "<2-3 sentence high-level take>",
  "approval": "approve | approve-with-nits | request-changes",
  "score": {{ "maintainability": 0-5, "correctness": 0-5, "performance": 0-5, "observability": 0-5 }},
  "findings": [
    {{
      "id": "CR-001",
      "type": "bug | design | readability | performance | test-gap | dependency | docs",
      "severity": "low | medium | high | critical",
      "file": "path/to/file.ts",
      "line": 123,
      "title": "Short issue title",
      "evidence": "Quote the problematic snippet or behavior",
      "why_it_matters": "1-2 sentences of impact",
      "recommendation": "Clear, minimal fix",
      "patch_suggestion": "```diff\\n<valid diff>\\n```"
    }}
  ],
  "nits": ["Optional quick wins in bullets"],
  "test_suggestions": ["List missing or valuable tests to add"]
}}
```

## PR Diff
{pr_diff}
"""

# Professional QA Engineer Agent Prompt
QA_ENGINEER_PROMPT = """
You are a **Senior QA Engineer** focused on fast, high-value validation. You create a targeted test plan, identify risk, and (optionally) generate runnable test artifacts. You do not re-design product scope; you ensure the delivered behavior matches intent and is robust.

## Inputs
* PR_TITLE: {pr_title}
* PR_DESC: {pr_desc}
* PR_DIFF: See below
* TICKET: {ticket}
* RISK_PROFILE: {risk_profile}
* STACK_INFO: {stack_info}
* TEST_INFRA: {test_infra}
* NON_FUNC: {non_func}

## QA checklist

1. **Acceptance Coverage** – Every criterion mapped to ≥1 test.
2. **Regression Surface** – Neighbor features impacted? Shared libs?
3. **State & Data** – Empty, minimal, typical, extreme, and invalid inputs.
4. **AuthN/Z & Tenancy** – Role matrix, tenant isolation, RLS policies.
5. **Error Handling & Resilience** – Timeouts, retries, offline, partial failure.
6. **Performance & UX** – Latency, loading states, pagination/virtualization.
7. **Accessibility** – Keyboard nav, labels, color contrast, ARIA landmarks.
8. **Cross-Env** – Local, CI, staging parity; feature flags toggled both ways.

## Output contract
Return **only** this JSON:

```json
{{
  "summary": "<short overview of risk and coverage>",
  "risk_level": "low | medium | high",
  "test_matrix": [
    {{
      "id": "TC-001",
      "area": "feature | api | workflow | migration",
      "goal": "What this test proves",
      "type": "unit | integration | e2e | accessibility | performance",
      "preconditions": ["seeded data X", "flag Y=on"],
      "steps": ["step 1", "step 2", "…"],
      "expected": ["assertion 1", "assertion 2"],
      "negatives": ["invalid input Z ⇒ 400", "timeout ⇒ retry path"],
      "notes": "Any special handling"
    }}
  ],
  "automation_artifacts": {{
    "unit": ["<file paths to create / update>"],
    "integration": ["<file paths>"],
    "e2e": ["<spec names>"],
    "seeds_or_fixtures": ["<fixture files to add/update>"]
  }},
  "gaps": [
    {{
      "id": "GAP-01",
      "severity": "medium | high | critical",
      "description": "Missing coverage",
      "recommendation": "Add test XYZ",
      "sample_code": "```ts\\n<minimal example>\\n```"
    }}
  ],
  "browser_device_matrix": ["Chrome latest", "Safari latest", "Firefox ESR"],
  "accessibility_checks": ["labels", "roles", "focus order", "contrast ≥ AA"]
}}
```

## PR Diff
{pr_diff}
"""

# Professional Security Review Agent Prompt
SECURITY_REVIEW_PROMPT = """
You are a **Senior Application Security Engineer** doing a lightweight threat assessment and secure-coding review. Use OWASP ASVS & Top 10 as mental checklists. Be practical: propose the **smallest secure fix**. Assume stack: TypeScript, Next.js, Supabase (Postgres + RLS), Temporal, WorkOS SSO, GCP.

## Inputs
* PR_TITLE: {pr_title}
* PR_DESC: {pr_desc}
* PR_DIFF: See below
* DATA_CLASSIFICATION: {data_classification}
* AUTHZ_MODEL: {authz_model}
* SECRETS_POLICY: {secrets_policy}
* COMPLIANCE: {compliance}
* KNOWN_THREATS: {known_threats}

## Security checklist (flag with evidence)

1. **AuthN/AuthZ** – Enforce tenant isolation on every query; verify RLS; deny-by-default; least privilege; no direct object reference.
2. **Input Validation & Output Encoding** – Server-side validation; sanitize HTML; parameterized queries; escape output.
3. **Secrets & Config** – No secrets in code/diff; correct scopes; rotation noted; secure defaults.
4. **Cryptography** – Approved algorithms/libs; proper key mgmt; avoid custom crypto.
5. **Data Protection & Privacy** – Minimize data; mask/avoid logging PII/PHI; retention noted.
6. **Transport & Session** – HTTPS only; secure cookies; CSRF on state-changing routes; SameSite set.
7. **Supply Chain** – New dependencies risk (malware, license, maintenance); pin versions.
8. **DoS/Abuse & Rate Limiting** – Validation before heavy work; pagination; caps on batch sizes.
9. **Temporal/Scheduler Safety** – Idempotency, dedupe, activity timeouts, retry policies safe.
10. **Observability** – Security-relevant logs (auth failures, privilege changes) without PII.

## Severity rubric
* **Critical**: exploitable remote compromise/data-leak.
* **High**: authz bypass or reliable data corruption.
* **Medium**: limited exploit or with preconditions.
* **Low**: best practice / defense-in-depth.

## Output contract
Return **only** this JSON:

```json
{{
  "summary": "<2-3 sentence security posture readout>",
  "overall_risk": "low | medium | high | critical",
  "controls_map": [
    {{
      "control": "ASVS-<section or Top10 tag>",
      "status": "pass | warn | fail",
      "evidence": "Short proof (file:line or snippet)"
    }}
  ],
  "findings": [
    {{
      "id": "SEC-001",
      "severity": "low | medium | high | critical",
      "category": "authz | injection | secrets | crypto | misconfig | supply-chain | privacy | dos | observability",
      "file": "path/to/file.ts",
      "line": 42,
      "title": "Short title",
      "evidence": "Quote the vulnerable code/path",
      "impact": "What can a real attacker do?",
      "recommendation": "Precise fix",
      "patch_suggestion": "```diff\\n<secure diff>\\n```"
    }}
  ],
  "dependency_review": [
    {{
      "package": "name@version",
      "risk": "low | medium | high",
      "reason": "e.g., unmaintained, CVEs, permissive API misuse",
      "mitigation": "pin/replace/remove"
    }}
  ],
  "secret_scan": {{ "hardcoded_secrets": false, "notes": "…" }}
}}
```

## PR Diff
{pr_diff}
"""


@dataclass
class ProjectContext:
    """Project-specific context for review agents"""
    pr_title: str = ""
    pr_desc: str = ""
    ticket: str = ""
    arch_notes: str = "Python/TypeScript monorepo, REST APIs, PostgreSQL, Docker, AWS"
    conventions: str = "PEP8 for Python, ESLint/Prettier for JS/TS, conventional commits"
    non_goals: str = ""
    risk_profile: str = "Standard web application"
    stack_info: str = "Python/FastAPI, TypeScript/React, PostgreSQL, Redis, Docker"
    test_infra: str = "pytest, jest, testing-library, playwright"
    non_func: str = "Response time <500ms, accessibility WCAG 2.1 AA"
    data_classification: str = "Internal"
    authz_model: str = "Role-based access control (RBAC)"
    secrets_policy: str = "Environment variables, no hardcoded secrets"
    compliance: str = "SOC 2 Type 1"
    known_threats: str = ""


class ClaudeReviewOrchestrator:
    """Orchestrates Claude-based review agents.
    
    Args:
        worktree_path: Path to the git worktree to review
        context: Optional project context for customization
    """
    
    def __init__(self, worktree_path: Path, context: Optional[ProjectContext] = None):
        self.worktree_path = self._validate_worktree_path(worktree_path)
        self.context = context or ProjectContext()
        # Load project context but don't fail if git operations fail
        try:
            self.load_project_context()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            logging.debug(_sanitize_pii_for_logging(f"Could not fully load project context: {e}"))
    
    def _validate_worktree_path(self, path: Path) -> Path:
        """Validate worktree path is safe and contains a git repository.
        
        Args:
            path: The path to validate
            
        Returns:
            Resolved and validated path
            
        Raises:
            ValueError: If path is invalid or unsafe
        """
        try:
            # Check for path traversal patterns FIRST before resolving
            if '..' in str(path) or str(path.resolve()).count('/') > 20:
                raise ValueError(f"Potentially unsafe path: {path}")
            
            resolved = path.resolve()
            
            # Check if path exists and is a directory
            if not resolved.exists() or not resolved.is_dir():
                raise ValueError(f"Path does not exist or is not a directory: {resolved}")
            
            # Check if it's a git repository (has .git directory or file)
            if not (resolved / '.git').exists():
                raise ValueError(f"Not a git repository: {resolved}")
                
            return resolved
        except (OSError, RuntimeError) as e:
            raise ValueError(f"Invalid worktree path {path}: {e}")
    
    def _safe_path_join(self, base: Path, filename: str) -> Path:
        """Safely join paths preventing directory traversal.
        
        Args:
            base: Base directory path
            filename: Filename to join (must not contain path separators)
            
        Returns:
            Safe joined path
            
        Raises:
            ValueError: If filename contains unsafe characters
        """
        # Prevent directory traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            raise ValueError(f"Unsafe filename: {filename}")
        
        if filename.startswith('.') and filename not in ['.agent.json', '.git', '.env']:
            raise ValueError(f"Suspicious filename: {filename}")
        
        result = (base / filename).resolve()
        
        # Ensure result is within base directory
        try:
            result.relative_to(base.resolve())
        except ValueError:
            raise ValueError(f"Path traversal detected: {result}")
        
        return result
    
    def load_project_context(self):
        """Load project context from various sources with secure file handling."""
        # Load from .agent.json if available
        try:
            agent_json_path = self._safe_path_join(self.worktree_path, '.agent.json')
            if agent_json_path.exists():
                with open(agent_json_path, 'r', encoding='utf-8') as f:
                    agent_data = json.load(f)
                    if 'links' in agent_data and agent_data['links'].get('linear'):
                        self.context.ticket = f"Linear: {agent_data['links']['linear']}"
        except (ValueError, OSError, json.JSONDecodeError) as e:
            logging.debug(_sanitize_pii_for_logging(f"Could not load .agent.json: {e}"))
        
        # Load from git commit messages with timeout
        try:
            result = subprocess.run(
                ['git', 'log', '--oneline', '-10'],
                cwd=self.worktree_path,
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                commits = result.stdout.strip()
                self.context.pr_desc = f"Recent commits:\n{commits}"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            logging.debug(_sanitize_pii_for_logging(f"Could not load git commits: {e}"))
        
        # Get branch name for PR title with timeout
        try:
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=self.worktree_path,
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                branch = result.stdout.strip()
                if not self.context.pr_title:
                    # Sanitize branch name for title
                    safe_branch = ''.join(c for c in branch if c.isalnum() or c in '-_ ')
                    self.context.pr_title = safe_branch.replace('-', ' ').replace('_', ' ').title()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            logging.debug(_sanitize_pii_for_logging(f"Could not load git branch: {e}"))
    
    def get_diff(self) -> str:
        """Get git diff for review with secure subprocess handling.
        
        Returns:
            Git diff output as string, empty if no changes or on error
        """
        # Try multiple diff strategies with timeouts and proper error handling
        diff_strategies = [
            (['git', 'diff', 'origin/main...HEAD'], "diff vs origin/main"),
            (['git', 'diff', '--cached'], "staged changes"),
            (['git', 'diff'], "unstaged changes")
        ]
        
        for cmd, description in diff_strategies:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.worktree_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
                logging.debug(_sanitize_pii_for_logging(f"Git {description} failed: {e}"))
                continue
        
        # If all strategies failed, log and return empty
        logging.warning(_sanitize_pii_for_logging("No git diff available from any strategy"))
        return ""
    
    def _sanitize_context_value(self, value: str, max_length: int = 1000) -> str:
        """Sanitize context values for safe template usage.
        
        Args:
            value: The value to sanitize
            max_length: Maximum allowed length
            
        Returns:
            Sanitized value safe for template substitution
        """
        if not isinstance(value, str):
            value = str(value)
        
        # Remove dangerous shell and template injection characters
        # Specifically remove: $, `, &, |, ;, (, ), {, }, <, >, \, and other shell metacharacters
        dangerous_chars = '$`&|;()<>{}\\'
        safe_value = ''.join(c for c in value if c not in dangerous_chars)
        
        # Keep only alphanumeric, safe punctuation, and whitespace
        safe_value = ''.join(c for c in safe_value if c.isalnum() or c in ' .,;:!?-_()[]/@#%^*+=~"|\n\t')
        
        # Truncate if too long
        if len(safe_value) > max_length:
            safe_value = safe_value[:max_length] + "..."
        
        return safe_value
    
    def format_agent_prompt(self, prompt_template: str, diff: str) -> str:
        """Format prompt with context and diff using safe template substitution.
        
        Args:
            prompt_template: The prompt template string
            diff: Git diff content
            
        Returns:
            Formatted prompt with sanitized context values
        """
        # Truncate diff at line boundaries to avoid breaking mid-line
        max_diff_lines = 200
        diff_lines = diff.split('\n')
        if len(diff_lines) > max_diff_lines:
            diff = '\n'.join(diff_lines[:max_diff_lines]) + "\n\n[... diff truncated for length ...]"
        
        # Use Template for safer substitution
        template = Template(prompt_template)
        
        # Sanitize all context values
        safe_context = {
            'pr_title': self._sanitize_context_value(self.context.pr_title),
            'pr_desc': self._sanitize_context_value(self.context.pr_desc, 2000),
            'pr_diff': self._sanitize_context_value(diff, 10000),
            'ticket': self._sanitize_context_value(self.context.ticket),
            'arch_notes': self._sanitize_context_value(self.context.arch_notes),
            'conventions': self._sanitize_context_value(self.context.conventions),
            'non_goals': self._sanitize_context_value(self.context.non_goals),
            'risk_profile': self._sanitize_context_value(self.context.risk_profile),
            'stack_info': self._sanitize_context_value(self.context.stack_info),
            'test_infra': self._sanitize_context_value(self.context.test_infra),
            'non_func': self._sanitize_context_value(self.context.non_func),
            'data_classification': self._sanitize_context_value(self.context.data_classification),
            'authz_model': self._sanitize_context_value(self.context.authz_model),
            'secrets_policy': self._sanitize_context_value(self.context.secrets_policy),
            'compliance': self._sanitize_context_value(self.context.compliance),
            'known_threats': self._sanitize_context_value(self.context.known_threats)
        }
        
        try:
            return template.safe_substitute(**safe_context)
        except (KeyError, ValueError) as e:
            logging.error(_sanitize_pii_for_logging(f"Template substitution failed: {e}"))
            return prompt_template  # Return original template if substitution fails
    
    def create_agent_configs(self) -> List[Dict[str, Any]]:
        """Create configuration for each review agent"""
        diff = self.get_diff()
        if not diff:
            return []
        
        agents = [
            {
                "name": "Senior Developer Code Review",
                "type": "code-review",
                "prompt": self.format_agent_prompt(CODE_REVIEW_AGENT_PROMPT, diff),
                "description": "Comprehensive code review focusing on correctness, maintainability, and best practices"
            },
            {
                "name": "QA Engineer Review",
                "type": "qa-review",
                "prompt": self.format_agent_prompt(QA_ENGINEER_PROMPT, diff),
                "description": "Test coverage analysis and quality assurance review"
            },
            {
                "name": "Security Review",
                "type": "security-review",
                "prompt": self.format_agent_prompt(SECURITY_REVIEW_PROMPT, diff),
                "description": "Security vulnerability assessment and threat analysis"
            }
        ]
        
        return agents
    
    def save_review_config(self) -> Path:
        """Save review configuration for Claude to use"""
        config = {
            "timestamp": datetime.now().isoformat(),
            "worktree": str(self.worktree_path),
            "context": asdict(self.context),
            "agents": self.create_agent_configs(),
            "instructions": self.get_claude_instructions()
        }
        
        config_path = self.worktree_path / '.cproj_review.json'
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        return config_path
    
    def get_claude_instructions(self) -> str:
        """Get instructions for Claude to run the review"""
        return """
# Automated PR Review Instructions

Please run the following review agents using the Task tool:

1. **Senior Developer Code Review**
   - Use subagent_type: "general-purpose"
   - Review for correctness, maintainability, and best practices
   - Output strict JSON contract

2. **QA Engineer Review**
   - Use subagent_type: "general-purpose"  
   - Assess test coverage and quality
   - Output strict JSON contract

3. **Security Review**
   - Use subagent_type: "general-purpose"
   - Identify security vulnerabilities
   - Output strict JSON contract

For each agent:
1. Pass the full prompt from the configuration
2. Parse the JSON response
3. Track all findings

After all agents complete:
1. Aggregate findings by severity
2. Determine if PR should be blocked (any CRITICAL issues)
3. Generate consolidated report with actionable recommendations

The review passes only if there are no CRITICAL findings.
"""
    
    def format_console_report(self, results: List[Dict]) -> str:
        """Format a console-friendly review report"""
        report = []
        report.append("=" * 60)
        report.append("📋 AUTOMATED PR REVIEW REPORT")
        report.append("=" * 60)
        report.append("")
        
        # Aggregate findings
        all_findings = []
        for agent_result in results:
            if 'findings' in agent_result:
                for finding in agent_result['findings']:
                    finding['agent'] = agent_result.get('agent_name', 'Unknown')
                    all_findings.append(finding)
        
        # Count by severity
        severity_counts = {
            'critical': 0,
            'high': 0,
            'medium': 0,
            'low': 0
        }
        
        for finding in all_findings:
            severity = finding.get('severity', 'low').lower()
            if severity in severity_counts:
                severity_counts[severity] += 1
        
        # Summary
        report.append("📊 Summary:")
        report.append(f"   Total findings: {len(all_findings)}")
        if severity_counts['critical'] > 0:
            report.append(f"   🔴 Critical: {severity_counts['critical']}")
        if severity_counts['high'] > 0:
            report.append(f"   🟠 High: {severity_counts['high']}")
        if severity_counts['medium'] > 0:
            report.append(f"   🟡 Medium: {severity_counts['medium']}")
        if severity_counts['low'] > 0:
            report.append(f"   🔵 Low: {severity_counts['low']}")
        
        # Detailed findings
        if all_findings:
            report.append("")
            report.append("📝 Findings:")
            
            for severity in ['critical', 'high', 'medium', 'low']:
                findings = [f for f in all_findings if f.get('severity', '').lower() == severity]
                if findings:
                    report.append("")
                    report.append(f"{severity.upper()}:")
                    for finding in findings:
                        report.append(f"  • [{finding['agent']}] {finding.get('title', finding.get('message', 'No description'))}")
                        if finding.get('file'):
                            line_info = f":{finding['line']}" if finding.get('line') else ""
                            report.append(f"    File: {finding['file']}{line_info}")
                        if finding.get('recommendation'):
                            report.append(f"    💡 {finding['recommendation']}")
        
        # Verdict
        report.append("")
        report.append("=" * 60)
        if severity_counts['critical'] > 0:
            report.append("❌ Review FAILED - Critical issues must be resolved")
        else:
            report.append("✅ Review PASSED - Ready for PR submission")
        report.append("=" * 60)
        
        return "\n".join(report)


def setup_review(worktree_path: Path, context: Optional[ProjectContext] = None) -> Dict:
    """Setup review configuration for Claude"""
    orchestrator = ClaudeReviewOrchestrator(worktree_path, context)
    config_path = orchestrator.save_review_config()
    
    return {
        "status": "ready",
        "config_path": str(config_path),
        "agents": len(orchestrator.create_agent_configs()),
        "diff_size": len(orchestrator.get_diff()),
        "instructions": orchestrator.get_claude_instructions()
    }


def safe_json_loads(data: str, max_nested_depth: int = 10, max_nested_objects: int = 100) -> dict:
    """Safely parse JSON with size and content validation.
    
    Args:
        data: JSON string to parse
        max_nested_depth: Maximum nesting depth allowed  
        max_nested_objects: Maximum total nested objects allowed
        
    Returns:
        Parsed JSON data
        
    Raises:
        ValueError: If JSON is invalid or too large
    """
    if not isinstance(data, str):
        raise ValueError("JSON input must be a string")
    
    if len(data) > 10000:  # 10KB limit
        raise ValueError("JSON input too large (max 10KB)")
    
    try:
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            raise ValueError("JSON input must be an object")
        
        # Validate nested structure to prevent DoS attacks
        _validate_json_structure(parsed, max_nested_depth, max_nested_objects)
        
        return parsed
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")


def _validate_json_structure(obj: Any, max_depth: int, max_objects: int, current_depth: int = 0, object_count: int = 0) -> int:
    """Recursively validate JSON structure depth and object count.
    
    Args:
        obj: Object to validate
        max_depth: Maximum allowed nesting depth
        max_objects: Maximum total objects allowed
        current_depth: Current nesting depth
        object_count: Running count of objects processed
        
    Returns:
        Updated object count
        
    Raises:
        ValueError: If structure is too deep or contains too many objects
    """
    if current_depth > max_depth:
        raise ValueError(f"JSON nesting too deep (max {max_depth} levels)")
    
    if object_count > max_objects:
        raise ValueError(f"JSON contains too many objects (max {max_objects})")
    
    if isinstance(obj, dict):
        object_count += 1
        if object_count > max_objects:
            raise ValueError(f"JSON contains too many objects (max {max_objects})")
        
        for value in obj.values():
            object_count = _validate_json_structure(value, max_depth, max_objects, current_depth + 1, object_count)
    
    elif isinstance(obj, list):
        if len(obj) > 1000:  # Limit array size
            raise ValueError("JSON array too large (max 1000 items)")
        
        for item in obj:
            object_count = _validate_json_structure(item, max_depth, max_objects, current_depth + 1, object_count)
    
    return object_count


def main():
    """CLI entry point with input validation"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Claude-based PR review system")
    parser.add_argument("path", nargs="?", default=".", help="Worktree path")
    parser.add_argument("--setup", action="store_true", help="Setup review configuration")
    parser.add_argument("--context", type=safe_json_loads, help="JSON context overrides")
    
    try:
        args = parser.parse_args()
    except SystemExit:
        raise
    except Exception as e:
        print(f"Error parsing arguments: {e}", file=sys.stderr)
        sys.exit(1)
    
    try:
        worktree_path = Path(args.path).absolute()
    except (OSError, ValueError) as e:
        print(f"Error: Invalid path '{args.path}': {e}", file=sys.stderr)
        sys.exit(1)
    
    if not (worktree_path / ".git").exists():
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)
    
    # Load context with validation
    context = ProjectContext()
    if args.context:
        allowed_fields = {f.name for f in context.__dataclass_fields__.values()}
        for key, value in args.context.items():
            if key in allowed_fields and isinstance(value, str) and len(value) < 1000:
                setattr(context, key, value)
            else:
                print(f"Warning: Ignoring invalid context field '{key}'", file=sys.stderr)
    
    if args.setup:
        try:
            result = setup_review(worktree_path, context)
            print(f"Review configuration created: {result['config_path']}")
            print(f"Agents configured: {result['agents']}")
            print(f"Diff size: {result['diff_size']} bytes")
            print("\nNext: Run 'cproj review agents' to execute the review")
        except Exception as e:
            print(f"Error setting up review: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Claude PR Review System")
        print("Usage:")
        print("  python claude_review_agents.py --setup     # Setup review")
        print("  cproj review agents                         # Run review")


if __name__ == "__main__":
    main()