"""Schema 1 -> 2 migration and old-writer refusal tests."""
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

ROOT = Path(__file__).resolve().parents[1]
OLD_COMMIT = "bc72aca100f5f4e5de7638b75de57085c9a1c7d0"


def old_archive(destination):
    exists = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", OLD_COMMIT],
                            capture_output=True)
    if exists.returncode:
        raise unittest.SkipTest("old commit not available in this clone")
    data = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=zip", OLD_COMMIT],
                          capture_output=True, check=True).stdout
    archive = destination / "old.zip"
    archive.write_bytes(data)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination / "old")
    return destination / "old"


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Anchor 迁移 中文 ")
        self.root = Path(self.tmp.name)
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
        self.assertEqual(ledger["schema"], 2)
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
        memory.task_change(self.project, state["revision"], "approve", {"task_id": "T1"},
                           "重新批准", source="user")
        state, _, ledger = memory.load(self.project)
        self.assertFalse(ledger["tasks"][0]["legacy_unverified"])
        self.assertEqual(ledger["tasks"][0]["approved_scope"]["version"], 1)


if __name__ == "__main__":
    unittest.main()
