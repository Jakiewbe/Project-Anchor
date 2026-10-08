"""Bounded public app-server queries; no model requests from doctor."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
from .atomic_io import KitError, read_json


class CodexClient:
    def __init__(self, home, cwd, env=None):
        executable = shutil.which("codex")
        if not executable:
            raise KitError("未找到 Codex，原生发现无法验证")
        self.queue = queue.Queue()
        self.events = []
        self.rid = 0
        self.process = subprocess.Popen([executable, "app-server", "--stdio"], cwd=cwd,
                                        env=dict(env or os.environ, CODEX_HOME=str(home)),
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def read(stream, capture):
            for line in iter(stream.readline, b""):
                if capture:
                    self.queue.put(json.loads(line))
        threading.Thread(target=read, args=(self.process.stdout, True), daemon=True).start()
        threading.Thread(target=read, args=(self.process.stderr, False), daemon=True).start()
        try:
            self.request("initialize", {"clientInfo": {"name": "codex_rules", "version": "1.1.0"},
                                        "capabilities": {"experimentalApi": True}})
            self.send({"method": "initialized"})
        except Exception:
            self.close()
            raise

    def send(self, value):
        self.process.stdin.write((json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8"))
        self.process.stdin.flush()

    def request(self, method, params, timeout=25):
        self.rid += 1
        rid = self.rid
        self.send({"id": rid, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                value = self.queue.get(timeout=0.5)
            except queue.Empty:
                if self.process.poll() is not None:
                    raise KitError("Codex 原生接口已退出")
                continue
            self.events.append(value)
            if value.get("id") == rid:
                if "error" in value:
                    raise KitError("Codex 接口错误: " + str(value["error"]))
                return value["result"]
        raise KitError("Codex 原生接口超时；没有验证成功")

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def skill_discovery(home, cwd):
    checks = []
    try:
        manifest = read_json(Path(home) / "codex-rules/install.json")
        expected = Path(manifest["skill"]["path"]) / "SKILL.md"
        with CodexClient(home, str(Path(cwd).resolve())) as client:
            result = client.request("skills/list", {"cwds": [str(Path(cwd).resolve())], "forceReload": True})
        found = [skill for entry in result["data"] for skill in entry["skills"]
                 if skill["name"] == "codex-rules" and Path(skill["path"]) == expected]
        status = "PASS" if len(found) == 1 and found[0]["enabled"] else "FAIL"
        checks.append({"status": status, "check": "Skill 原生发现", "detail": str(expected) if found else "当前 Codex 未发现实际安装路径"})
        others = [skill for entry in result["data"] for skill in entry["skills"] if skill["name"] == "codex-rules" and Path(skill["path"]) != expected]
        if others:
            checks.append({"status": "WARN", "check": "同名 Skill", "detail": "还存在其他来源，Codex 不会自动合并同名 Skill"})
    except (KitError, OSError, ValueError, KeyError, TypeError) as exc:
        checks.append({"status": "UNVERIFIED", "check": "Skill 原生发现", "detail": str(exc)})
    return checks
