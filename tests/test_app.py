import io
import os
import json
import tempfile
import shutil
import zipfile
import pytest

# Patch memory_ops paths before importing app
tmpdir = tempfile.mkdtemp()

import memory_ops
memory_ops.GLOBAL_MEMORY_DIR = os.path.join(tmpdir, ".claude", "memory")
memory_ops.PROJECTS_DIR = os.path.join(tmpdir, ".claude", "projects")
memory_ops.MANAGER_DIR = os.path.join(tmpdir, "manager")
memory_ops.LOG_FILE = os.path.join(tmpdir, "manager", "logs", "operations.jsonl")
memory_ops.BACKUP_DIR = os.path.join(tmpdir, "manager", "backups")

from app import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def setup_dirs():
    global_mem = memory_ops.GLOBAL_MEMORY_DIR
    os.makedirs(global_mem, exist_ok=True)
    with open(os.path.join(global_mem, "MEMORY.md"), "w") as f:
        f.write("- [g.md](g.md) — global entry\n")
    with open(os.path.join(global_mem, "g.md"), "w") as f:
        f.write("---\nname: g\ndescription: global entry\ntype: user\n---\n\nGlobal body")
    proj_mem = os.path.join(str(memory_ops.PROJECTS_DIR), "-home-user-proj", "memory")
    os.makedirs(proj_mem, exist_ok=True)
    with open(os.path.join(proj_mem, "MEMORY.md"), "w") as f:
        f.write("- [p.md](p.md) — project entry\n")
    with open(os.path.join(proj_mem, "p.md"), "w") as f:
        f.write("---\nname: p\ndescription: project entry\ntype: feedback\n---\n\nProject body")
    yield
    shutil.rmtree(os.path.join(tmpdir, ".claude"), ignore_errors=True)
    shutil.rmtree(os.path.join(tmpdir, "manager"), ignore_errors=True)

def test_get_containers(client):
    resp = client.get("/api/containers")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 2
    assert data[0]["id"] == "global"

def test_get_memories(client):
    resp = client.get("/api/memories/global")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["filename"] == "g.md"

def test_get_memory_content(client):
    resp = client.get("/api/memory/global/g.md")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "Global body" in data["content"]

def test_get_memory_404(client):
    resp = client.get("/api/memory/global/nonexistent.md")
    assert resp.status_code == 404

def test_move(client):
    resp = client.post("/api/move", json={"files": ["p.md"], "from": "-home-user-proj", "to": "global"})
    assert resp.status_code == 200
    assert os.path.exists(os.path.join(str(memory_ops.GLOBAL_MEMORY_DIR), "p.md"))

def test_move_conflict(client):
    with open(os.path.join(str(memory_ops.GLOBAL_MEMORY_DIR), "p.md"), "w") as f:
        f.write("conflict")
    resp = client.post("/api/move", json={"files": ["p.md"], "from": "-home-user-proj", "to": "global"})
    assert resp.status_code == 409

def test_delete(client):
    resp = client.post("/api/delete", json={"files": ["g.md"], "container": "global"})
    assert resp.status_code == 200
    assert not os.path.exists(os.path.join(str(memory_ops.GLOBAL_MEMORY_DIR), "g.md"))

def test_export(client):
    resp = client.post("/api/export", json={"files": ["g.md"], "container": "global"})
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        assert "g.md" in zf.namelist()
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest[0]["file"] == "g.md"

def test_import(client):
    resp = client.post("/api/export", json={"files": ["p.md"], "container": "-home-user-proj"})
    zip_bytes = resp.data
    client.post("/api/delete", json={"files": ["p.md"], "container": "-home-user-proj"})
    resp = client.post("/api/import",
        data={"file": (io.BytesIO(zip_bytes), "export.zip"), "container": "global"},
        content_type="multipart/form-data")
    assert resp.status_code == 200
    assert os.path.exists(os.path.join(str(memory_ops.GLOBAL_MEMORY_DIR), "p.md"))

def test_edit_memory(client):
    new_content = "---\nname: g\ndescription: updated\ntype: user\n---\n\nUpdated body"
    resp = client.put("/api/memory/global/g.md", json={
        "old_content": "---\nname: g\ndescription: global entry\ntype: user\n---\n\nGlobal body",
        "new_content": new_content,
    })
    assert resp.status_code == 200
    with open(os.path.join(str(memory_ops.GLOBAL_MEMORY_DIR), "g.md")) as f:
        assert f.read() == new_content

def test_edit_memory_conflict(client):
    resp = client.put("/api/memory/global/g.md", json={"old_content": "wrong", "new_content": "new"})
    assert resp.status_code == 409
