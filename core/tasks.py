"""The task ledger is the sole task source; progress is a derived view."""
from datetime import datetime, timezone
from collections import deque
import re
from .atomic_io import KitError

STATUSES = {"todo", "doing", "blocked", "done", "cancelled"}
TRANSITIONS = {
    "todo": {"doing", "blocked", "cancelled"},
    "doing": {"done", "blocked", "todo", "cancelled"},
    "blocked": {"doing", "todo", "cancelled"},
    "done": {"doing"},
    "cancelled": {"todo"},
}
EVIDENCE_TYPES = {"test", "file", "review", "manual", "command"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise KitError(f"{label} 必须是非空文字")


def validate(ledger, project_id=None):
    if not isinstance(ledger, dict) or ledger.get("schema") != 1:
        raise KitError("不支持的任务账本版本")
    if project_id and ledger.get("project_id") != project_id:
        raise KitError("任务账本属于其他项目")
    if type(ledger.get("revision")) is not int or ledger["revision"] < 0:
        raise KitError("任务修订号无效")
    tasks = ledger.get("tasks")
    if not isinstance(tasks, list) or not isinstance(ledger.get("history"), list):
        raise KitError("任务或变更历史损坏")
    by_id = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise KitError("任务格式错误")
        for key in ("task_id", "title", "description", "milestone", "status", "plan"):
            text(task.get(key), key)
        tid = task["task_id"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", tid) or tid in by_id:
            raise KitError("任务 ID 无效或重复")
        if task["status"] not in STATUSES or task["plan"] not in {"draft", "approved"}:
            raise KitError("任务状态或计划状态无效")
        for key in ("dependencies", "acceptance_criteria", "evidence"):
            if not isinstance(task.get(key), list):
                raise KitError(f"{key} 必须为数组")
        if not task["acceptance_criteria"]:
            raise KitError("任务必须有验收标准")
        for criterion in task["acceptance_criteria"]:
            text(criterion, "验收标准")
        if any(not isinstance(dep, str) for dep in task["dependencies"]) or len(set(task["dependencies"])) != len(task["dependencies"]):
            raise KitError("依赖格式错误或重复")
        if not isinstance(task.get("blocker"), str):
            raise KitError("blocker 必须为文字")
        if task["status"] == "blocked":
            text(task["blocker"], "阻塞原因")
        evidence = task["evidence"]
        for item in evidence:
            if not isinstance(item, dict) or item.get("type") not in EVIDENCE_TYPES:
                raise KitError("证据类型无效")
            text(item.get("detail"), "证据描述")
            if type(item.get("criterion")) is not int or not 1 <= item["criterion"] <= len(task["acceptance_criteria"]):
                raise KitError("证据须对应验收标准序号（从 1 开始）")
        if task["status"] in {"doing", "done"} and task["plan"] != "approved":
            raise KitError("草案任务不能开始或完成")
        if task["status"] == "done" and {item["criterion"] for item in evidence} != set(range(1, len(task["acceptance_criteria"]) + 1)):
            raise KitError("完成任务需要覆盖全部验收标准的证据")
        by_id[tid] = task
    remaining, successors = {}, {tid: [] for tid in by_id}
    for tid, task in by_id.items():
        remaining[tid] = len(task["dependencies"])
        for dep in task["dependencies"]:
            if dep not in by_id:
                raise KitError(f"依赖任务不存在: {dep}")
            if by_id[tid]["status"] in {"doing", "done"} and by_id[dep]["status"] != "done":
                raise KitError("开始或完成任务前必须完成所有依赖")
            successors[dep].append(tid)
    ready = deque(tid for tid, count in remaining.items() if count == 0)
    visited = 0
    while ready:
        tid = ready.popleft()
        visited += 1
        for successor in successors[tid]:
            remaining[successor] -= 1
            if remaining[successor] == 0:
                ready.append(successor)
    if visited != len(by_id):
        raise KitError("任务循环依赖")
    return ledger


def mutate(ledger, action, payload, reason):
    text(reason, "变更原因")
    tasks = ledger["tasks"]
    tid = payload.get("task_id")
    previous = next((t for t in tasks if t["task_id"] == tid), None)
    if action == "add":
        if previous:
            raise KitError("任务 ID 已存在")
        item = dict(payload)
        allowed = {"task_id", "title", "description", "milestone", "status", "plan", "dependencies", "acceptance_criteria", "evidence", "blocker"}
        if set(item) - allowed:
            raise KitError("未知任务字段")
        item.setdefault("description", item.get("title", ""))
        for key, default in {"milestone": "默认", "status": "todo", "plan": "draft", "dependencies": [], "evidence": [], "blocker": ""}.items():
            item.setdefault(key, default)
        if item["status"] != "todo":
            raise KitError("新增任务必须从 todo 开始")
        item["updated_at"] = now()
        tasks.append(item)
    elif action == "update":
        if previous is None:
            raise KitError("任务不存在")
        allowed = {"task_id", "title", "description", "milestone", "status", "plan", "dependencies", "acceptance_criteria", "evidence", "blocker"}
        if set(payload) - allowed:
            raise KitError("未知任务字段")
        status = payload.get("status", previous["status"])
        if status != previous["status"] and status not in TRANSITIONS[previous["status"]]:
            raise KitError(f"不允许从 {previous['status']} 转为 {status}")
        if previous["status"] == "done" and any(key in payload for key in {"acceptance_criteria", "dependencies", "evidence"}) and status == "done":
            raise KitError("先重新打开任务再更改验收范围或证据")
        if previous["status"] == "done" and status == "doing":
            previous["evidence"] = []
        previous.update(payload)
        previous["updated_at"] = now()
        if status == "done":
            previous["completed_at"] = now()
        else:
            previous.pop("completed_at", None)
    else:
        raise KitError("未知任务操作（删除请使用 cancelled 保留历史）")
    ledger["revision"] += 1
    ledger["history"].append({"revision": ledger["revision"], "timestamp": now(), "action": action, "payload": payload, "reason": reason})
    return validate(ledger)


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def progress(name, ledger):
    validate(ledger)
    tasks = ledger["tasks"]
    counted = [t for t in tasks if t["status"] != "cancelled"]
    done = [t for t in counted if t["status"] == "done"]
    rate = len(done) / len(counted) if counted else 0
    lines = [f"# {cell(name)} — 进度（程序生成，请勿手工编辑）", "",
             f"账本修订: {ledger['revision']}", f"总任务: {len(tasks)}；有效任务: {len(counted)}；已完成: {len(done)}；完成率: {rate:.0%}",
             "[" + "#" * int(rate * 20) + "-" * (20 - int(rate * 20)) + "]", "", "## 里程碑", "", "| 里程碑 | 完成 / 有效任务 |", "| --- | --- |"]
    for milestone in sorted({t["milestone"] for t in tasks}):
        subset = [t for t in counted if t["milestone"] == milestone]
        lines.append(f"| {cell(milestone)} | {sum(t['status'] == 'done' for t in subset)} / {len(subset)} |")
    for title, subset in [
        ("当前活跃", [t for t in tasks if t["status"] == "doing"]),
        ("阻塞任务", [t for t in tasks if t["status"] == "blocked"]),
        ("最近完成", sorted(done, key=lambda t: t.get("completed_at", ""), reverse=True)[:10]),
        ("下一阶段", [t for t in tasks if t["status"] == "todo"]),
    ]:
        lines.extend(["", f"## {title}", "", "| ID | 标题 | 计划 | 依赖 / 阻塞 |", "| --- | --- | --- | --- |"])
        for t in subset:
            lines.append(f"| {cell(t['task_id'])} | {cell(t['title'])} | {t['plan']} | {cell(t['blocker'] or ', '.join(t['dependencies']))} |")
    return "\n".join(lines) + "\n"
