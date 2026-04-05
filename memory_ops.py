import os
import re
import json
import shutil
import zipfile
import io
import difflib
from datetime import datetime
from itertools import product
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
GLOBAL_MEMORY_DIR = CLAUDE_DIR / "memory"
PROJECTS_DIR = CLAUDE_DIR / "projects"
MANAGER_DIR = Path.home() / ".claude-memory-manager"
LOG_FILE = MANAGER_DIR / "logs" / "operations.jsonl"
BACKUP_DIR = MANAGER_DIR / "backups"


def _parse_index(memory_dir):
    """Parse MEMORY.md and return {filename: index_line} dict."""
    index_path = os.path.join(memory_dir, "MEMORY.md")
    result = {}
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            for line in f:
                m = re.match(r"- \[[^\]]+\]\(([^)]+)\)", line.strip())
                if m:
                    result[m.group(1)] = line.strip()
    return result


def _desc_from_index_line(index_line):
    """Extract description text from an index line (text after ' — ')."""
    m = re.search(r" (?:—|-) (.+)$", index_line)
    return m.group(1) if m else ""


def scan_container(memory_dir):
    """Scan a memory directory and return list of entry dicts."""
    index = _parse_index(memory_dir)
    entries = []
    seen_files = set()

    for filename, index_line in index.items():
        filepath = os.path.join(memory_dir, filename)
        status = "ok" if os.path.exists(filepath) else "orphan"
        entries.append({
            "filename": filename,
            "name": filename.replace(".md", ""),
            "description": _desc_from_index_line(index_line),
            "status": status,
            "index_line": index_line,
        })
        seen_files.add(filename)

    if os.path.isdir(memory_dir):
        for fname in sorted(os.listdir(memory_dir)):
            if fname.endswith(".md") and fname != "MEMORY.md" and fname not in seen_files:
                entries.append({
                    "filename": fname,
                    "name": fname.replace(".md", ""),
                    "description": "",
                    "status": "unindexed",
                    "index_line": "",
                })

    return entries


def _friendly_name(encoded):
    home_user = f"-home-{os.environ.get('USER', 'user')}-"
    if not encoded.startswith(home_user):
        return encoded.replace("-", "/")
    suffix = encoded[len(home_user):]
    home = str(Path.home())
    # Try all 2^n decodings of '-' as '/' or '-', return first existing path
    parts = suffix.split("-")
    for combo in product(*[["/" , "-"] if i > 0 else [""] for i in range(len(parts))]):
        candidate = parts[0] + "".join(c + p for c, p in zip(combo[1:], parts[1:]))
        if os.path.isdir(os.path.join(home, candidate)):
            return "~/" + candidate
    return "~/" + suffix.replace("-", "/")


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
            if f"({fname})" in line:
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


def edit_memory(memory_dir, filename, old_content, new_content, container_id="", log_file=None):
    filepath = os.path.join(memory_dir, filename)
    with open(filepath, "r") as f:
        current = f.read()
    if current != old_content:
        raise ValueError("conflict: file has been modified since last read")
    patch = "".join(difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    ))
    with open(filepath, "w") as f:
        f.write(new_content)
    _write_log({
        "action": "edit_memory",
        "container": container_id,
        "file": filename,
        "patch": patch,
    }, log_file=log_file)



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


def _decode_project_path(encoded):
    """Decode an encoded project directory name back to a real filesystem path."""
    home = str(Path.home())
    home_user = f"-home-{os.environ.get('USER', 'user')}-"
    if not encoded.startswith(home_user):
        return "/" + encoded.replace("-", "/")
    suffix = encoded[len(home_user):]
    parts = suffix.split("-")
    for combo in product(*[["/" , "-"] if i > 0 else [""] for i in range(len(parts))]):
        candidate = parts[0] + "".join(c + p for c, p in zip(combo[1:], parts[1:]))
        full = os.path.join(home, candidate)
        if os.path.isdir(full):
            return full
    return os.path.join(home, suffix.replace("-", "/"))


def list_settings_containers(global_dir=None, projects_dir=None):
    """Return list of containers that have settings files."""
    if global_dir is None:
        global_dir = str(CLAUDE_DIR)
    if projects_dir is None:
        projects_dir = str(PROJECTS_DIR)
    containers = []

    global_files = []
    if os.path.isfile(os.path.join(global_dir, "settings.json")):
        global_files.append("settings.json")
    if global_files:
        containers.append({"id": "global", "name": "Global", "files": global_files})

    if os.path.isdir(projects_dir):
        for dirname in sorted(os.listdir(projects_dir)):
            project_path = _decode_project_path(dirname)
            claude_dir = os.path.join(project_path, ".claude")
            files = []
            for fname in ("settings.json", "settings.local.json"):
                if os.path.isfile(os.path.join(claude_dir, fname)):
                    files.append(fname)
            if files:
                containers.append({
                    "id": dirname,
                    "name": _friendly_name(dirname),
                    "files": files,
                })
    return containers


def get_settings_content(container_id, filename):
    """Read and return the content of a settings file."""
    if filename not in ("settings.json", "settings.local.json"):
        raise ValueError("Invalid settings filename")

    if container_id == "global":
        filepath = os.path.join(str(CLAUDE_DIR), filename)
    else:
        project_path = _decode_project_path(container_id)
        filepath = os.path.join(project_path, ".claude", filename)

    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Settings file not found: {filepath}")

    with open(filepath, "r") as f:
        return f.read()
