#!/usr/bin/env python3
"""Single CLI entrypoint; runtime dependency: Python standard library only."""
import argparse
import json
from pathlib import Path
import sys

if sys.version_info < (3, 11):
    sys.stderr.write("codex-rules 需要 Python 3.11+；Windows 请使用 py -3 kit.py\n")
    raise SystemExit(2)

from core import VERSION
from core.atomic_io import KitError, locked, read_json, recover
from core.config import codex_home, install, uninstall, locations, trust_project
from core.diagnostics import doctor
from core.memory import (doc_change, init_project, knowledge_add, load, paths,
                         project_root, rebuild, retro, snapshot, snapshot_check,
                         task_change, git_info)


def parser():
    p = argparse.ArgumentParser(description="Codex-Rules 本地项目治理工具箱")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("install-global", "uninstall-global", "doctor"):
        child = sub.add_parser(command)
        child.add_argument("--codex-home")
        if command == "doctor":
            child.add_argument("path", nargs="?", default=".")
            child.add_argument("--json", action="store_true")
    child = sub.add_parser("init-project")
    child.add_argument("path")
    child.add_argument("--name", required=True)
    child.add_argument("--git-init", action="store_true")
    child.add_argument("--snapshot-keep", type=int, default=20)
    child.add_argument("--log-max-bytes", type=int, default=65536)
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
    child.add_argument("--file", required=True, help="包含任务或修改字段的 UTF-8 JSON")
    child.add_argument("--expected-revision", type=int, required=True)
    child.add_argument("--reason", required=True)
    child = sub.add_parser("state")
    child.add_argument("action", choices=["update", "adopt"])
    child.add_argument("path")
    child.add_argument("document", choices=["GOAL.md", "CURRENT.md", "DECISIONS.md", "LESSONS.md"])
    child.add_argument("--file", required=True)
    child.add_argument("--expected-revision", type=int, required=True)
    child.add_argument("--reason", required=True)
    child.add_argument("--approved", action="store_true")
    child = sub.add_parser("trust-project")
    child.add_argument("path")
    child.add_argument("--codex-home")
    child.add_argument("--approved", action="store_true", required=True)
    child = sub.add_parser("knowledge-add")
    child.add_argument("--file", required=True)
    child.add_argument("--approved", action="store_true")
    child = sub.add_parser("recover")
    child.add_argument("path", nargs="?", default=".")
    child.add_argument("--global", dest="global_install", action="store_true")
    child.add_argument("--knowledge", action="store_true")
    child.add_argument("--codex-home")
    child.add_argument("--rollback", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = None
        if args.command == "install-global":
            result = install(codex_home(args.codex_home))
        elif args.command == "uninstall-global":
            result = uninstall(codex_home(args.codex_home))
        elif args.command == "doctor":
            checks = doctor(codex_home(args.codex_home), args.path)
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
            with locked(lock):
                recover(root, journal, args.rollback)
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
                result = {"revision": task_change(root, args.expected_revision, args.action, read_json(args.file), args.reason)}
            elif args.command == "state":
                value = Path(args.file).read_text(encoding="utf-8-sig")
                result = {"revision": doc_change(root, args.expected_revision, args.document, value, args.reason,
                                                args.approved, args.action == "adopt")}
            elif args.command == "trust-project":
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
