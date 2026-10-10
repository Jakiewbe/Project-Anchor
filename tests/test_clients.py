"""Codex-independent installs: generic Agent Skills directory and the Claude Code adapter."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from core import atomic_io as io
from core.clients import claude_hook_groups, client_home, install_client, recover_client, uninstall_client
from core.config import install
from core.memory import init_project, load
from core.skill_install import skill_payload

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def frontmatter(text):
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    fields, metadata, key = {}, {}, None
    for line in match.group(1).splitlines():
        if line.startswith("  "):
            name, value = line.strip().split(":", 1)
            metadata[name] = json.loads(value.strip())
        else:
            key, value = line.split(":", 1)
            fields[key] = json.loads(value.strip()) if value.strip().startswith('"') else value.strip()
    fields["metadata"] = metadata
    return fields


class SpecTests(unittest.TestCase):
    def test_skill_frontmatter_follows_agent_skills_spec(self):
        folder = ROOT / "skills/project-anchor"
        fields = frontmatter((folder / "SKILL.md").read_text(encoding="utf-8"))
        self.assertLessEqual(set(fields), FIELDS)
        self.assertRegex(fields["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertLessEqual(len(fields["name"]), 64)
        self.assertEqual(fields["name"], folder.name)
        self.assertTrue(1 <= len(fields["description"]) <= 1024, len(fields["description"]))
        self.assertTrue(all(isinstance(v, str) for v in fields["metadata"].values()))


class ClientBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Client 中文 空格 ")
        self.root = Path(self.tmp.name)
        self.user = self.root / "用户 目录"
        self.project = self.root / "合成 项目"
        self.project.mkdir(parents=True)
        # The child sees a fake home and no CODEX_HOME, so any Codex fallback would be visible.
        self.env = {k: v for k, v in os.environ.items() if k not in ("CODEX_HOME", "PROJECT_ANCHOR_CLIENT",
                                                                     "PROJECT_ANCHOR_CLIENT_HOME", "CLAUDE_CONFIG_DIR")}
        self.env.update(USERPROFILE=str(self.user), HOME=str(self.user), PYTHONUTF8="1")

    def tearDown(self):
        self.tmp.cleanup()

    def run_skill(self, skill, *args, payload=None):
        return subprocess.run([sys.executable, "-X", "utf8", str(skill / "scripts/run.py"), *map(str, args)],
                              input=payload, env=self.env, cwd=self.root, capture_output=True,
                              encoding="utf-8", timeout=30)

    def files(self, folder):
        return {p: p.read_bytes() for p in Path(folder).rglob("*") if p.is_file() and p.suffix != ".lock"}


class AgentsInstallTests(ClientBase):
    def setUp(self):
        super().setUp()
        self.home = self.root / "anchor 清单"
        self.parent = self.root / "共享 skills"
        self.result = install_client("agents", self.home, self.parent)
        self.skill = self.parent / "project-anchor"

    def test_runtime_has_no_codex_dependency(self):
        runtime = io.read_json(self.skill / "runtime.json")
        self.assertEqual((runtime["client"], runtime["home"]), ("agents", str(self.home)))
        self.assertNotIn("codex_home", runtime)
        self.assertLessEqual({p.name for p in self.home.iterdir()}, {".lock", "install.json", "runtime"})
        self.assertFalse(any(self.home.glob("**/AGENTS.md")) or any(self.home.glob("**/hooks.json")))

    def test_default_home_and_environment_override(self):
        with patch.dict(os.environ, {"PROJECT_ANCHOR_HOME": str(self.home)}):
            self.assertEqual(client_home("agents"), self.home.resolve())
        with patch.dict(os.environ, {}, clear=True), patch("core.clients.Path.home", return_value=self.user):
            self.assertEqual(client_home("agents"), (self.user / ".project-anchor").resolve())

    def test_idempotent_and_preserves_unrelated_files(self):
        other = self.parent / "other/SKILL.md"
        other.parent.mkdir()
        other.write_text("other", encoding="utf-8")
        before = self.files(self.skill)
        self.assertFalse(install_client("agents", self.home, self.parent)["changed"])
        self.assertEqual(before, self.files(self.skill))
        note = self.skill / "user-notes.md"
        note.write_text("keep", encoding="utf-8")
        uninstall_client("agents", self.home)
        self.assertEqual((other.read_text(encoding="utf-8"), note.read_text(encoding="utf-8")), ("other", "keep"))
        self.assertFalse((self.skill / "SKILL.md").exists())
        self.assertFalse((self.home / "install.json").exists())

    def test_update_backs_up_previous_skill(self):
        before = (self.skill / "SKILL.md").read_bytes()
        payload = skill_payload(self.home, "agents")
        payload["SKILL.md"] += b"\nUpdated\n"
        with patch("core.skill_install.skill_payload", return_value=payload):
            result = install_client("agents", self.home, self.parent)
        self.assertTrue(result["changed"])
        self.assertEqual((Path(result["backup"]) / "skill/SKILL.md").read_bytes(), before)
        self.assertTrue((self.skill / "SKILL.md").read_bytes().endswith(b"Updated\n"))

    def test_drift_refuses_update_and_uninstall(self):
        path = self.skill / "SKILL.md"
        path.write_text("user change", encoding="utf-8")
        for action in (lambda: install_client("agents", self.home, self.parent), lambda: uninstall_client("agents", self.home)):
            with self.assertRaises(io.KitError):
                action()
        self.assertEqual(path.read_text(encoding="utf-8"), "user change")

    def test_codex_and_generic_installs_do_not_take_over_each_other(self):
        with self.assertRaisesRegex(io.KitError, "agents"):
            install(self.root / "codex", self.parent)
        uninstall_client("agents", self.home)
        install(self.root / "codex", self.parent)
        with self.assertRaisesRegex(io.KitError, "codex"):
            install_client("agents", self.root / "other", self.parent)

    def test_failed_install_rolls_back_and_recovers(self):
        uninstall_client("agents", self.home)
        original = io.atomic_write
        def crash(path, data):
            original(path, data)
            if Path(path).name == "SKILL.md":
                raise KeyboardInterrupt()
        with patch("core.atomic_io.atomic_write", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                install_client("agents", self.home, self.parent)
        with self.assertRaises(io.KitError):
            install_client("agents", self.home, self.parent)
        recover_client("agents", self.home, self.parent, rollback=True)
        self.assertFalse((self.skill / "SKILL.md").exists())
        self.assertFalse((self.home / "install.json").exists())
        install_client("agents", self.home, self.parent)

    def test_adapter_workflow_without_codex(self):
        steps = [("init-project", self.project, "--name", "合成项目"),
                 ("status", self.project)]
        for args in steps:
            result = self.run_skill(self.skill, *args)
            self.assertEqual(result.returncode, 0, result.stderr)
        task = {"task_id": "T1", "title": "核对", "plan": "approved", "acceptance_criteria": ["通过"]}
        result = self.run_skill(self.skill, "task", "add", self.project, "--json-input", "--expected-revision", 0,
                                "--reason", "规划", payload=json.dumps(task, ensure_ascii=False))
        self.assertEqual(result.returncode, 0, result.stderr)
        decisions = load(self.project)[1]["DECISIONS.md"] + "\n- 合成决定：使用通用入口。\n"
        result = self.run_skill(self.skill, "state", "update", self.project, "DECISIONS.md", "--text-input",
                                "--expected-revision", 1, "--reason", "保存决定", payload=decisions)
        self.assertEqual(result.returncode, 0, result.stderr)
        doctor = self.run_skill(self.skill, "doctor", self.project, "--json")
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        checks = {c["check"]: c for c in json.loads(doctor.stdout)}
        self.assertEqual(checks["agents 安装清单"]["status"], "PASS")
        self.assertEqual(checks["项目状态完整性"]["status"], "PASS")
        self.assertNotIn("全局安装路径", checks)
        self.assertFalse((self.user / ".codex").exists())
        self.assertIn("合成决定", load(self.project)[1]["DECISIONS.md"])

    def test_cli_entrypoints(self):
        import kit
        home, parent = self.root / "cli home", self.root / "cli skills"
        self.assertEqual(kit.main(["install-client", "agents", "--home", str(home), "--skills-dir", str(parent)]), 0)
        self.assertTrue((parent / "project-anchor/SKILL.md").exists())
        self.assertEqual(kit.main(["recover", "--client", "agents", "--client-home", str(home)]), 1)
        self.assertEqual(kit.main(["uninstall-client", "agents", "--home", str(home)]), 0)
        self.assertFalse((parent / "project-anchor/SKILL.md").exists())
        self.assertEqual(kit.main(["uninstall-client", "agents", "--home", str(home)]), 1)

    def test_doctor_rejects_codex_only_options(self):
        result = self.run_skill(self.skill, "doctor", self.project, "--native-skills")
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.user / ".codex").exists())


class ClaudeInstallTests(ClientBase):
    def setUp(self):
        super().setUp()
        self.home = self.root / "claude 配置"
        self.home.mkdir()
        self.settings = self.home / "settings.json"
        self.user_settings = {"model": "user-choice", "permissions": {"allow": ["Bash(git status)"]},
                              "hooks": {"SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "echo user"}]}]}}
        self.settings.write_bytes(io.encode_json(self.user_settings))
        self.result = install_client("claude", self.home)
        self.skill = self.home / "skills/project-anchor"
        self.rules = self.home / "rules/project-anchor.md"

    def test_install_preserves_user_settings_and_adds_owned_items(self):
        settings = io.read_json(self.settings)
        self.assertEqual((settings["model"], settings["permissions"]), ("user-choice", self.user_settings["permissions"]))
        self.assertIn(self.user_settings["hooks"]["SessionStart"][0], settings["hooks"]["SessionStart"])
        for event, group in claude_hook_groups(self.home / "project-anchor").items():
            self.assertEqual(settings["hooks"][event].count(group), 1)
        self.assertEqual(self.rules.read_bytes(), (ROOT / "global/CLIENT_RULES.md").read_bytes())
        self.assertEqual(io.read_json(self.skill / "runtime.json")["client"], "claude")
        self.assertFalse((self.home / "CLAUDE.md").exists())

    def test_idempotent_uninstall_restores_settings(self):
        before = self.files(self.home)
        self.assertFalse(install_client("claude", self.home)["changed"])
        self.assertEqual(before, self.files(self.home))
        uninstall_client("claude", self.home)
        self.assertEqual(io.read_json(self.settings), self.user_settings)
        self.assertFalse(self.rules.exists() or (self.skill / "SKILL.md").exists())

    def test_uninstall_removes_files_it_created(self):
        uninstall_client("claude", self.home)
        self.settings.unlink()
        install_client("claude", self.home)
        uninstall_client("claude", self.home)
        self.assertFalse(self.settings.exists())

    def test_refuses_foreign_rules_and_modified_hooks(self):
        uninstall_client("claude", self.home)
        self.rules.parent.mkdir(exist_ok=True)
        self.rules.write_text("user rules", encoding="utf-8")
        with self.assertRaises(io.KitError):
            install_client("claude", self.home)
        self.assertEqual(self.rules.read_text(encoding="utf-8"), "user rules")
        self.rules.unlink()
        install_client("claude", self.home)
        settings = io.read_json(self.settings)
        settings["hooks"]["PreCompact"][0]["hooks"][0]["timeout"] = 99
        self.settings.write_bytes(io.encode_json(settings))
        with self.assertRaises(io.KitError):
            uninstall_client("claude", self.home)
        self.assertEqual(io.read_json(self.settings)["hooks"]["PreCompact"][0]["hooks"][0]["timeout"], 99)

    def test_rejects_skills_dir_override(self):
        with self.assertRaises(io.KitError):
            install_client("claude", self.root / "other", self.root / "x")

    def hook(self, event, extra):
        group = io.read_json(self.settings)["hooks"][event][-1]
        value = {"session_id": "claude-test", "transcript_path": str(self.root / "t.jsonl"), "cwd": str(self.project),
                 "hook_event_name": event, **extra}
        return subprocess.run(group["hooks"][0]["command"], shell=True, input=json.dumps(value, ensure_ascii=False),
                              env=self.env, capture_output=True, encoding="utf-8", timeout=60)

    def test_configured_hook_commands_use_claude_storage(self):
        init_project(self.project, "合成项目")
        start = self.hook("SessionStart", {"source": "startup", "model": "test"})
        self.assertEqual(start.returncode, 0, start.stderr)
        context = json.loads(start.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("未注入内容摘要", context)
        compact = self.hook("PreCompact", {"trigger": "manual", "custom_instructions": ""})
        self.assertEqual(compact.returncode, 0, compact.stderr)
        self.assertEqual(len(list((self.project / ".agent/runtime/snapshots").glob("snapshot-*.json"))), 1)
        log = (self.home / "project-anchor/runtime/hooks.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["status"] for line in log], ["PASS", "PASS"])
        self.assertFalse((self.user / ".codex").exists())

    def test_reviewed_project_context_and_doctor(self):
        import kit
        init_project(self.project, "合成项目")
        self.assertEqual(kit.main(["trust-project", str(self.project), "--client", "claude",
                                   "--client-home", str(self.home), "--approved"]), 0)
        start = self.hook("SessionStart", {"source": "resume"})
        self.assertIn("project_id", json.loads(start.stdout)["hookSpecificOutput"]["additionalContext"])
        doctor = self.run_skill(self.skill, "doctor", self.project, "--json")
        checks = {c["check"]: c["status"] for c in json.loads(doctor.stdout)}
        self.assertEqual(doctor.returncode, 0, doctor.stdout)
        for name in ("claude 安装清单", "Claude 用户规则完整性", "SessionStart 已配置", "PreCompact 已配置", "Skill 安装完整性"):
            self.assertEqual(checks[name], "PASS", name)
        self.assertEqual(checks["Claude 原生加载"], "UNVERIFIED")


class CrossClientTests(ClientBase):
    def test_two_clients_share_one_ledger_and_reject_stale_revision(self):
        agents = install_client("agents", self.root / "anchor", self.root / "agents skills")
        claude_home = self.root / "claude"
        install_client("claude", claude_home)
        first, second = Path(agents["skill"]), claude_home / "skills/project-anchor"
        init_project(self.project, "共享项目")
        task = {"task_id": "T1", "title": "共享", "plan": "approved", "acceptance_criteria": ["通过"]}
        result = self.run_skill(first, "task", "add", self.project, "--json-input", "--expected-revision", 0,
                                "--reason", "客户端一", payload=json.dumps(task, ensure_ascii=False))
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = json.loads(self.run_skill(second, "snapshot", self.project).stdout)["snapshot"]
        before = (self.project / ".agent/tasks.json").read_bytes()
        stale = self.run_skill(second, "task", "update", self.project, "--json-input", "--expected-revision", 0,
                               "--reason", "旧修订", payload='{"task_id":"T1","status":"doing"}')
        self.assertEqual(stale.returncode, 1)
        self.assertEqual(before, (self.project / ".agent/tasks.json").read_bytes())
        status = json.loads(self.run_skill(second, "status", self.project).stdout)
        result = self.run_skill(second, "task", "update", self.project, "--json-input", "--expected-revision",
                                status["revision"], "--reason", "客户端二", payload='{"task_id":"T1","status":"doing"}')
        self.assertEqual(result.returncode, 0, result.stderr)
        check = json.loads(self.run_skill(first, "snapshot", self.project, "--check", snapshot).stdout)
        self.assertEqual((check["stale"], check["automatic_restore"]), (True, False))
        self.assertEqual(load(self.project)[2]["tasks"][0]["status"], "doing")


if __name__ == "__main__":
    unittest.main()
