"""Opt-in native lifecycle test; requires officially reviewed hooks beforehand.

Does not set or bypass trust, copy login, or change persistent configuration.
Uses synthetic projects, ephemeral threads, existing login and a normal sandbox.
"""
import argparse
import hashlib
import json
import queue
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.config import codex_home
from core.memory import init_project, load, doc_change, task_change, snapshot, validate_snapshot
from core.native import CodexClient
from core.atomic_io import read_json


def protect(project):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (project / ".agent").glob("*") if p.is_file() and p.name != ".lock"}


def wait_event(client, predicate, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = client.queue.get(timeout=0.5)
        except queue.Empty:
            if client.process.poll() is not None:
                raise RuntimeError("Native client exited before lifecycle completion")
            continue
        client.events.append(value)
        if getattr(client, "event_log", None):
            client.event_log.write_text(json.dumps(client.events, ensure_ascii=False, indent=2), encoding="utf-8")
        if value.get("method") == "error":
            raise RuntimeError("Native client reported an error: " + str(value.get("params", {}).get("error", {}).get("message", "unknown")))
        if predicate(value):
            return value
    raise RuntimeError("Native lifecycle timed out; no successful completion claimed")


def turn(client, tid, text):
    result = client.request("turn/start", {"threadId": tid, "input": [{"type": "text", "text": text}]})
    turn_id = result["turn"]["id"]
    value = wait_event(client, lambda v: v.get("method") == "turn/completed"
                       and v.get("params", {}).get("turn", {}).get("id") == turn_id)
    if value["params"]["turn"]["status"] != "completed":
        raise RuntimeError("Model turn did not complete successfully")


def is_compaction(value):
    # Current native API emits contextCompaction items. thread/compacted is
    # deprecated and is not emitted by the installed client.
    return (value.get("method") == "item/completed"
            and value.get("params", {}).get("item", {}).get("type") == "contextCompaction")


def fixture(project):
    init_project(project, "原生Hook隔离验收")
    s, content, _ = load(project)
    goal = content["GOAL.md"].replace("待用户确认：填写一句话目标。", "交付输出5的标准库演示；稳定目标标记 GOAL-5371。")
    goal = goal.replace("待确认：填写可验证的交付条件。", "演示实际输出5；只读接续不得改变治理文件。")
    doc_change(project, s["revision"], "GOAL.md", goal, "合成测试明确批准的固定目标", approved=True)
    s, content, _ = load(project)
    doc_change(project, s["revision"], "DECISIONS.md", content["DECISIONS.md"] + "\n测试已确认：使用JSON文件，不使用数据库；决策标记 DECISION-4826。\n", "合成测试已确认决策")
    s, _, _ = load(project)
    task_change(project, s["revision"], "add", {"task_id": "T1", "title": "验证输出5", "plan": "approved",
                "acceptance_criteria": ["演示实际输出5"]}, "合成验收任务")
    snapshot(project, "synthetic-old-checkpoint")
    s, content, _ = load(project)
    current = content["CURRENT.md"] + "\n最新工作断点 CURRENT-9462：任务T1尚未完成。\n"
    doc_change(project, s["revision"], "CURRENT.md", current, "合成最新工作断点")


def logs(home, tid):
    path = home / "codex-rules/runtime/hooks.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line and json.loads(line).get("session_id") == tid] if path.exists() else []


def case(folder, home, automatic):
    project = folder / ("自动压缩 项目" if automatic else "手动压缩 项目")
    fixture(project)
    before = protect(project)
    config = {"features.multi_agent": False}
    if automatic:
        # Process/thread-only threshold; actual trigger must be recorded as auto.
        config["model_auto_compact_token_limit"] = 10000
        config["model_auto_compact_token_limit_scope"] = "body_after_prefix"
    with CodexClient(home, project) as client:
        client.event_log = folder / ("auto-events-partial.json" if automatic else "manual-events-partial.json")
        hooks = client.request("hooks/list", {"cwds": [str(project)]})
        owned = [h for e in hooks["data"] for h in e["hooks"]
                 if Path(h.get("sourcePath", "")).resolve() == home / "hooks.json"]
        if len(owned) != 2 or not all(h["trustStatus"] == "trusted" and h["enabled"] for h in owned):
            raise RuntimeError("Exact tool hooks must be reviewed and enabled before this test")
        started = client.request("thread/start", {"cwd": str(project), "ephemeral": True,
                    "approvalPolicy": "never", "sandbox": "workspace-write", "config": config})
        tid = started["thread"]["id"]
        session_id = started["thread"].get("sessionId", tid)
        client.event_log.write_text(json.dumps(client.events, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"running": "auto" if automatic else "manual", "thread": tid}, ensure_ascii=False), flush=True)
        prompt = "只读核对这个项目：请用现有工具读取GOAL、CURRENT、任务和DECISIONS，返回稳定目标标记、最新工作断点标记、决策标记及T1状态。不要修改文件或任务。"
        turn(client, tid, prompt)
        if protect(project) != before:
            raise RuntimeError("Initial read-only model turn changed governance files")
        s, content, _ = load(project)
        doc_change(project, s["revision"], "CURRENT.md", content["CURRENT.md"]
                   + "\n接续验收的最新断点 CURRENT-NEW-7214：以这一新状态为准，T1仍未完成。\n",
                   "验收已批准：在旧快照及旧会话信息之后保存更新的断点")
        before = protect(project)
        if not automatic:
            count = sum(is_compaction(e) for e in client.events)
            client.request("thread/compact/start", {"threadId": tid}, timeout=60)
            # Handle either a notification already consumed with the RPC response
            # or the following asynchronous completion notification.
            if sum(is_compaction(e) for e in client.events) == count:
                completed = wait_event(client, is_compaction)
            else:
                completed = [e for e in client.events if is_compaction(e)][-1]
            compact_turn = completed["params"]["turnId"]
            def finished(v):
                return (v.get("method") == "turn/completed"
                        and v.get("params", {}).get("turn", {}).get("id") == compact_turn)
            done = next((e for e in client.events if finished(e)), None) or wait_event(client, finished)
            if done["params"]["turn"]["status"] != "completed":
                raise RuntimeError("Native compaction turn failed")
        turn(client, tid, prompt)
        events = list(client.events)
    records = logs(home, session_id)
    native_completed = [e["params"]["run"] for e in events if e.get("method") == "hook/completed"
                        and Path(e["params"]["run"].get("sourcePath", "")).resolve() == home / "hooks.json"
                        and e["params"]["run"].get("status") == "completed"]
    compacted = [e for e in events if is_compaction(e)]
    trigger = "auto" if automatic else "manual"
    pre = [r for r in records if r.get("event") == "PreCompact" and r.get("trigger") == trigger and r["status"] == "PASS"]
    recovered = [r for r in records if r.get("event") == "SessionStart" and r.get("source") == "compact" and r["status"] == "PASS"]
    startup = [r for r in records if r.get("event") == "SessionStart" and r.get("source") == "startup" and r["status"] == "PASS"]
    messages = [e.get("params", {}).get("item", {}).get("text", "") for e in events
                if e.get("method") == "item/completed" and e.get("params", {}).get("item", {}).get("type") == "agentMessage"]
    reply = messages[-1] if messages else ""
    intact = protect(project) == before
    snapshot_ok = False
    for r in pre:
        data = read_json(project / ".agent/runtime/snapshots" / r["snapshot"])
        validate_snapshot(data, load(project)[0]["project_id"])
        snapshot_ok = snapshot_ok or "CURRENT-9462" in data["files"]["CURRENT.md"]
    older = [read_json(p) for p in (project / ".agent/runtime/snapshots").glob("snapshot-*.json")]
    stale_preserved = any("CURRENT-9462" not in v["files"]["CURRENT.md"] for v in older)
    native_confirmed = (sum(r["eventName"] == "sessionStart" for r in native_completed) >= 2
                        and any(r["eventName"] == "preCompact" for r in native_completed))
    report = {"mode": trigger, "thread": tid, "startup": bool(startup), "native_compaction": bool(compacted),
              "native_hook_notifications": native_confirmed, "precompact_snapshot": bool(pre) and snapshot_ok,
              "compact_session_restore": bool(recovered), "disk_unchanged": intact,
              "old_snapshot_preserved": stale_preserved,
              "latest_markers_read": all(t in reply for t in ["GOAL-5371", "CURRENT-NEW-7214", "DECISION-4826", "T1"]),
              "records": records, "reply": reply}
    report["status"] = "PASS" if all(report[k] for k in ["startup", "native_compaction", "native_hook_notifications",
          "precompact_snapshot", "compact_session_restore", "disk_unchanged", "old_snapshot_preserved", "latest_markers_read"]) else "FAIL"
    (folder / (trigger + "-events.json")).write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / (trigger + "-result.json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--mode", choices=["manual", "auto", "both"], default="manual")
    args = parser.parse_args()
    folder = Path(tempfile.mkdtemp(prefix="codex-rules 原生Hook实测 "))
    print(json.dumps({"folder": str(folder)}, ensure_ascii=False), flush=True)
    results = []
    try:
        for automatic in ([False, True] if args.mode == "both" else [args.mode == "auto"]):
            results.append(case(folder, codex_home(), automatic))
            if results[-1]["status"] != "PASS":
                break
    except Exception as exc:
        (folder / "failure.json").write_text(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False), encoding="utf-8")
        raise
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
