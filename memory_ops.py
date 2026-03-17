import os
import re
import json
import shutil
import zipfile
import io
from datetime import datetime
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
GLOBAL_MEMORY_DIR = CLAUDE_DIR / "memory"
PROJECTS_DIR = CLAUDE_DIR / "projects"
MANAGER_DIR = Path.home() / ".claude-memory-manager"
LOG_FILE = MANAGER_DIR / "logs" / "operations.jsonl"
BACKUP_DIR = MANAGER_DIR / "backups"


def parse_frontmatter(content):
    """Parse YAML frontmatter from markdown content.
    Returns dict with name, description, type, body."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            meta = {}
            for line in parts[1].strip().splitlines():
                if ": " in line:
                    key, val = line.split(": ", 1)
                    meta[key.strip()] = val.strip()
            return {
                "name": meta.get("name", ""),
                "description": meta.get("description", ""),
                "type": meta.get("type", "unknown"),
                "body": parts[2].strip(),
            }
    return {"name": "", "description": "", "type": "unknown", "body": content}


def _parse_index(memory_dir):
    """Parse MEMORY.md and return {filename: index_line} dict."""
    index_path = os.path.join(memory_dir, "MEMORY.md")
    result = {}
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            for line in f:
                m = re.match(r"- \[([^\]]+)\]\(", line.strip())
                if m:
                    result[m.group(1)] = line.strip()
    return result


def scan_container(memory_dir):
    """Scan a memory directory and return list of entry dicts."""
    index = _parse_index(memory_dir)
    entries = []
    seen_files = set()

    for filename, index_line in index.items():
        filepath = os.path.join(memory_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                meta = parse_frontmatter(f.read())
            entries.append({
                "filename": filename,
                "name": meta["name"] or filename.replace(".md", ""),
                "description": meta["description"],
                "type": meta["type"],
                "status": "ok",
                "index_line": index_line,
            })
        else:
            entries.append({
                "filename": filename,
                "name": filename.replace(".md", ""),
                "description": "",
                "type": "unknown",
                "status": "orphan",
                "index_line": index_line,
            })
        seen_files.add(filename)

    if os.path.isdir(memory_dir):
        for fname in sorted(os.listdir(memory_dir)):
            if fname.endswith(".md") and fname != "MEMORY.md" and fname not in seen_files:
                filepath = os.path.join(memory_dir, fname)
                with open(filepath, "r") as f:
                    meta = parse_frontmatter(f.read())
                entries.append({
                    "filename": fname,
                    "name": meta["name"] or fname.replace(".md", ""),
                    "description": meta["description"],
                    "type": meta["type"],
                    "status": "unindexed",
                    "index_line": "",
                })

    return entries


def _friendly_name(encoded):
    home_user = f"-home-{os.environ.get('USER', 'user')}-"
    if encoded.startswith(home_user):
        return "~/" + encoded[len(home_user):].replace("-", "/")
    return encoded.replace("-", "/")


def list_containers(global_dir=None, projects_dir=None):
    if global_dir is None:
        global_dir = str(GLOBAL_MEMORY_DIR)
    if projects_dir is None:
        projects_dir = str(PROJECTS_DIR)
    containers = []
    if os.path.isdir(global_dir):
        entries = scan_container(global_dir)
        containers.append({"id": "global", "name": "Global", "path": global_dir, "count": len(entries)})
    if os.path.isdir(projects_dir):
        for dirname in sorted(os.listdir(projects_dir)):
            mem_dir = os.path.join(projects_dir, dirname, "memory")
            if os.path.isdir(mem_dir):
                entries = scan_container(mem_dir)
                containers.append({"id": dirname, "name": _friendly_name(dirname), "path": mem_dir, "count": len(entries)})
    return containers
