"""Execute configured checks and record self-review, never infer user approval."""
import copy
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
import uuid

from .atomic_io import KitError, atomic_write, digest, encode_json, locked, read_json, safe_path
from .tasks import criterion_hash, evidence_valid, now, validate

OUTPUT_LIMIT = 8 * 1024 * 1024


def fingerprint(root, inputs):
    root = Path(root).resolve()
    files = {}
    for item in inputs:
        target = safe_path(root / item, root)
        if not target.exists():
            raise KitError(f"检查输入不存在: {item}")
        if target == root or target.is_relative_to(root / ".agent") or target.is_relative_to(root / ".git"):
            raise KitError("检查输入不能是项目根目录、账本或运行目录；请明确业务材料目录")
        candidates = [target] if target.is_file() else sorted(target.rglob("*"))
        found = False
        for path in candidates:
            path = safe_path(path, root)
            if path.is_file():
                files[path.relative_to(root).as_posix()] = digest(path.read_bytes())
                found = True
        if not found:
            raise KitError(f"检查输入没有文件: {item}")
    if not files:
        raise KitError("检查输入不能为空")
    return digest(encode_json(dict(sorted(files.items()))))


def _receipt_path(root, run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise KitError("执行凭据 ID 无效")
    return safe_path(Path(root) / ".agent/evidence" / (run_id + ".json"), root)


def read_receipt(root, run_id):
    path = _receipt_path(root, run_id)
    receipt = read_json(path)
    identity = read_json(safe_path(Path(root) / ".agent/state.json", root))["project_id"]
    if not isinstance(receipt, dict) or receipt.get("schema") != 1 or receipt.get("project_id") != identity or receipt.get("run_id") != run_id:
        raise KitError("执行凭据损坏或属于其他项目")
    return receipt


def show(root, run_id):
    value = read_receipt(root, run_id)
    result = dict(value)
    logs = {}
    for name, metadata in value.get("logs", {}).items():
        path = safe_path(Path(root) / metadata["path"], root)
        logs[name] = path.is_file() and digest(path.read_bytes()) == metadata["sha256"]
    result["logs_available"] = logs
    result["incomplete"] = value.get("result") == "running"
    return result


def state(root, task):
    if task.get("verification_legacy") or task.get("legacy_unverified"):
        return "legacy"
    if not task.get("checks"):
        return "unconfigured"
    outcomes = []
    for check in task["checks"]:
        evidence = next((ev for ev in reversed(task["evidence"])
                         if ev["criterion"] == check["criterion"] and not ev.get("invalidated_at")), None)
        if evidence is None:
            outcomes.append("pending")
            continue
        try:
            receipt = read_receipt(root, evidence["run_id"])
            if digest(_receipt_path(root, evidence["run_id"]).read_bytes()) != evidence["receipt_sha256"]:
                raise KitError("执行凭据哈希不一致")
            if (receipt["task_id"] != task["task_id"] or receipt["scope_version"] != task["approved_scope"]["version"]
                    or receipt["criteria_hash"] != criterion_hash(task["acceptance_criteria"][check["criterion"] - 1])
                    or receipt["criterion"] != check["criterion"] or receipt["kind"] != check["kind"]
                    or receipt["input_hash"] != evidence["input_hash"]):
                raise KitError("执行凭据与批准范围不一致")
            if receipt["result"] != "pass" or evidence.get("result") != "pass":
                outcomes.append("failed")
            elif not evidence_valid(task, evidence):
                outcomes.append("invalid")
            else:
                try:
                    outcomes.append("pass" if fingerprint(root, check["inputs"]) == receipt["input_hash"] else "stale")
                except (OSError, KitError):
                    outcomes.append("stale")
        except (OSError, KitError, KeyError, TypeError, ValueError):
            outcomes.append("invalid")
    for outcome in ("invalid", "failed", "stale", "pending"):
        if outcome in outcomes:
            return outcome
    return "pass"


def require_fresh(root, task):
    value = state(root, task)
    if value != "pass":
        raise KitError(f"任务 {task['task_id']} 的验收记录为 {value}，需要当前材料对应的检查结果")


def _prepare(root, expected, task_id, criterion, kind, reason):
    from .memory import load, paths, require_schema2, _revision
    if not isinstance(reason, str) or not reason.strip():
        raise KitError("检查需要原因")
    _, lock, _ = paths(root)
    with locked(lock):
        project, _, ledger = load(root)
        require_schema2(ledger)
        _revision(project, expected)
        task = next((t for t in ledger["tasks"] if t["task_id"] == task_id), None)
        if not task or task["plan"] != "approved" or task.get("verification_legacy") or task.get("legacy_unverified"):
            raise KitError("检查需要已批准的新版任务")
        if task["status"] == "cancelled":
            raise KitError("已取消任务不能验收")
        if type(criterion) is not int:
            raise KitError("验收标准序号必须是整数")
        check = next((c for c in task["checks"] if c["criterion"] == criterion), None)
        if not check or check["kind"] != kind:
            raise KitError("验收类型不匹配")
        run_id = uuid.uuid4().hex
        receipt = {"schema": 1, "run_id": run_id, "project_id": project["project_id"],
                   "task_id": task_id, "criterion": criterion, "kind": kind,
                   "scope_version": task["approved_scope"]["version"], "scope_hash": task["approved_scope"]["hash"],
                   "criteria_hash": criterion_hash(task["acceptance_criteria"][criterion - 1]),
                   "expected_revision": expected, "input_hash": fingerprint(root, check["inputs"]),
                   "inputs": check["inputs"], "started_at": now(), "reason": reason, "result": "running"}
        if kind == "command":
            receipt["argv"] = check["argv"]
        atomic_write(_receipt_path(root, run_id), encode_json(receipt))
        return copy.deepcopy(check), receipt


def _finish(root, receipt):
    from .memory import load, paths, _revision, _save
    # Persist the final result first. A crash/conflict never reruns the command.
    path = _receipt_path(root, receipt["run_id"])
    if read_json(path).get("result") != "running":
        raise KitError("执行凭据已结束，拒绝覆盖")
    receipt["finished_at"] = now()
    atomic_write(path, encode_json(receipt))
    _, lock, _ = paths(root)
    with locked(lock):
        project, _, ledger = load(root)
        try:
            _revision(project, receipt["expected_revision"])
        except KitError as exc:
            raise KitError(f"{exc}；结果保留但未登记证据，run_id={receipt['run_id']}") from exc
        task = next(t for t in ledger["tasks"] if t["task_id"] == receipt["task_id"])
        if task.get("approved_scope", {}).get("hash") != receipt["scope_hash"]:
            raise KitError(f"检查期间批准范围变化；结果保留但未登记证据，run_id={receipt['run_id']}")
        check = next(c for c in task["checks"] if c["criterion"] == receipt["criterion"])
        if fingerprint(root, check["inputs"]) != receipt["input_hash"]:
            raise KitError(f"检查期间输入文件变化；结果保留但未登记证据，run_id={receipt['run_id']}")
        evidence = {"type": "test" if receipt["kind"] == "command" else "review",
                    "criterion": receipt["criterion"], "detail": receipt.get("summary", receipt["reason"]),
                    "level": "observed" if receipt["kind"] == "command" else "claimed",
                    "run_id": receipt["run_id"], "receipt_sha256": digest(path.read_bytes()),
                    "input_hash": receipt["input_hash"], "result": receipt["result"],
                    "scope_version": receipt["scope_version"], "criteria_hash": receipt["criteria_hash"],
                    "recorded_at": now()}
        if receipt["kind"] == "review":
            evidence["reviewer_kind"] = "self"
        task["evidence"].append(evidence)
        task["updated_at"] = now()
        ledger["revision"] += 1
        ledger["history"].append({"action": "verify:" + receipt["kind"], "revision": ledger["revision"],
                                   "timestamp": now(), "run_id": receipt["run_id"], "reason": receipt["reason"]})
        validate(ledger)
        revision = _save(root, project, ledger, {"tasks.json": encode_json(ledger)}, "verify:record", receipt["reason"])
        return {"run_id": receipt["run_id"], "result": receipt["result"], "revision": revision, "attached": True}


def review(root, expected, task_id, payload, reason):
    if (not isinstance(payload, dict) or set(payload) != {"criterion", "findings", "resolution", "simpler", "result"}
            or payload["result"] not in {"pass", "fail"}
            or any(not isinstance(payload[k], str) or not payload[k].strip() for k in ("findings", "resolution", "simpler"))):
        raise KitError("自查需要 criterion/findings/resolution/simpler/result，不接受审核来源或等级覆盖")
    _, receipt = _prepare(root, expected, task_id, payload["criterion"], "review", reason)
    receipt.update({"review": payload, "reviewer_kind": "self", "result": payload["result"],
                    "summary": payload["resolution"]})
    return _finish(root, receipt)


def _kill(child):
    if child.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True)
    else:
        os.killpg(child.pid, signal.SIGKILL)
    child.wait()


def run(root, expected, task_id, criterion, reason):
    check, receipt = _prepare(root, expected, task_id, criterion, "command", reason)
    receipt["argv"] = check["argv"]
    receipt["exit_code"] = None
    receipt["logs"] = {}
    logs = safe_path(Path(root) / ".agent/runtime/checks" / receipt["run_id"], root)
    logs.mkdir(parents=True, exist_ok=True)
    child = None
    threads = []
    overflow = threading.Event()
    errors = []
    total = [0]
    counter_lock = threading.Lock()
    def capture(stream, name):
        try:
            with (logs / name).open("wb") as target:
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    with counter_lock:
                        total[0] += len(chunk)
                        if total[0] > OUTPUT_LIMIT:
                            overflow.set()
                    if not overflow.is_set():
                        target.write(chunk)
        except OSError:
            errors.append("检查日志写入失败")
            overflow.set()
        finally:
            stream.close()
    try:
        child = subprocess.Popen(check["argv"], cwd=root, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                                 env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
                                 **({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
                                    if os.name == "nt" else {"start_new_session": True}))
        for stream, name in ((child.stdout, "stdout.log"), (child.stderr, "stderr.log")):
            thread = threading.Thread(target=capture, args=(stream, name), daemon=True)
            thread.start()
            threads.append(thread)
        deadline = time.monotonic() + check.get("timeout_seconds", 600)
        while child.poll() is None:
            if overflow.is_set():
                raise KitError("检查输出超过上限或日志写入失败")
            if time.monotonic() >= deadline:
                raise KitError("检查超时")
            time.sleep(0.02)
        for thread in threads:
            thread.join(timeout=5)
        if any(t.is_alive() for t in threads):
            raise KitError("检查输出未结束，可能存在仍在运行的子进程")
        if overflow.is_set() or errors:
            raise KitError("检查输出超过上限或日志写入失败")
        receipt["exit_code"] = child.returncode
        receipt["result"] = "pass" if child.returncode == 0 else "fail"
    except (OSError, KitError, KeyboardInterrupt) as exc:
        if child:
            _kill(child)
        receipt["result"] = "fail"
        receipt["error"] = "检查已取消" if isinstance(exc, KeyboardInterrupt) else str(exc)
    finally:
        for thread in threads:
            thread.join(timeout=5)
        for name in ("stdout.log", "stderr.log"):
            path = logs / name
            if path.is_file():
                receipt["logs"][name] = {"path": path.relative_to(root).as_posix(),
                                          "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
    return _finish(root, receipt)
