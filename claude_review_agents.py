#!/usr/bin/env python3
"""
Claude-based review agents for cproj
Professional-grade code review system using Claude's Task tool
"""

import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import textwrap


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
    """Orchestrates Claude-based review agents"""
    
    def __init__(self, worktree_path: Path, context: Optional[ProjectContext] = None):
        self.worktree_path = worktree_path
        self.context = context or ProjectContext()
        self.load_project_context()
    
    def load_project_context(self):
        """Load project context from various sources"""
        # Load from .agent.json if available
        agent_json_path = self.worktree_path / '.agent.json'
        if agent_json_path.exists():
            with open(agent_json_path) as f:
                agent_data = json.load(f)
                if 'links' in agent_data and agent_data['links'].get('linear'):
                    self.context.ticket = f"Linear: {agent_data['links']['linear']}"
        
        # Load from git commit messages
        try:
            result = subprocess.run(
                ['git', 'log', '--oneline', '-10'],
                cwd=self.worktree_path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                commits = result.stdout.strip()
                self.context.pr_desc = f"Recent commits:\n{commits}"
        except:
            pass
        
        # Get branch name for PR title
        try:
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=self.worktree_path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                if not self.context.pr_title:
                    self.context.pr_title = branch.replace('-', ' ').replace('_', ' ').title()
        except:
            pass
    
    def get_diff(self) -> str:
        """Get git diff for review"""
        try:
            # Try to get diff vs origin/main
            result = subprocess.run(
                ['git', 'fetch', 'origin', 'main'],
                cwd=self.worktree_path,
                capture_output=True,
                text=True
            )
            
            result = subprocess.run(
                ['git', 'diff', 'origin/main...HEAD'],
                cwd=self.worktree_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
            
            # Fallback to staged changes
            result = subprocess.run(
                ['git', 'diff', '--cached'],
                cwd=self.worktree_path,
                capture_output=True,
                text=True
            )
            
            if result.stdout.strip():
                return result.stdout
            
            # Fallback to unstaged changes
            result = subprocess.run(
                ['git', 'diff'],
                cwd=self.worktree_path,
                capture_output=True,
                text=True
            )
            
            return result.stdout
        except:
            return ""
    
    def format_agent_prompt(self, prompt_template: str, diff: str) -> str:
        """Format prompt with context and diff"""
        # Limit diff size to avoid token limits
        max_diff_size = 8000
        if len(diff) > max_diff_size:
            diff = diff[:max_diff_size] + "\n\n[... diff truncated for length ...]"
        
        return prompt_template.format(
            pr_title=self.context.pr_title,
            pr_desc=self.context.pr_desc,
            pr_diff=diff,
            ticket=self.context.ticket,
            arch_notes=self.context.arch_notes,
            conventions=self.context.conventions,
            non_goals=self.context.non_goals,
            risk_profile=self.context.risk_profile,
            stack_info=self.context.stack_info,
            test_infra=self.context.test_infra,
            non_func=self.context.non_func,
            data_classification=self.context.data_classification,
            authz_model=self.context.authz_model,
            secrets_policy=self.context.secrets_policy,
            compliance=self.context.compliance,
            known_threats=self.context.known_threats
        )
    
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


def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Claude-based PR review system")
    parser.add_argument("path", nargs="?", default=".", help="Worktree path")
    parser.add_argument("--setup", action="store_true", help="Setup review configuration")
    parser.add_argument("--context", type=json.loads, help="JSON context overrides")
    
    args = parser.parse_args()
    
    worktree_path = Path(args.path).absolute()
    
    if not (worktree_path / ".git").exists():
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)
    
    # Load context
    context = ProjectContext()
    if args.context:
        for key, value in args.context.items():
            if hasattr(context, key):
                setattr(context, key, value)
    
    if args.setup:
        result = setup_review(worktree_path, context)
        print(f"Review configuration created: {result['config_path']}")
        print(f"Agents configured: {result['agents']}")
        print(f"Diff size: {result['diff_size']} bytes")
        print("\nNext: Run 'cproj review agents' to execute the review")
    else:
        print("Claude PR Review System")
        print("Usage:")
        print("  python claude_review_agents.py --setup     # Setup review")
        print("  cproj review agents                         # Run review")


if __name__ == "__main__":
    main()