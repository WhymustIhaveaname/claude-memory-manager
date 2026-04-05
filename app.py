import os
import sys
import io
import argparse

# Resolve plugin root: CLAUDE_PLUGIN_ROOT env var, or the directory containing this script
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_ROOT)

from flask import Flask, request, jsonify, send_file, render_template
import memory_ops

app = Flask(__name__, template_folder=os.path.join(PLUGIN_ROOT, "templates"))


def _resolve_container(container_id):
    if container_id == "global":
        path = str(memory_ops.GLOBAL_MEMORY_DIR)
        return path if os.path.isdir(path) else None
    mem_dir = os.path.join(str(memory_ops.PROJECTS_DIR), container_id, "memory")
    if os.path.isdir(mem_dir):
        return mem_dir
    return None


@app.errorhandler(500)
def handle_500(e):
    return jsonify({"error": str(e)}), 500


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/containers")
def get_containers():
    return jsonify(memory_ops.list_containers())


@app.route("/api/memories/<container_id>")
def get_memories(container_id):
    path = _resolve_container(container_id)
    if not path:
        return jsonify({"error": "Container not found"}), 404
    return jsonify(memory_ops.scan_container(path))


@app.route("/api/memory/<container_id>/<filename>", methods=["GET", "PUT"])
def handle_memory(container_id, filename):
    path = _resolve_container(container_id)
    if not path:
        return jsonify({"error": "Container not found"}), 404
    if request.method == "GET":
        filepath = os.path.join(path, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404
        with open(filepath, "r") as f:
            content = f.read()
        return jsonify({"content": content})
    else:  # PUT
        data = request.get_json()
        if not data or not all(k in data for k in ("old_content", "new_content")):
            return jsonify({"error": "Missing fields: old_content, new_content"}), 400
        try:
            memory_ops.edit_memory(path, filename, data["old_content"], data["new_content"], container_id=container_id)
            return jsonify({"ok": True})
        except ValueError:
            return jsonify({"error": "Conflict: file modified since last read"}), 409


@app.route("/api/move", methods=["POST"])
def move():
    data = request.get_json()
    if not data or not all(k in data for k in ("files", "from", "to")):
        return jsonify({"error": "Missing fields: files, from, to"}), 400
    src = _resolve_container(data["from"])
    dst = _resolve_container(data["to"])
    if not src or not dst:
        return jsonify({"error": "Container not found"}), 404
    try:
        memory_ops.move_memories(src, dst, data["files"], from_id=data["from"], to_id=data["to"])
        return jsonify({"ok": True})
    except FileExistsError as e:
        return jsonify({"error": str(e)}), 409


@app.route("/api/delete", methods=["POST"])
def delete():
    data = request.get_json()
    if not data or not all(k in data for k in ("files", "container")):
        return jsonify({"error": "Missing fields: files, container"}), 400
    path = _resolve_container(data["container"])
    if not path:
        return jsonify({"error": "Container not found"}), 404
    memory_ops.delete_memories(path, data["files"], container_id=data["container"])
    return jsonify({"ok": True})


@app.route("/api/export", methods=["POST"])
def export():
    data = request.get_json()
    if not data or not all(k in data for k in ("files", "container")):
        return jsonify({"error": "Missing fields: files, container"}), 400
    path = _resolve_container(data["container"])
    if not path:
        return jsonify({"error": "Container not found"}), 404
    zip_bytes = memory_ops.export_memories(path, data["files"], container_id=data["container"])
    return send_file(io.BytesIO(zip_bytes), mimetype="application/zip", as_attachment=True, download_name="claude-memory-export.zip")


@app.route("/api/import", methods=["POST"])
def import_memories():
    if "file" not in request.files or "container" not in request.form:
        return jsonify({"error": "Missing file or container"}), 400
    container_id = request.form["container"]
    path = _resolve_container(container_id)
    if not path:
        return jsonify({"error": "Container not found"}), 404
    zip_bytes = request.files["file"].read()
    try:
        memory_ops.import_memories(path, zip_bytes, container_id=container_id)
        return jsonify({"ok": True})
    except FileExistsError as e:
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        return jsonify({"error": f"Invalid zip: {e}"}), 400



@app.route("/api/settings-containers")
def get_settings_containers():
    return jsonify(memory_ops.list_settings_containers())


@app.route("/api/settings/<container_id>/<filename>")
def get_settings(container_id, filename):
    try:
        content = memory_ops.get_settings_content(container_id, filename)
        return jsonify({"content": content})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()
    app.run(host="127.0.0.1", port=args.port)
