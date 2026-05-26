# Delivery Manager MCP Server
## Project Definition & Brief for Claude Code
*May 2026*

---

## 1. Context and Motivation

This project was built in the context of TaskRay's Senior AI Engineer opening (https://taskray.applytojob.com/apply/7EeZRtCaET/Senior-AI-Engineer). TaskRay is the leading post-sale project management product in the Salesforce ecosystem, and the role is centered on building an off-platform agent layer — PM Agent, Execution Agent, and External Onboarding Agent — on a foundation of MCP server infrastructure connecting those agents to TaskRay's project, customer, and onboarding data. The JD is the primary reference for domain and architectural decisions made in this project.

The project has two goals. The first is practical: to build hands-on fluency with MCP server construction across all three primitives, using a domain and architecture pattern that directly mirrors what TaskRay is building. The second is demonstrative: to produce a portfolio artifact that shows not just that the protocol works, but that the author understands why each design decision was made — the distinction between tool-driven and host-driven access patterns, the role of typed schemas in governed agentic writes, and the use of prompt templates as reusable agentic context rather than mere information delivery.

The domain — accounts, projects, tasks, milestones — is modeled on TaskRay's core data model but kept deliberately generic. The server is not coupled to Salesforce or any specific platform, which makes it reusable as a reference implementation beyond this application while remaining an accurate structural analog to the environment TaskRay is building in.

---

## 2. Project Summary

A Python MCP server exposing a post-sale delivery management domain over SSE transport. The server implements all three MCP primitives:

- **Tools** — typed, schema-validated callable functions for agent interaction, including read tools, a guarded write tool, and a composite multi-step tool modeling flow-like business logic
- **Resources** — structured data endpoints the host can fetch and inject as context
- **Prompts** — server-defined templates with arguments that orient an agent to assess project health and decide on next actions, feeding directly into tool calls

SQLite provides the data layer. The agent loop is driven by Claude Code CLI against the live SSE server, demonstrating the full agentic integration pattern in a realistic host environment. Error handling and input validation are baked in from the start, not retrofitted.

---

## 3. Key Design Decisions

### SSE Transport from the Start

stdio transport is simpler to initialize but is a local-only pattern. SSE (HTTP + Server-Sent Events) reflects how an MCP server is actually deployed as an off-platform service — the pattern used by production agent platforms including Salesforce Agentforce. SSE is implemented from Phase 1 rather than retrofitted later.

### Guarded Write Tool

Production agent systems that mutate state need governance. The write tool enforces a precondition check before executing — modeling the field-level security and sharing rule enforcement that Salesforce applies to every MCP tool call. This demonstrates production-minded thinking about agentic writes rather than naive CRUD exposure.

### Composite Flow-Analog Tool

A single tool that internally executes a sequence of operations with gate conditions — updating a task, checking milestone completion, conditionally advancing project state — models the Flow-as-tool pattern central to Salesforce ISV MCP server architecture. This is the layer where domain expertise is encoded; it cannot be replicated by pointing a generic MCP server at a data store.

### Resource as a Template

Resources are application-controlled — the host decides when to fetch and inject them, not the model. The resource is implemented as a resource template with a dynamic URI parameter (e.g. `project://status/{account_id}`) rather than a fixed URI. This means a single resource definition serves any account record, which is the realistic pattern for a domain-oriented server. The host fetches the relevant record by ID and injects it as context before or during the conversation.

### Prompt Template as Agentic Context

Prompts are user-controlled by spec — they require explicit invocation rather than autonomous triggering by the agent. In Claude Code, they surface as slash commands: the user types `/assess-project-health` (or equivalent), Claude Code fetches the filled template from the server, and injects it into the conversation. The agentic loop — tool calls, state mutation, agent conclusion — begins after that invocation. The prompt template takes a project or account ID as an argument and returns a filled message combining retrieved context with a decision framing (escalate, proceed, or request more information). This correctly demonstrates the primitive: the user initiates, the agent executes.

### Claude Code as Host

An off-the-shelf MCP-native agent is the correct host choice for this project. Writing a custom client would demonstrate protocol implementation, not domain expertise — and would reintroduce scope that adds no signal for the target role. Claude Code is what a technical evaluator would reach for, and its use mirrors realistic production integration.

---

## 4. Feature Priority List

| # | Feature | Notes |
|---|---------|-------|
| 1 | SSE transport + server scaffold | Running server; foundation for all subsequent work |
| 2 | SQLite schema + seed data | Accounts, Projects, Tasks, Milestones; minimal but realistic |
| 3 | 3 read tools with typed schemas | `get_account`, `list_tasks`, `get_milestone_status` or equivalent |
| 4 | Error handling scaffold | Baked in from start; malformed inputs, graceful degradation |
| 5 | Multi-step agent loop | Claude Code driving tool calls; validates end-to-end function |
| 6 | Write tool with guard | `update_task_status` or equivalent; precondition check before mutation |
| 7 | Composite flow-analog tool | Multi-step internal logic behind single tool surface; gate conditions |
| 8 | Resource | Implemented as a resource template with dynamic URI parameter (e.g. `project://status/{account_id}`); host fetches by ID and injects as context |
| 9 | Prompt template with arguments | User-invoked via slash command in Claude Code; takes project/account ID; returns filled context + decision framing; agent loop follows |
| 10 | Schema validation hardening | Tighten input validation across all tools; complete error coverage |
| 11 | README + demo transcript | Clear start-server / Claude Code flow; full loop transcript; design rationale |

*Note: features 1, 2, 3, and 4 are implemented concurrently as the Phase 1 foundation. Time estimates are tracked at the phase level below.*

---

## 5. Phased Implementation

| Phase | Work | Features | Estimate |
|-------|------|----------|----------|
| 1 | Server foundation | SSE transport, SQLite schema + seed data, 3 read tools, error handling scaffold | 2–3 hrs |
| 2 | Write and flow tools | Guarded write tool, composite flow-analog tool | 1–2 hrs |
| 3 | Full primitive coverage + agentic loop | Resource, prompt template, Claude Code config, end-to-end demo loop | 2–3 hrs |
| 4 | Hardening + documentation | Schema validation, README, demo transcript | 1–2 hrs |
| | **Total** | | **6–10 hrs** |

Phase 1 constitutes the minimum viable artifact for portfolio listing. The widest uncertainty is in Phase 3, where the behavioral interaction between the prompt template and tool sequencing in Claude Code may require iteration. Phases 1 and 2 are straightforward implementation against a well-defined spec.

Implementation uses Claude Code CLI throughout, consistent with the spec-driven agentic development workflow used across the author's recent projects.

---

## 6. Deliverable

- GitHub repository, public
- Python throughout
- SQLite data layer — no external database dependencies
- README: prerequisites, start-server instructions, Claude Code configuration, demo walkthrough
- Demo transcript: full loop showing user slash command → prompt injection → agent tool calls → state mutation → agent conclusion
- No live hosted deployment — server runs locally over SSE

### A Note on Scope

The feature set of this project is intentionally narrow. Every feature exists to demonstrate a specific MCP server pattern — not to build a general-purpose delivery management application. There is no auth layer, no multi-tenancy, no full CRUD surface, no pagination, no user management. These are out of scope by design, not oversight.

The risk is that a reviewer who clicks through the repository without reading the README sees a thin feature set and draws the wrong conclusion. The mitigation is not to expand the features — doing so would dilute the signal each feature is meant to send — but to frame the scope explicitly and early in the README, before any technical content. The opening paragraph should state that this is a focused demonstration of MCP server patterns in a post-sale delivery domain, designed to exercise all three MCP primitives in a coherent agentic loop, and should name what is intentionally absent. A senior engineer reading that framing knows immediately they are looking at a deliberate demonstration, not an abandoned side project.

---

## 7. Demo Scenario (Suggested)

*The following is a suggested demo scenario, not a hard specification. Its purpose is to ensure that all implemented features are exercised in a coherent narrative, and to give Claude Code a concrete picture of intent when making implementation decisions. Details should be refined during the software spec phase.*

### Domain Model

Accounts contain Projects. Projects are divided into ordered Milestones (phases). Each Milestone contains Tasks. Tasks have owners, statuses, and optionally blockers. This is the minimal structure needed to support all three agent types TaskRay describes — PM Agent (project health), Execution Agent (task mutation), and External Onboarding Agent (customer-facing status and document requests) — without overbuilding the schema.

### Seed Data

Two accounts in meaningfully different states give the agent something to reason about and contrast:

- **Account A — healthy:** one milestone complete, current milestone mostly done with one open task that is actionable and unblocked
- **Account B — at-risk:** current milestone stalled; one task blocked on a customer dependency (e.g. document not yet submitted); one task in an invalid state for direct mutation (to exercise the write guard rejection path)

### Demo Sequence

The demo focuses on Account B. The host pre-loads the account resource by ID before the session. The user invokes the prompt template via slash command, passing Account B's ID. The template returns a briefing: milestone is stalled, a task is blocked on customer document submission, N days since last update — and frames the decision: escalate, nudge customer, or mark on-hold.

The agent then drives the following sequence:

1. **`get_account`** — confirm account context and current project
2. **`list_tasks`** — pull open tasks for the stalled milestone; identify the blocked task and the invalid-state task
3. **`get_milestone_status`** — confirm the blocked task is the only thing preventing milestone completion
4. **`update_task_status` (guard rejection)** — agent attempts to update the invalid-state task; guard fires and rejects the transition; agent acknowledges and proceeds
5. **`update_task_status` (success)** — agent marks the blocked task as pending-customer (nudge action); guard passes; state updated
6. **`complete_onboarding_step` (flow tool)** — agent attempts to advance the milestone; flow tool checks all sibling tasks; gate condition fails (blocked task is not yet resolved); milestone remains in current state; agent reports status and concludes

### Feature Coverage

The demo sequence exercises every feature in the priority list. Account A exists in the seed data and is readable via all three read tools, but is not the focus of the demo — it provides contrast and validates that the server handles multiple accounts correctly. The guard rejection in step 4 is the primary demonstration of the guarded write primitive; it should be legible in the transcript as an intentional design feature, not an error.

The flow tool gate failing in step 6 is intentional: it demonstrates that the tool correctly withholds advancement when preconditions are not met, and gives the agent something meaningful to report. A demo where everything succeeds unconditionally is less convincing than one where the system correctly identifies and communicates a constraint.

---

## Appendix: Draft Resume Entry

*The following is a draft resume entry for this project, for reference. The entry is written to be substantiated by Phase 1 completion while remaining accurate as subsequent phases are added. It should reflect the project as built, not define it.*

> **Delivery Manager MCP Server** — Python MCP server exposing a post-sale delivery management domain over SSE transport; supports agentic integration via Claude Code and MCP-native hosts
