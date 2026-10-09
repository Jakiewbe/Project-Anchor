import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from core import config, memory
from core.atomic_io import KitError
from core.diagnostics import doctor
from core.hook_runtime import context, log_event
from core.native import inspect_native_hooks
from tests.test_kit import Environment


class DeploymentTests(Environment):
    def test_onboarding_preserves_existing_business_and_declared_write_scope(self):
        originals = {
            "main.py": b"print(2 + 3)\r\n",
            "package.json": b'{"name":"existing-business","dependencies":{}}\r\n',
            "sources/reference.txt": b"read-only reference\r\n",
            "AGENTS.md": "继续已有业务工程，不要重新初始化项目或重构正常模块。\r\n".encode(),
            ".gitignore": b"existing-cache/\r\n",
            ".gitattributes": b"*.txt text eol=crlf\r\n",
        }
        for name, data in originals.items():
            p = self.project / name
            p.parent.mkdir(exist_ok=True)
            p.write_bytes(data)
        self.init()
        appended = {"AGENTS.md", ".gitignore", ".gitattributes"}
        for name, data in originals.items():
            actual = (self.project / name).read_bytes()
            if name in appended:
                self.assertTrue(actual.startswith(data))
                self.assertGreater(len(actual), len(data))
            else:
                self.assertEqual(actual, data)
        self.assertFalse((self.project / ".git").exists())
        for p in self.project.rglob("*"):
            if p.is_file() and p.relative_to(self.project).parts[0] != ".agent":
                self.assertIn(p.relative_to(self.project).as_posix(), originals)

    def test_onboarding_keeps_existing_git_identity_and_business_bytes(self):
        subprocess.run(["git", "init", str(self.project)], check=True, capture_output=True)
        (self.project / "main.py").write_bytes(b"print(5)\n")
        subprocess.run(["git", "-C", str(self.project), "add", "main.py"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.project), "-c", "user.name=fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture"],
                       check=True, capture_output=True)
        before = {name: (self.project / ".git" / name).read_bytes() for name in ["HEAD", "config", "index"]}
        head = subprocess.run(["git", "-C", str(self.project), "rev-parse", "HEAD"],
                              check=True, capture_output=True).stdout
        self.init()
        self.assertEqual((self.project / "main.py").read_bytes(), b"print(5)\n")
        self.assertEqual(before, {name: (self.project / ".git" / name).read_bytes() for name in before})
        self.assertEqual(subprocess.run(["git", "-C", str(self.project), "rev-parse", "HEAD"],
                                       check=True, capture_output=True).stdout, head)

    def test_invalid_inline_hook_table_fails_before_installation(self):
        self.home.mkdir()
        (self.home / "config.toml").write_text('hooks = "invalid"\n', encoding="utf-8")
        with self.assertRaises(KitError):
            config.install(self.home, self.base / ".agents/skills")
        self.assertFalse((self.home / "AGENTS.md").exists())
        self.assertFalse((self.home / "codex-rules/install.json").exists())
    def test_native_trust_metadata_is_not_a_second_hook_source(self):
        self.home.mkdir()
        (self.home / "config.toml").write_text('[hooks.state.fixture]\ntrusted_hash = "sha256:fixture"\n', encoding="utf-8")
        result = config.install(self.home, self.base / ".agents/skills")
        self.assertFalse(result["inline_hooks_present"])
        self.assertFalse(any(c["check"] == "用户双 Hook 来源" for c in doctor(self.home, self.project)))

    def test_actual_inline_handlers_still_warn_about_two_sources(self):
        self.home.mkdir()
        (self.home / "config.toml").write_text('[[hooks.SessionStart]]\nmatcher = "startup"\n[[hooks.SessionStart.hooks]]\ntype = "command"\ncommand = "echo test"\n', encoding="utf-8")
        result = config.install(self.home, self.base / ".agents/skills")
        self.assertTrue(result["inline_hooks_present"])
        self.assertTrue(any(c["check"] == "用户双 Hook 来源" for c in doctor(self.home, self.project)))
    def test_initialization_rejects_home_before_writing(self):
        with patch("core.memory.Path.home", return_value=self.base):
            with self.assertRaises(KitError):
                memory.init_project(self.base, "home")
        self.assertFalse((self.base / ".agent").exists())

    def test_initialization_rejects_drive_root_before_writing(self):
        with self.assertRaises(KitError):
            memory.init_project(Path(self.project.anchor), "root")
    def record(self, session, event="SessionStart", origin="invocation", status="PASS"):
        log_event(self.home, {"session_id": session, "event": event, "origin": origin,
                             "status": status, "definition_hash": config.definition_hash()})

    def event_status(self, session, expected=()):
        return {c["check"]: c["status"] for c in doctor(self.home, self.project, session, expected)
                if "本会话执行" in c["check"]}

    def test_previous_session_is_not_current_success(self):
        self.record("old")
        self.assertEqual(self.event_status("new")["SessionStart 本会话执行"], "UNVERIFIED")

    def test_expected_missing_event_is_failure(self):
        self.record("old")
        self.assertEqual(self.event_status("new", ["SessionStart"])["SessionStart 本会话执行"], "FAIL")

    def test_compaction_not_expected_without_client_evidence(self):
        self.record("current")
        statuses = self.event_status("current", ["SessionStart"])
        self.assertEqual(statuses["SessionStart 本会话执行"], "PASS")
        self.assertEqual(statuses["PreCompact 本会话执行"], "UNVERIFIED")

    def test_simulation_does_not_prove_current_native_execution(self):
        self.record("current", origin="simulation")
        self.assertEqual(self.event_status("current", ["SessionStart"])["SessionStart 本会话执行"], "FAIL")

    def test_expected_events_require_session(self):
        with self.assertRaises(KitError):
            doctor(self.home, self.project, expected_events=["PreCompact"])
        result = self.cli("doctor", self.project, "--expect-event", "PreCompact")
        self.assertEqual(result.returncode, 1)

    def test_unreviewed_context_requires_current_disk_read(self):
        self.init()
        config.trust_project(self.project, self.home)
        state, content, _ = memory.load(self.project)
        memory.doc_change(self.project, state["revision"], "CURRENT.md",
                          content["CURRENT.md"] + "\n已确认的最新断点。\n", "保存断点")
        reminder = context(self.project, self.home)
        self.assertIn("status", reminder)
        self.assertIn("读取资料不需要重新 trust-project", reminder)
        self.assertNotIn("已确认的最新断点", reminder)
        result = self.cli("status", self.project)
        self.assertEqual(result.returncode, 0)
        self.assertIn("已确认的最新断点", json.loads(result.stdout)["current"])

    def test_simulated_protocol_records_lifecycle_source(self):
        self.init()
        result = self.hook(source="compact")
        self.assertEqual(result.returncode, 0)
        records = [json.loads(line) for line in (self.home / "codex-rules/runtime/hooks.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[-1]["source"], "compact")

    def native_fixture(self):
        groups = config.hook_groups()
        hooks = []
        for event, name in [("SessionStart", "sessionStart"), ("PreCompact", "preCompact")]:
            group = groups[event]; handler = group["hooks"][0]
            hooks.append({"eventName": name, "sourcePath": str(self.home / "hooks.json"),
                          "command": handler["command"], "matcher": group["matcher"],
                          "timeoutSec": handler["timeout"], "handlerType": "command", "async": False,
                          "statusMessage": handler["statusMessage"],
                          "additionalContextLimit": handler.get("additionalContextLimit"),
                          "enabled": True, "trustStatus": "untrusted", "currentHash": "sha256:fixture"})
        return {"data": [{"hooks": hooks, "errors": []}]}, {"groups": groups}

    def native_status(self, value, manifest):
        checks = inspect_native_hooks(value, self.home, manifest)
        return next(c["status"] for c in checks if c["check"] == "Hook 已信任")

    def test_native_untrusted_definition_reports_warning(self):
        value, manifest = self.native_fixture()
        self.assertEqual(self.native_status(value, manifest), "WARN")

    def test_native_reviewed_definition_is_not_lifecycle_proof(self):
        value, manifest = self.native_fixture()
        for h in value["data"][0]["hooks"]: h["trustStatus"] = "trusted"
        checks = inspect_native_hooks(value, self.home, manifest)
        checked = next(c for c in checks if c["check"] == "Hook 已信任")
        self.assertEqual(checked["status"], "PASS")
        self.assertIn("仍需独立核对实际执行", checked["detail"])

    def test_other_trusted_hook_cannot_prove_tool_trust(self):
        value, manifest = self.native_fixture()
        for h in value["data"][0]["hooks"]:
            h["trustStatus"] = "trusted"; h["command"] = "other-command"
        self.assertEqual(self.native_status(value, manifest), "UNVERIFIED")
        self.assertEqual(sum(c["status"] == "FAIL" for c in inspect_native_hooks(value, self.home, manifest)), 2)

    def test_disabled_native_hook_is_not_running(self):
        value, manifest = self.native_fixture()
        for h in value["data"][0]["hooks"]: h["trustStatus"] = "trusted"
        value["data"][0]["hooks"][0]["enabled"] = False
        self.assertEqual(self.native_status(value, manifest), "WARN")

    def test_native_config_error_is_reported(self):
        value, manifest = self.native_fixture()
        value["data"][0]["errors"] = ["invalid fixture"]
        checks = inspect_native_hooks(value, self.home, manifest)
        self.assertTrue(any(c["status"] == "FAIL" and c["check"] == "原生 Hook 配置解析" for c in checks))
        self.assertEqual(self.native_status(value, manifest), "UNVERIFIED")

    def test_missing_native_definition_hash_stays_unverified(self):
        value, manifest = self.native_fixture()
        for h in value["data"][0]["hooks"]:
            h["trustStatus"] = "trusted"; h.pop("currentHash")
        self.assertEqual(self.native_status(value, manifest), "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
