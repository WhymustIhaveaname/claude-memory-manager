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
