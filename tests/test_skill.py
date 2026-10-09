"""Install/adapter/safety tests; model triggering is in skill_native_probe.py."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from core import VERSION
from core import atomic_io as io
from core.config import install, uninstall, locations
from core.diagnostics import doctor
from core.skill_install import skill_directory, skill_payload
from core.memory import init_project, load, doc_change, snapshot, task_change

ROOT = Path(__file__).resolve().parents[1]


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Skill 中文 空格 ")
        self.root = Path(self.tmp.name)
        self.home = self.root / "自定义 CODEX_HOME"
        self.parent = self.root / "用户/.agents/skills"
        self.project = self.root / "项目"
        self.project.mkdir()
        self.result = install(self.home, self.parent)
        self.skill = self.parent / "project-anchor"
        self.runner = self.skill / "scripts/run.py"
        self.env = dict(os.environ, CODEX_HOME=str(self.root / "wrong-home"), PYTHONUTF8="1")

    def tearDown(self):
        self.tmp.cleanup()

    def run_skill(self, *args, payload=None):
        return subprocess.run([sys.executable, "-X", "utf8", str(self.runner), *map(str, args)],
                              input=payload, env=self.env, cwd=self.project, capture_output=True,
                              encoding="utf-8", timeout=20)

    def test_defaults_use_real_user_agents_directory(self):
        with patch("core.skill_install.Path.home", return_value=self.root / "用户"):
            self.assertEqual(skill_directory(), self.parent / "project-anchor")

    def test_install_has_only_one_business_implementation(self):
        self.assertTrue((self.skill / "SKILL.md").is_file())
        self.assertFalse((self.skill / "core").exists())
        self.assertFalse((self.skill / "kit.py").exists())
        runtime = io.read_json(self.skill / "runtime.json")
        self.assertEqual(runtime["kit"], str(ROOT / "kit.py"))
        self.assertEqual(runtime["python"], str(Path(sys.executable).resolve()))

    def test_idempotent(self):
        first = {p: p.read_bytes() for p in self.skill.rglob("*") if p.is_file()}
        result = install(self.home, self.parent)
        self.assertFalse(result["changed"])
        self.assertEqual(first, {p: p.read_bytes() for p in self.skill.rglob("*") if p.is_file()})

    def test_unrelated_skill_and_new_user_file_preserved(self):
        other = self.parent / "another/SKILL.md"
        other.parent.mkdir()
        other.write_text("other", encoding="utf-8")
        addition = self.skill / "user-notes.md"
        addition.write_text("keep", encoding="utf-8")
        install(self.home, self.parent)
        uninstall(self.home)
        self.assertEqual(other.read_text(), "other")
        self.assertEqual(addition.read_text(), "keep")
        self.assertFalse((self.skill / "SKILL.md").exists())

    def test_foreign_same_name_refused(self):
        home = self.root / "new-home"
        before = (self.skill / "SKILL.md").read_bytes()
        with self.assertRaises(io.KitError):
            install(home, self.parent)
        self.assertEqual(before, (self.skill / "SKILL.md").read_bytes())
        self.assertFalse((home / "AGENTS.md").exists())

    def test_owned_file_drift_refuses_upgrade_and_uninstall(self):
        path = self.skill / "SKILL.md"
        path.write_text("user modification", encoding="utf-8")
        for action in (lambda: install(self.home, self.parent), lambda: uninstall(self.home)):
            with self.assertRaises(io.KitError):
                action()
        self.assertEqual(path.read_text(), "user modification")
        self.assertEqual(next(c["status"] for c in doctor(self.home, self.project) if c["check"] == "Skill 安装完整性"), "FAIL")

    def test_template_upgrade_backs_up_and_keeps_config(self):
        config = self.home / "config.toml"
        config.write_text('model = "user-choice"\n', encoding="utf-8")
        before = (self.skill / "SKILL.md").read_bytes()
        payload = skill_payload(self.home)
        payload["SKILL.md"] += b"\nUpdated workflow\n"
        with patch("core.skill_install.skill_payload", return_value=payload):
            result = install(self.home, self.parent)
        self.assertTrue(result["changed"])
        self.assertEqual((Path(result["backup"]) / "skill/SKILL.md").read_bytes(), before)
        self.assertEqual(config.read_text(), 'model = "user-choice"\n')

    def test_old_v1_manifest_upgrade(self):
        uninstall(self.home)
        old_home = self.root / "legacy"
        # A first install with only legacy managed content and no Skill record.
        from core.config import BEGIN, END, hook_groups
        block = b"\n" + BEGIN + b"\nlegacy rules\n" + END + b"\n"
        old_home.mkdir()
        (old_home / "AGENTS.md").write_bytes(b"user\n" + block)
        (old_home / "hooks.json").write_bytes(io.encode_json({"hooks": {e: [g] for e,g in hook_groups().items()}}))
        metadata = {"schema":1,"version":"1.0.0","block":block.decode(),"groups":hook_groups(),"agents_existed":True,"hooks_existed":True}
        io.atomic_write(old_home / "codex-rules/install.json", io.encode_json(metadata))
        result = install(old_home, self.parent)
        self.assertTrue((self.skill / "SKILL.md").exists())
        self.assertTrue((old_home / "AGENTS.md").read_bytes().startswith(b"user\n"))

    def test_cross_directory_install_failure_rolls_back_all(self):
        uninstall(self.home)
        original = io.atomic_write
        def fail(path, data):
            if Path(path) == self.runner:
                raise OSError("injected adapter write failure")
            original(path, data)
        with patch("core.atomic_io.atomic_write", side_effect=fail):
            with self.assertRaises(OSError):
                install(self.home, self.parent)
        self.assertFalse((self.home / "AGENTS.md").exists())
        self.assertFalse((self.home / "codex-rules/install.json").exists())
        self.assertFalse((self.skill / "SKILL.md").exists())

    def test_multi_scope_crash_recovery_checks_scope(self):
        main, second = self.root / "main", self.root / "second"
        main.mkdir(); second.mkdir()
        first, last, journal = main / "a", second / "b", main / "journal"
        first.write_bytes(b"old")
        original = io.atomic_write
        def crash(path,data):
            original(path,data)
            if Path(path) == first:
                raise KeyboardInterrupt()
        with patch("core.atomic_io.atomic_write", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                io.transaction(main,journal,{first:b"new",last:b"added"},additional_roots={"skill":second})
        with self.assertRaises(io.KitError):
            io.recover(main,journal,additional_roots={"skill": self.root / "wrong"})
        io.recover(main,journal,additional_roots={"skill":second})
        self.assertEqual(last.read_bytes(),b"added")

    def test_adapter_locates_from_other_cwd_and_home(self):
        result = self.run_skill("--locate")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["codex_home"], str(self.home))

    def test_global_recovery_locks_shared_skill_directory(self):
        import kit
        _, _, journal = locations(self.home)
        first = self.home / "AGENTS.md"
        original = io.atomic_write
        def crash(path, data):
            original(path, data)
            if Path(path) == first:
                raise KeyboardInterrupt()
        with patch("core.atomic_io.atomic_write", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                io.transaction(self.home, journal, {first: b"changed", self.skill / "runtime.json": b"changed"},
                               additional_roots={"skill": self.skill})
        with patch("kit.locked", wraps=io.locked) as observed:
            self.assertEqual(kit.main(["recover", "--global", "--codex-home", str(self.home), "--rollback"]), 0)
        self.assertIn(self.skill.parent / ".codex-rules.lock", [call.args[0] for call in observed.call_args_list])

    def test_adapter_init_and_read_only_progress(self):
        result = self.run_skill("init-project",self.project,"--name","测试项目")
        self.assertEqual(result.returncode,0,result.stderr)
        before=(self.project / ".agent/state.json").read_bytes()
        result=self.run_skill("status",self.project)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(before,(self.project / ".agent/state.json").read_bytes())
        self.assertFalse((self.project / ".git").exists())

    def test_adapter_task_and_memory_handoff(self):
        init_project(self.project,"project")
        task={"task_id":"T1","title":"检查","plan":"approved","acceptance_criteria":["通过"]}
        for action, payload, rev in [("add",task,0),("update",{"task_id":"T1","status":"doing"},1),
                                     ("update",{"task_id":"T1","status":"done","evidence":[{"type":"manual","criterion":1,"detail":"实际检查通过"}]},2)]:
            result=self.run_skill("task",action,self.project,"--json-input","--expected-revision",rev,"--reason","验收",payload=json.dumps(payload,ensure_ascii=False))
            self.assertEqual(result.returncode,0,result.stderr)
        state, content, ledger=load(self.project)
        current=content["CURRENT.md"].replace("确认目标和计划。","准备交接。")
        result=self.run_skill("state","update",self.project,"CURRENT.md","--text-input","--expected-revision",3,"--reason","主动交接",payload=current)
        self.assertEqual(result.returncode,0,result.stderr)
        result=self.run_skill("snapshot",self.project)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(Path(json.loads(result.stdout)["snapshot"]).exists())
        self.assertEqual(load(self.project)[0]["current_task_revision"],3)
        self.assertIn("完成率: 100%",(self.project / ".agent/PROGRESS.md").read_text(encoding="utf-8"))

    def test_adapter_invalid_evidence_preserves_ledger(self):
        init_project(self.project,"project")
        task_change(self.project,0,"add",{"task_id":"T1","title":"任务","plan":"approved","acceptance_criteria":["验收"]},"添加")
        task_change(self.project,1,"update",{"task_id":"T1","status":"doing"},"开始")
        before=(self.project / ".agent/tasks.json").read_bytes()
        result=self.run_skill("task","update",self.project,"--json-input","--expected-revision",2,"--reason","完成",payload='{"task_id":"T1","status":"done"}')
        self.assertEqual(result.returncode,1)
        self.assertEqual(before,(self.project / ".agent/tasks.json").read_bytes())

    def test_adapter_version_drift_fails(self):
        path=self.skill / "runtime.json"
        data=io.read_json(path); data["version"]="0.0.0"; path.write_bytes(io.encode_json(data))
        result=self.run_skill("--locate")
        self.assertEqual(result.returncode,1)

    def test_cli_still_operates_without_skill(self):
        self.runner.unlink()
        result=subprocess.run([sys.executable,str(ROOT / "kit.py"),"--version"],capture_output=True,encoding="utf-8")
        self.assertEqual(result.stdout.strip(),VERSION)
        self.assertEqual(result.returncode,0)

    def test_adapter_doctor_uses_installation_home(self):
        result=self.run_skill("doctor",self.project,"--json")
        self.assertEqual(result.returncode,0,result.stderr)
        checks=json.loads(result.stdout)
        self.assertEqual(next(c["detail"] for c in checks if c["check"]=="全局安装路径"),str(self.home))
        self.assertFalse((self.root / "wrong-home").exists())

    def test_shell_metacharacters_are_literal_arguments(self):
        name="任务 $x `echo nope` & other"
        result=self.run_skill("init-project",self.project,"--name",name)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(load(self.project)[0]["name"],name)


if __name__=="__main__":
    unittest.main()
