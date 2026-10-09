"""Non-Codex installs. Same ownership manifest, backup, lock and transaction rules as install-global."""
from contextlib import ExitStack
import os
from pathlib import Path
import shlex
import sys
import uuid
from . import VERSION, NAME
from .atomic_io import (KitError, atomic_write, check_pending, digest, encode_json, locked,
                        raw, read_json, recover, safe_path, transaction)
from .config import HOOK_EVENTS, _remove_groups, windows_command
from .memory import KIT_ROOT
from .skill_install import inspect_skill, prepare_skill, skill_directory

CLIENTS = ("agents", "claude")
RULES = "global/CLIENT_RULES.md"


def client_home(client, value=None):
    if client not in CLIENTS:
        raise KitError(f"不支持的客户端: {client}")
    variable, default = (("PROJECT_ANCHOR_HOME", ".project-anchor") if client == "agents"
                         else ("CLAUDE_CONFIG_DIR", ".claude"))
    selected = value or os.environ.get(variable)
    return Path(selected).expanduser().resolve() if selected else (Path.home() / default).resolve()


def client_locations(client, home):
    home = Path(home).resolve()
    managed = home if client == "agents" else safe_path(home / NAME, home)
    return managed, managed / ".lock", managed / ".transaction.json"


def skills_parent(client, home, skills_dir=None):
    if client == "claude":
        if skills_dir is not None:
            raise KitError("Claude Code 只扫描 <配置目录>/skills；不接受 --skills-dir")
        return Path(home) / "skills"
    return skills_dir


def claude_hook_groups(managed):
    result = {}
    for event, script, matcher in HOOK_EVENTS:
        arguments = [str(Path(sys.executable).resolve()), "-X", "utf8", str(KIT_ROOT / "hooks" / script),
                     "--managed-dir", str(managed)]
        command = windows_command(arguments) if os.name == "nt" else shlex.join(arguments)
        result[event] = {"matcher": matcher, "hooks": [{"type": "command", "command": command, "timeout": 15,
                                                        "statusMessage": "Project Anchor " + event}]}
    return result


def _settings(path):
    value = read_json(path) if path.exists() else {}
    if not isinstance(value, dict):
        raise KitError("settings.json 必须是 JSON 对象")
    hooks = value.get("hooks", {})
    if not isinstance(hooks, dict):
        raise KitError("settings.json hooks 必须是对象")
    for event, groups in hooks.items():
        if not isinstance(groups, list) or any(not isinstance(g, dict) or not isinstance(g.get("hooks"), list) for g in groups):
            raise KitError(f"settings.json Hook 组格式错误: {event}")
    return value


def _scopes(client, home, target):
    managed, _, _ = client_locations(client, home)
    return (Path(home).resolve() if client == "claude" else managed), {"skill": target}


def _target(client, home, manifest, skills_dir):
    return Path(manifest["skill"]["path"]) if manifest else skill_directory(skills_parent(client, home, skills_dir))


def install_client(client, home, skills_dir=None):
    home = Path(home).resolve()
    managed, lock, journal = client_locations(client, home)
    with locked(lock), ExitStack() as stack:
        check_pending(journal)
        manifest_path = managed / "install.json"
        manifest_bytes = raw(manifest_path)
        manifest = read_json(manifest_path) if manifest_bytes is not None else None
        if manifest and manifest.get("client") != client:
            raise KitError("安装清单属于其他客户端，拒绝覆盖")
        target = _target(client, home, manifest, skills_dir)
        stack.enter_context(locked(target.parent / ".codex-rules.lock"))
        target, updates, expected, skill_info = prepare_skill(home, manifest, skills_parent(client, home, skills_dir),
                                                              client=client)
        root, extra = _scopes(client, home, target)
        new_manifest = {"schema": 1, "client": client, "version": VERSION, "kit_root": str(KIT_ROOT),
                        "python": str(Path(sys.executable).resolve()), "skill": skill_info}
        if client == "claude":
            rules = safe_path(home / "rules" / f"{NAME}.md", home)
            old_rules = raw(rules)
            if manifest:
                if old_rules is None or digest(old_rules) != manifest["rules_hash"]:
                    raise KitError("Claude 规则文件已修改或缺失，拒绝覆盖")
            elif old_rules is not None:
                raise KitError("已存在同名 Claude 规则文件但不属于本安装，拒绝覆盖")
            rules_data = (KIT_ROOT / RULES).read_bytes()
            settings_path = safe_path(home / "settings.json", home)
            old_settings = raw(settings_path)
            settings = _settings(settings_path)
            had_hooks = manifest["settings_had_hooks"] if manifest else "hooks" in settings
            settings.setdefault("hooks", {})
            if manifest:
                _remove_groups(settings, manifest["groups"])
            groups = claude_hook_groups(managed)
            for event, group in groups.items():
                current = settings["hooks"].setdefault(event, [])
                if group in current:
                    raise KitError("发现没有归属记录的同名 Hook")
                current.append(group)
            unchanged = old_settings is not None and _settings(settings_path) == settings
            updates.update({rules: rules_data, settings_path: old_settings if unchanged else encode_json(settings)})
            expected.update({rules: old_rules, settings_path: old_settings})
            new_manifest.update(rules_hash=digest(rules_data), groups=groups,
                                settings_existed=manifest["settings_existed"] if manifest else old_settings is not None,
                                settings_had_hooks=had_hooks)
        updates[manifest_path] = encode_json(new_manifest)
        expected[manifest_path] = manifest_bytes
        if all(raw(p) == content for p, content in updates.items()):
            return {"changed": False, "client": client, "home": str(home), "skill": str(target)}
        # Backup only files this install edits; never auth, transcripts or unrelated configuration.
        backup = managed / "runtime/backups" / uuid.uuid4().hex
        for path, old in expected.items():
            if old is not None:
                scope = "skill" if path.is_relative_to(target) else "main"
                base = target if scope == "skill" else root
                atomic_write(backup / scope / path.relative_to(base), old)
        transaction(root, journal, updates, expected, extra)
        return {"changed": True, "client": client, "home": str(home), "skill": str(target), "backup": str(backup),
                "hooks": "UNVERIFIED" if client == "claude" else "NOT_CONFIGURED"}


def uninstall_client(client, home):
    home = Path(home).resolve()
    managed, lock, journal = client_locations(client, home)
    with locked(lock), ExitStack() as stack:
        check_pending(journal)
        manifest_path = managed / "install.json"
        if not manifest_path.exists():
            raise KitError("未找到安装清单，拒绝删除未知文件")
        manifest = read_json(manifest_path)
        if manifest.get("client") != client:
            raise KitError("安装清单属于其他客户端，拒绝卸载")
        stack.enter_context(locked(Path(manifest["skill"]["path"]).parent / ".codex-rules.lock"))
        target, updates, expected, _ = prepare_skill(home, manifest, uninstall=True, client=client)
        root, extra = _scopes(client, home, target)
        updates[manifest_path] = None
        if client == "claude":
            rules = safe_path(home / "rules" / f"{NAME}.md", home)
            current = raw(rules)
            if current is None or digest(current) != manifest["rules_hash"]:
                raise KitError("Claude 规则文件被修改，卸载拒绝覆盖")
            settings_path = safe_path(home / "settings.json", home)
            old_settings = raw(settings_path)
            settings = _settings(settings_path)
            settings.setdefault("hooks", {})
            _remove_groups(settings, manifest["groups"])
            if not settings["hooks"] and not manifest["settings_had_hooks"]:
                settings.pop("hooks")
            content = None if not settings and not manifest["settings_existed"] else encode_json(settings)
            updates.update({rules: None, settings_path: content})
            expected.update({rules: current, settings_path: old_settings})
        transaction(root, journal, updates, expected, extra)
        return {"uninstalled": True, "client": client, "runtime_backups_retained": True}


def recover_client(client, home, skills_dir=None, rollback=False):
    home = Path(home).resolve()
    managed, lock, journal = client_locations(client, home)
    with locked(lock), ExitStack() as stack:
        manifest_path = managed / "install.json"
        manifest = read_json(manifest_path) if manifest_path.exists() else None
        target = _target(client, home, manifest, skills_dir)
        stack.enter_context(locked(target.parent / ".codex-rules.lock"))
        root, extra = _scopes(client, home, target)
        recover(root, journal, rollback, extra)


def inspect_client(client, home):
    """Install-file checks only. Native discovery, trust and execution stay separate evidence."""
    home = Path(home).resolve()
    managed, _, journal = client_locations(client, home)
    checks = [("FAIL" if journal.exists() else "PASS", "安装事务",
               f"有未完成事务，执行 recover --client {client}" if journal.exists() else "无中断记录")]
    manifest_path = managed / "install.json"
    if not manifest_path.exists():
        return checks + [("UNVERIFIED", f"{client} 安装", "所选目录没有 Project Anchor 安装清单")]
    manifest = read_json(manifest_path)
    checks.append(("PASS" if manifest.get("client") == client else "FAIL", f"{client} 安装清单", str(manifest_path)))
    checks.append(("PASS" if manifest.get("version") == VERSION else "WARN", "安装版本",
                   f"工具版本 {VERSION}；安装版本 {manifest.get('version')}"))
    checks.append(("PASS" if manifest.get("kit_root") == str(KIT_ROOT) and manifest.get("python") == str(Path(sys.executable).resolve())
                   else "FAIL", "安装位置与解释器", "迁移后必须重新安装"))
    checks.extend(inspect_skill(home, manifest, client))
    if client == "claude":
        rules = home / "rules" / f"{NAME}.md"
        intact = rules.is_file() and digest(rules.read_bytes()) == manifest.get("rules_hash")
        checks.append(("PASS" if intact else "FAIL", "Claude 用户规则完整性", str(rules)))
        checks.append(("PASS" if intact and digest(rules.read_bytes()) == digest((KIT_ROOT / RULES).read_bytes()) else "WARN",
                       "Claude 用户规则版本", "与当前模板比对"))
        settings = _settings(home / "settings.json")
        for event, group in claude_hook_groups(managed).items():
            checks.append(("PASS" if settings.get("hooks", {}).get(event, []).count(group) == 1 else "FAIL",
                           f"{event} 已配置", "检查 settings.json 中本安装的命令及匹配器"))
        checks.append(("UNVERIFIED", "Claude 原生加载", "规则加载、Skill 发现和 Hook 执行以真实 Claude Code 会话证据为准"))
    else:
        checks.append(("UNVERIFIED", "生命周期 Hook", "通用安装不配置 Hook；各客户端生命周期能力见能力矩阵"))
    return checks
