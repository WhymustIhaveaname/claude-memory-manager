# Claude Memory Manager

## Background

Claude Code keeps memory files per project (`~/.claude/projects/<project>/memory/`). Two things are missing:

- **No global memory.** Fix Claude's behavior in project A, and project B still doesn't know about it. Settings have global and per-project tiers; memory only has per-project.
- **No way to see or manage memories.** Files are scattered under `~/.claude/`. You can't browse, edit, or clean them up without digging through directories by hand.

## What this does

Adds global memory and a web UI for managing all of Claude's memories.

**Global memory:**
- Keeps cross-project memories in `~/.claude/memory/`
- Injects them into context at session start via a SessionStart hook
- Tells Claude about global memory so it can read and write there during conversations

**Web UI** (default `localhost:5050`, picks another port if taken):
- Three-panel layout: folders, memory list, preview/edit
- Drag-and-drop between containers, bulk move/delete
- Export as `.zip`, import on another machine

## Install

1. In Claude Code, run `/plugin` → **Marketplaces** → **+ Add Marketplace** → `WhymustIhaveaname/claude-memory-manager`
2. Switch to **Discover** → install `claude-memory-manager`

## Architecture

```
claude-memory-manager/
├── .claude-plugin/
│   ├── plugin.json         # Plugin manifest
│   └── marketplace.json    # Marketplace metadata
├── hooks/
│   └── hooks.json          # SessionStart hook config
├── scripts/
│   └── session-start.sh    # Install deps, start server, inject memories, print summary
├── app.py                  # Flask routes → memory_ops
├── memory_ops.py           # Pure functions for all file operations
├── templates/              # Single-file frontend, inline CSS/JS
├── tests/                  # Unit + integration tests
```

Runtime data (not in the repo):

```
~/.claude/memory/                          # Global memory container
~/.claude-memory-manager/
└── logs/operations.jsonl                  # Write operation log
```

## See also

- [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) — Persistent memory for Claude Code. Automatically preserves context across sessions with semantic search, vector database, and web UI
