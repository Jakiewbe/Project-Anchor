"""Opt-in real model tests of business-preserving governance onboarding.

Uses the actual installed Skill and user rules, normal workspace sandbox and
auto-review. No approvals are bypassed; only synthetic fixtures are modified.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.config import codex_home
from core.memory import load


def run_case(folder, name, prompt, onboarding):
    project = folder / name
    project.mkdir()
    original = {"main.py": b"print(2 + 3)\n",
                "AGENTS.md": "# 既有项目约束\n继续已有工程，不要重新初始化项目，也不要重构已经正常工作的模块。\n".encode(),
                ".gitignore": b"existing-cache/\n", ".gitattributes": b"*.txt text eol=crlf\n"}
    for key, data in original.items():
        (project / key).write_bytes(data)
    command = [shutil.which("codex"), "--no-daemon", "exec", "--ephemeral", "--approve-for-me",
               "--disable", "multi_agent", "--skip-git-repo-check",
               "--json", "-C", str(project), "-"]
    log = folder / (name + ".jsonl")
    timed_out = False
    with log.open("wb") as out, (folder / (name + ".stderr.txt")).open("wb") as err:
        p = subprocess.Popen(command, cwd=project, env=dict(os.environ, CODEX_HOME=str(codex_home()),
                             PYTHONUTF8="1"), stdin=subprocess.PIPE, stdout=out, stderr=err)
        try:
            p.communicate(prompt.encode("utf-8"), timeout=300)
        except subprocess.TimeoutExpired:
            timed_out = True
            p.kill()
            p.wait()
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.startswith("{")]
    commands = [e.get("item", {}).get("command", "") for e in events
                if e.get("item", {}).get("type") == "command_execution"]
    completed = not timed_out and p.returncode == 0 and any(e.get("type") == "turn.completed" for e in events)
    unchanged_business = (project / "main.py").read_bytes() == original["main.py"]
    preserved = all((project / key).read_bytes().startswith(data) for key, data in original.items())
    ran = subprocess.run([sys.executable, str(project / "main.py")], capture_output=True)
    readme = (project / "README.md").is_file()
    governed = (project / ".agent/state.json").is_file()
    if governed:
        load(project)  # Actual state and hash validation, no inferred success.
    if onboarding:
        behavior = governed and preserved and any("run.py" in c and "init-project" in c for c in commands)
        behavior = behavior and all(len((project / k).read_bytes()) > len(original[k])
                                   for k in ["AGENTS.md", ".gitignore", ".gitattributes"])
    else:
        behavior = not (project / ".agent").exists()
        behavior = behavior and all((project / k).read_bytes() == original[k] for k in original)
    result = {"name": name, "status": "PASS" if completed and behavior and unchanged_business and readme
              and not (project / ".git").exists() and ran.returncode == 0 and ran.stdout.strip() == b"5" else "FAIL",
              "completed": completed, "governance_created": governed, "business_unchanged": unchanged_business,
              "original_notes_preserved": preserved, "behavior": behavior, "log": str(log)}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", required=True)
    parser.parse_args()
    folder = Path(tempfile.mkdtemp(prefix="codex-rules 接入约束实测 "))
    print(json.dumps({"folder":str(folder)}, ensure_ascii=False), flush=True)
    cases = [
        ("保留业务工程", "继续开发这个已有项目。不要重新初始化项目，也不要重构已经正常工作的模块。现有main.py输出5，请完善使用说明，并实际运行演示验收仍输出5。不增加功能。", True),
        ("明确禁止治理", "继续这个已有工程，完善使用说明并验证演示仍输出5。本次禁止启用项目治理，不要创建.agent，也不要修改AGENTS.md、.gitignore或.gitattributes。不初始化Git，不改main.py。", False),
    ]
    results = []
    for case in cases:
        results.append(run_case(folder, *case))
        (folder / "result.json").write_text(json.dumps({"cases":results,
             "sandbox":"workspace-write", "approval":"auto-review", "hooks":"actual user configuration"},
             ensure_ascii=False, indent=2), encoding="utf-8")
        if results[-1]["status"] != "PASS":
            break
    return 0 if len(results) == len(cases) and all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
