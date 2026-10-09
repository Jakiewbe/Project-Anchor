"""Read-only diagnostics. Configuration is not proof of model compliance."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from . import VERSION
from .atomic_io import KitError, digest, read_json
from .config import (BEGIN, END, _hooks, codex_home, definition_hash, hook_groups,
                     locations, read_toml, has_inline_hooks)
from .memory import KIT_ROOT, load, project_root, validate_snapshot, git_info
from .tasks import progress
from .skill_install import inspect_skill


def doctor(home, cwd=None, session_id=None, expected_events=()):
    home, cwd = Path(home).resolve(), Path(cwd or Path.cwd()).resolve()
    if expected_events and not session_id:
        raise KitError("检查预期 Hook 事件必须指定 --session-id")
    checks = []
    def add(status, check, detail):
        checks.append({"status": status, "check": check, "detail": detail})
    add("PASS" if sys.version_info >= (3, 11) else "FAIL", "Python", sys.version.split()[0])
    add("PASS" if shutil.which("git") else "WARN", "Git", "可用" if shutil.which("git") else "未找到")
    exe = shutil.which("codex")
    if exe:
        try:
            result = subprocess.run([exe, "--version"], capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                                    env=dict(os.environ, CODEX_HOME=str(home)))
            add("PASS" if result.returncode == 0 else "WARN", "Codex 版本", result.stdout.strip() or "版本查询失败")
        except (OSError, subprocess.TimeoutExpired):
            add("WARN", "Codex 版本", "查询失败")
    else:
        add("UNVERIFIED", "Codex 版本", "未找到；基础 CLI 可独立运行")
    managed, _, journal = locations(home)
    add("FAIL" if journal.exists() else "PASS", "安装事务", "有未完成事务，执行 recover --global" if journal.exists() else "无中断记录")
    manifest = None
    try:
        if (managed / "install.json").exists():
            manifest = read_json(managed / "install.json")
            add("PASS", "全局安装路径", str(home))
            expected = b"\n" + BEGIN + b"\n" + (KIT_ROOT / "global/AGENTS.md").read_bytes() + END + b"\n"
            actual = (home / "AGENTS.md").read_bytes()
            add("PASS" if actual.count(expected) == 1 and actual.count(BEGIN) == 1 and actual.count(END) == 1 else "FAIL", "全局规则一致性", "与当前模板比对")
            add("PASS" if manifest.get("version") == VERSION else "WARN", "规则版本", f"工具版本 {VERSION}；安装版本 {manifest.get('version')}")
            add("PASS" if manifest.get("kit_root") == str(KIT_ROOT) and manifest.get("python") == str(Path(sys.executable).resolve()) else "FAIL", "安装位置与解释器", "迁移后必须重新安装")
            add("PASS" if manifest.get("definition_hash") == definition_hash() else "WARN", "Hook 脚本版本", "脚本变更后重新安装及审核 Hook")
            hooks = _hooks(home / "hooks.json")
            for status, check, detail in inspect_skill(home, manifest):
                add(status, check, detail)
            for event, group in hook_groups().items():
                add("PASS" if hooks["hooks"].get(event, []).count(group) == 1 else "FAIL", f"{event} 已配置", "检查当前平台命令及匹配器")
        else:
            add("UNVERIFIED", "全局安装", "尚未安装到所选 CODEX_HOME")
    except (KitError, OSError, KeyError, TypeError, AttributeError) as exc:
        add("FAIL", "安装完整性", str(exc))
    add("UNVERIFIED", "Hook 已信任", "无法从稳定公开磁盘协议证明；在 Codex /hooks 检查当前定义")
    add("UNVERIFIED", "模型实际遵守规则", "文件存在或脚本日志不能证明；执行 SMOKE_TEST.md")
    configs = [(home / "config.toml", "用户")]
    root = None
    if (cwd / ".agent/.transaction.json").exists():
        add("FAIL", "项目未完成事务", "执行 recover，初始化中断时也必须先恢复")
    try:
        root = project_root(cwd)
    except (KitError, OSError):
        pass
    if root:
        relative = cwd.relative_to(root)
        configs += [(candidate / ".codex/config.toml", "项目") for candidate in [root, *(root / Path(*relative.parts[:n]) for n in range(1, len(relative.parts) + 1))]]
    limit, fallback_names = 32768, []
    for path, scope in configs:
        try:
            config = read_toml(path)
            if "project_doc_fallback_filenames" in config:
                value = config["project_doc_fallback_filenames"]
                if not isinstance(value, list) or any(not isinstance(n, str) or not n or Path(n).name != n for n in value):
                    raise KitError("project_doc_fallback_filenames 无效")
                fallback_names = value
            if config.get("developer_instructions") or config.get("model_instructions_file"):
                add("WARN", f"{scope}额外指令", "存在额外指令配置，需在客户端核对最终加载内容")
            if "project_doc_max_bytes" in config:
                value = config["project_doc_max_bytes"]
                if type(value) is not int or value < 1:
                    raise KitError("project_doc_max_bytes 无效")
                limit = value
            features = config.get("features", {})
            if features.get("hooks") is False or features.get("codex_hooks") is False:
                add("WARN", f"{scope}配置关闭 Hook", str(path))
            if has_inline_hooks(config) and path.with_name("hooks.json").exists():
                add("WARN", f"{scope}双 Hook 来源", "JSON 和 TOML 同时存在；匹配 Hook 都可能执行")
            if config.get("allow_managed_hooks_only") or config.get("hooks", {}).get("allow_managed_hooks_only"):
                add("WARN", f"{scope}管理限制", "可能只允许运行管理 Hook")
        except (KitError, OSError, AttributeError, TypeError) as exc:
            add("FAIL", f"{scope}配置解析", str(exc))
    for path in home.glob("*.config.toml"):
        add("WARN", "Profile 配置", f"存在 {path.name}；是否启用无法从当前文件确定")
    add("UNVERIFIED", "完整配置优先级", "CLI 覆盖、信任项目层、MDM、云配置和系统要求需在实际客户端核对")
    instruction_paths = []
    scopes = [home]
    if root:
        scopes.extend([root, *(root / Path(*cwd.relative_to(root).parts[:n]) for n in range(1, len(cwd.relative_to(root).parts) + 1))])
    for folder in scopes:
        override = folder / "AGENTS.override.md"
        if override.exists() and override.stat().st_size:
            add("WARN", "指令覆盖文件", str(override))
        candidates = [override, folder / "AGENTS.md"]
        if folder != home:
            candidates.extend(folder / name for name in fallback_names)
        selected = next((p for p in candidates if p.is_file() and p.stat().st_size), None)
        if selected:
            instruction_paths.append(selected)
            if selected.name not in ("AGENTS.md", "AGENTS.override.md"):
                add("WARN", "指令替代文件", str(selected))
    total = sum(p.stat().st_size for p in instruction_paths if p.exists())
    add("WARN" if total > limit else "PASS", "已知指令大小", f"按已知文件加载链总计 {total} 字节；已知上限 {limit}；项目层是否信任及 CLI 覆盖仍需客户端核对")
    _hook_checks(add, managed / "runtime/hooks.jsonl", session_id, expected_events)
    _project_checks(add, root)
    return checks


def client_doctor(client, home, cwd=None, session_id=None, expected_events=()):
    from .clients import client_locations, inspect_client
    home, cwd = Path(home).resolve(), Path(cwd or Path.cwd()).resolve()
    if expected_events and not session_id:
        raise KitError("检查预期 Hook 事件必须指定 --session-id")
    checks = []
    def add(status, check, detail):
        checks.append({"status": status, "check": check, "detail": detail})
    add("PASS" if sys.version_info >= (3, 11) else "FAIL", "Python", sys.version.split()[0])
    add("PASS" if shutil.which("git") else "WARN", "Git", "可用" if shutil.which("git") else "未找到")
    add("PASS", "客户端安装目录", f"{client}: {home}")
    try:
        for status, check, detail in inspect_client(client, home):
            add(status, check, detail)
    except (KitError, OSError, KeyError, TypeError, AttributeError, ValueError) as exc:
        add("FAIL", "安装完整性", str(exc))
    add("UNVERIFIED", "模型实际遵守规则", "文件存在或脚本日志不能证明；按 docs/CLIENT_VALIDATION.md 在真实客户端验收")
    if client == "claude":
        managed, _, _ = client_locations(client, home)
        _hook_checks(add, managed / "runtime/hooks.jsonl", session_id, expected_events)
    root = None
    if (cwd / ".agent/.transaction.json").exists():
        add("FAIL", "项目未完成事务", "执行 recover，初始化中断时也必须先恢复")
    try:
        root = project_root(cwd)
    except (KitError, OSError):
        pass
    _project_checks(add, root)
    return checks


def _hook_checks(add, log, session_id, expected_events):
    records = []
    if log.exists():
        try:
            records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
        except (OSError, ValueError, UnicodeError):
            add("FAIL", "Hook 日志", "日志损坏，无法推断执行结果")
    current_definition = definition_hash()
    for event in ("SessionStart", "PreCompact"):
        matching = [r for r in records if isinstance(r, dict) and r.get("event") == event and r.get("definition_hash") == current_definition
                    and (session_id is None or r.get("session_id") == session_id)]
        if session_id:
            # Simulated input cannot prove that the native client ran this event.
            matching = [r for r in matching if r.get("origin") == "invocation"]
            name = f"{event} 本会话执行"
            if not matching:
                add("FAIL" if event in expected_events else "UNVERIFIED", name,
                    "已确认应触发，但没有本会话真实调用记录" if event in expected_events else "没有本会话记录；未确认该事件应触发")
            else:
                latest = matching[-1]
                status = "FAIL" if latest.get("status") == "FAIL" else "PASS" if latest.get("status") == "PASS" else "WARN"
                add(status, name, f"session_id={session_id}；{latest.get('timestamp')}；仅证明脚本记录，需与客户端事件核对")
            continue
        if not matching:
            add("UNVERIFIED", f"{event} 曾执行", "当前脚本定义没有执行记录")
        else:
            latest = matching[-1]
            status = "FAIL" if latest.get("status") == "FAIL" else "PASS" if latest.get("status") == "PASS" else "WARN"
            add(status, f"{event} 最近执行", f"{latest.get('timestamp')}；{latest.get('origin')}；仅证明脚本记录，不能证明客户端或模型遵从")


def _project_checks(add, root):
    if root:
        try:
            state, content, ledger = load(root)
            add("PASS", "项目状态完整性", f"{state['name']}；修订 {state['revision']}；任务修订 {ledger['revision']}")
            add("PASS" if state["goal_approved"] else "WARN", "目标批准", "已登记批准" if state["goal_approved"] else "目标仍是草案")
            add("PASS" if state["current_task_revision"] == ledger["revision"] else "WARN", "CURRENT 修订", "与任务修订比对")
            expected = progress(state["name"], ledger)
            actual = (root / ".agent/PROGRESS.md").read_text(encoding="utf-8") if (root / ".agent/PROGRESS.md").exists() else ""
            add("PASS" if actual == expected else "WARN", "进度视图", "视图比对；不一致时执行 status --rebuild")
            folder = root / ".agent/runtime/snapshots"
            snapshots = list(folder.glob("snapshot-*.json"))
            if not snapshots:
                add("UNVERIFIED", "项目快照", "尚无快照；当前磁盘状态有效")
            for path in snapshots:
                try:
                    value = validate_snapshot(read_json(path), state["project_id"])
                    if value["revision"] > state["revision"]:
                        add("WARN", "快照修订", "快照比磁盘修订高；不自动恢复")
                except (KitError, OSError, ValueError, TypeError, KeyError):
                    add("WARN", "快照异常", path.name + " 保留供人工检查")
            git = git_info(root)
            if git["root"]:
                ignored = subprocess.run(["git", "-C", str(root), "check-ignore", ".agent/runtime/probe", ".agent/.lock", ".agent/.transaction.json"], capture_output=True, timeout=10)
                add("PASS" if ignored.returncode == 0 and len(ignored.stdout.splitlines()) == 3 else "WARN", "Git 运行数据排除", "检查 .gitignore 是否实际生效")
            else:
                add("WARN", "项目 Git", "没有仓库；未自动初始化")
        except (KitError, OSError, KeyError, ValueError, TypeError) as exc:
            add("FAIL", "项目状态", str(exc))
    else:
        add("UNVERIFIED", "项目状态", "当前路径未初始化")
