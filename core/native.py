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
from . import VERSION


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
            self.request("initialize", {"clientInfo": {"name": "codex_rules", "version": VERSION},
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


def inspect_native_hooks(value, home, manifest):
    """Match only this install's exact native definitions, never unrelated hooks."""
    entries = value["data"]
    handlers = [h for entry in entries for h in entry["hooks"]]
    checks, owned = [], []
    events = {"SessionStart": "sessionStart", "PreCompact": "preCompact"}
    for event, name in events.items():
        group = manifest["groups"][event]
        handler = group["hooks"][0]
        command = handler.get("commandWindows", handler["command"]) if os.name == "nt" else handler["command"]
        found = [h for h in handlers if h["eventName"] == name and h.get("sourcePath")
                 and Path(h["sourcePath"]).resolve() == (Path(home) / "hooks.json").resolve()
                 and h.get("command") == command and h.get("matcher") == group["matcher"]
                 and h.get("handlerType") == "command" and h.get("async") == handler.get("async", False)
                 and h.get("statusMessage") == handler.get("statusMessage")
                 and h.get("timeoutSec") == handler["timeout"]
                 and h.get("additionalContextLimit") == handler.get("additionalContextLimit")]
        if len(found) != 1:
            checks.append({"status": "FAIL", "check": f"{event} 原生定义", "detail": "未找到唯一、与本安装清单一致的定义"})
        else:
            owned.append(found[0])
            checks.append({"status": "PASS", "check": f"{event} 原生定义", "detail": str(Path(home) / "hooks.json")})
    errors = [error for entry in entries for error in entry.get("errors", [])]
    if errors:
        checks.append({"status": "FAIL", "check": "原生 Hook 配置解析", "detail": "Codex 报告配置错误；未验证生命周期"})
    if len(owned) != 2 or errors:
        status, detail = "UNVERIFIED", "当前定义核对未通过，不能证明审核或执行"
    elif any(not h.get("enabled") for h in owned):
        status, detail = "WARN", "工具 Hook 被禁用，不能自动执行"
    elif any(h.get("trustStatus") != "trusted" for h in owned):
        status, detail = "WARN", "当前工具 Hook 尚未全部审核信任；在原生 /hooks 审核后才能自动执行"
    elif any(not h.get("currentHash") for h in owned):
        status, detail = "UNVERIFIED", "原生接口未给出当前定义哈希"
    else:
        status, detail = "PASS", "原生接口确认两项当前定义已信任；仍需独立核对实际执行和压缩效果"
    checks.append({"status": status, "check": "Hook 已信任", "detail": detail})
    return checks


def hook_discovery(home, cwd):
    try:
        manifest = read_json(Path(home) / "codex-rules/install.json")
        with CodexClient(home, str(Path(cwd).resolve())) as client:
            value = client.request("hooks/list", {"cwds": [str(Path(cwd).resolve())]})
        return inspect_native_hooks(value, home, manifest)
    except (KitError, OSError, ValueError, KeyError, TypeError) as exc:
        return [{"status": "UNVERIFIED", "check": "Hook 已信任", "detail": "原生查询未成功：" + str(exc)}]
