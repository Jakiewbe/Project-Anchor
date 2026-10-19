"""Versioned task ledger; progress is a derived view.

Schema 2 makes the approved scope an explicit, program-owned snapshot.  A task
cannot become approved through ``task update`` or ``task add``; approval is its
own operation, and changing the scope requires a revision plus a fresh
approval.  Evidence is bound to the approval version and criterion text so a
reordered or weakened criterion cannot silently reuse old evidence.
"""
from collections import deque
from datetime import datetime, timezone
import json
import re

from .atomic_io import KitError, digest

SCHEMA = 2
STATUSES = {"todo", "doing", "blocked", "done", "cancelled"}
TRANSITIONS = {
    "todo": {"doing", "blocked", "cancelled"},
    "doing": {"done", "blocked", "todo", "cancelled"},
    "blocked": {"doing", "todo", "cancelled"},
    "done": {"doing"},
    "cancelled": {"todo"},
}
EVIDENCE_TYPES = {"test", "file", "review", "manual", "command"}
EVIDENCE_LEVELS = {"claimed", "observed", "reviewed"}
SCOPE_FIELDS = ("description", "acceptance_criteria", "dependencies")
TASK_FIELDS = {
    "task_id", "title", "description", "milestone", "status", "plan",
    "dependencies", "acceptance_criteria", "evidence", "blocker",
    "approved_scope", "legacy_unverified", "updated_at", "completed_at",
}
EVIDENCE_FIELDS = {
    "type", "criterion", "detail", "level", "scope_version", "criteria_hash",
    "recorded_at", "invalidated_at", "invalidated_reason",
}
APPROVED_SCOPE_FIELDS = {
    "project_id", "task_id", "version", "hash", "description",
    "acceptance_criteria", "dependencies", "approved_at", "source", "reason",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise KitError(f"{label} 必须是非空文字")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def criterion_hash(value):
    return digest(value.encode("utf-8"))


def scope_values(description, criteria, dependencies):
    return {"description": description, "acceptance_criteria": list(criteria),
            "dependencies": list(dependencies)}


def scope_hash(task):
    return digest(_canonical(scope_values(task["description"], task["acceptance_criteria"], task["dependencies"])))


def approved_scope_hash(scope):
    return digest(_canonical(scope_values(scope["description"], scope["acceptance_criteria"], scope["dependencies"])))


def scope_dirty(task):
    """True when the working scope no longer matches the last approved snapshot."""
    if task["plan"] != "approved":
        return False
    if task.get("legacy_unverified"):
        return False
    approved = task.get("approved_scope")
    if not approved:
        return True
    return approved.get("hash") != scope_hash(task)


def evidence_valid(task, item):
    if item.get("invalidated_at"):
        return False
    if task.get("legacy_unverified"):
        return True
    approved = task.get("approved_scope")
    if not approved:
        return False
    if item.get("scope_version") != approved["version"]:
        return False
    index = item["criterion"]
    criteria = task["acceptance_criteria"]
    return item.get("criteria_hash") == criterion_hash(criteria[index - 1])


def coverage_ok(task):
    if task.get("legacy_unverified"):
        covered = {item["criterion"] for item in task["evidence"]}
    else:
        covered = {item["criterion"] for item in task["evidence"] if evidence_valid(task, item)}
    return covered == set(range(1, len(task["acceptance_criteria"]) + 1))


def validate(ledger, project_id=None):
    """Validate schema 1 (read-only legacy) or schema 2 (current)."""
    schema = ledger.get("schema") if isinstance(ledger, dict) else None
    if schema == 1:
        return _validate_v1(ledger, project_id)
    if schema == 2:
        return _validate_v2(ledger, project_id)
    raise KitError("不支持的任务账本版本")


def _validate_v1(ledger, project_id=None):
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


def _validate_v2(ledger, project_id=None):
    if not isinstance(ledger, dict) or ledger.get("schema") != 2:
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
        unknown = set(task) - TASK_FIELDS
        if unknown:
            raise KitError(f"未知任务字段: {', '.join(sorted(unknown))}")
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
        legacy = task.get("legacy_unverified", False)
        if type(legacy) is not bool:
            raise KitError("legacy_unverified 必须为布尔值")
        approved = task.get("approved_scope")
        if approved is not None:
            if not isinstance(approved, dict):
                raise KitError("approved_scope 必须为对象")
            unknown_scope = set(approved) - APPROVED_SCOPE_FIELDS
            if unknown_scope:
                raise KitError(f"未知批准范围字段: {', '.join(sorted(unknown_scope))}")
            if approved.get("project_id") != ledger.get("project_id"):
                raise KitError("批准范围属于其他项目")
            if approved.get("task_id") != tid:
                raise KitError("批准范围属于其他任务")
            if type(approved.get("version")) is not int or approved["version"] < 1:
                raise KitError("批准范围版本无效")
            if not isinstance(approved.get("hash"), str) or not HEX64.fullmatch(approved["hash"]):
                raise KitError("批准范围哈希无效")
            text(approved.get("description"), "批准范围描述")
            criteria = approved.get("acceptance_criteria")
            if not isinstance(criteria, list) or not criteria:
                raise KitError("批准范围缺少验收标准")
            for criterion in criteria:
                text(criterion, "批准范围验收标准")
            deps = approved.get("dependencies")
            if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
                raise KitError("批准范围依赖格式错误")
            text(approved.get("approved_at"), "批准时间")
            text(approved.get("source"), "批准来源")
            text(approved.get("reason"), "批准原因")
            if approved["hash"] != approved_scope_hash(approved):
                raise KitError("批准范围内容与哈希不一致")
        if legacy and approved is not None:
            raise KitError("legacy 任务不能同时带有批准范围")
        if task["plan"] == "approved" and not legacy and approved is None:
            raise KitError("已批准任务缺少批准范围记录")
        evidence = task["evidence"]
        for item in evidence:
            if not isinstance(item, dict) or item.get("type") not in EVIDENCE_TYPES:
                raise KitError("证据类型无效")
            unknown_evidence = set(item) - EVIDENCE_FIELDS
            if unknown_evidence:
                raise KitError(f"未知证据字段: {', '.join(sorted(unknown_evidence))}")
            text(item.get("detail"), "证据描述")
            if type(item.get("criterion")) is not int or not 1 <= item["criterion"] <= len(task["acceptance_criteria"]):
                raise KitError("证据须对应验收标准序号（从 1 开始）")
            level = item.get("level")
            if level not in EVIDENCE_LEVELS:
                raise KitError("证据级别无效")
            if type(item.get("scope_version")) is not int or item["scope_version"] < 0:
                raise KitError("证据范围版本无效")
            if not isinstance(item.get("criteria_hash"), str) or not HEX64.fullmatch(item["criteria_hash"]):
                raise KitError("证据标准哈希无效")
            text(item.get("recorded_at"), "证据记录时间")
            if "invalidated_at" in item:
                text(item["invalidated_at"], "证据失效时间")
            if "invalidated_reason" in item:
                text(item["invalidated_reason"], "证据失效原因")
        if task["status"] in {"doing", "done"} and task["plan"] != "approved":
            raise KitError("草案任务不能开始或完成")
        if task["status"] == "done" and not coverage_ok(task):
            raise KitError("完成任务需要覆盖当前批准范围内全部验收标准的有效证据")
        if task["status"] in {"doing", "done"} and not legacy and scope_dirty(task):
            raise KitError("任务当前范围与批准范围不一致，请先重新批准")
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


def _invalidate_evidence(task, reason):
    stamp = now()
    changed = False
    for item in task["evidence"]:
        if not item.get("invalidated_at"):
            item["invalidated_at"] = stamp
            item["invalidated_reason"] = reason
            changed = True
    return changed


def _new_evidence(task, items):
    approved = task.get("approved_scope")
    if not approved:
        raise KitError("任务没有批准范围，不能登记证据；请先 task approve")
    result = []
    for item in items:
        if not isinstance(item, dict) or set(item) - {"type", "criterion", "detail"}:
            raise KitError("证据只能提交 type、criterion、detail；内部字段由程序生成")
        if item.get("type") not in EVIDENCE_TYPES:
            raise KitError("证据类型无效")
        text(item.get("detail"), "证据描述")
        if type(item.get("criterion")) is not int or not 1 <= item["criterion"] <= len(task["acceptance_criteria"]):
            raise KitError("证据须对应验收标准序号（从 1 开始）")
        criterion = task["acceptance_criteria"][item["criterion"] - 1]
        result.append({"type": item["type"], "criterion": item["criterion"],
                       "detail": item["detail"], "level": "claimed",
                       "scope_version": approved["version"],
                       "criteria_hash": criterion_hash(criterion),
                       "recorded_at": now()})
    return result


def _approve(task, ledger, reason, source):
    text(source, "批准来源")
    if task["status"] in {"done", "cancelled"}:
        raise KitError("已完成或取消的任务不能直接批准；请先 task revise")
    if task["plan"] == "approved" and not task.get("legacy_unverified") and not scope_dirty(task):
        return task, False
    previous = task.get("approved_scope")
    version = (previous["version"] + 1) if previous else 1
    task["approved_scope"] = {
        "project_id": ledger["project_id"], "task_id": task["task_id"],
        "version": version, "hash": scope_hash(task),
        "description": task["description"],
        "acceptance_criteria": list(task["acceptance_criteria"]),
        "dependencies": list(task["dependencies"]),
        "approved_at": now(), "source": source, "reason": reason,
    }
    task["plan"] = "approved"
    task["legacy_unverified"] = False
    task.pop("completed_at", None)
    _invalidate_evidence(task, "范围重新批准，旧证据失效")
    task["updated_at"] = now()
    return task, True


def _revise(task):
    if task["plan"] != "approved" and not task.get("legacy_unverified"):
        raise KitError("只有已批准任务需要修订；草案可直接修改")
    if task["status"] == "cancelled":
        raise KitError("已取消任务不能修订；请先恢复为 todo")
    task["plan"] = "draft"
    task["status"] = "todo"
    task["legacy_unverified"] = False
    task.pop("completed_at", None)
    _invalidate_evidence(task, "任务范围修订，旧证据失效")
    task["updated_at"] = now()


def mutate(ledger, action, payload, reason, source=None):
    text(reason, "变更原因")
    if ledger.get("schema") != 2:
        raise KitError("任务账本为 schema 1，只读；请先执行 migrate")
    validate(ledger)
    if not isinstance(payload, dict):
        raise KitError("任务输入必须为对象")
    tasks = ledger["tasks"]
    tid = payload.get("task_id")
    previous = next((t for t in tasks if t["task_id"] == tid), None)
    if action == "add":
        if previous:
            raise KitError("任务 ID 已存在")
        if payload.get("plan", "draft") != "draft":
            raise KitError("新增任务只能建立草案；批准请使用 task approve")
        if "evidence" in payload or "approved_scope" in payload or "legacy_unverified" in payload:
            raise KitError("新增任务不能携带证据或批准范围")
        allowed = {"task_id", "title", "description", "milestone", "plan", "dependencies", "acceptance_criteria", "blocker"}
        if set(payload) - allowed:
            raise KitError("未知任务字段")
        item = dict(payload)
        item.setdefault("description", item.get("title", ""))
        for key, default in {"milestone": "默认", "dependencies": [], "acceptance_criteria": [], "blocker": ""}.items():
            item.setdefault(key, default)
        item.update({"status": "todo", "plan": "draft", "evidence": [], "legacy_unverified": False})
        item["updated_at"] = now()
        tasks.append(item)
    elif action == "update":
        if previous is None:
            raise KitError("任务不存在")
        internal = {"plan", "approved_scope", "legacy_unverified"}
        if set(payload) & internal:
            raise KitError("plan、approved_scope、legacy_unverified 不能由 task update 修改；请使用 task approve/revise")
        allowed = {"task_id", "title", "description", "milestone", "status", "dependencies", "acceptance_criteria", "evidence", "blocker"}
        if set(payload) - allowed:
            raise KitError("未知任务字段")
        status = payload.get("status", previous["status"])
        if status != previous["status"] and status not in TRANSITIONS[previous["status"]]:
            raise KitError(f"不允许从 {previous['status']} 转为 {status}")
        scope_change = any(key in payload and payload[key] != previous[key] for key in SCOPE_FIELDS)
        if previous["plan"] == "approved" and scope_change:
            raise KitError("已批准任务的验收标准、依赖或描述发生变化；请先 task revise，再重新批准")
        candidate = {**previous, **{key: value for key, value in payload.items() if key != "evidence"}}
        if "status" in payload and status in {"doing", "done"} and candidate.get("legacy_unverified"):
            raise KitError("旧任务批准来源未验证，请先 task approve 再开始或完成")
        if "evidence" in payload:
            if status == "done" and previous["status"] == "done":
                raise KitError("先重新打开任务再更改证据")
            if candidate.get("plan") != "approved":
                raise KitError("只有已批准任务可以登记证据")
            if candidate.get("legacy_unverified"):
                raise KitError("旧任务必须先 task approve 才能登记新证据")
            candidate["evidence"] = previous["evidence"] + _new_evidence(candidate, payload["evidence"])
        validate({**ledger, "tasks": [candidate if item is previous else item for item in tasks]})
        if all(previous.get(key) == value for key, value in payload.items() if key != "evidence") and "evidence" not in payload:
            return ledger
        if previous["status"] == "done" and status == "doing":
            _invalidate_evidence(previous, "任务重新打开，旧证据失效")
        old_status = previous["status"]
        previous.update(candidate)
        previous["updated_at"] = now()
        if status == "done" and old_status != "done":
            previous["completed_at"] = now()
        elif status != "done":
            previous.pop("completed_at", None)
    elif action == "approve":
        if previous is None:
            raise KitError("任务不存在")
        if set(payload) - {"task_id"}:
            raise KitError("task approve 只接受 task_id")
        candidate = {**previous}
        candidate, changed = _approve(candidate, ledger, reason, source)
        if not changed:
            return ledger
        previous.update(candidate)
    elif action == "revise":
        if previous is None:
            raise KitError("任务不存在")
        if set(payload) - {"task_id"}:
            raise KitError("task revise 只接受 task_id")
        candidate = {**previous}
        _revise(candidate)
        previous.update(candidate)
    else:
        raise KitError("未知任务操作（删除请使用 cancelled 保留历史）")
    ledger["revision"] += 1
    ledger["history"].append({"revision": ledger["revision"], "timestamp": now(), "action": action,
                              "payload": payload, "reason": reason})
    return validate(ledger)


def decorate(task):
    value = dict(task)
    value["scope_dirty"] = scope_dirty(task)
    value.setdefault("legacy_unverified", False)
    return value


def task_view(ledger, brief=False, task_ids=None, milestone=None):
    """An explicit selection; never infer the current scope from timestamps."""
    validate(ledger)
    items = ledger["tasks"]
    ids = set(task_ids or [])
    unknown = ids - {item["task_id"] for item in items}
    if unknown:
        raise KitError(f"任务不存在: {', '.join(sorted(unknown))}")
    if milestone is not None and not any(item["milestone"] == milestone for item in items):
        raise KitError(f"里程碑不存在: {milestone}")
    selected = [item for item in items if (not ids or item["task_id"] in ids)
                and (milestone is None or item["milestone"] == milestone)]
    if (ids or milestone is not None) and not selected:
        raise KitError("任务与里程碑筛选没有交集")
    counts = {status: sum(item["status"] == status for item in selected) for status in sorted(STATUSES)}
    approved = [item for item in selected if item["plan"] == "approved" and item["status"] != "cancelled"]
    evidence_levels = {level: sum(1 for item in selected for ev in item["evidence"] if ev.get("level") == level)
                       for level in sorted(EVIDENCE_LEVELS)}
    summary = {"total": len(selected), "draft": sum(item["plan"] == "draft" for item in selected),
               "approved_active": len(approved), "approved_done": sum(item["status"] == "done" for item in approved),
               "legacy_unverified": sum(bool(item.get("legacy_unverified")) for item in selected),
               "scope_dirty": sum(scope_dirty(item) for item in selected),
               "invalidated_evidence": sum(1 for item in selected for ev in item["evidence"] if ev.get("invalidated_at")),
               "evidence_levels": evidence_levels, "statuses": counts}
    fields = ("task_id", "title", "milestone", "plan", "status", "dependencies", "blocker",
              "scope_dirty", "legacy_unverified")
    decorated = [decorate(item) for item in selected]
    visible = [{key: item[key] for key in fields} for item in decorated] if brief else decorated
    by_id = {item["task_id"]: item for item in items}
    external = sorted({dep for item in selected for dep in item["dependencies"]} - {item["task_id"] for item in selected})
    dependencies = [{key: decorate(by_id[tid])[key] for key in fields} for tid in external]
    return visible, summary, dependencies


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
