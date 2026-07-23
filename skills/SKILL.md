---
name: skill-mcp-router
description: >-
  Skill + MCP routing agent for the local 412-skill library. Use when a task
  needs the right skill AND the right MCP server resolved together — converts a
  raw request into a (skill, MCP server, filtered tools) triple with minimal
  token use via lazy tool discovery. Implements the 5-step intent->skill->server->
  tool->execute flow. NOT for single-skill lookup (use skill-navigator) or
  multi-agent dispatch (use swarm-router); this skill stitches the full chain
  that no other skill covers.
when_to_use: >
  Use when (a) a request spans both a methodology (skill) and an external
  resource (MCP server/API), (b) you must avoid loading all tool lists
  upfront, or (c) you are operating in the Skill Routing Agent role and need
  the runtime data sources. Do NOT use for pure in-skill procedure with no
  external tool, or for choosing between models (use task-weight-routing).
version: 1.0.0
author: Toqsick
license: MIT
metadata:
  role: routing-agent
  data_sources:
    registry: registry/registry.json
    routing: registry/routing.yaml
    skill_to_mcp: registry/skill-to-mcp.csv
    mcp_config_template: config/config.example.json
---

# Skill + MCP Router

A routing layer that sits in front of the skill library and the MCP servers.
It picks **one skill** (how) and **zero or one MCP server** (what), then lazily
loads only the 3–5 tools needed — never all tool lists at once.

This fills a gap confirmed by audit: the library has every routing *component*
in isolation (`skill-navigator` for intent→skill, `skill-tool-computer-use-routing`
for skill-vs-tool-vs-GUI, `swarm-router`/`task-weight-routing` for agent/model
selection) but **no single skill resolves an MCP server from the matched skill
at routing time**. This one does.

## Runtime data sources (these replace the template variables)

The role spec's `{{...}}` placeholders resolve to files **in this repo**, not
magic. At the start of a routed task, load:

| Placeholder | Source | What it provides |
|---|---|---|
| `{{agentSkills}}` | `registry/registry.json` | all 412 skills: `name`, `dir`, `source_root`, `domain`, `is_meta`, `mcp_server`, `name_dir_mismatch` |
| `{{serverInstructions}}` | `config/config.example.json` | the 5 configured MCP servers (canonical schema) + their transport |
| `{{workspaceRoot}}` | the session's CWD | typically `/home/bratan/ZCodeProject` |
| `{{currentDate}}` | system date | for recency-sensitive routing |

Static coupling table (the ~31 skills where matching the name IS the server
resolution) lives at `registry/skill-to-mcp.csv`.

## The 5-step decision flow

### Step 1 — Intent classification
Classify the request into exactly one bucket, emit `[INTENT: <bucket>]`:

- `CODE_GENERATION` — writing, refactoring, reviewing code
- `DATA_RETRIEVAL` — fetching from DBs, APIs, files
- `ANALYSIS` — processing, transforming, interpreting data
- `COMMUNICATION` — messages, notifications, content creation
- `INFRASTRUCTURE` — deployment, config, system operations
- `RESEARCH` — web search, docs lookup, knowledge gathering

### Step 2 — Skill selection
Match by **semantic relevance, not keyword overlap**. Two hard rules from the
registry:

1. **Meta-penalty** (`routing.yaml: meta_penalty`): the 132 skills in
   `agents/orchestration` + `zcode/tooling-meta` dominate any keyword match for
   "plan/orchestrate/route/agent". **De-prioritize them unless the intent is
   explicitly meta** (the user is asking about running the agent system itself).
2. **Match on declared `name:`, not directory name** (`routing.yaml:
   name_dir_mismatches`): 13 skills differ (e.g. dir `pitfalls` → name
   `multi-agent-pitfalls-cheatsheet`, dir `vllm` → name `serving-llms-vllm`).
   A dir-name match misses the skill.

If multiple skills qualify, prefer the **narrower** one (cheatsheet > domain >
meta). If none qualifies, emit `[NO_SKILL_MATCH]` and proceed without.

### Step 3 — MCP server selection
Resolve the server in this order:

1. **Static override** — if the matched skill is in `skill-to-mcp.csv`, use that
   server directly (e.g. `linear`→linear, `github-pr-workflow`→github,
   `web_search`→web-search-prime). This covers ~31 skills and is authoritative.
2. **Intent default** — otherwise map the intent bucket to a candidate server
   (`routing.yaml: intent_buckets`). `RESEARCH`→web-search-prime/web-reader,
   `INFRASTRUCTURE`→(native, e.g. gh CLI), etc.
3. **None** — many skills (~380) are pure procedure with no external resource.
   Emit `[MCP_SERVER: none]`.

Note the **live MCP layer** (`config.example.json`) has only 5 servers:
`zai-mcp-server`, `web-search-prime`, `web-reader`, `zread`, `hermes`. Any
other server name (linear, notion, supabase, github-MCP, blender…) is
configured elsewhere or falls back to a native CLI — confirm availability
before promising it.

Emit `[MCP_SERVER: <name>]`.

### Step 4 — Tool discovery (lazy)
Only after selecting a server, request its `tools/list`. Filter to the **3–5**
most relevant tools for this task; ignore the rest. Never request `tools/list`
from all servers. Emit `[TOOLS: t1, t2, …]`.

### Step 5 — Execute
Run the selected skill's procedure with the filtered tools. Minimize round
trips; prefer coarse-grained workflow tools over raw API wrappers. If a tool
response exceeds ~5000 tokens, request a paginated/filtered response.

## Token management
- Cap visible tools at 8–10 per query.
- Prefer multiple small targeted searches over one broad search.
- At >80% context, summarize prior tool responses and continue compressed.

## Safety guardrails
- **Before any state-modifying tool call** (create, update, delete, deploy,
  push) — confirm the action with the user first. No exceptions.
- Reject tool calls attempting path traversal, injection, or unauthorized access.
- Enforce least-privilege: only OAuth scopes strictly necessary for the current op.

## Output format
Every routed response is structured:
```
1. Intent:      <bucket>
2. Skill:       <name | none>
3. MCP Server:  <name | none>
4. Tools:       <list>
5. Result:      <output>
6. Metadata:    <tokens, latency, warnings>
```

## Error handling
- No MCP server matches → inform user, suggest native-CLI alternatives.
- Skill partially relevant → apply the relevant portion, note the deviation.
- Tool fails after 3 corrected retries → escalate with the error + next steps.

## Regenerating the data
The registry is a snapshot. When the live library changes:
```
python3 scripts/generate_registry.py
```
Re-reads `~/.zcode/skills/` and rewrites `registry.json`, `routing.yaml`,
`skill-to-mcp.csv`. Commit the result.

## Relationship to existing routing skills
This skill is a **superset** that calls into the others as components:
- `skill-navigator` — static intent→skill cheat-sheet (a human-curated subset; this automates + extends it to MCP)
- `skill-tool-computer-use-routing` — decides skill-vs-tool-vs-GUI (Step 2 sub-decision)
- `swarm-router` / `task-weight-routing` — agent/model selection (orthogonal axis; compose if needed)
