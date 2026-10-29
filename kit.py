#!/usr/bin/env python3
"""Single CLI entrypoint; runtime dependency: Python standard library only."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys

# CLI reads must not create bytecode directories even when code lives in the project.
sys.dont_write_bytecode = True

if sys.version_info < (3, 11):
    sys.stderr.write("Project Anchor 需要 Python 3.11+；Windows 请使用 py -3 kit.py\n")
    raise SystemExit(2)

from core import VERSION, NAME, LEGACY_NAME
from core.atomic_io import KitError, locked, read_json, recover
from core.config import codex_home, install, uninstall, locations, trust_project
from core.diagnostics import doctor
from core.memory import (doc_change, init_project, knowledge_add, load, migrate, paths,
                         project_root, rebuild, retro, snapshot, snapshot_check,
                         task_change, git_info, rename_project, reading, current_alignment)
from core.tasks import decorate, task_view, deliverable_coverage


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
            child.add_argument("--client", choices=["codex", "agents", "claude", "dsh"],
                               help="检查对象；默认取 PROJECT_ANCHOR_CLIENT，否则 codex")
            child.add_argument("--client-home", help="agents/claude/dsh 安装目录；默认取 PROJECT_ANCHOR_CLIENT_HOME 或客户端默认目录")
            child.add_argument("--native-skills", action="store_true", help="通过真实 Codex skills/list 核对发现情况（不调用模型）")
            child.add_argument("--native-hooks", action="store_true", help="查询 Codex 实际 Hook 配置与当前定义审核状态；不设置信任")
            child.add_argument("--session-id", help="只核对指定会话的 Hook 调用记录")
            child.add_argument("--expect-event", action="append", choices=["SessionStart", "PreCompact"], default=[],
                               help="已确认应触发的事件；缺少该会话记录时报告 FAIL，需要 --session-id")
    for command in ("install-client", "uninstall-client"):
        child = sub.add_parser(command, help="不依赖 Codex 的 Skill 安装；agents=通用目录，claude=Claude Code，dsh=DeepSeek Harness")
        child.add_argument("client", choices=["agents", "claude", "dsh"])
        child.add_argument("--home", help="agents: 清单目录，默认 PROJECT_ANCHOR_HOME 或 ~/.project-anchor；"
                                          "claude: 配置目录，默认 CLAUDE_CONFIG_DIR 或 ~/.claude；"
                                          "dsh: 配置目录，默认 DSH_HOME 或 ~/.dsh")
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
    child.add_argument("--brief", action="store_true", help="保留完整目标和断点，仅省略任务长证据与描述；已完成/取消任务折叠进 summary")
    child.add_argument("--all", action="store_true", help="配合 --brief 保留全部任务，不折叠已完成或已取消")
    child.add_argument("--focus", action="store_true", help="只读取显式设置的本轮任务，不猜测")
    child.add_argument("--task", action="append", metavar="ID", help="按明确任务 ID 查询，可重复")
    child.add_argument("--milestone", help="按里程碑精确查询；不猜测本轮任务")
    child = sub.add_parser("context", help="只读：输出与 Hook 同源的会话注入摘要")
    child.add_argument("path", nargs="?", default=".")
    child.add_argument("--limit", type=int, default=6000, help="摘要字符上限")
    child.add_argument("--managed-dir", help="客户端存储目录（受信任登记与日志）；默认用 codex home")
    child.add_argument("--codex-home")
    child.add_argument("--json", action="store_true")
    child = sub.add_parser("migrate")
    child.add_argument("path")
    child.add_argument("--expected-revision", type=int, required=True)
    child.add_argument("--reason", required=True)
    child.add_argument("--dry-run", action="store_true", help="只报告迁移范围，不写文件")
    child.add_argument("--rollback", metavar="BACKUP", help="仅在迁移结果未改变时回退到指定备份")
    child = sub.add_parser("focus")
    child.add_argument("action", choices=["set", "clear"])
    child.add_argument("path")
    child.add_argument("--task", action="append")
    child.add_argument("--expected-revision", type=int, required=True)
    child.add_argument("--reason", required=True)
    child = sub.add_parser("verify")
    child.add_argument("action", choices=["run", "show"])
    child.add_argument("path")
    child.add_argument("--task")
    child.add_argument("--criterion", type=int)
    child.add_argument("--run-id")
    child.add_argument("--expected-revision", type=int)
    child.add_argument("--reason")
    child = sub.add_parser("history")
    child.add_argument("action", choices=["list", "show"])
    child.add_argument("path")
    child.add_argument("--file")
    child.add_argument("--archive")
    child = sub.add_parser("snapshot")
    child.add_argument("path", nargs="?", default=".")
    child.add_argument("--session-id", default="manual")
    child.add_argument("--check", metavar="SNAPSHOT_FILE")
    child = sub.add_parser("retro")
    child.add_argument("path", nargs="?", default=".")
    child = sub.add_parser("task")
    child.add_argument("action", choices=["add", "update", "approve", "revise", "review"])
    child.add_argument("path")
    inputs = child.add_mutually_exclusive_group()
    inputs.add_argument("--file", help="包含任务或修改字段的 UTF-8 JSON")
    inputs.add_argument("--json-input", action="store_true", help="从 stdin 读取 UTF-8 JSON")
    child.add_argument("--task-id", help="approve/revise 的任务 ID")
    child.add_argument("--source", choices=["user", "policy"], help="approve 的批准来源声明（不是身份验证）")
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
    association = child.add_mutually_exclusive_group()
    association.add_argument("--task", action="append", metavar="ID")
    association.add_argument("--no-task", action="store_true")
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
    child.add_argument("--client", choices=["agents", "claude", "dsh"], help="恢复 install-client 安装事务")
    child.add_argument("--client-home")
    child.add_argument("--rollback", action="store_true")
    return p


def _doctor_client(args):
    if args.client or args.codex_home:
        return args.client or "codex"
    client = os.environ.get("PROJECT_ANCHOR_CLIENT", "codex")
    if client not in ("codex", "agents", "claude", "dsh"):
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
                if args.focus and (args.task or args.milestone is not None):
                    raise KitError("--focus 与 --task/--milestone 不能组合")
                if args.rebuild and (args.focus or args.task or args.milestone is not None):
                    raise KitError("筛选查询不能重建全项目进度；请单独执行 status PATH --rebuild")
                if args.rebuild:
                    rebuild(root)
                with reading(root):
                    state, content, ledger = load(root)
                    from core.verification import state as verification_state
                    focus = state.get("focus")
                    selected_ids = focus["task_ids"] if args.focus and focus else args.task
                    selected, summary, external = task_view(ledger, args.brief, selected_ids, args.milestone,
                                                            args.all or args.focus)
                    if args.focus and not focus:
                        selected, external = [], []
                        summary = {**summary, "selected_total": 0}
                    by_id = {t["task_id"]: t for t in ledger["tasks"]}
                    visible = {t["task_id"] for t in [*selected, *external]}
                    pending = list(visible)
                    while pending:
                        for dep in by_id[pending.pop()]["dependencies"]:
                            if dep not in visible:
                                visible.add(dep)
                                pending.append(dep)
                    cache = {}
                    views = {tid: verification_state(root, by_id[tid], cache) if ledger["schema"] >= 3 else "legacy"
                             for tid in sorted(visible)}
                    for task in [*selected, *external]:
                        source = by_id[task["task_id"]]
                        task["verification_state"] = views[task["task_id"]]
                        task["deliverable_coverage"] = deliverable_coverage(source)
                        task["check_summary"] = [{"criterion": c["criterion"], "kind": c["kind"],
                                                  "level": "observed" if c["kind"] == "command" else "claimed/self",
                                                  "result": next((e.get("result", "unknown") for e in reversed(source["evidence"])
                                                                  if e["criterion"] == c["criterion"] and not e.get("invalidated_at")), "pending")}
                                                 for c in source.get("checks", [])]
                    result = {"project": str(root), "name": state["name"], "revision": state["revision"],
                              "goal_version": state["goal_version"], "goal_approved": state["goal_approved"],
                              "current_stale": state["current_task_revision"] != ledger["revision"],
                              "current_alignment": current_alignment(state), "current_scope": state.get("current_scope"),
                              "task_revision": ledger["revision"], "task_schema": ledger["schema"],
                              "goal": content["GOAL.md"], "current": content["CURRENT.md"], "git": git_info(root),
                              "dependency_verification": {tid: views[tid] for tid in sorted(visible)
                                                          if tid not in {t["task_id"] for t in selected}}}
                result.update(tasks=selected, summary=summary, external_dependencies=external, focus=focus,
                              focus_missing=bool(args.focus and not focus),
                              selection={"task_ids": selected_ids or [], "milestone": args.milestone, "focus": args.focus})
            elif args.command == "focus":
                from core.memory import focus_change
                if args.action == "set" and not args.task or args.action == "clear" and args.task:
                    raise KitError("focus set 需要 --task；focus clear 不接受 --task")
                revision = focus_change(root, args.expected_revision, args.task, args.reason)
                result = {"revision": revision, "changed": revision != args.expected_revision}
            elif args.command == "verify":
                from core.verification import run, show
                if args.action == "show":
                    if not args.run_id or args.task or args.criterion is not None or args.expected_revision is not None or args.reason:
                        raise KitError("verify show 只接受 --run-id")
                    result = show(root, args.run_id)
                else:
                    if not args.task or args.criterion is None or args.expected_revision is None or not args.reason or args.run_id:
                        raise KitError("verify run 需要 --task/--criterion/--expected-revision/--reason")
                    result = run(root, args.expected_revision, args.task, args.criterion, args.reason)
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    return 0 if result["result"] == "pass" else 1
            elif args.command == "history":
                from core.history import listing, show
                if args.action == "list":
                    if args.archive:
                        raise KitError("history list 不接受 --archive")
                    result = listing(root, args.file)
                else:
                    if not args.archive or args.file:
                        raise KitError("history show 需要 --archive，不接受 --file")
                    result = show(root, args.archive)
            elif args.command == "context":
                from core.hook_runtime import context
                managed = Path(args.managed_dir).resolve() if args.managed_dir else None
                home = managed if managed is not None else codex_home(args.codex_home)
                payload = context(root, home, args.limit, managed)
                if args.json:
                    result = {"project": str(root), "context": payload,
                              "trusted_injected": "不是新的行为规则" in payload}
                else:
                    print(payload)
                    result = {"project": str(root)}
            elif args.command == "migrate":
                if args.rollback:
                    if args.dry_run:
                        raise KitError("--rollback 与 --dry-run 互斥")
                    from core.memory import migration_rollback
                    result = migration_rollback(root, args.expected_revision, args.reason, args.rollback)
                else:
                    result = migrate(root, args.expected_revision, args.reason, args.dry_run)
            elif args.command == "snapshot":
                result = snapshot_check(root, args.check) if args.check else {"snapshot": str(snapshot(root, args.session_id))}
            elif args.command == "retro":
                result = {"retro": str(retro(root))}
            elif args.command == "task":
                if args.action == "review":
                    if not args.task_id or not (args.file or args.json_input) or args.source:
                        raise KitError("task review 需要 --task-id 与 --file/--json-input，不接受 --source")
                    payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig")) if args.json_input else read_json(args.file)
                    from core.verification import review
                    result = review(root, args.expected_revision, args.task_id, payload, args.reason)
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    return 0 if result["result"] == "pass" else 1
                if args.action in ("add", "update"):
                    if args.task_id:
                        raise KitError("add/update 的任务 ID 放在 JSON 中，不接受 --task-id")
                    if not (args.file or args.json_input):
                        raise KitError("add/update 需要 --file 或 --json-input")
                    payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig")) if args.json_input else read_json(args.file)
                else:
                    if args.file or args.json_input:
                        raise KitError("approve/revise 不接受 --file/--json-input；使用 --task-id")
                    if not args.task_id:
                        raise KitError("approve/revise 需要 --task-id")
                    if args.action == "approve" and not args.source:
                        raise KitError("task approve 需要 --source user|policy（调用者声明，不是身份验证）")
                    payload = {"task_id": args.task_id}
                revision = task_change(root, args.expected_revision, args.action, payload, args.reason,
                                       source=args.source)
                result = {"revision": revision, "changed": revision != args.expected_revision}
            elif args.command == "rename-project":
                result = {"revision": rename_project(root, args.expected_revision, args.name, args.reason)}
            elif args.command == "state":
                value = sys.stdin.buffer.read().decode("utf-8-sig") if args.text_input else Path(args.file).read_text(encoding="utf-8-sig")
                revision = doc_change(root, args.expected_revision, args.document, value, args.reason,
                                      args.approved, args.action == "adopt", [] if args.no_task else args.task)
                result = {"revision": revision, "changed": revision != args.expected_revision}
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
