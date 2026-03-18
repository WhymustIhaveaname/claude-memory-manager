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

# ---------- 1. Ensure Flask is installed ----------
if ! python3 -c "import flask" 2>/dev/null; then
  if command -v uv >/dev/null 2>&1; then
    uv pip install flask --quiet 2>/dev/null || true
  else
    python3 -m pip install flask --quiet 2>/dev/null || true
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

  nohup python3 "$PLUGIN_ROOT/app.py" --port "$PORT" > "$LOG_FILE" 2>&1 &
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

# Rewrite entries with full paths: [file.md](file.md) -> [file.md](~/.claude/memory/file.md)
import re
def add_full_path(entry):
    return re.sub(r'\]\(([^)]+)\)', lambda m: f'](~/.claude/memory/{m.group(1)})', entry)

full_path_entries = [add_full_path(e) for e in global_entries]

# Terminal message (shown to user via systemMessage)
msg_parts = []
msg_parts.append("")
msg_parts.append("[claude-memory-manager] Contents of ~/.claude/memory/MEMORY.md (user's persistent global memory, applies to all projects, always loaded into context):")
if full_path_entries:
    for entry in full_path_entries:
        msg_parts.append(f"  {entry}")
else:
    msg_parts.append("  (none)")
msg_parts.append("")
msg_parts.append(f"Manage memories @ http://localhost:{port}")
system_message = "\n".join(msg_parts)

# Context for Claude (matches official project memory format)
header = "Contents of ~/.claude/memory/MEMORY.md (user's persistent global memory, applies to all projects, always loaded into context):"
ctx_lines = [header, ""]
if full_path_entries:
    ctx_lines.extend(full_path_entries)
else:
    ctx_lines.append("(empty)")
ctx_lines.append("")
ctx_lines.append("Global memories live in ~/.claude/memory/. Same format as per-project memories. Read and write files there directly.")
context = "\n".join(ctx_lines)

output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context
    },
    "systemMessage": system_message
}
print(json.dumps(output, ensure_ascii=False))
PYEOF
