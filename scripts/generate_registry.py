#!/usr/bin/env python3
"""Generate routing artifacts from live skill frontmatter.

Read-only: walks ~/.zcode/skills/ (symlink farm), resolves each to its real
source root, parses SKILL.md frontmatter, and emits:
  - registry/registry.json     (per-skill manifest)
  - registry/routing.yaml      (intent buckets -> candidate skills -> MCP)
  - registry/skill-to-mcp.csv  (static identity-coupled skill->server overrides)

Source-of-truth: the 2026-07-23 audit taxonomy + skill-to-MCP coupling map.
"""
import csv
import json
import os
import re
import sys
from pathlib import Path

ZCODE_SKILLS = Path("/home/bratan/.zcode/skills")
OUT = Path("/home/bratan/ZCodeProject/zcode-skills/registry")

# --- Domain taxonomy (from audit) ---------------------------------------------
# Keyword -> bucket. First match wins. Order matters (specific before general).
DOMAIN_RULES = [
    ("agents/orchestration", [r"\borchestr", r"multi-agent", r"swarm", r"subagent",
                              r"kanban", r"dispatch", r"\bagent\b", r"delegate", r"queen", r"yuno"]),
    ("zcode/tooling-meta",   [r"\bskill\b", r"\bmcp\b", r"zcode", r"claude-code",
                              r"agent-config", r"context-engineer", r"prompt-engineer"]),
    ("content/media",        [r"video", r"audio", r"image", r"music", r"song", r"podcast",
                              r"youtube", r"tiktok", r"creative", r"design", r"art",
                              r"voice", r"soundtrack", r"gif", r"pixel", r"anime",
                              r"presentation", r"infographic", r"icon", r"poster"]),
    ("web/frontend",         [r"frontend", r"\bui\b", r"react", r"vue", r"tailwind",
                              r"\bcss\b", r"landing", r"threejs", r"webgl", r"\bhtml\b",
                              r"dashboard"]),
    ("backend/database",     [r"backend", r"database", r"sql", r"postgres", r"supabase",
                              r"clickhouse", r"api", r"express", r"koa", r"nest",
                              r"\bcode\b", r"refactor", r"debug", r"typescript", r"python"]),
    ("devops/infra",         [r"docker", r"kubernetes", r"\bk8s\b", r"deploy", r"infra",
                              r"github", r"\bci\b", r"\bcd\b", r"linux", r"nginx",
                              r"host", r"system", r"waydroid", r"wine", r"display",
                              r"wifi", r"nvidia", r"\bvpc\b"]),
    ("AI/ML/LLM",            [r"\bllm\b", r"\bml\b", r"\bai\b", r"model", r"huggingface",
                              r"ollama", r"llama", r"vllm", r"axolotl", r"comfyui",
                              r"minimax", r"gemini", r"\bdspy\b", r"rag", r"embedding",
                              r"weights", r"wandb", r"jupyter", r"bioinformatic"]),
    ("productivity/notes",   [r"obsidian", r"notion", r"apple", r"reminder", r"note",
                              r"email", r"imessage", r"himalaya", r"calendar", r"briefing",
                              r"report", r"kanban", r"todo", r"reminder", r"findmy"]),
    ("research/web",         [r"research", r"arxiv", r"web.?search", r"web.?archive",
                              r"scraper", r"firecrawl", r"perplexity", r"zread",
                              r"web.?reader", r"polymarket", r"trend", r"wiki",
                              r"briefing", r"knowledge", r"digest"]),
    ("security/audit",       [r"security", r"audit", r"vuln", r"\bctf\b", r"forensic",
                              r"attestation", r"lockin", r"vendor", r"hygiene"]),
    ("gaming/greyhack",      [r"greyhack", r"greyscript", r"minecraft", r"pokemon",
                              r"game", r"cp77", r"modding"]),
    ("iot/hardware",         [r"3d.?print", r"stl", r"parametric", r"openhue", r"wear",
                              r"esp", r"iot", r"raspberry"]),
    ("communication",        [r"telegram", r"webhook", r"feishu", r"teamspeak",
                              r"discord", r"agentmail", r"slack"]),
    ("writing/docs",         [r"\bdocx\b", r"\bpdf\b", r"\bxlsx\b", r"\bexcel\b",
                              r"epub", r"writing", r"humaniz", r"blog", r"seo",
                              r"transcript", r"documentation", r"prd", r"spec",
                              r"manim"]),
]
ALL_BUCKETS = [b for b, _ in DOMAIN_RULES] + ["other"]

# Meta-penalty buckets: these dominate keyword matches for "plan/orchestrate/
# route/agent" and should be de-prioritized unless intent is explicitly meta.
META_BUCKETS = {"agents/orchestration", "zcode/tooling-meta"}

# --- Static skill -> MCP server overrides (identity-coupled, from audit) ------
# For ~25 skills, matching the skill name IS the MCP resolution.
SKILL_TO_MCP = {
    "linear": ("linear", "Linear GraphQL API; requires LINEAR_API_KEY"),
    "notion": ("notion", "Notion API"),
    "supabase": ("supabase", "Supabase/Postgres"),
    "supabase-postgres-best-practices": ("supabase", "Supabase/Postgres"),
    "github-workflow": ("github", "GitHub MCP / gh CLI fallback"),
    "github-issues": ("github", "GitHub MCP / gh CLI fallback"),
    "github-code-review": ("github", "GitHub MCP / gh CLI fallback"),
    "github-pr-workflow": ("github", "GitHub MCP / gh CLI fallback"),
    "github-auth": ("github", "GitHub MCP / gh CLI fallback"),
    "github-repo-management": ("github", "GitHub MCP / gh CLI fallback"),
    "github-branch-inventory": ("github", "GitHub MCP / gh CLI fallback"),
    "github-pr-merge-readiness": ("github", "GitHub MCP / gh CLI fallback"),
    "github-sweep-orchestration": ("github", "GitHub MCP / gh CLI fallback"),
    "github-portfolio-launch": ("github", "GitHub MCP / gh CLI fallback"),
    "github-grayhack-workflow": ("github", "GitHub MCP / gh CLI fallback"),
    "web_search": ("web-search-prime", "web_search_prime MCP"),
    "firecrawl-web": ("firecrawl", "Firecrawl MCP"),
    "notebooklm-bridge": ("notebooklm", "NotebookLM MCP"),
    "blender-mcp": ("blender", "Blender MCP"),
    "touchdesigner-mcp": ("touchdesigner", "TouchDesigner MCP"),
    "arxiv": ("web-search-prime", "arxiv via web search"),
    "airtable": ("airtable", "Airtable API"),
    "spotify": ("spotify", "Spotify API"),
    "maps": ("maps", "Google Maps API"),
    "openhue": ("openhue", "Philips Hue API"),
    "findmy": ("findmy", "Apple FindMy"),
    "imessage": ("imessage", "macOS iMessage bridge"),
    "himalaya": ("himalaya", "himalaya CLI IMAP"),
    "agentmail": ("agentmail", "AgentMail API"),
    "feishu-webhook": ("feishu", "Feishu/Lark webhook"),
    "1password": ("1password", "1Password MCP"),
    "google-workspace": ("google-workspace", "Google Workspace API"),
    "mmx-cli": ("mmx", "MMX CLI"),
}

# Name vs directory mismatches (router must match on declared name:, not dir)
NAME_DIR_MISMATCHES = {
    "pitfalls": "multi-agent-pitfalls-cheatsheet",
    "media": "animal-podcast",
    "navigator": "skill-navigator",
    "integration": "hermes-memory",
    "image": "image-remix",
    "audio": "voice-clone",
    "video": "youtube-creator",
    "creative-ideation": "ideation",
    "lm-evaluation-harness": "evaluating-llms-harness",
    "segment-anything": "segment-anything-model",
    "vllm": "serving-llms-vllm",
    "excel-xlsx": "Excel / XLSX",
    "data-analysis": "Data Analysis",
}


def parse_frontmatter(text):
    """Parse the ---delimited--- frontmatter. Returns dict of top-level scalars."""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = parts[1]
    result = {}
    # Handle block scalars: key: > or key: | then indented continuation
    lines = fm.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^(\w[\w-]*)\s*:\s*(.*)$', line)
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if val in (">", "|", ">-", "|-", ">", "|"):
            # folded/literal block: gather indented continuation
            buf = []
            i += 1
            while i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\t")):
                buf.append(lines[i].strip())
                i += 1
            result[key] = " ".join(b for b in buf if b)
        elif val == "":
            # might be block with content on next indented lines, or empty
            i += 1
            buf = []
            while i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\t")):
                buf.append(lines[i].strip())
                i += 1
            result[key] = " ".join(b for b in buf if b) if buf else ""
        else:
            result[key] = val.strip('"').strip("'")
            i += 1
    return result


def classify_domain(name, desc):
    blob = f"{name} {desc}".lower()
    for bucket, patterns in DOMAIN_RULES:
        for p in patterns:
            if re.search(p, blob):
                return bucket
    return "other"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    skills = []
    for entry in sorted(ZCODE_SKILLS.iterdir()):
        if entry.name.startswith("."):
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            # resolve symlink
            try:
                resolved = entry.resolve()
            except OSError:
                continue
            skill_md = resolved / "SKILL.md"
            if not skill_md.is_file():
                continue
        try:
            real = skill_md.resolve()
        except OSError:
            continue
        text = skill_md.read_text(errors="replace")
        fm = parse_frontmatter(text)
        name = fm.get("name", entry.name).strip()
        desc = fm.get("description", "").strip()
        # source_root: which content root the real file lives in
        parts = str(real).split("/")
        source_root = "unknown"
        for marker in (".claude", ".agents", ".hermes", ".config/opencode"):
            if f"/{marker}/" in str(real):
                source_root = f"~/{marker}"
                break
        domain = classify_domain(name, desc)
        mcp = SKILL_TO_MCP.get(name)
        skills.append({
            "name": name,
            "dir": entry.name,
            "source_root": source_root,
            "real_path": str(real).replace(os.path.expanduser("~"), "~"),
            "domain": domain,
            "is_meta": domain in META_BUCKETS,
            "description": desc[:250],
            "mcp_server": mcp[0] if mcp else None,
            "mcp_note": mcp[1] if mcp else None,
            "name_dir_mismatch": NAME_DIR_MISMATCHES.get(entry.name),
        })

    # --- registry.json ---
    (OUT / "registry.json").write_text(
        json.dumps({
            "_generated": "2026-07-23",
            "_source": "~/.zcode/skills (symlink farm, 412 entries)",
            "_count": len(skills),
            "_domain_counts": {b: sum(1 for s in skills if s["domain"] == b) for b in ALL_BUCKETS if any(s["domain"] == b for s in skills)},
            "_mcp_coupled_count": sum(1 for s in skills if s["mcp_server"]),
            "skills": skills,
        }, indent=2, ensure_ascii=False)
    )

    # --- skill-to-mcp.csv ---
    with open(OUT / "skill-to-mcp.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["skill_name", "mcp_server", "note"])
        for s in skills:
            if s["mcp_server"]:
                w.writerow([s["name"], s["mcp_server"], s["mcp_note"]])

    # --- routing.yaml (hand-stitched structure referencing the data) ---
    by_domain = {}
    for s in skills:
        by_domain.setdefault(s["domain"], []).append(s["name"])
    meta_names = [s["name"] for s in skills if s["is_meta"]]

    yaml_lines = [
        "# Routing map — intent buckets -> candidate skills -> MCP server -> tool hints.",
        "# GENERATED 2026-07-23 from live skill frontmatter (~/.zcode/skills).",
        "# Consumed by skills/SKILL.md (skill-mcp-router). Do not hand-edit the",
        "# candidate lists; regenerate via scripts/generate_registry.py.",
        "",
        "meta_penalty:",
        "  description: >",
        "    Skills in these buckets dominate keyword matches for 'plan/orchestrate/",
        "    route/agent' and MUST be de-prioritized unless the intent is explicitly",
        "    meta (i.e. the user is asking about running the agent system itself).",
        f"  buckets: {sorted(META_BUCKETS)}",
        f"  count: {len(meta_names)}",
        "",
        "name_dir_mismatches:",
        "  description: >",
        "    Router MUST match on the declared frontmatter 'name:', not the directory",
        "    name. These entries differ; a dir-name match will miss the skill.",
    ]
    for d, n in NAME_DIR_MISMATCHES.items():
        yaml_lines.append(f"  {d}: \"{n}\"")
    yaml_lines += ["", "intent_buckets:"]
    bucket_map = {
        "CODE_GENERATION": ["backend/database", "web/frontend", "zcode/tooling-meta"],
        "DATA_RETRIEVAL": ["backend/database", "research/web", "productivity/notes"],
        "ANALYSIS": ["research/web", "zcode/tooling-meta", "AI/ML/LLM", "security/audit"],
        "COMMUNICATION": ["communication", "content/media", "writing/docs"],
        "INFRASTRUCTURE": ["devops/infra", "backend/database"],
        "RESEARCH": ["research/web", "AI/ML/LLM"],
    }
    for intent, doms in bucket_map.items():
        yaml_lines.append(f"  {intent}:")
        yaml_lines.append(f"    candidate_domains: {doms}")
        cands = []
        for d in doms:
            for n in sorted(by_domain.get(d, []))[:8]:
                cands.append(n)
        yaml_lines.append(f"    sample_candidates: {cands[:20]}")
    yaml_lines += [
        "",
        "mcp_servers_configured:",
        "  description: The 6 servers in ~/.zcode/cli/config.json (canonical fields).",
        "  - zai-mcp-server   # stdio, npx -y @z_ai/mcp-server, needs Z_AI_API_KEY",
        "  - web-search-prime # http, api.z.ai",
        "  - web-reader       # http, api.z.ai",
        "  - zread            # http, api.z.ai",
        "  - hermes           # http, 127.0.0.1:8643 (local)",
        "  - github           # stdio, Docker toqsick/github-mcp-server:develop; host PAT",
        "",
        "see_also:",
        "  - registry.json        # full per-skill manifest with source_root + domain",
        "  - skill-to-mcp.csv     # static skill->server overrides (~33 identity-coupled)",
        "  - bundles/*.yaml       # 12 pre-assembled skill bundles (.hermes/skill-bundles)",
    ]
    (OUT / "routing.yaml").write_text("\n".join(yaml_lines) + "\n")

    print(f"skills indexed: {len(skills)}")
    print(f"mcp-coupled:    {sum(1 for s in skills if s['mcp_server'])}")
    print(f"meta-penalized: {len(meta_names)}")
    print("domain counts:")
    for b in ALL_BUCKETS:
        c = sum(1 for s in skills if s["domain"] == b)
        if c:
            print(f"  {b:24} {c}")
    print(f"mismatches:     {sum(1 for s in skills if s['name_dir_mismatch'])}")
    print("wrote: registry.json, routing.yaml, skill-to-mcp.csv")


if __name__ == "__main__":
    main()
