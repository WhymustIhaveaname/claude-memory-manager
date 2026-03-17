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


def _write_log(entry, log_file=None):
    if log_file is None:
        log_file = str(LOG_FILE)
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    entry["timestamp"] = datetime.now().isoformat()
    with open(log_file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _backup_file(filepath, backup_dir=None):
    if backup_dir is None:
        backup_dir = str(BACKUP_DIR)
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    backup_name = f"{ts}_{os.path.basename(filepath)}"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(filepath, backup_path)
    return backup_path


def _remove_index_lines(memory_dir, filenames):
    index_path = os.path.join(memory_dir, "MEMORY.md")
    if not os.path.exists(index_path):
        return {}
    removed = {}
    with open(index_path, "r") as f:
        lines = f.readlines()
    new_lines = []
    for line in lines:
        matched = False
        for fname in filenames:
            if f"[{fname}]" in line:
                removed[fname] = line.strip()
                matched = True
                break
        if not matched:
            new_lines.append(line)
    with open(index_path, "w") as f:
        f.writelines(new_lines)
    return removed


def _append_index_lines(memory_dir, lines):
    """Append lines to MEMORY.md. Ensures a leading newline if file doesn't end with one."""
    index_path = os.path.join(memory_dir, "MEMORY.md")
    os.makedirs(memory_dir, exist_ok=True)
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            content = f.read()
        if content and not content.endswith("\n"):
            with open(index_path, "a") as f:
                f.write("\n")
    with open(index_path, "a") as f:
        for line in lines:
            f.write(line + "\n")


def delete_memories(memory_dir, filenames, container_id="", log_file=None, backup_dir=None):
    removed_lines = _remove_index_lines(memory_dir, filenames)
    for fname in filenames:
        filepath = os.path.join(memory_dir, fname)
        if os.path.exists(filepath):
            backup_path = _backup_file(filepath, backup_dir=backup_dir)
            _write_log({
                "action": "delete",
                "container": container_id,
                "file": fname,
                "index_line": removed_lines.get(fname, ""),
                "backup_path": backup_path,
            }, log_file=log_file)
            os.remove(filepath)


def move_memories(src_dir, dst_dir, filenames, from_id="", to_id="", log_file=None):
    for fname in filenames:
        if os.path.exists(os.path.join(dst_dir, fname)):
            raise FileExistsError(f"File already exists in target: {fname}")
    removed_lines = _remove_index_lines(src_dir, filenames)
    lines_to_add = []
    for fname in filenames:
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(dst_dir, fname)
        shutil.copy2(src_path, dst_path)
        os.remove(src_path)
        index_line = removed_lines.get(fname, f"- [{fname}]({fname}) — ")
        lines_to_add.append(index_line)
        _write_log({
            "action": "move", "file": fname, "from": from_id, "to": to_id, "index_line": index_line,
        }, log_file=log_file)
    _append_index_lines(dst_dir, lines_to_add)


def export_memories(memory_dir, filenames, container_id="", log_file=None):
    index = _parse_index(memory_dir)
    buf = io.BytesIO()
    manifest = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in filenames:
            filepath = os.path.join(memory_dir, fname)
            if os.path.exists(filepath):
                zf.write(filepath, fname)
                manifest.append({
                    "file": fname,
                    "index_line": index.get(fname, f"- [{fname}]({fname}) — "),
                    "target": memory_dir.replace(str(Path.home()), "~"),
                })
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    _write_log({"action": "export", "container": container_id, "files": filenames}, log_file=log_file)
    return buf.getvalue()


def import_memories(memory_dir, zip_bytes, container_id="", log_file=None):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        for entry in manifest:
            dst_path = os.path.join(memory_dir, entry["file"])
            if os.path.exists(dst_path):
                raise FileExistsError(f"File already exists: {entry['file']}")
        lines_to_add = []
        imported_files = []
        for entry in manifest:
            fname = entry["file"]
            dst_path = os.path.join(memory_dir, fname)
            with open(dst_path, "wb") as f:
                f.write(zf.read(fname))
            lines_to_add.append(entry["index_line"])
            imported_files.append(fname)
        _append_index_lines(memory_dir, lines_to_add)
    _write_log({"action": "import", "container": container_id, "files": imported_files, "source_zip": "upload"}, log_file=log_file)


def edit_memory(memory_dir, filename, old_content, new_content):
    filepath = os.path.join(memory_dir, filename)
    with open(filepath, "r") as f:
        current = f.read()
    if current != old_content:
        raise ValueError("conflict: file has been modified since last read")
    with open(filepath, "w") as f:
        f.write(new_content)


def edit_index(memory_dir, old_line, new_line):
    index_path = os.path.join(memory_dir, "MEMORY.md")
    with open(index_path, "r") as f:
        content = f.read()
    if old_line not in content:
        raise ValueError("conflict: index line not found, may have been modified")
    content = content.replace(old_line, new_line, 1)
    with open(index_path, "w") as f:
        f.write(content)


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
