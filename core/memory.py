"""Versioned project state, snapshots, context and reviewed knowledge."""
import copy
import json
from pathlib import Path
import re
import subprocess
import uuid
from . import VERSION
from .atomic_io import (KitError, atomic_write, check_pending, digest, encode_json,
                        locked, read_json, safe_path, transaction)
from .tasks import now, progress, validate, mutate

KIT_ROOT = Path(__file__).resolve().parents[1]
DOCS = ("GOAL.md", "CURRENT.md", "DECISIONS.md", "LESSONS.md")
FILES = (*DOCS, "tasks.json")
GOAL_HEADINGS = ("核心目标", "项目背景", "关键约束", "非目标", "验收标准", "目标版本")
CURRENT_HEADINGS = ("当前阶段", "当前任务", "已完成工作", "当前阻塞", "下一步动作", "状态修订", "Git 检查")


def git_info(root):
    try:
        def run(args):
            result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, encoding="utf-8", errors="replace", timeout=10)
            return result.stdout.strip() if result.returncode == 0 else None
        top = run(["rev-parse", "--show-toplevel"])
        return {"root": top, "branch": run(["branch", "--show-current"]) if top else None,
                "commit": run(["rev-parse", "HEAD"]) if top else None,
                "changes": run(["status", "--porcelain"]) if top else None}
    except (OSError, subprocess.TimeoutExpired):
        return {"root": None, "branch": None, "commit": None, "changes": None}


def project_root(path):
    path = Path(path).resolve(strict=True)
    if not path.is_dir():
        raise KitError("项目路径必须为目录")
    for candidate in (path, *path.parents):
        if (candidate / ".agent/state.json").exists():
            safe_path(candidate / ".agent/state.json", candidate)
            return candidate
        if (candidate / ".git").exists():
            break
    raise KitError("当前目录及仓库内父目录未初始化 codex-rules")


def paths(root):
    agent = safe_path(Path(root) / ".agent", root)
    return agent, agent / ".lock", agent / ".transaction.json"


def validate_doc(name, value):
    if not isinstance(value, str) or not value.strip():
        raise KitError(f"{name} 不能为空")
    if len(value.encode("utf-8")) > 256 * 1024:
        raise KitError(f"{name} 超过 256 KiB")
    required = GOAL_HEADINGS if name == "GOAL.md" else CURRENT_HEADINGS if name == "CURRENT.md" else ()
    if any(f"## {heading}" not in value for heading in required):
        raise KitError(f"{name} 缺少必要章节: {', '.join(required)}")
    if name == "CURRENT.md" and len(value.splitlines()) > 50:
        raise KitError("CURRENT.md 不能超过 50 行")


def load(root, supplied_state=None):
    agent, _, journal = paths(root)
    check_pending(journal)
    state = supplied_state if supplied_state is not None else read_json(agent / "state.json")
    if not isinstance(state, dict) or state.get("schema") != 1:
        raise KitError("项目状态版本无效")
    try:
        uuid.UUID(state["project_id"])
        if not isinstance(state["name"], str) or not state["name"].strip() or not isinstance(state["history"], list):
            raise ValueError()
        for key in ("task_revision", "current_task_revision", "goal_version"):
            if type(state[key]) is not int or state[key] < (1 if key == "goal_version" else 0):
                raise ValueError()
        if type(state["goal_approved"]) is not bool:
            raise ValueError()
        if type(state["revision"]) is not int or state["revision"] < 0 or set(state["hashes"]) != set(FILES):
            raise ValueError()
        if type(state["snapshot_keep"]) is not int or not 1 <= state["snapshot_keep"] <= 1000:
            raise ValueError()
        if type(state["log_max_bytes"]) is not int or not 1024 <= state["log_max_bytes"] <= 10 * 1024 * 1024:
            raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise KitError("项目状态字段损坏") from exc
    content = {}
    for name in FILES:
        data = safe_path(agent / name, root).read_bytes()
        if digest(data) != state["hashes"][name]:
            raise KitError(f"{name} 与状态修订不一致，禁止静默覆盖。通过 state adopt 审核登记")
        try:
            content[name] = data.decode("utf-8-sig")
        except UnicodeError as exc:
            raise KitError(f"{name} 编码错误") from exc
        if name in DOCS:
            validate_doc(name, content[name])
    ledger = validate(read_json(agent / "tasks.json"), state["project_id"])
    if ledger["revision"] != state["task_revision"]:
        raise KitError("任务账本修订与状态记录不一致")
    return state, content, ledger


def init_project(path, name, git_init=False, snapshot_keep=20, log_max_bytes=65536):
    root = Path(path).resolve()
    if root == Path.home().resolve() or root == Path(root.anchor):
        raise KitError("用户主目录和磁盘根目录不能作为项目初始化；请选择具体项目目录")
    root.mkdir(parents=True, exist_ok=True)
    agent, lock, journal = paths(root)
    with locked(lock):
        check_pending(journal)
        if (agent / "state.json").exists():
            state, _, _ = load(root)
            if state["name"] != name:
                raise KitError("已初始化项目名称不同")
            return root
        if not name.strip() or not 1 <= snapshot_keep <= 1000 or not 1024 <= log_max_bytes <= 10485760:
            raise KitError("项目名或保留配置无效")
        collisions = [agent / p for p in (*FILES, "PROGRESS.md") if (agent / p).exists()]
        if collisions:
            raise KitError("存在未知项目状态文件，拒绝覆盖")
        info = git_info(root)
        if info["root"] and Path(info["root"]).resolve() != root:
            raise KitError("请在已有 Git 仓库根目录初始化")
        if git_init and not info["root"]:
            result = subprocess.run(["git", "init", str(root)], capture_output=True, timeout=15)
            if result.returncode:
                raise KitError("Git 初始化失败；尚未写入项目状态")
        project_id = str(uuid.uuid4())
        ledger = {"schema": 1, "project_id": project_id, "revision": 0, "tasks": [], "history": []}
        contents = {p: (KIT_ROOT / "project-template/.agent" / p).read_bytes() for p in DOCS}
        contents["tasks.json"] = encode_json(ledger)
        state = {"schema": 1, "kit_version": VERSION, "project_id": project_id, "name": name,
                 "revision": 0, "task_revision": 0, "current_task_revision": 0,
                 "goal_version": 1, "goal_approved": False, "updated_at": now(),
                 "snapshot_keep": snapshot_keep, "log_max_bytes": log_max_bytes,
                 "hashes": {p: digest(data) for p, data in contents.items()}, "history": []}
        updates = {agent / p: data for p, data in contents.items()}
        updates[agent / "state.json"] = encode_json(state)
        updates[agent / "PROGRESS.md"] = progress(name, ledger).encode("utf-8")
        rules = (KIT_ROOT / "project-template/AGENTS.md").read_bytes()
        agents_path = safe_path(root / "AGENTS.md", root)
        existing = agents_path.read_bytes() if agents_path.exists() else b""
        existing.decode("utf-8-sig")
        updates[agents_path] = existing + (b"\n" if existing else b"") + rules
        ignore = safe_path(root / ".gitignore", root)
        ignore_data = ignore.read_bytes() if ignore.exists() else b""
        ignore_data.decode("utf-8-sig")
        updates[ignore] = ignore_data + b"\n# codex-rules runtime and secrets\n.agent/runtime/\n.agent/.lock\n.agent/.transaction.json\n__pycache__/\n*.py[cod]\n.env\n.env.*\n*.pem\n*.key\n"
        attributes = safe_path(root / ".gitattributes", root)
        attribute_data = attributes.read_bytes() if attributes.exists() else b""
        attribute_data.decode("utf-8-sig")
        # State hashes describe bytes. Git must not translate their line endings.
        updates[attributes] = attribute_data + b"\n# codex-rules: preserve state bytes across computers\n.agent/** -text\n"
        transaction(root, journal, updates)
    return root


def _revision(state, expected):
    if state["revision"] != expected:
        raise KitError(f"修订冲突: 当前 {state['revision']}，请求 {expected}")


def _save(root, state, ledger, changes, action, reason):
    agent, _, journal = paths(root)
    on_disk = read_json(agent / "state.json")
    _revision(on_disk, state["revision"])
    for name in FILES:
        if digest(safe_path(agent / name, root).read_bytes()) != state["hashes"][name]:
            raise KitError(f"准备写入期间 {name} 发生修改")
    state["revision"] += 1
    state["updated_at"] = now()
    state["history"].append({"revision": state["revision"], "action": action, "reason": reason, "timestamp": now()})
    updates = {}
    for name, data in changes.items():
        updates[agent / name] = data
        state["hashes"][name] = digest(data)
    state["task_revision"] = ledger["revision"]
    updates[agent / "state.json"] = encode_json(state)
    # Progress is committed with the ledger, never claimed fresh after an error.
    updates[agent / "PROGRESS.md"] = progress(state["name"], ledger).encode("utf-8")
    transaction(root, journal, updates)
    return state["revision"]


def task_change(root, expected, action, payload, reason):
    agent, lock, _ = paths(root)
    with locked(lock):
        state, _, ledger = load(root)
        _revision(state, expected)
        revised = mutate(copy.deepcopy(ledger), action, payload, reason)
        return _save(root, state, revised, {"tasks.json": encode_json(revised)}, f"task:{action}", reason)


def doc_change(root, expected, name, value, reason, approved=False, adopt=False):
    if name not in DOCS or not reason.strip():
        raise KitError("状态文件名或变更原因无效")
    validate_doc(name, value)
    if name == "GOAL.md" and not approved:
        raise KitError("GOAL 变更必须先取得用户批准，传入 --approved")
    agent, lock, _ = paths(root)
    document_data = value.encode("utf-8")
    with locked(lock):
        if adopt:
            # Exactly one reviewed external document edit is allowed; all others
            # must still match their recorded hashes before the transaction.
            check_pending(agent / ".transaction.json")
            state = read_json(agent / "state.json")
            actual = (agent / name).read_bytes()
            if actual.decode("utf-8-sig").replace("\r\n", "\n") != value.replace("\r\n", "\n"):
                raise KitError("审核内容与磁盘内容不同")
            document_data = actual
            old_hash = state["hashes"].get(name)
            state["hashes"][name] = digest(actual)
            # Validate the remainder through a temporary in-memory hash override.
            state, _, ledger = load(root, state)
            state["hashes"][name] = old_hash
        else:
            state, _, ledger = load(root)
        _revision(state, expected)
        if name == "GOAL.md":
            state["goal_version"] += 1
            state["goal_approved"] = True
        if name == "CURRENT.md":
            state["current_task_revision"] = ledger["revision"]
        state["history"].append({"action": "document-version", "file": name,
                                 "previous_sha256": state["hashes"][name], "content": value,
                                 "user_approved": approved, "timestamp": now()})
        if adopt:
            state["hashes"][name] = digest(document_data)
        return _save(root, state, ledger, {name: document_data}, "state:adopt" if adopt else "state:update", reason)


def rebuild(root):
    agent, lock, _ = paths(root)
    with locked(lock):
        state, _, ledger = load(root)
        atomic_write(agent / "PROGRESS.md", progress(state["name"], ledger).encode("utf-8"))


def snapshot(root, session_id="manual"):
    agent, lock, _ = paths(root)
    with locked(lock):
        state, content, _ = load(root)
        # Retain the exact original encoding bytes, including UTF-8 BOM/CRLF.
        content = {name: safe_path(agent / name, root).read_bytes().decode("utf-8") for name in FILES}
        if any(digest(value.encode("utf-8")) != state["hashes"][name] for name, value in content.items()):
            raise KitError("快照准备期间状态文件发生修改")
        value = {"schema": 1, "project_id": state["project_id"], "timestamp": now(),
                 "session_id": session_id, "revision": state["revision"], "state": state,
                 "files": content, "hashes": {p: digest(text.encode("utf-8")) for p, text in content.items()}}
        folder = safe_path(agent / "runtime/snapshots", root)
        filename = "snapshot-" + re.sub(r"[^0-9]", "", now()) + "-" + uuid.uuid4().hex + ".json"
        target = folder / filename
        atomic_write(target, encode_json(value))
        # Prune only valid owned snapshots of this project; unknown files survive.
        owned = []
        for path in folder.glob("snapshot-*.json"):
            if path.is_symlink():
                continue
            try:
                item = read_json(path)
                validate_snapshot(item, state["project_id"])
                owned.append(path)
            except (KitError, OSError, KeyError, TypeError):
                continue
        for path in sorted(owned, key=lambda p: p.name)[:-state["snapshot_keep"]]:
            path.unlink()
        return target


def validate_snapshot(value, project_id):
    if not isinstance(value, dict) or value.get("schema") != 1 or value.get("project_id") != project_id:
        raise KitError("快照版本错误或属于其他项目")
    if set(value.get("files", {})) != set(FILES) or set(value.get("hashes", {})) != set(FILES):
        raise KitError("快照文件不完整")
    for name, content in value["files"].items():
        if not isinstance(content, str) or digest(content.encode("utf-8")) != value["hashes"][name]:
            raise KitError("快照内容损坏")
    if not isinstance(value.get("state"), dict) or value["state"].get("project_id") != project_id or value.get("revision") != value["state"].get("revision"):
        raise KitError("快照状态身份或修订不一致")
    if value["state"].get("hashes") != value["hashes"]:
        raise KitError("快照文件哈希与状态登记不一致")
    try:
        validate(json.loads(value["files"]["tasks.json"]), project_id)
    except ValueError as exc:
        raise KitError("快照任务账本损坏") from exc
    return value


def snapshot_check(root, path):
    state, _, _ = load(root)
    value = validate_snapshot(read_json(path), state["project_id"])
    return {"snapshot_revision": value["revision"], "disk_revision": state["revision"],
            "stale": value["revision"] < state["revision"], "automatic_restore": False}


def retro(root):
    agent, lock, _ = paths(root)
    with locked(lock):
        state, content, ledger = load(root)
        target = agent / "RETRO.md"
        if target.exists():
            raise KitError("RETRO.md 已存在，拒绝覆盖")
        body = (KIT_ROOT / "templates/RETRO.md").read_text(encoding="utf-8")
        body = body.replace("{{project}}", state["name"]).replace("{{goal}}", content["GOAL.md"])
        body = body.replace("{{delivered}}", "\n".join(f"- {t['task_id']}: {t['title']}；证据: {json.dumps(t['evidence'], ensure_ascii=False)}" for t in ledger["tasks"] if t["status"] == "done") or "尚无完成任务")
        body = body.replace("{{decisions}}", content["DECISIONS.md"]).replace("{{lessons}}", content["LESSONS.md"])
        atomic_write(target, body.encode("utf-8"))
        return target


def knowledge_add(source, approved, knowledge_root=None):
    if not approved:
        raise KitError("知识入库需要用户确认 --approved")
    item = read_json(source)
    for key in ("title", "conditions", "evidence", "limitations", "source_project", "lesson"):
        if not isinstance(item.get(key), str) or not item[key].strip():
            raise KitError(f"知识条目缺少 {key}")
    root = Path(knowledge_root or KIT_ROOT / "knowledge").resolve()
    with locked(root / ".lock"):
        journal = root / ".transaction.json"
        check_pending(journal)
        kid = digest(encode_json(item))[:20]
        path = root / "lessons" / (kid + ".json")
        if path.exists():
            if read_json(path) != item:
                raise KitError("知识 ID 冲突")
            return path
        index = root / "INDEX.md"
        existing = index.read_text(encoding="utf-8") if index.exists() else "# 跨项目知识索引\n"
        from .tasks import cell
        addition = f"\n- [{cell(item['title'])}](lessons/{kid}.json) — {cell(item['conditions'])}\n"
        transaction(root, journal, {path: encode_json(item), index: (existing + addition).encode("utf-8")})
        return path
