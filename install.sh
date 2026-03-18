#!/usr/bin/env bash
# Claude Memory Manager — one-line installer
# Usage: curl -fsSL https://raw.githubusercontent.com/<user>/claude-memory-manager/main/install.sh | bash
set -euo pipefail

MARKETPLACE_NAME="WhymustIhaveaname"
PLUGIN_NAME="claude-memory-manager"
PLUGIN_VERSION="1.0.0"
REPO_URL="https://github.com/WhymustIhaveaname/claude-memory-manager"

PLUGINS_DIR="$HOME/.claude/plugins"
MARKETPLACE_DIR="$PLUGINS_DIR/marketplaces/$MARKETPLACE_NAME"
CACHE_DIR="$PLUGINS_DIR/cache/$MARKETPLACE_NAME/$PLUGIN_NAME/$PLUGIN_VERSION"
KNOWN_FILE="$PLUGINS_DIR/known_marketplaces.json"
INSTALLED_FILE="$PLUGINS_DIR/installed_plugins.json"
SETTINGS_FILE="$HOME/.claude/settings.json"

echo "[memory-manager] Installing $PLUGIN_NAME v$PLUGIN_VERSION..."

# 1. Clone or update repository
if [ -d "$MARKETPLACE_DIR" ]; then
  echo "[memory-manager] Updating existing installation..."
  cd "$MARKETPLACE_DIR"
  git pull --quiet 2>/dev/null || true
  cd - >/dev/null
else
  echo "[memory-manager] Cloning repository..."
  mkdir -p "$(dirname "$MARKETPLACE_DIR")"
  git clone --depth 1 "$REPO_URL.git" "$MARKETPLACE_DIR" 2>/dev/null
fi

# 2. Copy to cache
echo "[memory-manager] Setting up cache..."
mkdir -p "$CACHE_DIR"
rsync -a --delete \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='node_modules' \
  "$MARKETPLACE_DIR/" "$CACHE_DIR/"

# 3. Register marketplace
echo "[memory-manager] Registering marketplace..."
if [ -f "$KNOWN_FILE" ]; then
  KNOWN=$(cat "$KNOWN_FILE")
else
  KNOWN="{}"
fi
KNOWN=$(echo "$KNOWN" | python3 -c "
import sys, json
data = json.load(sys.stdin)
data['$MARKETPLACE_NAME'] = {
    'source': '$REPO_URL',
    'installLocation': '$MARKETPLACE_DIR'
}
print(json.dumps(data, indent=2))
")
echo "$KNOWN" > "$KNOWN_FILE"

# 4. Register installed plugin
echo "[memory-manager] Registering plugin..."
if [ -f "$INSTALLED_FILE" ]; then
  INSTALLED=$(cat "$INSTALLED_FILE")
else
  INSTALLED="{}"
fi
INSTALLED=$(echo "$INSTALLED" | python3 -c "
import sys, json
from datetime import datetime
data = json.load(sys.stdin)
data['${PLUGIN_NAME}@${MARKETPLACE_NAME}'] = {
    'name': '$PLUGIN_NAME',
    'marketplace': '$MARKETPLACE_NAME',
    'version': '$PLUGIN_VERSION',
    'installPath': '$CACHE_DIR',
    'installedAt': datetime.now().isoformat()
}
print(json.dumps(data, indent=2))
")
echo "$INSTALLED" > "$INSTALLED_FILE"

# 5. Enable plugin in settings
echo "[memory-manager] Enabling plugin..."
if [ -f "$SETTINGS_FILE" ]; then
  SETTINGS=$(cat "$SETTINGS_FILE")
else
  SETTINGS="{}"
fi
SETTINGS=$(echo "$SETTINGS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'enabledPlugins' not in data:
    data['enabledPlugins'] = {}
data['enabledPlugins']['${PLUGIN_NAME}@${MARKETPLACE_NAME}'] = True
print(json.dumps(data, indent=2))
")
echo "$SETTINGS" > "$SETTINGS_FILE"

echo ""
echo "[memory-manager] Installation complete!"
echo "[memory-manager] Plugin: $PLUGIN_NAME v$PLUGIN_VERSION"
echo "[memory-manager] Location: $CACHE_DIR"
echo ""
echo "Start a new Claude Code session to activate the plugin."
echo "The memory manager web UI will start automatically."
