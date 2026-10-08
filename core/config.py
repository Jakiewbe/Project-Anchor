"""Conservative global installation: no TOML rewriting and no trust bypass."""
import base64
import copy
import os
from pathlib import Path
import shlex
import sys
import tomllib
import uuid
from . import VERSION
from .atomic_io import (KitError, check_pending, digest, encode_json, locked,
                        raw, read_json, safe_path, transaction, atomic_write)
from .memory import KIT_ROOT, load, paths

BEGIN = b"<!-- codex-rules:begin -->"
END = b"<!-- codex-rules:end -->"


def codex_home(value=None):
    selected = value or os.environ.get("CODEX_HOME")
    return Path(selected).expanduser().resolve() if selected else (Path.home() / ".codex").resolve()


def locations(home):
    home = Path(home).resolve()
    managed = safe_path(home / "codex-rules", home)
    return managed, managed / ".lock", managed / ".transaction.json"


def read_toml(path):
    if not Path(path).exists():
        return {}
    try:
        return tomllib.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise KitError(f"配置不是有效 UTF-8 TOML: {path}") from exc


def windows_command(arguments):
    # Explicit PowerShell expression, each argument is a literal; no interpolation.
    expression = "& " + " ".join("'" + str(arg).replace("'", "''") + "'" for arg in arguments)
    encoded = base64.b64encode(expression.encode("utf-16-le")).decode("ascii")
    return "powershell.exe -NoProfile -NonInteractive -EncodedCommand " + encoded


def hook_groups():
    result = {}
    for event, script, matcher in [("SessionStart", "session_context.py", "^(startup|resume|clear|compact)$"),
                                    ("PreCompact", "pre_compact.py", "^(manual|auto)$")]:
        arguments = [str(Path(sys.executable).resolve()), "-X", "utf8", str(KIT_ROOT / "hooks" / script)]
        unix = shlex.join(arguments)
        win = windows_command(arguments)
        handler = {"type": "command", "command": win if os.name == "nt" else unix,
                   "timeout": 15, "statusMessage": "Codex-Rules " + event}
        if os.name == "nt":
            handler["commandWindows"] = win
        if event == "SessionStart":
            handler["additionalContextLimit"] = 2500
        result[event] = {"matcher": matcher, "hooks": [handler]}
    return result


def definition_hash():
    data = {"version": VERSION, "groups": hook_groups(), "scripts": {}}
    for folder in ("core", "hooks"):
        for path in sorted((KIT_ROOT / folder).glob("*.py")):
            data["scripts"][path.relative_to(KIT_ROOT).as_posix()] = digest(path.read_bytes())
    return digest(encode_json(data))


def _hooks(path):
    value = read_json(path) if path.exists() else {"hooks": {}}
    if not isinstance(value, dict) or not isinstance(value.get("hooks"), dict):
        raise KitError("hooks.json 格式错误")
    for event, groups in value["hooks"].items():
        if not isinstance(groups, list) or any(not isinstance(g, dict) or not isinstance(g.get("hooks"), list) for g in groups):
            raise KitError(f"Hook 组格式错误: {event}")
    return value


def _remove_groups(hooks, owned):
    for event, group in owned.items():
        groups = hooks["hooks"].get(event, [])
        if groups.count(group) != 1:
            raise KitError(f"工具管理的 {event} Hook 已修改、缺失或重复，拒绝覆盖")
        groups.remove(group)
        if not groups:
            hooks["hooks"].pop(event, None)


def install(home):
    home = Path(home).resolve()
    managed, lock, journal = locations(home)
    with locked(lock):
        check_pending(journal)
        manifest_path = managed / "install.json"
        manifest_bytes = raw(manifest_path)
        manifest = read_json(manifest_path) if manifest_bytes is not None else None
        config = read_toml(safe_path(home / "config.toml", home))
        agents = safe_path(home / "AGENTS.md", home)
        hook_path = safe_path(home / "hooks.json", home)
        old_agents = raw(agents)
        data = old_agents or b""
        data.decode("utf-8-sig")
        old_hook = raw(hook_path)
        hooks = _hooks(hook_path)
        if raw(hook_path) != old_hook or raw(manifest_path) != manifest_bytes:
            raise KitError("安装准备期间配置发生修改")
        new_block = b"\n" + BEGIN + b"\n" + (KIT_ROOT / "global/AGENTS.md").read_bytes() + END + b"\n"
        if manifest:
            old_block = manifest["block"].encode("utf-8")
            if data.count(old_block) != 1 or data.count(BEGIN) != 1 or data.count(END) != 1:
                raise KitError("全局规则管理块发生变更，拒绝覆盖")
            data = data.replace(old_block, new_block, 1)
            _remove_groups(hooks, manifest["groups"])
        else:
            if BEGIN in data or END in data:
                raise KitError("发现无安装清单的管理块，先人工检查")
            data += new_block
        groups = hook_groups()
        for event, group in groups.items():
            target = hooks["hooks"].setdefault(event, [])
            if group in target:
                raise KitError("发现没有归属记录的同名 Hook")
            target.append(group)
        new_hook = old_hook if old_hook is not None and _hooks(hook_path) == hooks else encode_json(hooks)
        new_manifest = {"schema": 1, "version": VERSION, "kit_root": str(KIT_ROOT),
                        "python": str(Path(sys.executable).resolve()), "block": new_block.decode("utf-8"),
                        "groups": groups, "definition_hash": definition_hash(),
                        "agents_existed": manifest["agents_existed"] if manifest else old_agents is not None,
                        "hooks_existed": manifest["hooks_existed"] if manifest else old_hook is not None}
        updates = {agents: data, hook_path: new_hook, manifest_path: encode_json(new_manifest)}
        expected = {agents: old_agents, hook_path: old_hook, manifest_path: manifest_bytes}
        if all(raw(p) == content for p, content in updates.items()):
            return {"changed": False, "home": str(home), "trust": "UNVERIFIED"}
        # Backup only edited files; never read or copy auth, config secrets or transcripts.
        backup = managed / "runtime/backups" / uuid.uuid4().hex
        for path in (agents, hook_path, manifest_path):
            if path.exists():
                atomic_write(backup / path.name, path.read_bytes())
        transaction(home, journal, updates, expected)
        return {"changed": True, "home": str(home), "backup": str(backup),
                "trust": "UNVERIFIED", "inline_hooks_present": bool(config.get("hooks"))}


def uninstall(home):
    home = Path(home).resolve()
    managed, lock, journal = locations(home)
    with locked(lock):
        check_pending(journal)
        manifest_path = managed / "install.json"
        if not manifest_path.exists():
            raise KitError("未找到安装清单，拒绝删除未知文件")
        manifest = read_json(manifest_path)
        agents = safe_path(home / "AGENTS.md", home)
        hook_path = safe_path(home / "hooks.json", home)
        data = agents.read_bytes()
        block = manifest["block"].encode("utf-8")
        if data.count(block) != 1 or data.count(BEGIN) != 1 or data.count(END) != 1:
            raise KitError("管理块被修改，卸载拒绝覆盖")
        remaining = data.replace(block, b"", 1)
        hooks = _hooks(hook_path)
        _remove_groups(hooks, manifest["groups"])
        hook_content = encode_json(hooks)
        if not manifest["hooks_existed"] and hooks == {"hooks": {}}:
            hook_content = None
        if not manifest["agents_existed"] and remaining == b"":
            remaining = None
        transaction(home, journal, {agents: remaining, hook_path: hook_content, manifest_path: None})
        return {"uninstalled": True, "runtime_backups_retained": True, "project_trust_retained": True}


def trust_project(root, home):
    managed, lock, journal = locations(home)
    _, project_lock, _ = paths(root)
    with locked(lock), locked(project_lock):
        check_pending(journal)
        state, _, _ = load(root)
        path = managed / "trusted-projects.json"
        registry = read_json(path) if path.exists() else {}
        registry[str(Path(root).resolve())] = {"project_id": state["project_id"],
                                              "hashes": {p: state["hashes"][p] for p in ("GOAL.md", "CURRENT.md")}}
        atomic_write(safe_path(path, home), encode_json(registry))


def trusted(root, home, state):
    managed, _, journal = locations(home)
    check_pending(journal)
    path = safe_path(managed / "trusted-projects.json", home)
    if not path.exists():
        return False
    registry = read_json(path)
    return registry.get(str(Path(root).resolve())) == {
        "project_id": state["project_id"], "hashes": {p: state["hashes"][p] for p in ("GOAL.md", "CURRENT.md")}}
