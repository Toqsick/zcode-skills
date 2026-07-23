# MCP Server Schema (ZCode)

Source: `zcode-guide:diagnosing-mcp` skill + the 2026-07-23 audit of `~/.zcode/cli/config.json`.

## Canonical field names (strict schema)

The per-server schema is **strict** — an unknown top-level key causes the server to be **dropped** at load time with no error surfaced in most cases. This is the single most common silent-failure mode.

| Transport | Required | Optional | Legacy field → canonical |
|---|---|---|---|
| `stdio` | `command` (string) | `args[]`, `cwd`, `env`, `enabled`, `timeoutMs` | `environment` → **`env`** |
| `http` / `sse` | `url` | `headers`, `enabled`, `timeoutMs` | `type: "remote"` / `"sse"` → **`type: "http"`** |
| (any) | — | — | `enable` → **`enabled`** |

**Critical:** `command` is a **string**, not an array. OpenCode-style `"command": ["npx", "-y", "pkg"]` will fail with `command.trim is not a function`. Use `"command": "npx"` + `"args": ["-y", "pkg"]`.

## The two bugs that dropped all 5 servers (2026-07-23)

Before the fix, every session reported `"mcpServerCount":0`. Root causes:

1. `zai-mcp-server` used `"environment": {...}` instead of `"env"`. Unknown key → server dropped; additionally the `Z_AI_API_KEY` never reached the subprocess.
2. All four HTTP servers used `"type": "remote"` instead of `"type": "http"`. The desktop host's parser does not run the CLI migration that maps `remote`→`http`, so all four were dropped.

## Template variables

`${...}` expansion (e.g. `${Z_AI_API_KEY}`) is **plugin-only**. Configuration-file MCP servers do NOT expand templates — use absolute paths and concrete env wiring there. The `config.example.json` placeholders are documentation for the human copying the file, not runtime-expanded by ZCode.

## Default timeout

`30000` ms. For slow-starting servers add `"timeoutMs": 60000`.

## Verification after editing

Restart the session, then in **Settings → MCP** confirm each server is `connected` (not `failed`/`disabled`). Check the log for a `session/resume` line with the expected `mcpServerCount`:

```
command grep -o 'mcpServerCount":[0-9]*' ~/.zcode/v2/logs/$(date +%F).log | tail
```

## Precedence (override order for same-named servers)

CLI → environment → **user** (`~/.zcode/cli/config.json`) → workspace → system. **User overrides workspace.** Plugin-provided servers form the base layer.
