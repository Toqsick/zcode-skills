# zcode-skills

Private registry, routing layer, and sanitized MCP config for the local ZCode
skill library (412 skills). Created 2026-07-23.

This repo does **not** contain raw skill bodies — those live locally in
`~/.claude/skills/`, `~/.hermes/skills/`, `~/.agents/skills/`, and
`~/.config/opencode/skills/`, surfaced to ZCode through the
`~/.zcode/skills/` symlink farm (412 entries). Instead, this repo holds the
**metadata, routing logic, and config templates** needed to reproduce and
route that library.

## Layout

| Path | Purpose |
|---|---|
| `registry/registry.json` | Per-skill manifest: name, dir, `source_root`, domain, `is_meta`, `mcp_server`, mismatches |
| `registry/routing.yaml` | Intent buckets → candidate skills → MCP server; meta-penalty + name/dir-mismatch rules |
| `registry/skill-to-mcp.csv` | ~31 identity-coupled skill → MCP server overrides |
| `skills/SKILL.md` | `skill-mcp-router` — the routing-agent skill (fills the intent→skill→MCP→tool gap) |
| `config/config.example.json` | Sanitized MCP config template (5 servers, `${ENV_VAR}` placeholders) |
| `config/mcp-schema.md` | Canonical MCP field reference + the two legacy-field bugs that dropped all servers |
| `bundles/*.yaml` | 12 pre-assembled skill bundles (from `~/.hermes/skill-bundles/`) |
| `manifests/*.json` | Install-provenance lockfiles (`.agents/.skill-lock.json`, `.hermes/skills-lock.json`) |
| `scripts/generate_registry.py` | Regenerates `registry/*` from live `~/.zcode/skills/` frontmatter |

## Secrets policy

**No API keys or tokens are stored in this repo.** The real
`~/.zcode/cli/config.json` (with plaintext `Z_AI_API_KEY` + Bearer tokens) is
gitignored. `config/config.example.json` uses `${Z_AI_API_KEY}` placeholders.
To restore a working config locally, copy the example and substitute real
values from your secrets manager — never commit the result.

## Restore

1. `git clone <this-repo> ~/zcode-skills`
2. Regenerate the registry against a live skill tree:
   `python3 scripts/generate_registry.py` (edit `ZCODE_SKILLS` in the script if
   your skill root differs).
3. Create `~/.zcode/cli/config.json` from `config/config.example.json`,
   substituting `${Z_AI_API_KEY}` with a real key.
4. Symlink `skills/SKILL.md` into your skill discovery root if you want the
   router loadable as a skill:
   `ln -s ~/zcode-skills/skills/SKILL.md ~/.zcode/skills/skill-mcp-router/SKILL.md`

## Regenerating after library changes

```
python3 scripts/generate_registry.py
git add registry/ && git commit -m "regenerate registry"
```

## Audit context

This repo was created on the back of a 2026-07-23 audit that (a) fixed all 5
MCP servers in `~/.zcode/cli/config.json` (legacy `environment`→`env`,
`type:"remote"`→`"http"`), and (b) confirmed no existing skill implements the
full intent→skill→MCP→tool routing chain. See `config/mcp-schema.md` for the
field-level details.
