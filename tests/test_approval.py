"""Schema 2 approval invariants.

These tests intentionally exercise the bypasses that schema 1 allowed:
self-approval, scope weakening, dependency removal, and reusing evidence after
the acceptance criteria changed.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core import atomic_io as io
from core.memory import init_project, load, task_change
from core.tasks import criterion_hash

ROOT = Path(__file__).resolve().parents[1]


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Anchor 审批 中文 ")
        self.root = Path(self.tmp.name)
        self.project = self.root / "项目"
        init_project(self.project, "审批")

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, criteria=("完成",), **fields):
        state, _, _ = load(self.project)
        return task_change(self.project, state["revision"], "add",
                           {"task_id": "T1", "title": "任务", "description": "原始范围",
                            "acceptance_criteria": list(criteria), **fields}, "创建草案")

    def approve(self, source="user"):
        state, _, _ = load(self.project)
        return task_change(self.project, state["revision"], "approve", {"task_id": "T1"},
                           "用户批准", source=source)

    def update(self, tid="T1", **fields):
        state, _, _ = load(self.project)
        return task_change(self.project, state["revision"], "update", {"task_id": tid, **fields}, "更新")

    def revise(self):
        state, _, _ = load(self.project)
        return task_change(self.project, state["revision"], "revise", {"task_id": "T1"}, "修订")

    def task(self):
        return load(self.project)[2]["tasks"][0]

    def test_add_cannot_create_approved_task(self):
        state, _, _ = load(self.project)
        with self.assertRaises(io.KitError):
            task_change(self.project, state["revision"], "add",
                        {"task_id": "T1", "title": "任务", "acceptance_criteria": ["完成"],
                         "plan": "approved"}, "自批")
        self.assertEqual(load(self.project)[2]["tasks"], [])

    def test_update_cannot_set_plan_or_internal_fields(self):
        self.add()
        for payload in ({"plan": "approved"}, {"approved_scope": {}},
                        {"legacy_unverified": False}):
            with self.subTest(payload=payload):
                with self.assertRaises(io.KitError):
                    self.update(**payload)
        self.assertEqual(self.task()["plan"], "draft")

    def test_approve_records_scope_and_blocks_scope_edits(self):
        self.add(criteria=("a", "b"))
        self.approve()
        task = self.task()
        self.assertEqual(task["plan"], "approved")
        self.assertEqual(task["approved_scope"]["version"], 1)
        self.assertEqual(task["approved_scope"]["description"], "原始范围")
        self.assertEqual(task["approved_scope"]["acceptance_criteria"], ["a", "b"])
        for field, value in (("description", "扩大范围"), ("acceptance_criteria", ["a"])):
            with self.subTest(field=field):
                with self.assertRaises(io.KitError):
                    self.update(**{field: value})
        self.update(title="只改展示标题")
        self.assertEqual(self.task()["title"], "只改展示标题")

    def test_one_call_scope_and_done_fails(self):
        self.add()
        self.approve()
        self.update(status="doing")
        with self.assertRaises(io.KitError):
            self.update(status="done", acceptance_criteria=["trivial"],
                        evidence=[{"type": "test", "criterion": 1, "detail": "假的通过"}])
        self.assertEqual(self.task()["status"], "doing")

    def test_one_call_dependency_removal_and_doing_fails(self):
        self.add()
        self.approve()
        state, _, _ = load(self.project)
        task_change(self.project, state["revision"], "add",
                    {"task_id": "T2", "title": "依赖任务", "acceptance_criteria": ["完成"],
                     "dependencies": ["T1"]}, "创建依赖")
        state, _, _ = load(self.project)
        task_change(self.project, state["revision"], "approve", {"task_id": "T2"},
                    "批准", source="user")
        with self.assertRaises(io.KitError):
            self.update("T2", status="doing", dependencies=[])
        self.assertEqual(load(self.project)[2]["tasks"][1]["status"], "todo")

    def test_revise_reapprove_bumps_version_and_invalidates_evidence(self):
        self.add(criteria=("a",))
        self.approve()
        self.update(status="doing")
        self.update(status="done", evidence=[{"type": "manual", "criterion": 1, "detail": "第一次通过"}])
        first = self.task()["evidence"][0]
        self.assertEqual(first["scope_version"], 1)
        self.assertEqual(first["criteria_hash"], criterion_hash("a"))

        self.revise()
        task = self.task()
        self.assertEqual((task["plan"], task["status"]), ("draft", "todo"))
        self.assertTrue(task["evidence"][0].get("invalidated_at"))
        self.update(acceptance_criteria=["b"])
        self.approve()
        task = self.task()
        self.assertEqual(task["approved_scope"]["version"], 2)
        self.assertEqual(task["plan"], "approved")
        self.update(status="doing")
        with self.assertRaises(io.KitError):
            self.update(status="done")
        self.update(status="done", evidence=[{"type": "manual", "criterion": 1, "detail": "第二次通过"}])
        task = self.task()
        self.assertEqual(task["status"], "done")
        self.assertEqual(len(task["evidence"]), 2)
        self.assertTrue(task["evidence"][0]["invalidated_at"])
        self.assertEqual(task["evidence"][1]["scope_version"], 2)
        self.assertEqual(task["evidence"][1]["criteria_hash"], criterion_hash("b"))

    def test_evidence_internal_fields_are_rejected(self):
        self.add()
        self.approve()
        self.update(status="doing")
        with self.assertRaises(io.KitError):
            self.update(status="done", evidence=[{"type": "test", "criterion": 1,
                                                  "detail": "假的", "level": "observed"}])
        self.assertEqual(self.task()["status"], "doing")

    def test_approve_requires_source_and_cli_reports_changed(self):
        self.add()
        state, _, _ = load(self.project)
        with self.assertRaises(io.KitError):
            task_change(self.project, state["revision"], "approve", {"task_id": "T1"}, "无来源")
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "kit.py"), "task", "approve", str(self.project),
             "--task-id", "T1", "--expected-revision", str(state["revision"]), "--reason", "批准",
             "--source", "user"], capture_output=True, encoding="utf-8",
            env=dict(os.environ, PYTHONUTF8="1"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["changed"])
        self.assertEqual(self.task()["plan"], "approved")

    def test_revise_requires_approved_task(self):
        self.add()
        with self.assertRaises(io.KitError):
            self.revise()


if __name__ == "__main__":
    unittest.main()
