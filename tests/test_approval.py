"""Schema 2 approval invariants.

These tests intentionally exercise the bypasses that schema 1 allowed:
self-approval, scope weakening, dependency removal, and reusing evidence after
the acceptance criteria changed.
"""
import copy
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
from tests.helpers150 import checks_for, review_all

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
        fields.setdefault("checks", checks_for(self.project, criteria))
        return task_change(self.project, state["revision"], "add",
                           {"task_id": "T1", "title": "任务", "description": "原始范围",
                            "acceptance_criteria": list(criteria), **fields}, "创建草案")

    def approve(self, source="user"):
        state, _, _ = load(self.project)
        return task_change(self.project, state["revision"], "approve", {"task_id": "T1"},
                           "用户批准", source=source)

    def update(self, tid="T1", **fields):
        if "acceptance_criteria" in fields:
            fields["checks"] = checks_for(self.project, fields["acceptance_criteria"])
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

    def test_shrink_criteria_preserves_invalidated_evidence(self):
        self.add(criteria=("a", "b"))
        self.approve()
        self.update(status="doing")
        review_all(self.project, "T1")
        self.update(status="done")
        self.revise()
        historical = self.task()["evidence"]
        self.update(acceptance_criteria=["new a"])
        self.assertEqual(self.task()["evidence"], historical)
        self.approve()
        self.update(status="doing")
        with self.assertRaises(io.KitError):
            self.update(status="done")
        review_all(self.project, "T1")
        self.update(status="done")
        task = self.task()
        self.assertEqual(task["evidence"][:2], historical)
        self.assertEqual(task["approved_scope"]["version"], 2)
        self.assertEqual(task["status"], "done")

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
                     "dependencies": ["T1"], "checks": checks_for(self.project, ["完成"])}, "创建依赖")
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
        review_all(self.project, "T1")
        self.update(status="done")
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
        review_all(self.project, "T1")
        self.update(status="done")
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

    def test_reapproval_preserves_each_approval_snapshot_in_history(self):
        self.add()
        self.approve(source="user")
        first = copy.deepcopy(self.task()["approved_scope"])
        self.revise()
        self.update(description="修订范围", acceptance_criteria=["新标准"])
        self.approve(source="policy")
        ledger = load(self.project)[2]
        approvals = [item for item in ledger["history"] if item["action"] == "approve"]
        self.assertEqual(approvals[0]["approved_scope"], first)
        self.assertEqual(approvals[1]["approved_scope"], self.task()["approved_scope"])
        self.assertEqual(approvals[0]["approved_scope"]["source"], "user")
        self.assertEqual(approvals[1]["approved_scope"]["source"], "policy")

    def test_revise_archives_existing_snapshot_without_rewriting_old_history(self):
        self.add()
        self.approve()
        state, _, ledger = load(self.project)
        # Model an existing 1.4.0 approval, whose history did not store the scope.
        for item in ledger["history"]:
            item.pop("approved_scope", None)
        from core.tasks import mutate
        original = copy.deepcopy(ledger["history"])
        scope = copy.deepcopy(ledger["tasks"][0]["approved_scope"])
        revised = mutate(ledger, "revise", {"task_id": "T1"}, "修改范围")
        self.assertEqual(revised["history"][:-1], original)
        self.assertEqual(revised["history"][-1]["approved_scope"], scope)

    def test_empty_evidence_is_no_change_and_non_array_is_rejected(self):
        self.add()
        self.approve()
        before = {p.name: p.read_bytes() for p in (self.project / ".agent").iterdir()
                  if p.is_file() and p.name != ".lock"}
        self.update(evidence=[])
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.project / ".agent").iterdir()
                                 if p.is_file() and p.name != ".lock"})
        for value in ({}, "", None):
            with self.subTest(value=value), self.assertRaises(io.KitError):
                self.update(evidence=value)


if __name__ == "__main__":
    unittest.main()
