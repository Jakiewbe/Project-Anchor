"""Schema 1/2 -> 3 migration and old-writer refusal tests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from core import atomic_io as io
from core import memory
from core.tasks import criterion_hash
from tests.helpers150 import checks_for

ROOT = Path(__file__).resolve().parents[1]
OLD_COMMIT = "bc72aca100f5f4e5de7638b75de57085c9a1c7d0"


def old_archive(destination, commit=OLD_COMMIT):
    destination.mkdir(parents=True, exist_ok=True)
    exists = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", commit],
                            capture_output=True)
    if exists.returncode:
        if os.environ.get("CI"):
            raise AssertionError("CI 缺少旧版兼容提交；必须检出完整历史")
        raise unittest.SkipTest("old commit not available in this clone")
    data = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=zip", commit],
                          capture_output=True, check=True).stdout
    archive = destination / "old.zip"
    archive.write_bytes(data)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination / "old")
    return destination / "old"


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Anchor 迁移 中文 ")
        self.root = Path(self.tmp.name).resolve()
        self.old = old_archive(self.root)
        self.project = self.root / "项目"
        self.project.mkdir()
        self.env = dict(os.environ, PYTHONUTF8="1")

    def tearDown(self):
        self.tmp.cleanup()

    def old_kit(self, *args):
        return subprocess.run([sys.executable, "-X", "utf8", str(self.old / "kit.py"), *map(str, args)],
                              capture_output=True, encoding="utf-8", env=self.env)

    def new_kit(self, *args):
        return subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "kit.py"), *map(str, args)],
                              capture_output=True, encoding="utf-8", env=self.env)

    def make_legacy_project(self):
        result = self.old_kit("init-project", self.project, "--name", "旧项目")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.root / "task.json"
        payload.write_bytes(io.encode_json({"task_id": "T1", "title": "旧任务", "description": "旧范围",
                                            "plan": "approved", "acceptance_criteria": ["旧验收"]}))
        self.assertEqual(self.old_kit("task", "add", self.project, "--file", payload,
                                      "--expected-revision", 0, "--reason", "旧批准").returncode, 0)
        payload.write_bytes(io.encode_json({"task_id": "T1", "status": "doing"}))
        self.assertEqual(self.old_kit("task", "update", self.project, "--file", payload,
                                      "--expected-revision", 1, "--reason", "旧开始").returncode, 0)
        payload.write_bytes(io.encode_json({"task_id": "T1", "status": "done",
                                            "evidence": [{"type": "manual", "criterion": 1, "detail": "旧完成"}]}))
        self.assertEqual(self.old_kit("task", "update", self.project, "--file", payload,
                                      "--expected-revision", 2, "--reason", "旧完成").returncode, 0)

    def test_legacy_is_read_only_until_migrated(self):
        self.make_legacy_project()
        state, _, ledger = memory.load(self.project)
        self.assertEqual(ledger["schema"], 1)
        self.assertEqual(self.new_kit("status", self.project, "--brief").returncode, 0)
        with self.assertRaises(io.KitError):
            memory.doc_change(self.project, state["revision"], "DECISIONS.md",
                              memory.load(self.project)[1]["DECISIONS.md"] + "\n- x\n", "写入")
        dry = self.new_kit("migrate", self.project, "--expected-revision", str(state["revision"]),
                           "--reason", "预检", "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertFalse(json.loads(dry.stdout)["changed"])

    def test_migrate_marks_legacy_and_blocks_old_writer(self):
        self.make_legacy_project()
        state, _, _ = memory.load(self.project)
        result = self.new_kit("migrate", self.project, "--expected-revision", str(state["revision"]),
                              "--reason", "升级审批协议")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["changed"])
        state, _, ledger = memory.load(self.project)
        task = ledger["tasks"][0]
        self.assertEqual(ledger["schema"], 3)
        self.assertTrue(task["legacy_unverified"])
        self.assertNotIn("approved_scope", task)
        self.assertEqual(task["evidence"][0]["scope_version"], 0)
        self.assertEqual(task["evidence"][0]["criteria_hash"], criterion_hash("旧验收"))
        self.assertTrue(Path(json.loads(result.stdout)["backup"]).is_dir())

        old = self.old_kit("status", self.project)
        self.assertNotEqual(old.returncode, 0)
        self.assertIn("不支持的任务账本版本", old.stderr)
        before = (self.project / ".agent/tasks.json").read_bytes()
        old_update = self.old_kit("task", "update", self.project, "--file", self.root / "task.json",
                                  "--expected-revision", str(state["revision"]), "--reason", "旧写入")
        self.assertNotEqual(old_update.returncode, 0)
        self.assertEqual(before, (self.project / ".agent/tasks.json").read_bytes())

        again = self.new_kit("migrate", self.project, "--expected-revision", str(state["revision"]),
                             "--reason", "重复迁移")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertFalse(json.loads(again.stdout)["changed"])

    def test_legacy_requires_reapproval_before_execution(self):
        self.make_legacy_project()
        state, _, _ = memory.load(self.project)
        self.assertEqual(self.new_kit("migrate", self.project, "--expected-revision", str(state["revision"]),
                                      "--reason", "迁移").returncode, 0)
        state, _, _ = memory.load(self.project)
        with self.assertRaises(io.KitError):
            memory.task_change(self.project, state["revision"], "update", {"task_id": "T1", "status": "doing"},
                               "旧任务直接开始")
        memory.task_change(self.project, state["revision"], "revise", {"task_id": "T1"}, "修订")
        state, _, _ = memory.load(self.project)
        memory.task_change(self.project, state["revision"], "update", {"task_id": "T1", "checks": checks_for(self.project, ["旧验收"])}, "补齐验收")
        state, _, _ = memory.load(self.project)
        memory.task_change(self.project, state["revision"], "approve", {"task_id": "T1"},
                           "重新批准", source="user")
        state, _, ledger = memory.load(self.project)
        self.assertFalse(ledger["tasks"][0]["legacy_unverified"])
        self.assertEqual(ledger["tasks"][0]["approved_scope"]["version"], 1)

    def test_dry_run_validates_conversion_and_failure_creates_no_backup(self):
        self.make_legacy_project()
        state, _, ledger = memory.load(self.project)
        # Schema 1 accepted extension fields that schema 2 deliberately rejects.
        ledger["tasks"][0]["custom_note"] = "旧扩展"
        data = io.encode_json(ledger)
        (self.project / ".agent/tasks.json").write_bytes(data)
        state["hashes"]["tasks.json"] = io.digest(data)
        (self.project / ".agent/state.json").write_bytes(io.encode_json(state))
        memory.load(self.project)
        before = {name: (self.project / ".agent" / name).read_bytes()
                  for name in ("state.json", "tasks.json", "PROGRESS.md")}
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run), self.assertRaisesRegex(io.KitError, "未知任务字段"):
                memory.migrate(self.project, state["revision"], "检查迁移", dry_run=dry_run)
            self.assertFalse((self.project / ".agent/runtime/migrations").exists())
            self.assertEqual(before, {name: (self.project / ".agent" / name).read_bytes() for name in before})

    def test_schema2_preserves_scope_and_rolls_back_exact_bytes(self):
        self.old = old_archive(self.root / "schema2", "a85bdd997c6be29250941c89f75ae9ce520cebbf")
        self.assertEqual(self.old_kit("init-project", self.project, "--name", "v2").returncode, 0)
        payload = self.root / "v2-task.json"
        payload.write_bytes(io.encode_json({"task_id": "T1", "title": "old", "acceptance_criteria": ["old criterion"]}))
        self.assertEqual(self.old_kit("task", "add", self.project, "--file", payload,
                                      "--expected-revision", 0, "--reason", "old add").returncode, 0)
        self.assertEqual(self.old_kit("task", "approve", self.project, "--task-id", "T1", "--source", "user",
                                      "--expected-revision", 1, "--reason", "old approved").returncode, 0)
        state, _, ledger = memory.load(self.project)
        original_scope = ledger["tasks"][0]["approved_scope"]
        original_history = ledger["history"]
        original_bytes = {p.name: p.read_bytes() for p in (self.project / ".agent").iterdir()
                          if p.is_file() and p.name != ".lock"}
        memory.migrate(self.project, state["revision"], "dry", dry_run=True)
        self.assertEqual(original_bytes, {p.name: p.read_bytes() for p in (self.project / ".agent").iterdir()
                                         if p.is_file() and p.name != ".lock"})
        result = memory.migrate(self.project, state["revision"], "migrate")
        current, _, updated = memory.load(self.project)
        self.assertEqual(updated["tasks"][0]["approved_scope"], original_scope)
        self.assertEqual(updated["history"][:-1], original_history)
        self.assertTrue(updated["tasks"][0]["verification_legacy"])
        self.assertNotEqual(self.old_kit("status", self.project).returncode, 0)
        memory.migration_rollback(self.project, current["revision"], "rollback", result["backup"])
        self.assertEqual(original_bytes, {p.name: p.read_bytes() for p in (self.project / ".agent").iterdir()
                                         if p.is_file() and p.name != ".lock"})
        self.assertEqual(self.old_kit("status", self.project).returncode, 0)

    def test_rollback_refuses_changes_after_migration(self):
        self.make_legacy_project()
        state, _, _ = memory.load(self.project)
        result = memory.migrate(self.project, state["revision"], "migrate")
        state, content, _ = memory.load(self.project)
        memory.doc_change(self.project, state["revision"], "DECISIONS.md", content["DECISIONS.md"] + "\nnew decision", "new")
        state, _, _ = memory.load(self.project)
        before = (self.project / ".agent/state.json").read_bytes()
        with self.assertRaises(io.KitError):
            memory.migration_rollback(self.project, state["revision"], "rollback", result["backup"])
        self.assertEqual((self.project / ".agent/state.json").read_bytes(), before)


    def test_migrated_draft_can_configure_checks_and_be_approved(self):
        self.assertEqual(self.old_kit("init-project", self.project, "--name", "旧草案").returncode, 0)
        payload = self.root / "draft.json"
        payload.write_bytes(io.encode_json({"task_id": "D", "title": "draft", "acceptance_criteria": ["criterion"]}))
        self.assertEqual(self.old_kit("task", "add", self.project, "--file", payload,
                                      "--expected-revision", 0, "--reason", "draft").returncode, 0)
        memory.migrate(self.project, 1, "migrate")
        def change(action, value):
            return memory.task_change(self.project, memory.load(self.project)[0]["revision"], action, value, "configure", source="policy")
        change("revise", {"task_id": "D"})
        change("update", {"task_id": "D", "checks": checks_for(self.project, ["criterion"])})
        change("approve", {"task_id": "D"})
        self.assertFalse(memory.load(self.project)[2]["tasks"][0]["verification_legacy"])


if __name__ == "__main__":
    unittest.main()
