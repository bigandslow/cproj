description: Create a comprehensive Linear ticket from high-level input, automatically generating detailed context, acceptance criteria, and technical specifications using a core team of three specialist agents.
argument-hint: "<high-level description of work needed>"

## Mission

Transform high-level user input into a well-structured Linear ticket with comprehensive details. This command uses a core team of three agents (`product-manager`, `ux-designer`, `senior-software-engineer`) to handle all feature planning and specification in parallel. It focuses on **pragmatic startup estimation** to ensure tickets are scoped for rapid, iterative delivery.

**Pragmatic Startup Philosophy**:

  - 🚀 **Ship Fast**: Focus on working solutions over perfect implementations.
  - 💡 **80/20 Rule**: Deliver 80% of the value with 20% of the effort.
  - 🎯 **MVP First**: Define the simplest thing that could possibly work.

**Smart Ticket Scoping**: Automatically breaks down large work into smaller, shippable tickets if the estimated effort exceeds 2 days.

**Important**: This command ONLY creates the ticket(s). It does not start implementation or modify any code.

## Linear MCP Integration

This command uses the Linear MCP server with OAuth authentication to create tickets. The Linear MCP connection is established automatically through the workspace configuration.

**Prerequisites**:
- Linear MCP server must be running and authenticated via OAuth
- Workspace must have Linear organization, team, and project configured in `.claude/workspace.json`

## Linear Ticket Creation

This command creates Linear tickets using the `mcp__linear-server__create_issue` tool with the following parameter mapping:

**Required Parameters**:
- `title`: Generated from user input and agent findings
- `team`: Uses `linear.default_team` from workspace config, or prompts if not set

**Optional Parameters**:
- `description`: Comprehensive markdown description generated from agent research
- `project`: Uses `linear.default_project` from workspace config if available
- `labels`: Applied based on ticket type (e.g., "feature", "bug", "spike")
- `priority`: Set to 3 (Normal) by default, unless user specifies urgency
- `assignee`: Not set by default (tickets remain unassigned)
- `state`: Uses default team state (typically "Todo" or "Backlog")

**Workspace Configuration Access**:
The command reads Linear settings from `.claude/workspace.json`:
```json
{
  "linear": {
    "org": "company-name",
    "default_team": "TEAM-KEY",
    "default_project": "PROJECT-ID"
  }
}
```

## Core Agent Workflow

For any feature request that isn't trivial (i.e., not LIGHT), this command follows a strict parallel execution rule using the core agent trio.

### The Core Trio (Always Run in Parallel)

  - **`product-manager`**: Defines the "Why" and "What." Focuses on user stories, business context, and acceptance criteria.
  - **`ux-designer`**: Defines the "How" for the user. Focuses on user flow, states, accessibility, and consistency.
  - **`senior-software-engineer`**: Defines the "How" for the system. Focuses on technical approach, risks, dependencies, and effort estimation.

### Parallel Execution Pattern

```yaml
# CORRECT (Parallel and efficient):
- Task(product-manager, "Define user stories and business value for [feature]")
- Task(ux-designer, "Propose a simple UX, covering all states and accessibility")
- Task(senior-software-engineer, "Outline technical approach, risks, and estimate effort")
```

-----

## Ticket Generation Process

### 1) Smart Research Depth Analysis

The command first analyzes the request to determine if agents are needed at all.

LIGHT Complexity → NO AGENTS
- For typos, simple copy changes, minor style tweaks.
- Create the ticket immediately.
- Estimate: <2 hours.

STANDARD / DEEP Complexity → CORE TRIO OF AGENTS
- For new features, bug fixes, and architectural work.
- The Core Trio is dispatched in parallel.
- The depth (Standard vs. Deep) determines the scope of their investigation.

**Override Flags (optional)**:

  - `--light`: Force minimal research (no agents).
  - `--standard` / `--deep`: Force investigation using the Core Trio.
  - `--single` / `--multi`: Control ticket splitting.

### 2\) Scaled Investigation Strategy

#### LIGHT Research Pattern (Trivial Tickets)

NO AGENTS NEEDED.
1. Generate ticket title and description directly from the request.
2. Set pragmatic estimate (e.g., 1 hour).
3. Create ticket and finish.

#### STANDARD Research Pattern (Default for Features)

The Core Trio is dispatched with a standard scope:

  - **`product-manager`**: Define user stories and success criteria for the MVP.
  - **`ux-designer`**: Propose a user flow and wireframe description, reusing existing components.
  - **`senior-software-engineer`**: Outline a technical plan and provide a pragmatic effort estimate.

#### DEEP Spike Pattern (Complex or Vague Tickets)

The Core Trio is dispatched with a deeper scope:

  - **`product-manager`**: Develop comprehensive user stories, business impact, and success metrics.
  - **`ux-designer`**: Create a detailed design brief, including edge cases and state machines.
  - **`senior-software-engineer`**: Analyze architectural trade-offs, identify key risks, and create a phased implementation roadmap.

### 3\) Generate Ticket Content

Findings from the three agents are synthesized into a comprehensive ticket.

#### Description Structure

```markdown
## 🎯 Business Context & Purpose
<Synthesized from product-manager findings>
- What problem are we solving and for whom?
- What is the expected impact on business metrics?

## 📋 Expected Behavior/Outcome
<Synthesized from product-manager and ux-designer findings>
- A clear, concise description of the new user-facing behavior.
- Definition of all relevant states (loading, empty, error, success).

## 🔬 Research Summary
**Investigation Depth**: <LIGHT|STANDARD|DEEP>
**Confidence Level**: <High|Medium|Low>

### Key Findings
- **Product & User Story**: <Key insights from product-manager>
- **Design & UX Approach**: <Key insights from ux-designer>
- **Technical Plan & Risks**: <Key insights from senior-software-engineer>
- **Pragmatic Effort Estimate**: <From senior-software-engineer>

## ✅ Acceptance Criteria
<Generated from all three agents' findings>
- [ ] Functional Criterion (from PM): User can click X and see Y.
- [ ] UX Criterion (from UX): The page is responsive and includes a loading state.
- [ ] Technical Criterion (from Eng): The API endpoint returns a `201` on success.
- [ ] All new code paths are covered by tests.

## 🔗 Dependencies & Constraints
<Identified by senior-software-engineer and ux-designer>
- **Dependencies**: Relies on existing Pagination component.
- **Technical Constraints**: Must handle >10K records efficiently.

## 💡 Implementation Notes
<Technical guidance synthesized from senior-software-engineer>
- **Recommended Approach**: Extend the existing `/api/insights` endpoint...
- **Potential Gotchas**: Query performance will be critical; ensure database indexes are added.
```

### 4\) Smart Ticket Creation

**Single Ticket** (≤ 2 days estimated effort):
- Use `mcp__linear-server__create_issue` to create one comprehensive ticket
- Include all findings from the three agents in the description
- Use workspace config values for `team` and `project`

**Multiple Tickets** (> 2 days estimated effort):
- Break down into 2-3 smaller tickets automatically
- Create each ticket using `mcp__linear-server__create_issue`
- Link tickets using the `parentId` parameter for sub-issues or reference in descriptions
- Each ticket gets appropriate labels (e.g., "part-1", "part-2")

**MCP Tool Parameters Used**:
```json
{
  "title": "Generated title from agent findings",
  "description": "Comprehensive markdown description with all agent insights",
  "team": "workspace.linear.default_team",
  "project": "workspace.linear.default_project",
  "labels": ["feature", "researched"],
  "priority": 3
}
```

### 5\) Output & Confirmation

The command finishes by:
1. Displaying the Linear ticket URL(s) from the MCP tool response
2. Storing the Linear URL in the agent.json file (if using `--linear` flag)
3. Confirming successful ticket creation with ticket numbers and links