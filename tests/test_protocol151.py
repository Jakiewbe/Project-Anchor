"""1.5.1 observable contracts: readonly, scope, artifacts and migration."""
import copy
import contextlib
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import kit
from core import atomic_io, memory, tasks, verification
from core.hook_runtime import context
from core.diagnostics import _project_checks
from tests.test_migration import old_archive


class Protocol151Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Anchor151 中文 ")
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve() / "project"
        memory.init_project(self.project, "test151")
        (self.project / "src").mkdir()
        (self.project / "src/input.txt").write_text("input", encoding="utf8")

    def revision(self):
        return memory.load(self.project)[0]["revision"]

    def change(self, action, payload):
        return memory.task_change(self.project, self.revision(), action, payload, "test151", source="user")

    def task(self, tid="T1"):
        return next(t for t in memory.load(self.project)[2]["tasks"] if t["task_id"] == tid)

    def add(self, tid="T1", inputs=None, deliverables=None, **fields):
        inputs = inputs or ["src/input.txt"]
        value = {"task_id": tid, "title": tid, "acceptance_criteria": ["actual result"],
                 "deliverables": [] if deliverables is None else deliverables,
                 "checks": [{"criterion": 1, "kind": "command", "inputs": inputs,
                             "argv": [sys.executable, "-B", "-c", "print('pass')"]}], **fields}
        self.change("add", value)
        self.change("approve", {"task_id": tid})

    def finish(self, tid="T1"):
        self.change("update", {"task_id": tid, "status": "doing"})
        r = verification.run(self.project, self.revision(), tid, 1, "run")
        self.change("update", {"task_id": tid, "status": "done"})
        return r

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = kit.main([*map(str, args)])
        return code, json.loads(stdout.getvalue()) if stdout.getvalue() else None, stderr.getvalue()

    def snapshot(self):
        return {p.relative_to(self.project).as_posix(): p.read_bytes()
                for p in self.project.rglob("*") if p.is_file()}

    def test_read_queries_never_attempt_project_writes(self):
        self.add()
        run = self.finish()
        (self.project / ".agent/.lock").unlink()
        before = self.snapshot()
        real_open = Path.open
        def readonly(path, mode="r", *args, **kwargs):
            if path.is_relative_to(self.project) and any(c in mode for c in "wax+"):
                raise PermissionError("project is readonly")
            return real_open(path, mode, *args, **kwargs)
        with patch.object(Path, "open", readonly), patch.object(Path, "mkdir", side_effect=PermissionError("readonly")):
            self.assertEqual(self.cli("status", self.project, "--brief")[0], 0)
            self.assertIn("Project Anchor", context(self.project, self.project.parent / "home"))
            self.assertEqual(verification.show(self.project, run["run_id"])["result"], "pass")
            rows = []
            _project_checks(lambda *r: rows.append(r), self.project)
            self.assertFalse([r for r in rows if r[0] == "FAIL"], rows)
        self.assertEqual(before, self.snapshot())

    def test_pending_transaction_rejects_every_read(self):
        self.add()
        run = self.finish()
        (self.project / ".agent/.transaction.json").write_text("{}")
        self.assertNotEqual(self.cli("status", self.project)[0], 0)
        for call in [lambda: context(self.project, self.project.parent),
                     lambda: verification.show(self.project, run["run_id"])]:
            with self.assertRaises(atomic_io.KitError):
                call()
        rows = []
        _project_checks(lambda *r: rows.append(r), self.project)
        self.assertTrue(any(r[0] == "FAIL" for r in rows))

    def test_cli_without_B_never_creates_bytecode_in_target_source_tree(self):
        shutil.copytree(Path(kit.__file__).parent / "core", self.project / "core", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(kit.__file__, self.project / "kit.py")
        before = self.snapshot()
        env = dict(os.environ)
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        result = subprocess.run([sys.executable, str(self.project / "kit.py"), "status", str(self.project)],
                                capture_output=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(list(self.project.rglob("__pycache__")))

    def test_source_package_filters_runtime_auth_and_business_records(self):
        from tests.prepare_release151 import allowed
        for name in [".agent/state.json", ".agent/runtime/native-events.json", "docs/runtime/raw.txt",
                     "packages/node_modules/auth.json", "core/.env", "docs/raw.ndax", "docs/key.pem", "auth.json"]:
            self.assertFalse(allowed(name), name)
        for name in ["kit.py", "core/tasks.py", "docs/RELEASE_1_5_1.md", "packages/dsh/tools.js"]:
            self.assertTrue(allowed(name), name)

    def test_concurrent_committed_change_invalidates_status(self):
        original = memory.git_info
        def change(root):
            memory.focus_change(root, self.revision(), None, "concurrent")
            state, content, _ = memory.load(root)
            memory.doc_change(root, state["revision"], "DECISIONS.md", content["DECISIONS.md"] + "\nchange", "concurrent")
            return original(root)
        with patch("kit.git_info", side_effect=change):
            code, value, error = self.cli("status", self.project)
        self.assertEqual(code, 1)
        self.assertIsNone(value)
        self.assertIn("读取期间", error)

    def test_unregistered_document_edit_during_read_rejected(self):
        def change(root):
            with (root / ".agent/CURRENT.md").open("a", encoding="utf8") as f:
                f.write("\nunregistered")
            return {}
        with patch("kit.git_info", side_effect=change):
            self.assertEqual(self.cli("status", self.project)[0], 1)

    def test_current_binding_unknown_aligned_changed_and_explicit_empty(self):
        initial = self.cli("status", self.project)[1]
        self.assertFalse(initial["current_stale"])
        self.assertEqual(initial["current_alignment"], "unknown")
        self.add()
        state, content, _ = memory.load(self.project)
        self.assertEqual(memory.current_alignment(state), "unknown")
        with self.assertRaises(atomic_io.KitError):
            memory.doc_change(self.project, self.revision(), "CURRENT.md", content["CURRENT.md"], "missing")
        memory.focus_change(self.project, self.revision(), ["T1"], "scope")
        memory.doc_change(self.project, self.revision(), "CURRENT.md", content["CURRENT.md"], "bind", task_ids=["T1"])
        self.assertEqual(self.cli("status", self.project)[1]["current_alignment"], "aligned")
        memory.focus_change(self.project, self.revision(), None, "idle")
        self.assertEqual(self.cli("status", self.project)[1]["current_alignment"], "changed")
        memory.doc_change(self.project, self.revision(), "CURRENT.md", content["CURRENT.md"], "idle", task_ids=[])
        self.assertEqual(self.cli("status", self.project)[1]["current_alignment"], "aligned")

    def test_current_binding_goal_and_task_changes(self):
        self.add()
        memory.focus_change(self.project, self.revision(), ["T1"], "scope")
        state, content, _ = memory.load(self.project)
        memory.doc_change(self.project, self.revision(), "CURRENT.md", content["CURRENT.md"], "bind", task_ids=["T1"])
        memory.doc_change(self.project, self.revision(), "GOAL.md", content["GOAL.md"], "approve", approved=True)
        self.assertEqual(self.cli("status", self.project)[1]["current_alignment"], "changed")
        memory.doc_change(self.project, self.revision(), "CURRENT.md", content["CURRENT.md"], "bind", task_ids=["T1"])
        self.change("update", {"task_id": "T1", "title": "changed"})
        self.assertEqual(self.cli("status", self.project)[1]["current_alignment"], "changed")

    def test_no_task_cli_and_bad_association(self):
        current = self.project.parent / "current.md"
        current.write_text(memory.load(self.project)[1]["CURRENT.md"], encoding="utf8")
        code, _, _ = self.cli("state", "update", self.project, "CURRENT.md", "--file", current,
                             "--no-task", "--expected-revision", self.revision(), "--reason", "idle")
        self.assertEqual(code, 0)
        with self.assertRaises(atomic_io.KitError):
            memory.doc_change(self.project, self.revision(), "CURRENT.md", current.read_text(encoding="utf8"), "bad", task_ids=["missing"])

    def test_uncovered_theme_and_new_template_cannot_be_approved(self):
        self.change("add", {"task_id": "T1", "title": "shared style", "acceptance_criteria": ["real artifacts"],
                    "deliverables": ["catalog/shared-library/theme.json", "templates/shared/xy"],
                    "checks": [{"criterion": 1, "kind": "review", "inputs": ["src"]}]})
        with self.assertRaisesRegex(atomic_io.KitError, "未被"):
            self.change("approve", {"task_id": "T1"})

    def test_missing_deliverables_and_unknown_declaration(self):
        self.change("add", {"task_id": "T1", "title": "old", "acceptance_criteria": ["check"],
                            "checks": [{"criterion": 1, "kind": "review", "inputs": ["src"]}]})
        with self.assertRaisesRegex(atomic_io.KitError, "显式声明"):
            self.change("approve", {"task_id": "T1"})
        self.assertEqual(tasks.deliverable_coverage(self.task()), "undeclared")

    def test_declared_file_missing_cannot_check_or_finish(self):
        self.add(deliverables=["src/output.txt"], inputs=["src"])
        with self.assertRaisesRegex(atomic_io.KitError, "交付物不存在"):
            verification.run(self.project, self.revision(), "T1", 1, "missing")

    def test_artifact_removed_by_command_cannot_attach_pass_receipt(self):
        (self.project / "src/empty").mkdir()
        self.add(deliverables=["src/empty"], checks=[{"criterion": 1, "kind": "command", "inputs": ["src"],
            "argv": [sys.executable, "-B", "-c", "from pathlib import Path;Path('src/empty').rmdir()"]}])
        with self.assertRaisesRegex(atomic_io.KitError, "交付物消失"):
            verification.run(self.project, self.revision(), "T1", 1, "remove")
        self.assertEqual(self.task()["evidence"], [])

    @unittest.skipUnless(os.name == "nt", "Windows ACL check")
    def test_actual_readonly_acl_and_query_without_lock_file(self):
        self.add()
        run = self.finish()
        (self.project / ".agent/.lock").unlink()
        before = self.snapshot()
        sid_result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, check=True, text=True)
        import csv
        sid = next(csv.reader([sid_result.stdout.strip()]))[1]
        # Deny write-specific rights, not generic W's shared access-control bits.
        denied = subprocess.run(["icacls", str(self.project), "/deny", f"*{sid}:(OI)(CI)(WD,AD,WEA,WA)"], capture_output=True)
        self.assertEqual(denied.returncode, 0, denied.stderr)
        try:
            with self.assertRaises(PermissionError):
                (self.project / "write-probe.txt").write_text("must fail")
            for args in [["status", str(self.project)], ["context", str(self.project), "--codex-home", str(self.project.parent / "home")],
                         ["verify", "show", str(self.project), "--run-id", run["run_id"]],
                         ["doctor", str(self.project), "--client", "agents", "--client-home", str(self.project.parent / "home"), "--json"]]:
                result = subprocess.run([sys.executable, "-B", str(Path(kit.__file__)), *args], capture_output=True)
                if args[0] != "doctor":
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    rows = json.loads(result.stdout)
                    self.assertTrue(any(r["check"] == "项目状态完整性" and r["status"] == "PASS" for r in rows))
        finally:
            restored = subprocess.run(["icacls", str(self.project), "/remove:d", "*" + sid], capture_output=True)
            self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(before, self.snapshot())

    def test_bound_artifact_changes_stale_but_unrelated_file_does_not(self):
        self.add(deliverables=["src/input.txt"])
        self.finish()
        (self.project / "unrelated.txt").write_text("new")
        self.assertEqual(verification.state(self.project, self.task()), "pass")
        (self.project / "src/input.txt").write_text("changed")
        self.assertEqual(verification.state(self.project, self.task()), "stale")
        self.assertEqual(self.task()["status"], "done")

    def test_deliverable_scope_change_requires_revision_and_new_approval(self):
        self.add()
        with self.assertRaises(atomic_io.KitError):
            self.change("update", {"task_id": "T1", "deliverables": ["src/input.txt"]})
        self.change("revise", {"task_id": "T1"})
        self.change("update", {"task_id": "T1", "deliverables": ["src/input.txt"]})
        self.change("approve", {"task_id": "T1"})
        self.assertEqual(self.task()["approved_scope"]["deliverables"], ["src/input.txt"])

    def test_focus_only_fingerprints_selected_and_transitive_dependencies(self):
        for tid, deps in [("A", []), ("B", ["A"]), ("C", ["B"]), ("UNRELATED", [])]:
            (self.project / f"src/{tid}.txt").write_text(tid)
            self.add(tid, inputs=[f"src/{tid}.txt"], dependencies=deps)
            self.finish(tid)
        memory.focus_change(self.project, self.revision(), ["C"], "scope")
        seen = []
        original = verification.fingerprint
        def record(root, inputs, cache=None):
            seen.extend(inputs)
            return original(root, inputs, cache)
        with patch("core.verification.fingerprint", side_effect=record):
            code, value, _ = self.cli("status", self.project, "--focus")
        self.assertEqual(code, 0)
        self.assertEqual(set(seen), {"src/A.txt", "src/B.txt", "src/C.txt"})
        self.assertEqual(value["dependency_verification"], {"A": "pass", "B": "pass"})
        (self.project / "src/A.txt").write_text("stale")
        self.assertEqual(self.cli("status", self.project, "--focus")[1]["dependency_verification"]["A"], "stale")

    def test_query_caches_overlapping_files_only_inside_query(self):
        self.add()
        self.finish()
        self.add("T2")
        self.finish("T2")
        original = Path.read_bytes
        seen = []
        def record(path):
            if path == self.project / "src/input.txt":
                seen.append(path)
            return original(path)
        with patch.object(Path, "read_bytes", record):
            self.assertEqual(self.cli("status", self.project)[0], 0)
        self.assertEqual(len(seen), 1)

    def test_check_summary_keeps_self_review_separate_from_command_failure(self):
        self.add(checks=[{"criterion": 1, "kind": "review", "inputs": ["src"]}])
        verification.review(self.project, self.revision(), "T1", {"criterion": 1, "result": "pass",
            "findings": "render not accepted", "resolution": "only data accepted", "simpler": "one template"}, "scope")
        value = self.cli("status", self.project)[1]["tasks"][0]
        self.assertEqual(value["check_summary"][0]["level"], "claimed/self")
        self.assertEqual(value["deliverable_coverage"], "covered")

    def test_retro_has_indexes_not_evidence_dump_or_goal_copy(self):
        self.add()
        self.finish()
        body = memory.retro(self.project).read_text(encoding="utf8")
        self.assertIn("GOAL.md", body)
        self.assertIn("evidence/", body)
        self.assertNotIn('"input_hash"', body)
        self.assertNotIn("待用户确认：填写一句话目标", body)
        with self.assertRaises(atomic_io.KitError):
            memory.retro(self.project)

    def test_schema3_migration_preserves_real_receipts_and_old_writer_refuses4(self):
        old = old_archive(self.project.parent / "schema3", "090efe2cd70ac3dc9f32cd9b8536b51cfacc14e7")
        script = """from pathlib import Path
from core import memory,verification
import sys
p=Path(sys.argv[1]);memory.init_project(p,'schema3');(p/'in.txt').write_text('input')
def change(a,v): memory.task_change(p,memory.load(p)[0]['revision'],a,v,'old',source='user')
change('add',{'task_id':'OLD','title':'old','acceptance_criteria':['real'], 'checks':[{'criterion':1,'kind':'command','inputs':['in.txt'],'argv':[sys.executable,'-B','-c','print(5)']}]})
change('approve',{'task_id':'OLD'});change('update',{'task_id':'OLD','status':'doing'})
verification.run(p,memory.load(p)[0]['revision'],'OLD',1,'old');change('update',{'task_id':'OLD','status':'done'})
"""
        project = self.project.parent / "old project"
        p = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", script, str(project)], cwd=old, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        before = memory.load(project)[2]["tasks"]
        receipt = next((project / ".agent/evidence").glob("*.json"))
        receipt_bytes = receipt.read_bytes()
        revision = memory.load(project)[0]["revision"]
        memory.migrate(project, revision, "dry", dry_run=True)
        self.assertEqual(memory.load(project)[2]["schema"], 3)
        result = memory.migrate(project, revision, "upgrade")
        after = memory.load(project)[2]["tasks"]
        self.assertEqual(before, after)
        self.assertEqual(receipt.read_bytes(), receipt_bytes)
        self.assertEqual(verification.state(project, after[0]), "pass")
        self.assertEqual(tasks.deliverable_coverage(after[0]), "undeclared")
        with self.assertRaises(atomic_io.KitError):
            verification.require_fresh(project, after[0])
        p = subprocess.run([sys.executable, "-B", str(old / "kit.py"), "status", str(project)], capture_output=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse(memory.migrate(project, memory.load(project)[0]["revision"], "again")["changed"])
        memory.migration_rollback(project, memory.load(project)[0]["revision"], "rollback", result["backup"])
        self.assertEqual(memory.load(project)[2]["schema"], 3)


if __name__ == "__main__":
    unittest.main()
