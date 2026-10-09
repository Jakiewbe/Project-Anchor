"""Real Claude Code / OpenCode acceptance in an isolated synthetic project. Calls real models; run manually.

Each client keeps its own login. The project, installs, hook logs and results live in a new temp folder
whose path contains Chinese and spaces. Model answers are recorded verbatim for human review; keyword
checks below are only first-pass assertions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PYTHON = [sys.executable, "-X", "utf8"]
# User plugins (e.g. memory recorders) would observe synthetic sessions; disable them for this run only.
CLAUDE_OVERLAY = {"enabledPlugins": {"claude-mem@thedotmack": False, "superpowers@obra": False}}
CLAUDE_TOOLS = "Bash,Read,Write,Edit,Glob,Grep,Skill"


def kit(*args, check=True):
    result = subprocess.run([*PYTHON, str(ROOT / "kit.py"), *map(str, args)], capture_output=True,
                            encoding="utf-8", timeout=120)
    if check and result.returncode:
        raise SystemExit(f"kit {args[0]} failed: {result.stderr}")
    return json.loads(result.stdout)


def opencode_skills(project):
    launcher = Path(shutil.which("opencode")).parent / "node_modules/opencode-ai/bin/opencode"
    result = subprocess.run([shutil.which("node"), str(launcher), "debug", "skill"], cwd=project, capture_output=True,
                            encoding="utf-8", errors="replace", timeout=120)
    items = json.loads(result.stdout[result.stdout.find("["):])
    return [{"name": i["name"], "location": i["location"]} for i in items if i["name"] == "project-anchor"]


def fingerprint(project):
    agent = project / ".agent"
    commits = subprocess.run(["git", "-C", str(project), "rev-list", "--all"], capture_output=True).stdout.splitlines()
    business = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in project.glob("*.py")}
    hashes = {p.relative_to(agent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(agent.rglob("*")) if p.is_file()} if agent.exists() else {}
    if not (agent / "state.json").exists():
        return {"initialized": False, "agent_hashes": hashes, "business_hashes": business, "commits": len(commits)}
    state = json.loads((agent / "state.json").read_text(encoding="utf-8"))
    tasks = json.loads((agent / "tasks.json").read_text(encoding="utf-8"))
    return {"initialized": True, "revision": state["revision"], "goal_approved": state["goal_approved"],
            "tasks": {t["task_id"]: t["status"] for t in tasks["tasks"]},
            "current": hashlib.sha256((agent / "CURRENT.md").read_bytes()).hexdigest()[:12],
            "decisions": (agent / "DECISIONS.md").read_text(encoding="utf-8"), "agent_hashes": hashes,
            "business_hashes": business, "commits": len(commits)}


def capture_client(command, project, client, prompt=None, timeout=900):
    """Keep exact stdout/stderr, including failed requests, outside the model's workspace."""
    folder = Path(project).parent / "raw-client" / f"{client}-{uuid.uuid4().hex}"
    folder.mkdir(parents=True)
    metadata = {"client": client, "command": command, "cwd": str(project),
                "started_at": datetime.now(timezone.utc).isoformat()}
    stdout = stderr = b""
    try:
        result = subprocess.run(command, cwd=project, input=prompt.encode("utf-8") if prompt is not None else None,
                                stdin=subprocess.DEVNULL if prompt is None else None, capture_output=True,
                                timeout=timeout)
        stdout, stderr = result.stdout, result.stderr
        metadata["returncode"] = result.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
        metadata["error"] = "timeout; partial response preserved"
        exc.evidence = str(folder)
        raise
    except OSError as exc:
        metadata["error"] = f"{type(exc).__name__}: process could not start"
        exc.evidence = str(folder)
        raise
    finally:
        (folder / "stdout.jsonl").write_bytes(stdout)
        (folder / "stderr.txt").write_bytes(stderr)
        (folder / "request.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    result.stdout = stdout.decode("utf-8", errors="replace")
    result.stderr = stderr.decode("utf-8", errors="replace")
    result.evidence = str(folder)
    return result


def claude(project, prompt, resume=None):
    exe = Path(shutil.which("claude")).parent / "node_modules/@anthropic-ai/claude-code/bin/claude.exe"
    command = [str(exe), "-p", prompt, "--output-format", "stream-json", "--verbose",
               "--settings", json.dumps(CLAUDE_OVERLAY), "--allowedTools", CLAUDE_TOOLS]
    if resume:
        command += ["--resume", resume]
    started = time.time()
    result = capture_client(command, project, "claude")
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    final = next((e for e in reversed(events) if e.get("type") == "result"), {})
    tools = []
    for event in events:
        for part in (event.get("message") or {}).get("content", []) if event.get("type") == "assistant" else []:
            if isinstance(part, dict) and part.get("type") == "tool_use":
                tools.append({"name": part["name"], "input": json.dumps(part.get("input"), ensure_ascii=False)})
    return {"client": "claude", "session_id": final.get("session_id") or init.get("session_id"),
            "returncode": result.returncode, "seconds": round(time.time() - started, 1),
            "skills_listed": "project-anchor" in json.dumps(init.get("skills", []) + init.get("slash_commands", [])),
            "tools": tools, "answer": final.get("result", ""), "is_error": final.get("is_error"),
            "stderr": result.stderr, "raw": result.evidence}


def opencode(project, prompt, model):
    launcher = Path(shutil.which("opencode")).parent / "node_modules/opencode-ai/bin/opencode"
    command = [shutil.which("node"), str(launcher), "run", "--pure", "--format", "json", "-m", model, prompt]
    started = time.time()
    result = capture_client(command, project, "opencode")
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    tools, texts, session = [], [], None
    for event in events:
        part = event.get("part") or {}
        session = session or event.get("sessionID") or part.get("sessionID")
        if part.get("type") == "tool":
            tools.append({"name": part.get("tool"), "input": json.dumps((part.get("state") or {}).get("input"), ensure_ascii=False)})
        elif part.get("type") == "text" and part.get("text"):
            texts.append(part["text"])
    return {"client": "opencode", "session_id": session, "returncode": result.returncode,
            "is_error": any(event.get("type") == "error" for event in events),
            "seconds": round(time.time() - started, 1), "tools": tools, "answer": "\n".join(texts),
            "stderr": result.stderr, "raw": result.evidence}


def codex(project, prompt):
    # Uses existing login without copying auth or updating the real install.
    # Project-local Skill is installed by setup(); lifecycle Hooks are disabled for this workflow test.
    command = [shutil.which("codex"), "--no-daemon", "exec", "--disable", "hooks", "--disable", "multi_agent",
               "--ephemeral", "--approve-for-me", "--json", "-C", str(project), "-"]
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    config = home / "config.toml"
    before_config = hashlib.sha256(config.read_bytes()).hexdigest() if config.exists() else None
    started = time.time()
    result = capture_client(command, project, "codex", prompt)
    after_config = hashlib.sha256(config.read_bytes()).hexdigest() if config.exists() else None
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    tools, texts, session = [], [], None
    for event in events:
        session = session or event.get("thread_id")
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "command_execution":
            tools.append({"name": "command_execution", "input": item.get("command", "")})
        elif event.get("type") == "item.completed" and item.get("type") == "agent_message":
            texts.append(item.get("text", ""))
    return {"client": "codex", "session_id": session, "returncode": result.returncode,
            "is_error": not any(e.get("type") == "turn.completed" for e in events),
            "seconds": round(time.time() - started, 1), "tools": tools, "answer": "\n".join(texts),
            "stderr": result.stderr, "raw": result.evidence, "hooks_disabled": True,
            "installation_scope": "project-local agents; no install-global executed",
            "user_config_changed": before_config != after_config,
            "user_config_before_sha256": before_config, "user_config_after_sha256": after_config}


def used_anchor(step):
    return any(t["name"] in ("Skill", "skill") and "project-anchor" in t["input"] or "run.py" in t["input"]
               for t in step["tools"])


def hook_records(claude_home, sessions):
    log = claude_home / "project-anchor/runtime/hooks.jsonl"
    hooks = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return [{k: h.get(k) for k in ("event", "status", "origin", "source", "trigger", "error")}
            | {"session_matches": h.get("session_id") in sessions} for h in hooks]


def setup(base, clients):
    project = base / "合成 项目"
    project.mkdir()
    (project / "hello.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    installs = {}
    if "claude" in clients:
        installs["claude"] = kit("install-client", "claude", "--home", project / ".claude")
    if "opencode" in clients or "codex" in clients:
        installs["agents"] = kit("install-client", "agents", "--home", base / "anchor home",
                                 "--skills-dir", project / ".agents/skills")
    return project, installs


def claude_lifecycle(base, out):
    """No natural-language judgement: only whether the real client runs the configured hooks."""
    project, installs = setup(base, ["claude"])
    kit("init-project", project, "--name", "生命周期项目")
    record = {"project": str(project), "installs": installs, "runs": []}
    start = claude(project, "只回复 OK")
    record["runs"].append(start)
    record["runs"].append(claude(project, "/compact", start["session_id"]))
    sessions = {run["session_id"] for run in record["runs"]}
    record["claude_hooks"] = hook_records(project / ".claude", sessions)
    record["snapshots"] = len(list((project / ".agent/runtime/snapshots").glob("snapshot-*.json")))
    Path(out).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"skills_listed": start["skills_listed"], "hooks": record["claude_hooks"],
                      "snapshots": record["snapshots"]}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["workflow", "claude-lifecycle"], default="workflow")
    parser.add_argument("--primary", choices=["claude", "opencode", "codex"], default="claude")
    parser.add_argument("--secondary", choices=["claude", "opencode", "codex", "none"], default="opencode")
    parser.add_argument("--opencode-model", default="deepseek/deepseek-flash")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    base = Path(tempfile.mkdtemp(prefix="Anchor 实测 中文 空格 "))
    if args.mode == "claude-lifecycle":
        return claude_lifecycle(base, args.out)
    clients = [args.primary] + ([] if args.secondary == "none" else [args.secondary])
    project, installs = setup(base, clients)
    record = {"base": str(base), "project": str(project), "installs": installs, "steps": []}
    runners = {"claude": claude, "opencode": lambda p, prompt: opencode(p, prompt, args.opencode_model), "codex": codex}
    explicit = {"claude": "/project-anchor ", "opencode": "请使用 project-anchor skill：", "codex": "$project-anchor "}

    def step(name, client, expect, *call):
        before = fingerprint(project)
        started = time.time()
        try:
            outcome = runners[client](project, *call)
        except (subprocess.TimeoutExpired, OSError) as exc:
            outcome = {"client": client, "session_id": None, "returncode": None, "is_error": True,
                       "tools": [], "answer": "", "seconds": round(time.time() - started, 1),
                       "stderr": type(exc).__name__, "raw": getattr(exc, "evidence", None),
                       "user_config_changed": None}
        after = fingerprint(project)
        outcome.update(name=name, before=before, after=after, used_anchor=used_anchor(outcome))
        outcome["checks"] = {}
        if client == "codex":
            outcome["checks"]["real_config_unchanged"] = outcome["user_config_changed"] is False
        for key, test in expect.items():
            try:
                outcome["checks"][key] = bool(test(before, after, outcome))
            except (KeyError, TypeError):
                outcome["checks"][key] = False
        record["steps"].append(outcome)
        Path(args.out).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(name, outcome["checks"], outcome["seconds"], flush=True)
        if not all(outcome["checks"].values()):
            raise SystemExit(1)  # Preserve the first failure; do not issue dependent requests.
        return outcome

    unchanged = lambda b, a, o: b == a
    mentions = lambda *words: lambda b, a, o: all(w in o["answer"] for w in words)
    ok = lambda b, a, o: o["returncode"] == 0 and not o.get("is_error") and o["answer"].strip() != ""

    first, second = args.primary, args.secondary
    if "opencode" in clients:
        record["opencode_skills"] = opencode_skills(project)
    step(f"{first}-negative-uninitialized", first,
         {"ok": ok, "unchanged": unchanged, "no_anchor_call": lambda b, a, o: not o["used_anchor"]},
         "hello.py 里的 add 函数返回什么？只回答，不要修改任何文件。")
    step(f"{first}-nl-init", first,
         {"ok": ok, "initialized": lambda b, a, o: a["initialized"],
          "agents_md": lambda b, a, o: (project / "AGENTS.md").exists(),
          "business_code_kept": lambda b, a, o: (project / "hello.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n",
          "no_git_commit": lambda b, a, o: subprocess.run(["git", "-C", str(project), "rev-list", "--all"],
                                                          capture_output=True, encoding="utf-8").stdout == ""},
         "请为当前项目启用 Project Anchor 项目治理（目标、任务和长期记忆管理），项目名称为“合成项目”。只接入治理，不改业务代码。")
    step(f"{first}-nl-goal-approval", first,
         {"ok": ok, "goal_approved": lambda b, a, o: a["goal_approved"] and not b["goal_approved"]},
         "我确认并批准项目目标：核心目标是让 hello.py 的 add 函数有可靠的单元测试；背景是这是一个示例项目；"
         "关键约束是只用 Python 标准库；非目标是不新增其他功能；验收标准是 python -m unittest 全部通过；目标版本 1。请把它保存为正式目标。")
    step(f"{first}-explicit-task-add", first,
         {"ok": ok, "task_added": lambda b, a, o: a.get("tasks", {}).get("T1") == "todo"},
         explicit[first] + "添加任务：编号 T1，标题“为 add 函数补充单元测试”，验收标准“python -m unittest 通过”，计划已获我批准，状态保持 todo。")
    step(f"{first}-nl-decision", first,
         {"ok": ok, "decision_saved": lambda b, a, o: "UTF-8" in a.get("decisions", "")},
         "我们刚确认了一个决定：所有日志文件统一使用 UTF-8 编码。请把这个决定记录到项目的长期决策中。")
    step(f"{first}-nl-handoff", first,
         {"ok": ok, "current_updated": lambda b, a, o: a["current"] != b["current"] and a["revision"] > b["revision"]},
         "我准备结束本次会话了。请把当前进度、下一步动作写入项目断点，做好交接。")
    step(f"{first}-new-session-recovery", first,
         {"ok": ok, "unchanged": unchanged, "mentions": mentions("T1", "UTF-8")},
         "继续这个项目：请读取项目状态后告诉我当前目标、进行中或待办的任务编号，以及已记录的决定。只读，不要修改任何文件。")
    step(f"{first}-negative-initialized", first, {"ok": ok, "unchanged": unchanged},
         "add(2, 3) 的结果是多少？只回答数字。")
    if second != "none":
        step(f"{second}-new-session-recovery", second,
             {"ok": ok, "unchanged": unchanged, "mentions": mentions("T1", "UTF-8")},
             "继续这个项目：请读取项目状态后告诉我当前目标、待办任务编号，以及已记录的决定。只读，不要修改任何文件。")
        step(f"{second}-nl-task-update", second,
             {"ok": ok, "doing": lambda b, a, o: a.get("tasks", {}).get("T1") == "doing"},
             "开始做任务 T1：请把项目任务 T1 的状态更新为进行中。只更新任务状态，不改代码。")
        step(f"{first}-alternation-read", first,
             {"ok": ok, "unchanged": unchanged,
              "sees_doing": lambda b, a, o: "T1" in o["answer"] and any(w in o["answer"] for w in ("进行中", "doing"))},
             "新会话：请读取项目状态，告诉我任务 T1 现在的状态。只读，不要修改任何文件。")
    if "claude" in clients:
        sessions = {s["session_id"] for s in record["steps"] if s["client"] == "claude"}
        record["claude_hooks"] = hook_records(project / ".claude", sessions)
        record["doctor_claude"] = kit("doctor", project, "--client", "claude", "--client-home", project / ".claude",
                                      "--json", check=False)
    Path(args.out).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(all(s["checks"].values()) for s in record["steps"])
    print(f"steps passed {passed}/{len(record['steps'])}; results {args.out}")
    return 0 if passed == len(record["steps"]) else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
