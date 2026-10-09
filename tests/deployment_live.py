"""Opt-in real model checks of the permanent installation in synthetic projects.

Uses the current user's existing Codex login and configuration, without copying
authentication or changing hook trust. Each request is a new ephemeral session.
Hook execution is disabled for these model workflow checks and tested separately.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.config import codex_home
from core.memory import load


def protected(project):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (project / ".agent").glob("*") if p.is_file() and p.name != ".lock"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", required=True,
                        help="Explicitly authorize real model requests using existing login")
    parser.add_argument("--folder", type=Path, help="Continue an existing synthetic fixture")
    parser.add_argument("--start-at", default="default_onboarding", help="First workflow to execute")
    parser.add_argument("--skip-negatives", action="store_true")
    args = parser.parse_args()
    folder = args.folder.resolve(strict=True) if args.folder else Path(tempfile.mkdtemp(prefix="codex-rules 正式安装实测 "))
    project = folder / "中文 空格 项目"
    project.mkdir(exist_ok=True)
    original_agents = "# Existing project notes\nKeep main.py output equal to 5.\n".encode()
    if not args.folder:
        (project / "AGENTS.md").write_bytes(original_agents)
        (project / "main.py").write_text("print(2 + 3)\n", encoding="utf-8")
    cases = [
        ("default_onboarding", "开始开发当前项目。已确认目标：交付一个输出 5 的 Python 标准库演示和使用说明；只做这个演示，不增加服务。验收是 main.py 实际输出 5，README 说明如何运行。请开始项目工作并补充使用说明。", "init"),
        ("planning", "我确认当前项目目标。为下一次验收回归制定任务草案并保存到任务账本；保留已有已完成任务，先不执行新草案。", "plan"),
        ("memory", "记录我们刚才确定的技术路线：Python 标准库，状态保存为 JSON 文件，不使用数据库。这是已确认决策。", "memory"),
        ("progress", "现在项目进度如何？只读取真实账本，不更改状态。", "readonly"),
        ("handoff", "整理工作状态，保存工作断点，准备切换会话。", "handoff"),
        ("fresh_session", "继续这个项目。先读取项目最初目标、当前断点和技术决策，说明下一步；本次不要修改文件。", "resume"),
        ("retro", "总结当前项目的经验教训，生成复盘草案。未完成和未验证的内容保留，知识库不要入库。", "retro"),
        ("doctor", "$codex-rules 检查全局规则和 Hook 是否正常，只诊断，不更改配置。", "doctor"),
    ]
    results = []
    names = [c[0] for c in cases]
    if args.start_at not in names:
        parser.error("Unknown --start-at workflow")
    cases = cases[names.index(args.start_at):]
    result_file = folder / ("result.json" if not args.folder else "result-continuation.json")
    env = dict(os.environ, CODEX_HOME=str(codex_home()), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    def run_case(name, prompt, expected, target):
        before = protected(target)
        previous_ids = {t["task_id"] for t in load(target)[2]["tasks"]} if (target / ".agent/state.json").exists() else set()
        old_decisions = (target / ".agent/DECISIONS.md").read_bytes() if (target / ".agent/DECISIONS.md").exists() else None
        started = time.monotonic()
        command = [shutil.which("codex"), "--no-daemon", "exec", "--disable", "hooks", "--disable", "multi_agent",
                   "--ephemeral", "--approve-for-me", "--skip-git-repo-check", "--json", "-C", str(target), "-"]
        output = folder / (name + ".jsonl")
        errors = folder / (name + ".stderr.txt")
        timed_out = False
        with output.open("wb") as stdout, errors.open("wb") as stderr:
            process = subprocess.Popen(command, cwd=target, env=env, stdin=subprocess.PIPE,
                                       stdout=stdout, stderr=stderr)
            try:
                process.communicate(prompt.encode("utf-8"), timeout=300)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                process.wait()
        events = [json.loads(line) for line in output.read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("{")]
        commands = [e.get("item", {}).get("command", "") for e in events
                    if e.get("item", {}).get("type") == "command_execution"]
        used = any("codex-rules" in c and ("SKILL.md" in c or "run.py" in c) for c in commands)
        completed = not timed_out and process.returncode == 0 and any(e.get("type") == "turn.completed" for e in events)
        behavior, error = False, "Model request timed out; partial logs preserved" if timed_out else ""
        try:
            if expected == "negative":
                behavior = not used and not (target / ".agent").exists()
                if name == "scoped_edit":
                    behavior = behavior and "6" in (target / "main.py").read_text(encoding="utf-8")
            else:
                state, content, ledger = load(target)
                if expected == "init":
                    behavior = ((target / "README.md").is_file() and (target / "AGENTS.md").read_bytes().startswith(original_agents)
                                and not (target / ".git").exists() and "print(2 + 3)" in (target / "main.py").read_text(encoding="utf-8"))
                elif expected == "plan":
                    added = [t for t in ledger["tasks"] if t["task_id"] not in previous_ids]
                    behavior = bool(added) and all(t["plan"] == "draft" for t in added)
                elif expected == "memory":
                    behavior = (target / ".agent/DECISIONS.md").read_bytes() != old_decisions and "JSON" in content["DECISIONS.md"]
                elif expected in ("readonly", "doctor", "resume"):
                    behavior = protected(target) == before and any("run.py" in c and ("doctor" if expected == "doctor" else "status") in c for c in commands)
                    if expected == "resume":
                        behavior = behavior and any("DECISIONS" in c or "state" in c for c in commands)
                elif expected == "handoff":
                    behavior = protected(target) != before and state["current_task_revision"] == ledger["revision"] and bool(list((target / ".agent/runtime/snapshots").glob("*.json")))
                elif expected == "retro":
                    behavior = (target / ".agent/RETRO.md").is_file()
        except Exception as exc:
            error = str(exc)
        entry = {"name": name, "status": "PASS" if completed and behavior and (used or expected == "negative") else "FAIL",
                 "completed": completed, "skill_observed": used, "behavior": behavior,
                 "seconds": round(time.monotonic() - started, 1), "error": error}
        results.append(entry)
        result_file.write_text(json.dumps({"cases": results, "hooks_disabled": True,
                      "global_config_loaded": True, "new_ephemeral_session_per_case": True}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    print(json.dumps({"folder": str(folder), "project": str(project)}, ensure_ascii=False), flush=True)
    for name, prompt, expected in cases:
        run_case(name, prompt, expected, project)
        if results[-1]["status"] != "PASS":
            break  # Expose the first failure; do not cascade into unrelated writes.
    negatives = [] if args.skip_negatives else [("explanation", "解释 main.py 为什么输出 5。不要修改任何文件。"),
                         ("scoped_edit", "只修改 main.py，让它输出 6；只能改这个文件。")]
    for name, prompt in negatives:
        target = folder / name
        target.mkdir()
        (target / "main.py").write_text("print(2 + 3)\n", encoding="utf-8")
        run_case(name, prompt, "negative", target)
    print(json.dumps({"passed": sum(r["status"] == "PASS" for r in results),
                      "failed": sum(r["status"] == "FAIL" for r in results), "folder": str(folder)}, ensure_ascii=False))
    return 0 if all(r["status"] == "PASS" for r in results) and len(results) == len(cases) + len(negatives) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
