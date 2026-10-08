"""Opt-in, isolated Codex app-server discovery probe. No API/model requests.

Run: py -3 tests/native_probe.py
Creates only an isolated CODEX_HOME/project under .test-runtime.
Never trusts hooks or reads the user's authentication files.
"""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.atomic_io import encode_json
from core.config import install, windows_command
from core.memory import init_project


def probe():
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError("Codex executable not found")
    folder = ROOT / ".test-runtime" / ("native-" + uuid.uuid4().hex)
    home, project = folder / "配置 空格", folder / "项目 中文"
    project.mkdir(parents=True)
    subprocess.run(["git", "init", str(project)], check=True, capture_output=True)
    init_project(project, "原生接口测试")
    install(home, folder / ".agents/skills")
    env = dict(os.environ, CODEX_HOME=str(home), PYTHONUTF8="1")
    process = subprocess.Popen([executable, "app-server", "--stdio"], cwd=project, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    events, messages, errors = [], queue.Queue(), []
    def read(stream, target):
        for line in iter(stream.readline, b""):
            target.put(line) if hasattr(target, "put") else target.append(line.decode("utf-8", errors="replace"))
    threading.Thread(target=read, args=(process.stdout, messages), daemon=True).start()
    threading.Thread(target=read, args=(process.stderr, errors), daemon=True).start()
    def request(method, params, rid):
        process.stdin.write(encode_json({"id": rid, "method": method, "params": params}).replace(b"\n", b" ") + b"\n")
        process.stdin.flush()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                line = messages.get(timeout=0.5)
            except queue.Empty:
                if process.poll() is not None:
                    raise RuntimeError("Codex app-server exited: " + "".join(errors)[-1000:])
                continue
            value = json.loads(line)
            events.append(value)
            if value.get("id") == rid:
                if "error" in value:
                    raise RuntimeError(str(value["error"]))
                return value["result"]
        raise RuntimeError("Codex app-server response timeout")
    try:
        initialized = request("initialize", {"clientInfo": {"name": "codex_rules_probe", "version": "1.0.0"},
                                             "capabilities": {"experimentalApi": True}}, 1)
        process.stdin.write(b'{"method":"initialized"}\n')
        process.stdin.flush()
        result = request("hooks/list", {"cwds": [str(project)]}, 2)
        discovered = result["data"][0]
        hooks = discovered["hooks"]
        assert not discovered["errors"], discovered["errors"]
        assert {h["eventName"] for h in hooks} == {"sessionStart", "preCompact"}
        assert all(h["trustStatus"] == "untrusted" for h in hooks)
        started = request("thread/start", {"cwd": str(project), "ephemeral": True, "approvalPolicy": "never",
                                          "sandbox": "workspace-write"}, 3)
        assert not (home / "codex-rules/runtime/hooks.jsonl").exists(), "Untrusted hooks must not execute"
        shell_verified = False
        if os.name == "nt":
            # Exercise the exact installed Windows command with official input.
            # This is direct shell/protocol testing, not native trusted execution.
            payload = {"hook_event_name": "SessionStart", "session_id": "direct-shell",
                       "cwd": str(project), "source": "startup"}
            command = next(h["command"] for h in hooks if h["eventName"] == "sessionStart")
            shell = subprocess.run(command.split(), input=encode_json(payload), env=env, cwd=project,
                                   capture_output=True, timeout=20)
            assert shell.returncode == 0, shell.stderr.decode("utf-8", errors="replace")
            assert json.loads(shell.stdout)["hookSpecificOutput"]["hookEventName"] == "SessionStart"
            shell_verified = True
        summary = {"native_discovery": "PASS", "native_untrusted_skip": "PASS", "windows_command_protocol": "PASS" if shell_verified else "UNVERIFIED",
                   "trusted_lifecycle_execution": "UNVERIFIED", "model_context_delivery": "UNVERIFIED",
                   "native_compaction": "UNVERIFIED", "isolated_home": str(home),
                   "thread_ephemeral": True, "model_requests": 0, "tests": 3 if shell_verified else 2,
                   "passed": 3 if shell_verified else 2, "failed": 0, "skipped": 0}
        (folder / "result.json").write_bytes(encode_json(summary))
        (folder / "hooks-list.json").write_bytes(encode_json(result))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return summary
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    probe()
