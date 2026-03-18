---
name: manage-memory
description: Use when the user asks to manage, view, edit, organize, move, or delete Claude memory files, or mentions "global memory", "memory manager", "manage memories", "edit memory", "memory web UI".
---

# Claude Memory Manager

You have access to Claude's native auto-memory system and can manage it directly.

## Web UI

A visual three-panel memory manager is running in the background. The actual URL was printed at session start — check the session start output for the port number (default: http://localhost:5050). Tell the user to open it in their browser for drag-and-drop operations, bulk move/delete, export/import, and visual browsing.

## Direct File Editing

You can DIRECTLY read and edit memory files — both global and per-project:

### Global Memory (applies to all projects)
- Index: `~/.claude/memory/MEMORY.md`
- Files: `~/.claude/memory/*.md`

### Current Project Memory
- Index: `~/.claude/projects/<encoded-path>/memory/MEMORY.md`
- Files: `~/.claude/projects/<encoded-path>/memory/*.md`

The `<encoded-path>` is the project's absolute path with `/` replaced by `-`, e.g. `/home/user/myproject` becomes `-home-user-myproject`.

### MEMORY.md Index Format
Each line is an entry:
```
- [filename.md](filename.md) — description text
```

### Memory File Format
Markdown with YAML frontmatter:
```markdown
---
name: descriptive_name
description: Brief one-line description
type: user|feedback|project|reference
---

Memory content here.
```

### Type Meanings
- **user**: User's role, preferences, knowledge
- **feedback**: Workflow corrections, what to do/avoid
- **project**: Ongoing work, goals, deadlines
- **reference**: Pointers to external resources

## Rules
- Always read current file content before editing to avoid conflicts
- When adding a new memory file, also add an index line to MEMORY.md
- When deleting a memory file, also remove its MEMORY.md entry
- Keep MEMORY.md concise — it's an index, not content storage
