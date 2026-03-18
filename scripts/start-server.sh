#!/usr/bin/env bash
# Hook 1: Install Flask + start web server + print visible summary
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

# ---------- 0. Auto-sync marketplace → cache ----------
# /plugin u updates marketplace but not cache; CLAUDE_PLUGIN_ROOT points to cache
MARKETPLACE_DIR="$HOME/.claude/plugins/marketplaces/WhymustIhaveaname"
if [ -d "$MARKETPLACE_DIR" ] && [ "$PLUGIN_ROOT" != "$MARKETPLACE_DIR" ]; then
  # sync if marketplace hooks.json is newer than cache
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
  echo "[claude-memory-manager] Installing Flask..."
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

# ---------- 3. Print visible summary (must match what we inject into context) ----------
CLAUDE_DIR="$HOME/.claude"
GLOBAL_INDEX="$CLAUDE_DIR/memory/MEMORY.md"

echo ""
echo "[claude-memory-manager] Injected global memories:"
if [ -f "$GLOBAL_INDEX" ]; then
  while IFS= read -r line; do
    case "$line" in
      "- ["*) echo "  $line" ;;
    esac
  done < "$GLOBAL_INDEX"
else
  echo "  (none)"
fi

echo ""
echo "Manage memories @ http://localhost:${PORT}"
