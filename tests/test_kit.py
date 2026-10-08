import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core import atomic_io as io
from core import config, memory, tasks
from core.diagnostics import doctor
from core.hook_runtime import context, log_event

ROOT = Path(__file__).resolve().parents[1]


class Environment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="codex-rules 中文 ")
        self.base = Path(self.tmp.name)
        self.home = self.base / "用户配置 空格"
        self.project = self.base / "研发 项目"
        self.project.mkdir()
        self.env = dict(os.environ, CODEX_HOME=str(self.home), PYTHONUTF8="1")

    def tearDown(self):
        self.tmp.cleanup()

    def init(self, **kwargs):
        memory.init_project(self.project, "测试项目", **kwargs)
        return memory.load(self.project)

    def add(self, tid="T1", **fields):
        state, _, _ = memory.load(self.project)
        task = {"task_id": tid, "title": tid, "acceptance_criteria": ["可验证"], **fields}
        return memory.task_change(self.project, state["revision"], "add", task, "测试创建")

    def update(self, tid="T1", **fields):
        state, _, _ = memory.load(self.project)
        return memory.task_change(self.project, state["revision"], "update", {"task_id": tid, **fields}, "测试更新")

    def cli(self, *args, cwd=None):
        if args[0] == "install-global":
            args = (*args, "--skills-dir", str(self.base / ".agents/skills"))
        return subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "kit.py"), *map(str, args)],
                              cwd=cwd or self.base, env=self.env, capture_output=True,
                              encoding="utf-8", timeout=30)

    def hook(self, event="SessionStart", source="startup", **extra):
        script = "session_context.py" if event == "SessionStart" else "pre_compact.py"
        payload = {"hook_event_name": event, "cwd": str(self.project), "session_id": "test-session",
                   "source": source, "trigger": "auto", **extra}
        return subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "hooks" / script), "--simulate"],
                              input=json.dumps(payload), cwd=self.base, env=self.env, capture_output=True,
                              encoding="utf-8", timeout=30)


class AtomicTests(Environment):
    def test_atomic_replace_failure_preserves_original(self):
        path = self.base / "数据.txt"
        path.write_bytes(b"original")
        with patch("core.atomic_io.os.replace", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                io.atomic_write(path, b"new")
        self.assertEqual(path.read_bytes(), b"original")
        self.assertFalse(list(self.base.glob(".kit-*")))

    def test_transaction_rollback(self):
        first, second = self.base / "a", self.base / "b"
        first.write_bytes(b"old")
        original = io.atomic_write
        def fail(path, data):
            if Path(path) == second:
                raise OSError("injected")
            original(path, data)
        with patch("core.atomic_io.atomic_write", side_effect=fail):
            with self.assertRaises(OSError):
                io.transaction(self.base, self.base / "journal", {first: b"new", second: b"new"})
        self.assertEqual(first.read_bytes(), b"old")
        self.assertFalse(second.exists())
        self.assertFalse((self.base / "journal").exists())

    def test_recovery_after_hard_crash(self):
        path, journal = self.base / "file", self.base / "journal"
        path.write_bytes(b"old")
        original = io.atomic_write
        def crash(target, data):
            if Path(target) == path:
                original(target, data)
                raise KeyboardInterrupt()
            original(target, data)
        with patch("core.atomic_io.atomic_write", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                io.transaction(self.base, journal, {path: b"new"})
        with self.assertRaises(io.KitError):
            io.check_pending(journal)
        io.recover(self.base, journal, rollback=True)
        self.assertEqual(path.read_bytes(), b"old")

    def test_recovery_refuses_external_changes(self):
        path, journal = self.base / "file", self.base / "journal"
        path.write_bytes(b"user edit")
        io.atomic_write(journal, io.encode_json({"schema": 1, "entries": [{"path": "file", "old": io._pack(b"old"), "new": io._pack(b"new") }]}))
        with self.assertRaises(io.KitError):
            io.recover(self.base, journal)
        self.assertEqual(path.read_bytes(), b"user edit")
        self.assertTrue(journal.exists())

    def test_path_escape(self):
        with self.assertRaises(io.KitError):
            io.transaction(self.project, self.project / "journal", {self.base / "outside": b"bad"})

    def test_expected_file_change_refuses_transaction(self):
        path = self.base / "file"
        path.write_bytes(b"user edit")
        with self.assertRaises(io.KitError):
            io.transaction(self.base, self.base / "journal", {path: b"new"}, {path: b"old"})
        self.assertEqual(path.read_bytes(), b"user edit")
        self.assertFalse((self.base / "journal").exists())

    def test_process_lock_conflict(self):
        path = self.base / "lock"
        script = "from core.atomic_io import locked; from pathlib import Path; import sys;\nwith locked(Path(sys.argv[1]), timeout=0.1): pass"
        with io.locked(path):
            result = subprocess.run([sys.executable, "-c", script, str(path)], cwd=ROOT, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        with io.locked(path, timeout=0.1):
            pass


class ProjectTests(Environment):
    def test_empty_chinese_space_path(self):
        state, _, ledger = self.init()
        self.assertEqual(ledger["project_id"], state["project_id"])
        self.assertTrue((self.project / "AGENTS.md").exists())

    def test_existing_agents_preserved(self):
        existing = b"User rules\r\n"
        (self.project / "AGENTS.md").write_bytes(existing)
        self.init()
        self.assertTrue((self.project / "AGENTS.md").read_bytes().startswith(existing))

    def test_git_clone_preserves_hashed_state_bytes(self):
        self.init(git_init=True)
        current = self.project / ".agent/CURRENT.md"
        original = current.read_bytes()
        current.write_bytes(b"\xef\xbb\xbf" + original.replace(b"\n", b"\r\n"))
        memory.doc_change(self.project, 0, "CURRENT.md", current.read_text(encoding="utf-8-sig"), "确认编码", adopt=True)
        subprocess.run(["git", "-C", str(self.project), "-c", "core.autocrlf=true", "add", ".agent", ".gitattributes", ".gitignore", "AGENTS.md"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.project), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "state"], check=True, capture_output=True)
        clone = self.base / "克隆 项目"
        result = subprocess.run(["git", "-c", "core.autocrlf=true", "clone", "--no-hardlinks", str(self.project), str(clone)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        self.assertEqual(memory.load(clone)[0]["revision"], 1)
        self.assertEqual(current.read_bytes(), (clone / ".agent/CURRENT.md").read_bytes())

    def test_repeat_init(self):
        self.init()
        before = (self.project / ".agent/state.json").read_bytes()
        self.init()
        self.assertEqual(before, (self.project / ".agent/state.json").read_bytes())

    def test_repeat_different_name_refused(self):
        self.init()
        with self.assertRaises(io.KitError):
            memory.init_project(self.project, "其他项目")

    def test_existing_git_history_preserved(self):
        subprocess.run(["git", "init", str(self.project)], check=True, capture_output=True)
        (self.project / "business.txt").write_text("business")
        subprocess.run(["git", "-C", str(self.project), "add", "business.txt"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.project), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "existing"], check=True, capture_output=True)
        old = memory.git_info(self.project)["commit"]
        self.init(git_init=True)
        self.assertEqual(old, memory.git_info(self.project)["commit"])
        self.assertEqual((self.project / "business.txt").read_text(), "business")

    def test_git_failure_leaves_no_state(self):
        with patch("core.memory.git_info", return_value={"root": None}), patch("core.memory.subprocess.run", return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaises(io.KitError):
                self.init(git_init=True)
        self.assertFalse((self.project / ".agent/state.json").exists())

    def test_subdirectory_resolution(self):
        self.init()
        child = self.project / "src"
        child.mkdir()
        self.assertEqual(memory.project_root(child), self.project)

    def test_nested_git_boundary(self):
        self.init()
        child = self.project / "other"
        child.mkdir()
        subprocess.run(["git", "init", str(child)], check=True, capture_output=True)
        with self.assertRaises(io.KitError):
            memory.project_root(child)

    def test_unknown_state_preserved(self):
        folder = self.project / ".agent"
        folder.mkdir()
        (folder / "GOAL.md").write_text("user content")
        with self.assertRaises(io.KitError):
            self.init()
        self.assertEqual((folder / "GOAL.md").read_text(), "user content")

    def test_bad_encoding_refused(self):
        (self.project / "AGENTS.md").write_bytes(b"\xff")
        with self.assertRaises(UnicodeError):
            self.init()
        self.assertFalse((self.project / ".agent/state.json").exists())


class TaskTests(Environment):
    def setUp(self):
        super().setUp()
        self.init()

    def test_create_and_complete(self):
        self.add(plan="approved")
        self.update(status="doing")
        self.update(status="done", evidence=[{"type": "manual", "criterion": 1, "detail": "用户检查通过"}])
        self.assertEqual(memory.load(self.project)[2]["tasks"][0]["status"], "done")
        self.assertIn("完成率: 100%", (self.project / ".agent/PROGRESS.md").read_text(encoding="utf-8"))

    def test_duplicate_id(self):
        self.add()
        with self.assertRaises(io.KitError):
            self.add()

    def test_missing_dependency(self):
        with self.assertRaises(io.KitError):
            self.add(dependencies=["missing"])
        self.assertEqual(memory.load(self.project)[2]["tasks"], [])

    def test_cycle(self):
        self.add()
        self.add("T2", dependencies=["T1"])
        with self.assertRaises(io.KitError):
            self.update(dependencies=["T2"])

    def test_invalid_status(self):
        self.add()
        with self.assertRaises(io.KitError):
            self.update(status="unknown")

    def test_draft_cannot_start(self):
        self.add()
        with self.assertRaises(io.KitError):
            self.update(status="doing")

    def test_illegal_transition(self):
        self.add(plan="approved")
        with self.assertRaises(io.KitError):
            self.update(status="done", evidence=[{"type": "test", "criterion": 1, "detail": "test"}])

    def test_done_needs_evidence(self):
        self.add(plan="approved")
        self.update(status="doing")
        with self.assertRaises(io.KitError):
            self.update(status="done")

    def test_all_criteria_need_evidence(self):
        self.add(plan="approved", acceptance_criteria=["a", "b"])
        self.update(status="doing")
        with self.assertRaises(io.KitError):
            self.update(status="done", evidence=[{"type": "file", "criterion": 1, "detail": "a.md"}])

    def test_dependency_blocks_start(self):
        self.add()
        self.add("T2", plan="approved", dependencies=["T1"])
        with self.assertRaises(io.KitError):
            self.update("T2", status="doing")

    def test_blocked_needs_reason(self):
        self.add()
        with self.assertRaises(io.KitError):
            self.update(status="blocked")
        self.update(status="blocked", blocker="缺少材料")

    def test_revision_conflict(self):
        self.add()
        before = (self.project / ".agent/tasks.json").read_bytes()
        with self.assertRaises(io.KitError):
            memory.task_change(self.project, 0, "update", {"task_id": "T1", "title": "stale"}, "原因")
        self.assertEqual(before, (self.project / ".agent/tasks.json").read_bytes())

    def test_task_write_failure_rolls_back(self):
        state = (self.project / ".agent/state.json").read_bytes()
        original = io.atomic_write
        def fail(path, data):
            if Path(path).name == "PROGRESS.md":
                raise OSError("injected")
            return original(path, data)
        with patch("core.atomic_io.atomic_write", side_effect=fail):
            with self.assertRaises(OSError):
                self.add()
        self.assertEqual(state, (self.project / ".agent/state.json").read_bytes())
        self.assertEqual(memory.load(self.project)[2]["tasks"], [])

    def test_progress_rebuild(self):
        self.add()
        view = self.project / ".agent/PROGRESS.md"
        before = view.read_bytes()
        view.write_text("stale")
        memory.rebuild(self.project)
        self.assertEqual(view.read_bytes(), before)

    def test_cancel_preserves_history(self):
        self.add()
        self.update(status="cancelled")
        ledger = memory.load(self.project)[2]
        self.assertEqual(len(ledger["tasks"]), 1)
        self.assertEqual(len(ledger["history"]), 2)

    def test_two_processes_same_revision_one_wins(self):
        payload = self.base / "payload.json"
        payload.write_bytes(io.encode_json({"task_id": "C1", "title": "并发", "acceptance_criteria": ["一次写入"]}))
        args = [sys.executable, str(ROOT / "kit.py"), "task", "add", str(self.project), "--file", str(payload), "--expected-revision", "0", "--reason", "并发测试"]
        processes = [subprocess.Popen(args, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        for process in processes:
            process.communicate(timeout=15)
        self.assertEqual(sorted(p.returncode for p in processes), [0, 1])
        self.assertEqual(len(memory.load(self.project)[2]["tasks"]), 1)

    def test_reopen_dependency_refused(self):
        self.add(plan="approved")
        self.update(status="doing")
        self.update(status="done", evidence=[{"type": "review", "criterion": 1, "detail": "审阅通过"}])
        self.add("T2", plan="approved", dependencies=["T1"])
        self.update("T2", status="doing")
        with self.assertRaises(io.KitError):
            self.update(status="doing")

    def test_large_dependency_chain(self):
        state, _, ledger = memory.load(self.project)
        for i in range(1500):
            ledger["tasks"].append({"task_id": f"T{i}", "title": "任务", "description": "任务", "milestone": "m", "status": "todo", "plan": "draft", "acceptance_criteria": ["完成"], "evidence": [], "blocker": "", "dependencies": [f"T{i-1}"] if i else []})
        tasks.validate(ledger)

    def test_reopen_clears_old_evidence(self):
        self.add(plan="approved")
        self.update(status="doing")
        self.update(status="done", evidence=[{"type": "test", "criterion": 1, "detail": "上次测试"}])
        self.update(status="doing")
        self.assertEqual(memory.load(self.project)[2]["tasks"][0]["evidence"], [])

    def test_unknown_field_rejected(self):
        with self.assertRaises(io.KitError):
            self.add(unknown="field")


class MemoryTests(Environment):
    def setUp(self):
        super().setUp()
        self.init(snapshot_keep=2)

    def test_normal_snapshot_and_missing_snapshot(self):
        path = memory.snapshot(self.project)
        self.assertFalse(memory.snapshot_check(self.project, path)["stale"])
        with self.assertRaises(FileNotFoundError):
            memory.snapshot_check(self.project, self.base / "missing")

    def test_snapshot_retention_unknown_file_survives(self):
        path = memory.snapshot(self.project)
        unknown = path.parent / "snapshot-unknown.json"
        unknown.write_text("unknown")
        for _ in range(4):
            memory.snapshot(self.project)
        self.assertTrue(unknown.exists())
        self.assertEqual(len(list(path.parent.glob("snapshot-*.json"))), 3)

    def test_wrong_project_snapshot(self):
        path = memory.snapshot(self.project)
        other = self.base / "other"
        memory.init_project(other, "other")
        with self.assertRaises(io.KitError):
            memory.snapshot_check(other, path)

    def test_snapshot_corruption(self):
        path = memory.snapshot(self.project)
        value = io.read_json(path)
        value["files"]["GOAL.md"] = "corrupt"
        path.write_bytes(io.encode_json(value))
        with self.assertRaises(io.KitError):
            memory.snapshot_check(self.project, path)

    def test_snapshot_stale_not_restored(self):
        path = memory.snapshot(self.project)
        self.add()
        self.assertTrue(memory.snapshot_check(self.project, path)["stale"])
        self.assertEqual(memory.load(self.project)[0]["revision"], 1)

    def test_document_drift_fails(self):
        (self.project / ".agent/CURRENT.md").write_text("drift")
        with self.assertRaises(io.KitError):
            memory.load(self.project)

    def test_current_size_limit(self):
        value = memory.load(self.project)[1]["CURRENT.md"] + "line\n" * 60
        with self.assertRaises(io.KitError):
            memory.doc_change(self.project, 0, "CURRENT.md", value, "原因")

    def test_goal_approval_and_history(self):
        value = memory.load(self.project)[1]["GOAL.md"].replace("待确认。", "已确认内容。")
        with self.assertRaises(io.KitError):
            memory.doc_change(self.project, 0, "GOAL.md", value, "原因")
        memory.doc_change(self.project, 0, "GOAL.md", value, "用户确认", approved=True)
        state = memory.load(self.project)[0]
        self.assertEqual(state["goal_version"], 2)
        self.assertTrue(state["goal_approved"])

    def test_adopt_single_document(self):
        path = self.project / ".agent/CURRENT.md"
        value = path.read_text(encoding="utf-8") + "\n外部确认的修订。\n"
        path.write_text(value, encoding="utf-8")
        memory.doc_change(self.project, 0, "CURRENT.md", value, "审核编辑", adopt=True)
        self.assertEqual(memory.load(self.project)[0]["revision"], 1)

    def test_adopt_refuses_other_drift(self):
        path = self.project / ".agent/CURRENT.md"
        value = path.read_text(encoding="utf-8") + "\n编辑。\n"
        path.write_text(value, encoding="utf-8")
        (self.project / ".agent/LESSONS.md").write_text("another edit", encoding="utf-8")
        with self.assertRaises(io.KitError):
            memory.doc_change(self.project, 0, "CURRENT.md", value, "审核", adopt=True)

    def test_bom_document_snapshot_integrity(self):
        path = self.project / ".agent/CURRENT.md"
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        value = path.read_text(encoding="utf-8-sig")
        memory.doc_change(self.project, 0, "CURRENT.md", value, "审核 BOM", adopt=True)
        snap = memory.snapshot(self.project)
        self.assertFalse(memory.snapshot_check(self.project, snap)["stale"])
        self.assertTrue(io.read_json(snap)["files"]["CURRENT.md"].startswith("\ufeff"))

    def test_malformed_state_fields(self):
        path = self.project / ".agent/state.json"
        state = io.read_json(path)
        state["goal_approved"] = "maybe"
        path.write_bytes(io.encode_json(state))
        with self.assertRaises(io.KitError):
            memory.load(self.project)

    def test_context_requires_exact_external_review(self):
        self.assertIn("未审核", context(self.project, self.home))
        config.trust_project(self.project, self.home)
        self.assertIn("state_revision", context(self.project, self.home))
        value = memory.load(self.project)[1]["CURRENT.md"] + "\n更新\n"
        memory.doc_change(self.project, 0, "CURRENT.md", value, "状态更新")
        self.assertIn("未审核", context(self.project, self.home))

    def test_context_length(self):
        value = memory.load(self.project)[1]["GOAL.md"] + "很长的背景。" * 5000
        memory.doc_change(self.project, 0, "GOAL.md", value, "用户确认", approved=True)
        config.trust_project(self.project, self.home)
        result = context(self.project, self.home, limit=1200)
        self.assertLessEqual(len(result), 1200)
        self.assertIn('"truncated": true', result)

    def test_current_stale_then_update(self):
        self.add()
        state, content, ledger = memory.load(self.project)
        self.assertNotEqual(state["current_task_revision"], ledger["revision"])
        memory.doc_change(self.project, 1, "CURRENT.md", content["CURRENT.md"], "同步断点")
        self.assertEqual(memory.load(self.project)[0]["current_task_revision"], 1)


class InstallTests(Environment):
    def test_first_install(self):
        result = config.install(self.home, self.base / ".agents/skills")
        self.assertTrue(result["changed"])
        self.assertTrue((self.home / "hooks.json").exists())
        self.assertFalse((self.home / "config.toml").exists())

    def test_repeat_install_bytes_unchanged(self):
        config.install(self.home, self.base / ".agents/skills")
        first = (self.home / "hooks.json").read_bytes()
        self.assertFalse(config.install(self.home, self.base / ".agents/skills")["changed"])
        self.assertEqual(first, (self.home / "hooks.json").read_bytes())

    def test_user_config_agents_and_hooks_preserved(self):
        self.home.mkdir()
        original = b'model = "user-model"\r\n[features]\r\nhooks = true\r\n'
        (self.home / "config.toml").write_bytes(original)
        (self.home / "AGENTS.md").write_bytes(b"user rules\r\n")
        group = {"hooks": [{"type": "command", "command": "echo user"}]}
        (self.home / "hooks.json").write_bytes(io.encode_json({"description": "User", "hooks": {"SessionStart": [group]}}))
        config.install(self.home, self.base / ".agents/skills")
        self.assertEqual((self.home / "config.toml").read_bytes(), original)
        self.assertIn(group, io.read_json(self.home / "hooks.json")["hooks"]["SessionStart"])
        self.assertTrue((self.home / "AGENTS.md").read_bytes().startswith(b"user rules\r\n"))

    def test_install_failure_rolls_back(self):
        self.home.mkdir()
        original_agents = b"original rules"
        (self.home / "AGENTS.md").write_bytes(original_agents)
        original = io.atomic_write
        def fail(path, data):
            if Path(path) == self.home / "hooks.json":
                raise OSError("injected")
            original(path, data)
        with patch("core.atomic_io.atomic_write", side_effect=fail):
            with self.assertRaises(OSError):
                config.install(self.home, self.base / ".agents/skills")
        self.assertEqual((self.home / "AGENTS.md").read_bytes(), original_agents)
        self.assertFalse((self.home / "codex-rules/install.json").exists())

    def test_custom_home_env(self):
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home)}):
            self.assertEqual(config.codex_home(), self.home)

    def test_uninstall_preserves_later_additions(self):
        config.install(self.home, self.base / ".agents/skills")
        agents = self.home / "AGENTS.md"
        agents.write_bytes(agents.read_bytes() + b"\nLater user rules\n")
        hooks = io.read_json(self.home / "hooks.json")
        added = {"hooks": [{"type": "command", "command": "echo later"}]}
        hooks["hooks"]["Stop"] = [added]
        (self.home / "hooks.json").write_bytes(io.encode_json(hooks))
        config.uninstall(self.home)
        self.assertEqual(agents.read_bytes(), b"\nLater user rules\n")
        self.assertEqual(io.read_json(self.home / "hooks.json")["hooks"], {"Stop": [added]})

    def test_uninstall_pristine(self):
        config.install(self.home, self.base / ".agents/skills")
        config.uninstall(self.home)
        self.assertFalse((self.home / "AGENTS.md").exists())
        self.assertFalse((self.home / "hooks.json").exists())

    def test_uninstall_drift_refused(self):
        config.install(self.home, self.base / ".agents/skills")
        path = self.home / "AGENTS.md"
        changed = path.read_bytes().replace(config.VERSION.encode(), b"9.9.9")
        path.write_bytes(changed)
        with self.assertRaises(io.KitError):
            config.uninstall(self.home)
        self.assertEqual(path.read_bytes(), changed)

    def test_hook_drift_refused(self):
        config.install(self.home, self.base / ".agents/skills")
        path = self.home / "hooks.json"
        value = io.read_json(path)
        value["hooks"]["PreCompact"][0]["matcher"] = "wrong"
        path.write_bytes(io.encode_json(value))
        with self.assertRaises(io.KitError):
            config.install(self.home, self.base / ".agents/skills")

    def test_malformed_user_config_refused(self):
        self.home.mkdir()
        (self.home / "config.toml").write_text("not valid toml")
        with self.assertRaises(io.KitError):
            config.install(self.home, self.base / ".agents/skills")
        self.assertFalse((self.home / "AGENTS.md").exists())

    def test_encoded_windows_command_literal(self):
        command = config.windows_command(["C:/空 格/py'1.exe", "C:/test/$x`file.py"])
        script = base64.b64decode(command.split()[-1]).decode("utf-16-le")
        self.assertEqual(script, "& 'C:/空 格/py''1.exe' 'C:/test/$x`file.py'")


class HookAndDoctorTests(Environment):
    def setUp(self):
        super().setUp()
        self.init()

    def test_all_session_sources(self):
        config.trust_project(self.project, self.home)
        for source in ("startup", "resume", "clear", "compact"):
            with self.subTest(source=source):
                result = self.hook(source=source)
                self.assertEqual(result.returncode, 0, result.stderr)
                value = json.loads(result.stdout)
                self.assertTrue(value["continue"])
                self.assertEqual(value["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_precompact_snapshot_no_business_edits(self):
        file = self.project / "business.txt"
        file.write_bytes(b"keep")
        result = self.hook("PreCompact")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["continue"])
        self.assertEqual(file.read_bytes(), b"keep")
        self.assertEqual(len(list((self.project / ".agent/runtime/snapshots").glob("*.json"))), 1)

    def test_hook_failure_visible_and_logged(self):
        (self.project / ".agent/GOAL.md").write_bytes(b"broken")
        result = self.hook("PreCompact")
        self.assertEqual(result.returncode, 1)
        value = json.loads(result.stdout)
        self.assertTrue(value["continue"])
        self.assertIn("失败", value["systemMessage"])
        record = json.loads((self.home / "codex-rules/runtime/hooks.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(record["status"], "FAIL")

    def test_uninitialized_hook_skipped(self):
        result = self.hook(cwd=str(self.base))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("hookSpecificOutput", json.loads(result.stdout))

    def test_secret_input_not_logged(self):
        result = self.hook(source="invalid", secret="SECRET-DO-NOT-SAVE")
        self.assertEqual(result.returncode, 1)
        log = (self.home / "codex-rules/runtime/hooks.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("SECRET-DO-NOT-SAVE", log)

    def test_doctor_unverified_trust_and_execution(self):
        config.install(self.home, self.base / ".agents/skills")
        checks = doctor(self.home, self.project)
        for name in ("Hook 已信任", "SessionStart 曾执行", "模型实际遵守规则"):
            self.assertEqual(next(c["status"] for c in checks if c["check"] == name), "UNVERIFIED")
        self.assertFalse(any(c["status"] == "FAIL" for c in checks), checks)

    def test_doctor_recent_failure(self):
        self.hook(source="invalid")
        checks = doctor(self.home, self.project)
        self.assertEqual(next(c["status"] for c in checks if c["check"] == "SessionStart 最近执行"), "FAIL")

    def test_doctor_rule_version_drift(self):
        config.install(self.home, self.base / ".agents/skills")
        path = self.home / "codex-rules/install.json"
        manifest = io.read_json(path)
        manifest["version"] = "0.0.1"
        path.write_bytes(io.encode_json(manifest))
        rules = self.home / "AGENTS.md"
        rules.write_bytes(rules.read_bytes().replace(config.VERSION.encode(), b"2.0.0"))
        checks = doctor(self.home, self.project)
        self.assertEqual(next(c["status"] for c in checks if c["check"] == "规则版本"), "WARN")
        self.assertEqual(next(c["status"] for c in checks if c["check"] == "全局规则一致性"), "FAIL")

    def test_doctor_config_and_override_conflicts(self):
        config.install(self.home, self.base / ".agents/skills")
        (self.home / "AGENTS.override.md").write_text("override")
        local = self.project / ".codex"
        local.mkdir()
        (local / "config.toml").write_text("[features]\nhooks = false\n", encoding="utf-8")
        checks = doctor(self.home, self.project)
        self.assertTrue(any(c["check"] == "指令覆盖文件" and c["status"] == "WARN" for c in checks))
        self.assertTrue(any(c["check"] == "项目配置关闭 Hook" for c in checks))

    def test_doctor_size_limit(self):
        config.install(self.home, self.base / ".agents/skills")
        (self.home / "config.toml").write_text("project_doc_max_bytes = 10", encoding="utf-8")
        checks = doctor(self.home, self.project)
        self.assertEqual(next(c["status"] for c in checks if c["check"] == "已知指令大小"), "WARN")

    def test_doctor_selected_override_size(self):
        config.install(self.home, self.base / ".agents/skills")
        (self.home / "AGENTS.override.md").write_text("x" * 40000, encoding="utf-8")
        checks = doctor(self.home, self.project)
        self.assertEqual(next(c["status"] for c in checks if c["check"] == "已知指令大小"), "WARN")

    def test_doctor_fallback_file(self):
        config.install(self.home, self.base / ".agents/skills")
        (self.home / "config.toml").write_text('project_doc_fallback_filenames = ["PROJECT_RULES.md"]', encoding="utf-8")
        (self.project / "AGENTS.md").unlink()
        (self.project / "PROJECT_RULES.md").write_text("fallback", encoding="utf-8")
        checks = doctor(self.home, self.project)
        self.assertTrue(any(c["check"] == "指令替代文件" for c in checks))

    def test_log_rotation_bound(self):
        record = {"event": "SessionStart", "status": "PASS", "text": "x" * 80}
        for _ in range(30):
            log_event(self.home, record, 1024)
        folder = self.home / "codex-rules/runtime"
        self.assertLessEqual((folder / "hooks.jsonl").stat().st_size, 1024)
        self.assertLessEqual((folder / "hooks.jsonl.1").stat().st_size, 1024)

    def test_log_rotation_keeps_complete_json_lines(self):
        record = {"event": "SessionStart", "status": "PASS", "text": "中文" * 40}
        for _ in range(12):
            log_event(self.home, record, 2048)
        log_event(self.home, record, 1024)
        for name in ("hooks.jsonl", "hooks.jsonl.1"):
            path = self.home / "codex-rules/runtime" / name
            for line in path.read_text(encoding="utf-8").splitlines():
                self.assertIsInstance(json.loads(line), dict)

    def test_doctor_script_hash_change(self):
        config.install(self.home, self.base / ".agents/skills")
        with patch("core.diagnostics.definition_hash", return_value="changed"):
            checks = doctor(self.home, self.project)
        self.assertEqual(next(c["status"] for c in checks if c["check"] == "Hook 脚本版本"), "WARN")

    def test_wrong_project_identity_in_ledger(self):
        state = io.read_json(self.project / ".agent/state.json")
        ledger = io.read_json(self.project / ".agent/tasks.json")
        ledger["project_id"] = "wrong"
        data = io.encode_json(ledger)
        (self.project / ".agent/tasks.json").write_bytes(data)
        state["hashes"]["tasks.json"] = io.digest(data)
        (self.project / ".agent/state.json").write_bytes(io.encode_json(state))
        with self.assertRaises(io.KitError):
            memory.load(self.project)


class KnowledgeAndCLITests(Environment):
    def test_retro_preserves_existing(self):
        self.init()
        target = memory.retro(self.project)
        before = target.read_bytes()
        with self.assertRaises(io.KitError):
            memory.retro(self.project)
        self.assertEqual(before, target.read_bytes())

    def test_knowledge_requires_approval_and_complete_source(self):
        source = self.base / "lesson.json"
        source.write_bytes(io.encode_json({"title": "经验", "conditions": "适用", "evidence": "实验", "limitations": "局限", "source_project": "测试项目", "lesson": "教训"}))
        with self.assertRaises(io.KitError):
            memory.knowledge_add(source, False, self.base / "knowledge")
        first = memory.knowledge_add(source, True, self.base / "knowledge")
        second = memory.knowledge_add(source, True, self.base / "knowledge")
        self.assertEqual(first, second)
        self.assertEqual(len(list(first.parent.glob("*.json"))), 1)

    def test_cli_end_to_end_other_cwd(self):
        result = self.cli("init-project", self.project, "--name", "研发项目", "--git-init")
        self.assertEqual(result.returncode, 0, result.stderr)
        source = self.base / "task.json"
        source.write_bytes(io.encode_json({"task_id": "T1", "title": "检查", "plan": "approved", "acceptance_criteria": ["检查通过"]}))
        self.assertEqual(self.cli("task", "add", self.project, "--file", source, "--expected-revision", 0, "--reason", "用户批准").returncode, 0)
        source.write_bytes(io.encode_json({"task_id": "T1", "status": "doing"}))
        self.assertEqual(self.cli("task", "update", self.project, "--file", source, "--expected-revision", 1, "--reason", "开始").returncode, 0)
        source.write_bytes(io.encode_json({"task_id": "T1", "status": "done", "evidence": [{"type": "command", "criterion": 1, "detail": "用户验证通过"}]}))
        self.assertEqual(self.cli("task", "update", self.project, "--file", source, "--expected-revision", 2, "--reason", "完成").returncode, 0)
        for args in [("status", self.project, "--rebuild"), ("snapshot", self.project), ("retro", self.project), ("install-global",), ("doctor", self.project), ("uninstall-global",)]:
            result = self.cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
