"""Observable schema-3 behavior; real processes, bytes and transaction failures."""
import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import kit
from core.atomic_io import KitError, encode_json, read_json
from core import atomic_io, history, memory, verification


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Anchor 150 中文 空格 ")
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        (self.project / "material").mkdir()
        (self.project / "material/input.txt").write_text("original", encoding="utf8")
        memory.init_project(self.project, "test150")

    def revision(self):
        return memory.load(self.project)[0]["revision"]

    def task(self, tid="T1"):
        return next(t for t in memory.load(self.project)[2]["tasks"] if t["task_id"] == tid)

    def change(self, action, payload):
        return memory.task_change(self.project, self.revision(), action, payload, "test", source="user")

    def add(self, tid="T1", kind="command", code="print('actual result')", **fields):
        check = {"criterion": 1, "kind": kind, "inputs": ["material"]}
        if kind == "command":
            check["argv"] = [sys.executable, "-c", code]
        self.change("add", {"deliverables": [], "task_id": tid, "title": tid, "acceptance_criteria": ["works"],
                            "checks": [check], **fields})
        self.change("approve", {"task_id": tid})
        return check

    def run_check(self, tid="T1"):
        return verification.run(self.project, self.revision(), tid, 1, "test")

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = kit.main([*map(str, args)])
        return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def test_command_receipt_completion_and_stale_inputs(self):
        self.add()
        self.change("update", {"task_id": "T1", "status": "doing"})
        with self.assertRaises(KitError):
            self.change("update", {"task_id": "T1", "status": "done"})
        result = self.run_check()
        self.assertEqual(result["result"], "pass")
        receipt = verification.show(self.project, result["run_id"])
        self.assertEqual(receipt["exit_code"], 0)
        self.assertTrue(all(receipt["logs_available"].values()))
        self.assertEqual(self.task()["evidence"][-1]["level"], "observed")
        self.change("update", {"task_id": "T1", "status": "done"})
        (self.project / "material/input.txt").write_text("changed")
        self.assertEqual(verification.state(self.project, self.task()), "stale")
        self.assertEqual(self.task()["status"], "done")

    def test_failure_never_satisfies_completion(self):
        self.add(code="raise SystemExit(7)")
        self.change("update", {"task_id": "T1", "status": "doing"})
        self.assertEqual(self.run_check()["result"], "fail")
        self.assertEqual(verification.state(self.project, self.task()), "failed")
        with self.assertRaises(KitError):
            self.change("update", {"task_id": "T1", "status": "done"})

    def test_review_is_self_claim_and_cannot_fake_observed(self):
        self.add(kind="review")
        payload = {"criterion": 1, "findings": "查Bug无新增问题", "resolution": "材料满足要求",
                   "simpler": "当前实现已足够简单", "result": "pass"}
        with self.assertRaises(KitError):
            verification.review(self.project, self.revision(), "T1", {**payload, "level": "observed"}, "test")
        verification.review(self.project, self.revision(), "T1", payload, "test")
        evidence = self.task()["evidence"][-1]
        self.assertEqual((evidence["level"], evidence["reviewer_kind"]), ("claimed", "self"))
        with self.assertRaises(KitError):
            self.run_check()

    def test_review_failure_then_fix_and_recheck(self):
        self.add(kind="review")
        payload = {"criterion": 1, "findings": "问题", "resolution": "未修复", "simpler": "可简化", "result": "fail"}
        verification.review(self.project, self.revision(), "T1", payload, "test")
        self.assertEqual(verification.state(self.project, self.task()), "failed")
        verification.review(self.project, self.revision(), "T1", {**payload, "resolution": "修复并检查", "result": "pass"}, "test")
        self.assertEqual(verification.state(self.project, self.task()), "pass")

    def test_direct_evidence_injection_rejected(self):
        self.add()
        with self.assertRaises(KitError):
            self.change("update", {"task_id": "T1", "evidence": [{"type": "test", "criterion": 1, "detail": "fake"}]})

    def test_checks_are_approved_scope_and_old_receipts_invalidated(self):
        check = self.add()
        self.run_check()
        changed = {**check, "argv": [sys.executable, "-c", "print('new')"]}
        with self.assertRaises(KitError):
            self.change("update", {"task_id": "T1", "checks": [changed]})
        self.change("revise", {"task_id": "T1"})
        self.change("update", {"task_id": "T1", "checks": [changed]})
        self.change("approve", {"task_id": "T1"})
        self.assertEqual(verification.state(self.project, self.task()), "pending")

    def test_empty_config_cannot_approve(self):
        self.change("add", {"deliverables": [], "task_id": "T1", "title": "t", "acceptance_criteria": ["criterion"]})
        with self.assertRaises(KitError):
            self.change("approve", {"task_id": "T1"})

    def test_focus_missing_does_not_guess(self):
        self.add()
        code, result, _ = self.cli("status", self.project, "--brief", "--focus")
        self.assertEqual(code, 0)
        self.assertIs(result["focus_missing"], True)
        self.assertEqual(result["tasks"], [])
        self.assertEqual(self.cli("status", self.project, "--focus", "--task", "T1")[0], 1)

    def test_focus_completed_tasks_and_external_dependencies_survive(self):
        self.add("DEP")
        self.change("update", {"task_id": "DEP", "status": "doing"})
        self.run_check("DEP")
        self.change("update", {"task_id": "DEP", "status": "done"})
        self.add(dependencies=["DEP"])
        self.change("update", {"task_id": "T1", "status": "doing"})
        self.run_check()
        self.change("update", {"task_id": "T1", "status": "done"})
        memory.focus_change(self.project, self.revision(), ["T1"], "本轮")
        code, result, _ = self.cli("status", self.project, "--brief", "--focus")
        self.assertEqual(code, 0)
        self.assertEqual(result["tasks"][0]["status"], "done")
        self.assertEqual(result["external_dependencies"][0]["task_id"], "DEP")
        before = self.revision()
        self.assertEqual(memory.focus_change(self.project, before, ["T1"], "本轮"), before)

    def test_stale_dependency_prevents_start(self):
        self.add("DEP")
        self.change("update", {"task_id": "DEP", "status": "doing"})
        self.run_check("DEP")
        self.change("update", {"task_id": "DEP", "status": "done"})
        self.add(dependencies=["DEP"])
        (self.project / "material/new.txt").write_text("new input")
        with self.assertRaises(KitError):
            self.change("update", {"task_id": "T1", "status": "doing"})

    def test_stale_transitive_dependency_prevents_downstream_start(self):
        self.add("A")
        self.change("update", {"task_id": "A", "status": "doing"})
        self.run_check("A")
        self.change("update", {"task_id": "A", "status": "done"})
        (self.project / "other.txt").write_text("unchanged")
        check = self.add("B", dependencies=["A"])
        self.change("revise", {"task_id": "B"})
        self.change("update", {"task_id": "B", "checks": [{**check, "inputs": ["other.txt"]}]})
        self.change("approve", {"task_id": "B"})
        self.change("update", {"task_id": "B", "status": "doing"})
        self.run_check("B")
        self.change("update", {"task_id": "B", "status": "done"})
        self.add(dependencies=["B"])
        (self.project / "material/input.txt").write_text("A has changed")
        self.assertEqual(verification.state(self.project, self.task("B")), "pass")
        with self.assertRaises(KitError):
            self.change("update", {"task_id": "T1", "status": "doing"})

    def test_output_limit_timeout_and_missing_executable(self):
        for tid, code, modify in [("OUTPUT", "print('x'*100000)", False),
                                   ("TIME", "import time;time.sleep(3)", True)]:
            check = self.add(tid, code=code)
            if modify:
                self.change("revise", {"task_id": tid})
                self.change("update", {"task_id": tid, "checks": [{**check, "timeout_seconds": 1}]})
                self.change("approve", {"task_id": tid})
            with patch("core.verification.OUTPUT_LIMIT", 1024):
                self.assertEqual(self.run_check(tid)["result"], "fail")
        self.add("SPAWN", checks=[{"criterion": 1, "kind": "command", "inputs": ["material"], "argv": ["missing-executable-150"]}])
        self.assertEqual(self.run_check("SPAWN")["result"], "fail")

    def test_input_changes_during_execution_preserve_unattached_receipt(self):
        self.add(code="from pathlib import Path;Path('material/input.txt').write_text('changed')")
        with self.assertRaisesRegex(KitError, "输入文件变化"):
            self.run_check()
        receipts = list((self.project / ".agent/evidence").glob("*.json"))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(read_json(receipts[0])["result"], "pass")
        self.assertEqual(self.task()["evidence"], [])

    def test_command_completed_before_attach_crash_is_not_rerun(self):
        self.add(code="from pathlib import Path;Path('count.txt').write_text('once')")
        with patch("core.memory._save", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_check()
        receipt = read_json(next((self.project / ".agent/evidence").glob("*.json")))
        self.assertEqual(receipt["result"], "pass")
        self.assertEqual(self.task()["evidence"], [])
        verification.show(self.project, receipt["run_id"])
        self.assertEqual((self.project / "count.txt").read_text(), "once")

    def test_revision_conflict_during_check_keeps_actual_result(self):
        self.add()
        original = verification._finish
        def concurrent(root, receipt):
            memory.focus_change(root, self.revision(), ["T1"], "并发更新")
            return original(root, receipt)
        with patch("core.verification._finish", side_effect=concurrent):
            with self.assertRaisesRegex(KitError, "修订冲突"):
                self.run_check()
        self.assertEqual(self.task()["evidence"], [])
        self.assertEqual(read_json(next((self.project / ".agent/evidence").glob("*.json")))["result"], "pass")

    def test_interrupted_start_retains_running_receipt_and_registered_argv(self):
        check = self.add()
        with patch("core.verification.subprocess.Popen", side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                self.run_check()
        receipt = read_json(next((self.project / ".agent/evidence").glob("*.json")))
        self.assertEqual(receipt["argv"], check["argv"])
        self.assertTrue(verification.show(self.project, receipt["run_id"])["incomplete"])
        self.assertEqual(self.task()["evidence"], [])

    def test_deleted_logs_are_reported_without_claiming_they_exist(self):
        self.add()
        value = self.run_check()
        for path in (self.project / ".agent/runtime/checks" / value["run_id"]).glob("*.log"):
            path.unlink()
        self.assertFalse(any(verification.show(self.project, value["run_id"])["logs_available"].values()))

    def test_receipt_tampering_does_not_validate(self):
        self.add()
        value = self.run_check()
        path = self.project / ".agent/evidence" / (value["run_id"] + ".json")
        receipt = read_json(path); receipt["exit_code"] = 99
        path.write_bytes(encode_json(receipt))
        self.assertEqual(verification.state(self.project, self.task()), "invalid")

    def test_archives_survive_without_git_or_snapshots(self):
        current = memory.load(self.project)[1]["CURRENT.md"]
        with patch("core.memory.HISTORY_KEEP", 5), patch("core.memory.DOC_CONTENT_KEEP", 1):
            for i in range(7):
                memory.doc_change(self.project, self.revision(), "CURRENT.md", current + f"\nmarker{i}", "断点", task_ids=[])
        entries = history.listing(self.project)
        originals = [entry for item in entries for entry in history.show(self.project, item["archive_id"])["entries"]]
        self.assertTrue(any("marker0" in e.get("content", "") for e in originals))
        self.assertFalse((self.project / ".git").exists())
        self.assertFalse((self.project / ".agent/runtime/snapshots").exists())

    def test_archive_failure_leaves_every_governance_byte_unchanged(self):
        current = memory.load(self.project)[1]["CURRENT.md"]
        memory.doc_change(self.project, self.revision(), "CURRENT.md", current + "\none", "断点", task_ids=[])
        before = {p.name: p.read_bytes() for p in (self.project / ".agent").iterdir() if p.is_file()}
        original = atomic_io.atomic_write
        def fail_archive(path, data):
            if Path(path).parent.name == "history":
                raise OSError("archive unavailable")
            return original(path, data)
        with patch("core.memory.DOC_CONTENT_KEEP", 1), patch("core.atomic_io.atomic_write", side_effect=fail_archive):
            with self.assertRaises(OSError):
                memory.doc_change(self.project, self.revision(), "CURRENT.md", current + "\ntwo", "断点", task_ids=[])
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.project / ".agent").iterdir() if p.is_file()})

    def test_unapproved_focus_does_not_approve(self):
        self.change("add", {"deliverables": [], "task_id": "T1", "title": "t", "acceptance_criteria": ["criterion"]})
        memory.focus_change(self.project, self.revision(), ["T1"], "明确本轮")
        with self.assertRaises(KitError):
            self.change("update", {"task_id": "T1", "status": "doing"})

    def test_cancellation_records_failure(self):
        self.add()
        with patch("core.verification.subprocess.Popen", side_effect=KeyboardInterrupt):
            result = self.run_check()
        self.assertEqual(result["result"], "fail")
        self.assertEqual(verification.state(self.project, self.task()), "failed")

    def test_inputs_reject_missing_empty_and_linked_material(self):
        (self.project / "empty").mkdir()
        for item in ("missing", "empty", ".", ".agent"):
            with self.subTest(item=item), self.assertRaises(KitError):
                verification.fingerprint(self.project, [item])
        link = self.project / "material/link"
        try:
            link.symlink_to(self.project / "material/input.txt")
        except OSError:
            return  # Windows without symlink permission: other input cases still run.
        with self.assertRaises(KitError):
            verification.fingerprint(self.project, ["material"])

    def test_rename_delete_and_unchanged_bytes_with_new_timestamp(self):
        self.add(); self.run_check()
        path = self.project / "material/input.txt"
        path.write_text("original", encoding="utf8")
        self.assertEqual(verification.state(self.project, self.task()), "pass")
        path.rename(path.with_name("renamed.txt"))
        self.assertEqual(verification.state(self.project, self.task()), "stale")

    def test_archive_crash_can_recover_without_overwriting_external_edits(self):
        current = memory.load(self.project)[1]["CURRENT.md"]
        memory.doc_change(self.project, self.revision(), "CURRENT.md", current + "\none", "one", task_ids=[])
        original = atomic_io.atomic_write
        def crash_archive(path, data):
            original(path, data)
            if Path(path).parent.name == "history":
                raise KeyboardInterrupt()
        with patch("core.memory.DOC_CONTENT_KEEP", 1), patch("core.atomic_io.atomic_write", side_effect=crash_archive):
            with self.assertRaises(KeyboardInterrupt):
                memory.doc_change(self.project, self.revision(), "CURRENT.md", current + "\ntwo", "two", task_ids=[])
        journal = self.project / ".agent/.transaction.json"
        self.assertTrue(journal.exists())
        atomic_io.recover(self.project, journal)
        memory.load(self.project)
        self.assertTrue(history.listing(self.project))


if __name__ == "__main__":
    unittest.main()
