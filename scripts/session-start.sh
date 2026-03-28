#!/usr/bin/env bash
# Single SessionStart hook: install deps, start server, inject context via JSON
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

# ---------- 0. Auto-sync marketplace → cache ----------
MARKETPLACE_DIR="$HOME/.claude/plugins/marketplaces/WhymustIhaveaname"
if [ -d "$MARKETPLACE_DIR" ] && [ "$PLUGIN_ROOT" != "$MARKETPLACE_DIR" ]; then
  if [ "$MARKETPLACE_DIR/hooks/hooks.json" -nt "$PLUGIN_ROOT/hooks/hooks.json" ] 2>/dev/null; then
    rsync -a --delete --exclude='.git' --exclude='__pycache__' --exclude='.venv' --exclude='.pytest_cache' \
      "$MARKETPLACE_DIR/" "$PLUGIN_ROOT/"
  fi
fi

STATE_DIR="$HOME/.claude-memory-manager"
PID_FILE="$STATE_DIR/server.pid"
PORT_FILE="$STATE_DIR/server.port"
LOG_FILE="$STATE_DIR/server.log"
DEFAULT_PORT=5050

mkdir -p "$STATE_DIR"
mkdir -p "$HOME/.claude/memory"

# ---------- 1. Ensure venv & Flask are installed ----------
VENV_DIR="$PLUGIN_ROOT/.venv"
PYTHON="$VENV_DIR/bin/python"
if [ ! -f "$PYTHON" ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv "$VENV_DIR" --quiet 2>/dev/null || true
  elif [ -f "$HOME/.local/bin/uv" ]; then
    "$HOME/.local/bin/uv" venv "$VENV_DIR" --quiet 2>/dev/null || true
  else
    python3 -m venv "$VENV_DIR" 2>/dev/null || true
  fi
fi
if ! "$PYTHON" -c "import flask" 2>/dev/null; then
  if command -v uv >/dev/null 2>&1; then
    uv pip install flask --python "$PYTHON" --quiet 2>/dev/null || true
  elif [ -f "$HOME/.local/bin/uv" ]; then
    "$HOME/.local/bin/uv" pip install flask --python "$PYTHON" --quiet 2>/dev/null || true
  else
    "$PYTHON" -m pip install flask --quiet 2>/dev/null || true
  fi
fi

# ---------- 2. Start web server (dynamic port) ----------
server_running=false
if [ -f "$PID_FILE" ]; then
  old_pid=$(cat "$PID_FILE")
  if kill -0 "$old_pid" 2>/dev/null; then
    server_running=true
    PORT=$(cat "$PORT_FILE" 2>/dev/null || echo "$DEFAULT_PORT")
  else
    rm -f "$PID_FILE" "$PORT_FILE"
  fi
fi

if [ "$server_running" = false ]; then
  PORT=$DEFAULT_PORT
  for i in $(seq 0 9); do
    candidate=$((DEFAULT_PORT + i))
    if ! (echo >/dev/tcp/127.0.0.1/$candidate) 2>/dev/null; then
      PORT=$candidate
      break
    fi
  done

  nohup "$PYTHON" "$PLUGIN_ROOT/app.py" --port "$PORT" > "$LOG_FILE" 2>&1 &
  SERVER_PID=$!
  disown "$SERVER_PID" 2>/dev/null || true
  echo "$SERVER_PID" > "$PID_FILE"
  echo "$PORT" > "$PORT_FILE"

  for _ in $(seq 1 25); do
    if curl -sf "http://127.0.0.1:${PORT}/api/containers" >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done
fi

# ---------- 3. Output JSON (both context injection AND terminal display) ----------
python3 - "$PORT" <<'PYEOF'
import os, sys, json

port = sys.argv[1]
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

global_entries = read_memory_index(os.path.join(claude_dir, "memory", "MEMORY.md"))

# Terminal message (shown to user via systemMessage)
msg_parts = []
msg_parts.append("")
msg_parts.append("[claude-memory-manager] Injected global memories:")
if global_entries:
    for entry in global_entries:
        msg_parts.append(f"  {entry}")
else:
    msg_parts.append("  (none)")
msg_parts.append("")

# Shared rules and best practices (shown to both user and Claude)
rules_parts = []
rules_parts.append("### Global memory rules")
rules_parts.append("")
rules_parts.append("Global memory (`~/.claude/memory/`) is the cross-project counterpart to project memory (`~/.claude/projects/*/memory/`). Both tiers share the same types, format, save process, exclusion rules, staleness checks, and verification steps defined in the `# auto memory` section of your system prompt. The only differences are:")
rules_parts.append("")
rules_parts.append("- **Scope**: Global memories apply across ALL projects. Save something globally when it is not specific to one repo — user identity, cross-project preferences, workflow corrections, external system references. Proactively maintain global memories to improve the user experience across projects.")
rules_parts.append("- **Path**: Read and write global memory files directly in `~/.claude/memory/`. Index goes in `~/.claude/memory/MEMORY.md`.")
rules_parts.append("- **When to save globally vs per-project**: If the memory is about the user (role, preferences, feedback on your behavior) or spans multiple projects, save it globally. If it is about a specific codebase, architecture, or project decision, save it per-project.")
rules_parts.append("")
rules_parts.append("### Memory best practices")
rules_parts.append("")
rules_parts.append("- **Think before you write**: Before saving a memory, ask yourself: \"What can I write now that will be useful to a future me whose conversation context has been wiped clean?\" If the answer is nothing non-obvious, don't save it.")
rules_parts.append("- **Merge, don't proliferate**: When information on a topic evolves, fold it into the existing memory file for that topic — broaden the file's scope and update its description if needed. Only create a new file when there is genuinely no existing file it fits into. The goal is to avoid a sprawl of tiny, fragmented memory files.")
rules_parts.append("- **Write descriptions that filter correctly**: Only the index (`MEMORY.md`) with its one-line descriptions is loaded into conversation context by default. A future agent with a clean context will only open a memory file if the description looks relevant — so a well-scoped description is critical. Follow this process when writing or updating a description:")
rules_parts.append("  1. *(Do this in a subagent)* Imagine 5 realistic scenarios where this memory **should** be consulted and 5 where it **should not**. If any scenario feels ambiguous, ask the user to clarify before proceeding.")
rules_parts.append("  2. Write the description so that someone reading *only* the description — with no other context — can reliably judge whether the memory is needed in each of those 10 scenarios.")
rules_parts.append("  - When updating a memory's content, re-run the same steps to keep the description in sync.")
rules_text = "\n".join(rules_parts)

# Terminal message (append rules so user can see them too)
msg_parts.append("")
msg_parts.append(rules_text)
msg_parts.append("")
msg_parts.append(f"Manage memories @ http://localhost:{port}")
system_message = "\n".join(msg_parts)

# Context for Claude (injected silently)
inject_parts = []
inject_parts.append("## Claude Memory Manager Plugin Active")
inject_parts.append("")
if global_entries:
    inject_parts.append("### Global Memories (~/.claude/memory/)")
    for entry in global_entries:
        inject_parts.append(entry)
    inject_parts.append("")
inject_parts.append(rules_text)
context = "\n".join(inject_parts)

output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context
    },
    "systemMessage": system_message
}
print(json.dumps(output, ensure_ascii=False))
PYEOF
