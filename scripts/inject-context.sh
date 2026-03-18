#!/usr/bin/env bash
# Hook 2: Read MEMORY.md and output JSON for context injection
set -euo pipefail

python3 <<'PYEOF'
import os, json
home = os.path.expanduser("~")
claude_dir = os.path.join(home, ".claude")

def read_memory_index(path):
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("- ["):
                entries.append(line)
    return entries

def encode_project_path(path):
    return path.replace("/", "-")

global_entries = read_memory_index(os.path.join(claude_dir, "memory", "MEMORY.md"))

ctx_parts = []
ctx_parts.append("## Claude Memory Manager Plugin Active")
ctx_parts.append("")

if global_entries:
    ctx_parts.append("### Global Memories (~/.claude/memory/)")
    for entry in global_entries:
        ctx_parts.append(entry)
    ctx_parts.append("")

ctx_parts.append("You can directly read and edit memory files in ~/.claude/memory/ (global) and ~/.claude/projects/*/memory/ (per-project). Use the manage-memory skill for details.")

context = "\n".join(ctx_parts)

output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context
    }
}
print(json.dumps(output, ensure_ascii=False))
PYEOF
