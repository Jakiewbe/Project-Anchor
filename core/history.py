"""Immutable, transaction-owned cold history. Never restores project state."""
import re
from .atomic_io import KitError, digest, encode_json, read_json, safe_path


def prepare(root, project_id, revision, entries):
    if not entries:
        return {}
    value = {"schema": 1, "project_id": project_id, "source_revision": revision, "entries": entries}
    data = encode_json(value)
    target = safe_path(root / ".agent/history" / (digest(data) + ".json"), root)
    if target.exists() and target.read_bytes() != data:
        raise KitError("历史归档冲突，停止裁剪")
    return {target: data}


def show(root, archive_id):
    if not isinstance(archive_id, str) or not re.fullmatch(r"[a-f0-9]{64}", archive_id):
        raise KitError("归档 ID 必须是64位内容哈希")
    path = safe_path(root / ".agent/history" / (archive_id + ".json"), root)
    value = read_json(path)
    identity = read_json(safe_path(root / ".agent/state.json", root))["project_id"]
    if (digest(path.read_bytes()) != archive_id or value.get("schema") != 1
            or value.get("project_id") != identity or not isinstance(value.get("entries"), list)):
        raise KitError("历史归档损坏或属于其他项目")
    return value


def listing(root, filename=None):
    folder = safe_path(root / ".agent/history", root)
    result = []
    for path in sorted(folder.glob("*.json")):
        value = show(root, path.stem)
        entries = [e for e in value["entries"] if filename is None or e.get("file") == filename]
        if entries:
            result.append({"archive_id": path.stem, "source_revision": value["source_revision"],
                           "entries": len(entries), "revisions": [e.get("revision") for e in entries]})
    return result
