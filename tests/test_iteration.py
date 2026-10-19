"""Compatibility and observable safety checks for the 1.3 daily workflows."""
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
from core.config import install
from core.hook_runtime import context
from core.memory import init_project, load, doc_change, task_change
from core.skill_install import inspect_skill, skill_payload
from core.tasks import task_view

ROOT = Path(__file__).resolve().parents[1]


class IterationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Anchor 迭代 中文 空格 ")
        self.root = Path(self.tmp.name)
        self.project = self.root / "项目"
        init_project(self.project, "迭代")

    def tearDown(self):
        self.tmp.cleanup()

    def fingerprint(self):
        return {p.name: p.read_bytes() for p in (self.project / ".agent").iterdir()
                if p.is_file() and p.name != ".lock"}

    def add(self, tid="T1", **fields):
        s, _, _ = load(self.project)
        plan = fields.pop("plan", "draft")
        revision = task_change(self.project, s["revision"], "add",
                               {"task_id": tid, "title": tid, "acceptance_criteria": ["输出5"], **fields}, "授权测试范围")
        if plan == "approved":
            s, _, _ = load(self.project)
            revision = task_change(self.project, s["revision"], "approve", {"task_id": tid},
                                   "测试批准", source="user")
        return revision

    def approve(self, tid="T1"):
        s, _, _ = load(self.project)
        return task_change(self.project, s["revision"], "approve", {"task_id": tid},
                           "测试批准", source="user")

    def update(self, tid="T1", **fields):
        s, _, _ = load(self.project)
        return task_change(self.project, s["revision"], "update", {"task_id": tid, **fields}, "测试更新")

    def cli(self, *args, payload=None):
        return subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "kit.py"), *map(str, args)],
                              input=payload, capture_output=True, encoding="utf8", timeout=20,
                              env=dict(os.environ, PYTHONUTF8="1"))

    def test_same_task_update_preserves_all_files_in_each_state(self):
        for status in ("todo", "doing", "blocked", "done"):
            with self.subTest(status=status):
                self.add(status, plan="approved")
                if status == "doing":
                    self.update(status, status="doing")
                elif status == "blocked":
                    self.update(status, status="blocked", blocker="缺少实机")
                elif status == "done":
                    self.update(status, status="doing")
                    self.update(status, status="done", evidence=[{"type": "manual", "criterion": 1, "detail": "用户确认输出5"}])
                s, _, ledger = load(self.project)
                task = next(t for t in ledger["tasks"] if t["task_id"] == status)
                before = self.fingerprint()
                fields = {k: v for k, v in task.items()
                          if k in {"task_id", "title", "description", "milestone", "status", "dependencies",
                                   "acceptance_criteria", "blocker"}}
                rev = task_change(self.project, s["revision"], "update", fields, "重复完整字段")
                self.assertEqual(rev, s["revision"])
                self.assertEqual(before, self.fingerprint())

    def test_actual_done_title_edit_keeps_completion_time(self):
        self.add(plan="approved")
        self.update(status="doing")
        self.update(status="done", evidence=[{"type": "manual", "criterion": 1, "detail": "确认"}])
        completed = load(self.project)[2]["tasks"][0]["completed_at"]
        old_revision = load(self.project)[0]["revision"]
        self.update(title="明确的修订标题")
        s, _, ledger = load(self.project)
        self.assertEqual(s["revision"], old_revision + 1)
        self.assertEqual(ledger["tasks"][0]["title"], "明确的修订标题")
        self.assertEqual(ledger["tasks"][0]["completed_at"], completed)
        before = self.fingerprint()
        with self.assertRaises(io.KitError):
            self.update(evidence=[{"type": "review", "criterion": 1, "detail": "改变证据"}])
        self.assertEqual(before, self.fingerprint())

    def test_stale_noop_and_invalid_fields_still_fail_without_writes(self):
        self.add()
        before = self.fingerprint()
        with self.assertRaisesRegex(io.KitError, "本次未写入"):
            task_change(self.project, 0, "update", {"task_id": "T1", "status": "todo"}, "旧修订")
        with self.assertRaises(io.KitError):
            self.update(unknown=None)
        with self.assertRaises(io.KitError):
            task_change(self.project, 1, "update", [], "错误输入")
        self.assertEqual(before, self.fingerprint())

    def test_cli_noop_exposes_changed_false(self):
        self.add()
        before = self.fingerprint()
        result = self.cli("task", "update", self.project, "--json-input", "--expected-revision", 1,
                          "--reason", "重复", payload=json.dumps({"task_id": "T1", "status": "todo"}))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"revision": 1, "changed": False})
        self.assertEqual(before, self.fingerprint())

    def test_equivalent_but_invalid_evidence_cannot_use_noop(self):
        self.add(plan="approved")
        self.update(status="doing")
        self.update(status="done", evidence=[{"type": "manual", "criterion": 1, "detail": "确认"}])
        before = self.fingerprint()
        for invalid in (True, 1.0):
            with self.subTest(criterion=invalid):
                with self.assertRaises(io.KitError):
                    self.update(evidence=[{"type": "manual", "criterion": invalid, "detail": "确认"}])
                self.assertEqual(before, self.fingerprint())

    def test_doc_repeat_preserves_bom_and_crlf(self):
        s, c, _ = load(self.project)
        path = self.project / ".agent/DECISIONS.md"
        data = b"\xef\xbb\xbf" + c["DECISIONS.md"].replace("\n", "\r\n").encode()
        path.write_bytes(data)
        rev = doc_change(self.project, s["revision"], "DECISIONS.md", c["DECISIONS.md"], "登记测试编码", adopt=True)
        before = self.fingerprint()
        self.assertEqual(doc_change(self.project, rev, "DECISIONS.md", c["DECISIONS.md"], "内容相同"), rev)
        self.assertEqual(before, self.fingerprint())
        self.assertEqual(path.read_bytes(), data)
        self.assertEqual(doc_change(self.project, rev, "DECISIONS.md", c["DECISIONS.md"], "重复登记", adopt=True), rev)

    def test_same_goal_first_approval_and_same_current_sync_are_changes(self):
        s, c, _ = load(self.project)
        goal_bytes = (self.project / ".agent/GOAL.md").read_bytes()
        rev = doc_change(self.project, 0, "GOAL.md", c["GOAL.md"], "用户批准测试目标", approved=True)
        self.assertEqual(rev, 1)
        self.assertTrue(load(self.project)[0]["goal_approved"])
        self.assertEqual(goal_bytes, (self.project / ".agent/GOAL.md").read_bytes())
        before = self.fingerprint()
        self.assertEqual(doc_change(self.project, rev, "GOAL.md", c["GOAL.md"], "重复批准", approved=True), rev)
        self.assertEqual(before, self.fingerprint())
        self.add()
        s, c, ledger = load(self.project)
        current_bytes = (self.project / ".agent/CURRENT.md").read_bytes()
        rev = doc_change(self.project, s["revision"], "CURRENT.md", c["CURRENT.md"], "同步任务修订")
        self.assertEqual(rev, s["revision"] + 1)
        self.assertEqual(load(self.project)[0]["current_task_revision"], ledger["revision"])
        self.assertEqual(current_bytes, (self.project / ".agent/CURRENT.md").read_bytes())
        before = self.fingerprint()
        self.assertEqual(doc_change(self.project, rev, "CURRENT.md", c["CURRENT.md"], "重复同步"), rev)
        self.assertEqual(before, self.fingerprint())

    def test_same_goal_without_approval_is_not_accepted(self):
        s, c, _ = load(self.project)
        before = self.fingerprint()
        with self.assertRaises(io.KitError):
            doc_change(self.project, s["revision"], "GOAL.md", c["GOAL.md"], "未授权")
        self.assertEqual(before, self.fingerprint())

    def test_legacy_status_and_brief_filters_are_read_only(self):
        self.add(plan="approved", milestone="本轮")
        self.add("DRAFT", milestone="草案")
        s, c, _ = load(self.project)
        before = self.fingerprint()
        legacy = self.cli("status", self.project)
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        old = json.loads(legacy.stdout)
        self.assertEqual(set(old), {"project", "name", "revision", "goal_version", "goal_approved", "current_stale",
                                    "task_revision", "task_schema", "tasks", "goal", "current", "git"})
        result = self.cli("status", self.project, "--brief", "--milestone", "本轮", "--task", "T1")
        self.assertEqual(result.returncode, 0, result.stderr)
        view = json.loads(result.stdout)
        self.assertEqual(view["goal"], c["GOAL.md"])
        self.assertEqual(view["current"], c["CURRENT.md"])
        self.assertEqual([t["task_id"] for t in view["tasks"]], ["T1"])
        self.assertNotIn("evidence", view["tasks"][0])
        self.assertEqual(view["summary"]["approved_active"], 1)
        self.assertEqual(before, self.fingerprint())

    def test_selected_external_dependency_is_visible(self):
        self.add(plan="approved", milestone="旧轮")
        self.update(status="blocked", blocker="缺硬件")
        self.add("T2", plan="approved", milestone="本轮", dependencies=["T1"])
        visible, summary, external = task_view(load(self.project)[2], True, ["T2"])
        self.assertEqual([t["task_id"] for t in visible], ["T2"])
        self.assertEqual(external[0]["status"], "blocked")
        self.assertEqual(external[0]["blocker"], "缺硬件")
        self.assertEqual(summary["total"], 1)

    def test_summary_does_not_count_drafts_or_cancellations_as_approved_active(self):
        self.add()
        self.add("CANCELLED", plan="approved")
        self.update("CANCELLED", status="cancelled")
        self.add("DONE", plan="approved")
        self.update("DONE", status="doing")
        self.update("DONE", status="done", evidence=[{"type": "manual", "criterion": 1, "detail": "确认"}])
        _, summary, _ = task_view(load(self.project)[2], True)
        self.assertEqual((summary["draft"], summary["approved_active"], summary["approved_done"]), (1, 1, 1))

    def test_unknown_selection_fails_without_writes(self):
        self.add(milestone="旧轮")
        self.add("T2", milestone="本轮")
        before = self.fingerprint()
        for args in (("--task", "missing"), ("--milestone", "missing"), ("--task", "T1", "--milestone", "本轮")):
            with self.subTest(args=args):
                result = self.cli("status", self.project, "--brief", *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(before, self.fingerprint())

    def test_pending_transaction_is_not_bypassed_by_noop(self):
        self.add()
        journal = self.project / ".agent/.transaction.json"
        journal.write_bytes(io.encode_json({"schema": 1, "entries": []}))
        before = self.fingerprint()
        with self.assertRaises(io.KitError):
            self.update(status="todo")
        self.assertEqual(before, self.fingerprint())

    def test_filtered_rebuild_is_rejected_before_any_write(self):
        self.add(milestone="本轮")
        view = self.project / ".agent/PROGRESS.md"
        view.write_bytes(b"stale view; do not repair on a failed query")
        before = self.fingerprint()
        result = self.cli("status", self.project, "--rebuild", "--task", "T1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.fingerprint())

    def test_actual_write_failure_still_rolls_back(self):
        self.add()
        original = io.atomic_write
        def fail(path, data):
            if Path(path).name == "PROGRESS.md":
                raise OSError("测试事务失败")
            return original(path, data)
        self.approve()
        before = self.fingerprint()
        with patch("core.atomic_io.atomic_write", side_effect=fail):
            with self.assertRaises(OSError):
                self.update(status="doing")
        self.assertEqual(before, self.fingerprint())

    def test_local_task_can_be_approved_with_unapproved_project_goal(self):
        self.add(plan="approved", description="用户单独批准验证输出5")
        self.update(status="doing")
        s, _, ledger = load(self.project)
        self.assertFalse(s["goal_approved"])
        self.assertEqual(ledger["tasks"][0]["status"], "doing")
        reminder = context(self.project, self.root / "未安装")
        self.assertIn("已明确授权的局部任务", reminder)

    def test_doctor_distinguishes_template_updates_from_modified_install_files(self):
        home, parent = self.root / "客户端", self.root / "skills"
        install(home, parent)
        manifest = io.read_json(home / "codex-rules/install.json")
        baseline = skill_payload(home)
        changed = copy.deepcopy(baseline)
        changed["references/CLIENTS.md"] += b"\nTemplate update\n"
        with patch("core.skill_install.skill_payload", return_value=changed):
            checks = {name: (status, detail) for status, name, detail in inspect_skill(home, manifest)}
        self.assertEqual(checks["Skill 安装完整性"][0], "PASS")
        self.assertEqual(checks["Skill 模板版本"][0], "WARN")
        self.assertIn("references/CLIENTS.md", checks["Skill 模板版本"][1])
        (parent / "project-anchor/SKILL.md").write_bytes(b"User edit\n")
        checks = {name: (status, detail) for status, name, detail in inspect_skill(home, manifest)}
        self.assertEqual(checks["Skill 安装完整性"][0], "FAIL")
        self.assertIn("SKILL.md", checks["Skill 安装完整性"][1])
        with self.assertRaises(io.KitError):
            install(home, parent)


if __name__ == "__main__":
    unittest.main()
