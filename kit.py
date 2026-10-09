#!/usr/bin/env python3
"""Single CLI entrypoint; runtime dependency: Python standard library only."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys

if sys.version_info < (3, 11):
    sys.stderr.write("Project Anchor 需要 Python 3.11+；Windows 请使用 py -3 kit.py\n")
    raise SystemExit(2)

from core import VERSION, NAME, LEGACY_NAME
from core.atomic_io import KitError, locked, read_json, recover
from core.config import codex_home, install, uninstall, locations, trust_project
from core.diagnostics import doctor
from core.memory import (doc_change, init_project, knowledge_add, load, paths,
                         project_root, rebuild, retro, snapshot, snapshot_check,
                         task_change, git_info, rename_project)


def parser():
    p = argparse.ArgumentParser(description="Project Anchor 本地项目治理工具箱")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("install-global", "uninstall-global", "doctor"):
        child = sub.add_parser(command)
        child.add_argument("--codex-home")
        if command == "install-global":
            child.add_argument("--skills-dir", help="Skill 父目录；默认用户目录/.agents/skills")
        if command == "doctor":
            child.add_argument("path", nargs="?", default=".")
            child.add_argument("--json", action="store_true")
            child.add_argument("--client", choices=["codex", "agents", "claude"],
                               help="检查对象；默认取 PROJECT_ANCHOR_CLIENT，否则 codex")
            child.add_argument("--client-home", help="agents/claude 安装目录；默认取 PROJECT_ANCHOR_CLIENT_HOME 或客户端默认目录")
            child.add_argument("--native-skills", action="store_true", help="通过真实 Codex skills/list 核对发现情况（不调用模型）")
            child.add_argument("--native-hooks", action="store_true", help="查询 Codex 实际 Hook 配置与当前定义审核状态；不设置信任")
            child.add_argument("--session-id", help="只核对指定会话的 Hook 调用记录")
            child.add_argument("--expect-event", action="append", choices=["SessionStart", "PreCompact"], default=[],
                               help="已确认应触发的事件；缺少该会话记录时报告 FAIL，需要 --session-id")
    for command in ("install-client", "uninstall-client"):
        child = sub.add_parser(command, help="不依赖 Codex 的 Skill 安装；agents=通用目录，claude=Claude Code 适配")
        child.add_argument("client", choices=["agents", "claude"])
        child.add_argument("--home", help="agents: 清单目录，默认 PROJECT_ANCHOR_HOME 或 ~/.project-anchor；"
                                          "claude: 配置目录，默认 CLAUDE_CONFIG_DIR 或 ~/.claude")
        if command == "install-client":
            child.add_argument("--skills-dir", help="agents 的 Skill 父目录；默认用户目录/.agents/skills")
    child = sub.add_parser("init-project")
    child.add_argument("path")
    child.add_argument("--name", required=True)
    child.add_argument("--git-init", action="store_true")
    child.add_argument("--snapshot-keep", type=int, default=20)
    child.add_argument("--log-max-bytes", type=int, default=65536)
    child = sub.add_parser("rename-project")
    child.add_argument("path")
    child.add_argument("--name", required=True)
    child.add_argument("--expected-revision", type=int, required=True)
    child.add_argument("--reason", required=True)
    child = sub.add_parser("status")
    child.add_argument("path", nargs="?", default=".")
    child.add_argument("--rebuild", action="store_true")
    child = sub.add_parser("snapshot")
    child.add_argument("path", nargs="?", default=".")
    child.add_argument("--session-id", default="manual")
    child.add_argument("--check", metavar="SNAPSHOT_FILE")
    child = sub.add_parser("retro")
    child.add_argument("path", nargs="?", default=".")
    child = sub.add_parser("task")
    child.add_argument("action", choices=["add", "update"])
    child.add_argument("path")
    inputs = child.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--file", help="包含任务或修改字段的 UTF-8 JSON")
    inputs.add_argument("--json-input", action="store_true", help="从 stdin 读取 UTF-8 JSON")
    child.add_argument("--expected-revision", type=int, required=True)
    child.add_argument("--reason", required=True)
    child = sub.add_parser("state")
    child.add_argument("action", choices=["update", "adopt"])
    child.add_argument("path")
    child.add_argument("document", choices=["GOAL.md", "CURRENT.md", "DECISIONS.md", "LESSONS.md"])
    inputs = child.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--file")
    inputs.add_argument("--text-input", action="store_true", help="从 stdin 读取 UTF-8 Markdown")
    child.add_argument("--expected-revision", type=int, required=True)
    child.add_argument("--reason", required=True)
    child.add_argument("--approved", action="store_true")
    child = sub.add_parser("trust-project")
    child.add_argument("path")
    child.add_argument("--codex-home")
    child.add_argument("--client", choices=["codex", "claude"], default="codex")
    child.add_argument("--client-home", help="claude 配置目录；默认 CLAUDE_CONFIG_DIR 或 ~/.claude")
    child.add_argument("--approved", action="store_true", required=True)
    child = sub.add_parser("knowledge-add")
    child.add_argument("--file", required=True)
    child.add_argument("--approved", action="store_true")
    child = sub.add_parser("recover")
    child.add_argument("path", nargs="?", default=".")
    child.add_argument("--global", dest="global_install", action="store_true")
    child.add_argument("--knowledge", action="store_true")
    child.add_argument("--codex-home")
    child.add_argument("--skills-dir", help="恢复首次安装时使用的 Skill 父目录")
    child.add_argument("--client", choices=["agents", "claude"], help="恢复 install-client 安装事务")
    child.add_argument("--client-home")
    child.add_argument("--rollback", action="store_true")
    return p


def _doctor_client(args):
    if args.client or args.codex_home:
        return args.client or "codex"
    client = os.environ.get("PROJECT_ANCHOR_CLIENT", "codex")
    if client not in ("codex", "agents", "claude"):
        raise KitError(f"PROJECT_ANCHOR_CLIENT 无效: {client}")
    return client


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = None
        if args.command == "install-global":
            result = install(codex_home(args.codex_home), args.skills_dir)
        elif args.command == "uninstall-global":
            result = uninstall(codex_home(args.codex_home))
        elif args.command in ("install-client", "uninstall-client"):
            from core.clients import client_home, install_client, uninstall_client
            home = client_home(args.client, args.home)
            result = (install_client(args.client, home, args.skills_dir) if args.command == "install-client"
                      else uninstall_client(args.client, home))
        elif args.command == "doctor" and _doctor_client(args) != "codex":
            from core.clients import client_home
            from core.diagnostics import client_doctor
            client = _doctor_client(args)
            if args.native_skills or args.native_hooks or args.codex_home:
                raise KitError("--native-skills、--native-hooks、--codex-home 只适用于 Codex")
            selected = args.client_home or (os.environ.get("PROJECT_ANCHOR_CLIENT_HOME")
                                            if os.environ.get("PROJECT_ANCHOR_CLIENT") == client else None)
            checks = client_doctor(client, client_home(client, selected), args.path, args.session_id, args.expect_event)
            if args.json:
                print(json.dumps(checks, ensure_ascii=False, indent=2))
            else:
                for check in checks:
                    print(f"{check['status']:10} {check['check']}: {check['detail']}")
            return 1 if any(c["status"] == "FAIL" for c in checks) else 0
        elif args.command == "doctor":
            checks = doctor(codex_home(args.codex_home), args.path, args.session_id, args.expect_event)
            if args.native_skills:
                from core.native import skill_discovery
                checks.extend(skill_discovery(codex_home(args.codex_home), args.path))
            if args.native_hooks:
                from core.native import hook_discovery
                actual = hook_discovery(codex_home(args.codex_home), args.path)
                checks = [c for c in checks if c["check"] != "Hook 已信任"] + actual
            if args.json:
                result = checks
            else:
                for check in checks:
                    print(f"{check['status']:10} {check['check']}: {check['detail']}")
            if result is not None:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if any(c["status"] == "FAIL" for c in checks) else 0
        elif args.command == "init-project":
            result = {"project": str(init_project(args.path, args.name, args.git_init, args.snapshot_keep, args.log_max_bytes))}
        elif args.command == "recover" and args.client:
            if args.global_install or args.knowledge:
                raise KitError("恢复对象只能选择一个")
            from core.clients import client_home, recover_client
            recover_client(args.client, client_home(args.client, args.client_home), args.skills_dir, args.rollback)
            result = {"recovered": True, "rollback": args.rollback}
        elif args.command == "recover":
            if args.global_install and args.knowledge:
                raise KitError("恢复对象只能选择一个")
            if args.global_install:
                root = codex_home(args.codex_home)
                _, lock, journal = locations(root)
            elif args.knowledge:
                from core.memory import KIT_ROOT
                root = KIT_ROOT / "knowledge"
                lock, journal = root / ".lock", root / ".transaction.json"
            else:
                # Works even before init transaction installed state.json.
                root = Path(args.path).resolve()
                _, lock, journal = paths(root)
            with locked(lock), ExitStack() as stack:
                extra = None
                if args.global_install:
                    from core.skill_install import skill_directory, skill_scopes
                    manifest_path = root / "codex-rules/install.json"
                    manifest = read_json(manifest_path) if manifest_path.exists() else {}
                    target = Path(manifest["skill"]["path"]) if manifest.get("skill") else skill_directory(args.skills_dir)
                    recovery_record = read_json(journal)
                    migrating = "legacy_skill" in recovery_record.get("roots", {})
                    if target.name == LEGACY_NAME and migrating:
                        target = skill_directory(target.parent)
                    if recovery_record.get("roots"):
                        extra = skill_scopes(manifest, target, legacy=migrating)
                        stack.enter_context(locked(target.parent / ".codex-rules.lock"))
                recover(root, journal, args.rollback, extra)
            result = {"recovered": True, "rollback": args.rollback}
        elif args.command == "knowledge-add":
            result = {"knowledge": str(knowledge_add(args.file, args.approved))}
        else:
            root = project_root(args.path)
            if args.command == "status":
                if args.rebuild:
                    rebuild(root)
                _, lock, _ = paths(root)
                with locked(lock):
                    state, content, ledger = load(root)
                result = {"project": str(root), "name": state["name"], "revision": state["revision"],
                          "goal_version": state["goal_version"], "goal_approved": state["goal_approved"],
                          "current_stale": state["current_task_revision"] != ledger["revision"],
                          "task_revision": ledger["revision"], "tasks": ledger["tasks"],
                          "goal": content["GOAL.md"], "current": content["CURRENT.md"], "git": git_info(root)}
            elif args.command == "snapshot":
                result = snapshot_check(root, args.check) if args.check else {"snapshot": str(snapshot(root, args.session_id))}
            elif args.command == "retro":
                result = {"retro": str(retro(root))}
            elif args.command == "task":
                payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig")) if args.json_input else read_json(args.file)
                result = {"revision": task_change(root, args.expected_revision, args.action, payload, args.reason)}
            elif args.command == "rename-project":
                result = {"revision": rename_project(root, args.expected_revision, args.name, args.reason)}
            elif args.command == "state":
                value = sys.stdin.buffer.read().decode("utf-8-sig") if args.text_input else Path(args.file).read_text(encoding="utf-8-sig")
                result = {"revision": doc_change(root, args.expected_revision, args.document, value, args.reason,
                                                args.approved, args.action == "adopt")}
            elif args.command == "trust-project":
                if args.client == "claude":
                    from core.clients import client_home, client_locations
                    home = client_home("claude", args.client_home)
                    trust_project(root, home, client_locations("claude", home)[0])
                else:
                    trust_project(root, codex_home(args.codex_home))
                result = {"reviewed_project_state": True, "native_hook_trust": "UNVERIFIED"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KitError, OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
