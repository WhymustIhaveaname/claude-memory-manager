import os
import json
import tempfile
import shutil
import io
import zipfile
import pytest
from memory_ops import parse_frontmatter, scan_container, list_containers


class TestParseFrontmatter:
    def test_with_frontmatter(self):
        content = "---\nname: test\ndescription: A test\ntype: feedback\n---\n\nBody here"
        result = parse_frontmatter(content)
        assert result["name"] == "test"
        assert result["description"] == "A test"
        assert result["type"] == "feedback"
        assert result["body"] == "Body here"

    def test_without_frontmatter(self):
        content = "Just plain markdown\nNo frontmatter"
        result = parse_frontmatter(content)
        assert result["name"] == ""
        assert result["description"] == ""
        assert result["type"] == "unknown"
        assert result["body"] == content


class TestScanContainer:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.memory_dir = os.path.join(self.tmpdir, "memory")
        os.makedirs(self.memory_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_indexed_file(self):
        with open(os.path.join(self.memory_dir, "test.md"), "w") as f:
            f.write("---\nname: test\ndescription: A test\ntype: feedback\n---\n\nBody")
        with open(os.path.join(self.memory_dir, "MEMORY.md"), "w") as f:
            f.write("- [test.md](test.md) — A test\n")
        entries = scan_container(self.memory_dir)
        assert len(entries) == 1
        assert entries[0]["filename"] == "test.md"
        assert entries[0]["type"] == "feedback"
        assert entries[0]["status"] == "ok"

    def test_orphan_index_entry(self):
        with open(os.path.join(self.memory_dir, "MEMORY.md"), "w") as f:
            f.write("- [gone.md](gone.md) — Missing file\n")
        entries = scan_container(self.memory_dir)
        assert len(entries) == 1
        assert entries[0]["filename"] == "gone.md"
        assert entries[0]["status"] == "orphan"

    def test_unindexed_file(self):
        with open(os.path.join(self.memory_dir, "extra.md"), "w") as f:
            f.write("---\nname: extra\ndescription: Not indexed\ntype: user\n---\n\nContent")
        with open(os.path.join(self.memory_dir, "MEMORY.md"), "w") as f:
            f.write("")
        entries = scan_container(self.memory_dir)
        assert len(entries) == 1
        assert entries[0]["filename"] == "extra.md"
        assert entries[0]["status"] == "unindexed"


class TestListContainers:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = os.path.join(self.tmpdir, ".claude")
        self.global_mem = os.path.join(self.claude_dir, "memory")
        self.projects_dir = os.path.join(self.claude_dir, "projects")
        os.makedirs(self.global_mem)
        os.makedirs(self.projects_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_global_and_projects(self):
        with open(os.path.join(self.global_mem, "MEMORY.md"), "w") as f:
            f.write("- [a.md](a.md) — desc\n")
        with open(os.path.join(self.global_mem, "a.md"), "w") as f:
            f.write("content")
        proj_mem = os.path.join(self.projects_dir, "-home-user-myproject", "memory")
        os.makedirs(proj_mem)
        with open(os.path.join(proj_mem, "MEMORY.md"), "w") as f:
            f.write("")
        containers = list_containers(global_dir=self.global_mem, projects_dir=self.projects_dir)
        assert containers[0]["id"] == "global"
        assert containers[0]["name"] == "Global"
        assert containers[0]["count"] == 1
        assert containers[1]["id"] == "-home-user-myproject"
        assert "myproject" in containers[1]["name"]


class TestLoggingAndBackup:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manager_dir = os.path.join(self.tmpdir, "manager")

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_write_log(self):
        from memory_ops import _write_log
        log_file = os.path.join(self.manager_dir, "logs", "operations.jsonl")
        _write_log({"action": "test", "file": "x.md"}, log_file=log_file)
        with open(log_file) as f:
            line = json.loads(f.readline())
        assert line["action"] == "test"
        assert "timestamp" in line

    def test_backup_file(self):
        from memory_ops import _backup_file
        src = os.path.join(self.tmpdir, "source.md")
        with open(src, "w") as f:
            f.write("backup me")
        backup_dir = os.path.join(self.manager_dir, "backups")
        path = _backup_file(src, backup_dir=backup_dir)
        assert os.path.exists(path)
        with open(path) as f:
            assert f.read() == "backup me"


class TestDeleteMemories:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.memory_dir = os.path.join(self.tmpdir, "memory")
        self.manager_dir = os.path.join(self.tmpdir, "manager")
        os.makedirs(self.memory_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_delete_removes_file_and_index(self):
        with open(os.path.join(self.memory_dir, "a.md"), "w") as f:
            f.write("content a")
        with open(os.path.join(self.memory_dir, "MEMORY.md"), "w") as f:
            f.write("- [a.md](a.md) — desc a\n- [b.md](b.md) — desc b\n")
        from memory_ops import delete_memories
        delete_memories(
            self.memory_dir, ["a.md"],
            log_file=os.path.join(self.manager_dir, "logs", "ops.jsonl"),
            backup_dir=os.path.join(self.manager_dir, "backups"),
        )
        assert not os.path.exists(os.path.join(self.memory_dir, "a.md"))
        with open(os.path.join(self.memory_dir, "MEMORY.md")) as f:
            content = f.read()
        assert "a.md" not in content
        assert "b.md" in content

    def test_delete_creates_backup(self):
        with open(os.path.join(self.memory_dir, "a.md"), "w") as f:
            f.write("backup me")
        with open(os.path.join(self.memory_dir, "MEMORY.md"), "w") as f:
            f.write("- [a.md](a.md) — desc\n")
        from memory_ops import delete_memories
        delete_memories(
            self.memory_dir, ["a.md"],
            log_file=os.path.join(self.manager_dir, "logs", "ops.jsonl"),
            backup_dir=os.path.join(self.manager_dir, "backups"),
        )
        backups = os.listdir(os.path.join(self.manager_dir, "backups"))
        assert len(backups) == 1
        assert "a.md" in backups[0]


class TestMoveMemories:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src_dir = os.path.join(self.tmpdir, "src", "memory")
        self.dst_dir = os.path.join(self.tmpdir, "dst", "memory")
        self.manager_dir = os.path.join(self.tmpdir, "manager")
        os.makedirs(self.src_dir)
        os.makedirs(self.dst_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_move_transfers_file_and_index(self):
        with open(os.path.join(self.src_dir, "a.md"), "w") as f:
            f.write("content a")
        with open(os.path.join(self.src_dir, "MEMORY.md"), "w") as f:
            f.write("- [a.md](a.md) — desc a\n")
        with open(os.path.join(self.dst_dir, "MEMORY.md"), "w") as f:
            f.write("")
        from memory_ops import move_memories
        move_memories(
            self.src_dir, self.dst_dir, ["a.md"],
            log_file=os.path.join(self.manager_dir, "logs", "ops.jsonl"),
        )
        assert not os.path.exists(os.path.join(self.src_dir, "a.md"))
        assert os.path.exists(os.path.join(self.dst_dir, "a.md"))
        with open(os.path.join(self.dst_dir, "MEMORY.md")) as f:
            assert "a.md" in f.read()

    def test_move_conflict_raises(self):
        with open(os.path.join(self.src_dir, "a.md"), "w") as f:
            f.write("src")
        with open(os.path.join(self.dst_dir, "a.md"), "w") as f:
            f.write("dst already exists")
        with open(os.path.join(self.src_dir, "MEMORY.md"), "w") as f:
            f.write("- [a.md](a.md) — desc\n")
        with open(os.path.join(self.dst_dir, "MEMORY.md"), "w") as f:
            f.write("")
        from memory_ops import move_memories
        with pytest.raises(FileExistsError):
            move_memories(
                self.src_dir, self.dst_dir, ["a.md"],
                log_file=os.path.join(self.manager_dir, "logs", "ops.jsonl"),
            )


class TestExportMemories:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.memory_dir = os.path.join(self.tmpdir, "memory")
        self.manager_dir = os.path.join(self.tmpdir, "manager")
        os.makedirs(self.memory_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_export_creates_zip_with_manifest(self):
        with open(os.path.join(self.memory_dir, "a.md"), "w") as f:
            f.write("content a")
        with open(os.path.join(self.memory_dir, "MEMORY.md"), "w") as f:
            f.write("- [a.md](a.md) — desc a\n")
        from memory_ops import export_memories
        zip_bytes = export_memories(
            self.memory_dir, ["a.md"],
            log_file=os.path.join(self.manager_dir, "logs", "ops.jsonl"),
        )
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert "a.md" in zf.namelist()
            assert "manifest.json" in zf.namelist()
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest[0]["file"] == "a.md"
            assert "index_line" in manifest[0]
            assert "target" in manifest[0]


class TestImportMemories:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.memory_dir = os.path.join(self.tmpdir, "memory")
        self.manager_dir = os.path.join(self.tmpdir, "manager")
        os.makedirs(self.memory_dir)
        with open(os.path.join(self.memory_dir, "MEMORY.md"), "w") as f:
            f.write("")

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def _make_zip(self, files, manifest):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
            zf.writestr("manifest.json", json.dumps(manifest))
        return buf.getvalue()

    def test_import_adds_files_and_index(self):
        zip_bytes = self._make_zip(
            {"new.md": "---\nname: new\ntype: feedback\n---\nBody"},
            [{"file": "new.md", "index_line": "- [new.md](new.md) — new entry", "target": "/tmp"}],
        )
        from memory_ops import import_memories
        import_memories(
            self.memory_dir, zip_bytes,
            log_file=os.path.join(self.manager_dir, "logs", "ops.jsonl"),
        )
        assert os.path.exists(os.path.join(self.memory_dir, "new.md"))
        with open(os.path.join(self.memory_dir, "MEMORY.md")) as f:
            assert "new.md" in f.read()

    def test_import_conflict_raises(self):
        with open(os.path.join(self.memory_dir, "exist.md"), "w") as f:
            f.write("already here")
        zip_bytes = self._make_zip(
            {"exist.md": "new content"},
            [{"file": "exist.md", "index_line": "- [exist.md](exist.md) — x", "target": "/tmp"}],
        )
        from memory_ops import import_memories
        with pytest.raises(FileExistsError):
            import_memories(
                self.memory_dir, zip_bytes,
                log_file=os.path.join(self.manager_dir, "logs", "ops.jsonl"),
            )
