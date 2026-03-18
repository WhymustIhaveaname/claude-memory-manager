#!/usr/bin/env bash
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
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
  # Find an available port: try DEFAULT_PORT, then +1, +2, ... up to +9
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

  # Wait for server to be ready (up to 5 seconds)
  for _ in $(seq 1 25); do
    if curl -sf "http://127.0.0.1:${PORT}/api/containers" >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done
fi

# ---------- 3. Inject memory context ----------
# Use Python for reliable JSON escaping and MEMORY.md reading
python3 - "$PORT" "$PLUGIN_ROOT" <<'PYEOF'
import sys, os, json, re

port = sys.argv[1]
plugin_root = sys.argv[2]
project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
home = os.path.expanduser("~")
claude_dir = os.path.join(home, ".claude")

def read_memory_index(path):
    """Read MEMORY.md and return list of entry descriptions."""
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
    """Encode absolute path to container ID: /home/user/x -> -home-user-x"""
    return path.replace("/", "-")

# Read global memory index
global_index_path = os.path.join(claude_dir, "memory", "MEMORY.md")
global_entries = read_memory_index(global_index_path)

# Read current project memory index
project_entries = []
project_container = ""
if project_dir:
    project_container = encode_project_path(project_dir)
    project_index_path = os.path.join(claude_dir, "projects", project_container, "memory", "MEMORY.md")
    project_entries = read_memory_index(project_index_path)

# --- User-visible output (echo to stderr so it shows in terminal) ---
parts = []
parts.append(f"[memory-manager] Web UI: http://localhost:{port}")
if global_entries:
    parts.append(f"[memory-manager] Global memories: {len(global_entries)} entries")
if project_entries:
    parts.append(f"[memory-manager] Project memories: {len(project_entries)} entries")
if not global_entries and not project_entries:
    parts.append("[memory-manager] No memories found yet")

for p in parts:
    print(p, file=sys.stderr)

# --- Build context for Claude ---
ctx_parts = []
ctx_parts.append(f"## Claude Memory Manager Plugin Active")
ctx_parts.append(f"Web UI running at: http://localhost:{port}")
ctx_parts.append("")

if global_entries:
    ctx_parts.append("### Global Memories (~/.claude/memory/)")
    for entry in global_entries:
        ctx_parts.append(entry)
    ctx_parts.append("")

if project_entries:
    ctx_parts.append(f"### Project Memories (~/.claude/projects/{project_container}/memory/)")
    for entry in project_entries:
        ctx_parts.append(entry)
    ctx_parts.append("")

ctx_parts.append("You can directly read and edit memory files in ~/.claude/memory/ (global) and ~/.claude/projects/*/memory/ (per-project). Use the manage-memory skill for details.")

context = "\n".join(ctx_parts)

# --- Output JSON for Claude Code hook system ---
output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context
    }
}
print(json.dumps(output, ensure_ascii=False))
PYEOF
