"""DSH bundle: static contract checks plus a real run of the Host modules."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import kit
from core.memory import init_project, load

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "packages/dsh"
SUPPORTED_KEYWORDS = {"type", "oneOf", "properties", "required", "additionalProperties",
                      "items", "enum", "const", "description", "title"}
STUB_TOOLS = """
export function defineTool(options) {
  return { ...options }
}
"""
STUB_SCHEMASTERY = """
const chain = () => new Proxy(function () {}, {
  get: () => (..._args) => chain(),
  apply: () => chain(),
})
const z = new Proxy({}, { get: () => (..._args) => chain() })
export { z }
export default z
"""


def config_keys():
    text = (BUNDLE / "index.js").read_text(encoding="utf-8")
    block = text.split("export const Config = z.object({", 1)[1].split("\n})", 1)[0]
    keys = set()
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        keys.add(line.split(":", 1)[0].strip())
    return keys


def schema_violations(node, path, out):
    if not isinstance(node, dict):
        out.append(f"{path} must be an object")
        return
    unknown = set(node) - SUPPORTED_KEYWORDS
    if unknown:
        out.append(f"{path} has unsupported keywords {sorted(unknown)}")
    if "type" in node and "oneOf" in node:
        out.append(f"{path} declares both type and oneOf")
    properties = node.get("properties")
    if properties is not None:
        if node.get("additionalProperties") is not False:
            out.append(f"{path} object must set additionalProperties false")
        required = node.get("required")
        if not isinstance(required, list) or set(required) != set(properties):
            out.append(f"{path} required must list exactly its properties")
        for key, child in properties.items():
            schema_violations(child, f"{path}.{key}", out)
    items = node.get("items")
    if items is not None:
        schema_violations(items, f"{path}[]", out)


class ManifestTests(unittest.TestCase):
    def test_manifest_and_patch_agree(self):
        manifest = json.loads((BUNDLE / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "@local/project-anchor-dsh")
        self.assertTrue(manifest["private"])
        self.assertEqual(manifest["type"], "module")
        self.assertEqual(manifest["dsh"]["bundle"]["patch"], "./cordis.patch.yml")
        patch = (BUNDLE / manifest["dsh"]["bundle"]["patch"]).read_text(encoding="utf-8")
        self.assertIn("id: project-anchor-dsh", patch)
        self.assertIn(f"name: '{manifest['name']}'", patch)

    def test_patch_config_is_a_subset_of_the_schema(self):
        patch = (BUNDLE / "cordis.patch.yml").read_text(encoding="utf-8")
        body = patch.split("config:", 1)[1]
        used = {line.split(":", 1)[0].strip() for line in body.splitlines()
                if line.startswith("        ") and ":" in line}
        self.assertTrue(used)
        self.assertLessEqual(used, config_keys())

    def test_files_cover_every_runtime_module(self):
        manifest = json.loads((BUNDLE / "package.json").read_text(encoding="utf-8"))
        listed = set(manifest["files"])
        for name in ("index.js", "kit.js", "tools.js", "prompt.js", "cordis.patch.yml",
                     "locale/*.json", "icon.svg"):
            self.assertIn(name, listed)
        for module in ("index.js", "tools.js", "kit.js", "prompt.js"):
            self.assertTrue((BUNDLE / module).is_file(), module)
        index = (BUNDLE / "index.js").read_text(encoding="utf-8")
        for module in ("kit.js", "tools.js", "prompt.js"):
            self.assertIn(f"./{module}", index)

    def test_display_resources_are_real(self):
        for locale in ("en", "zh"):
            value = json.loads((BUNDLE / f"locale/{locale}.json").read_text(encoding="utf-8"))
            title = value["meta"]["title"]
            description = value["meta"]["description"]
            self.assertTrue(title and description)
            self.assertNotIn("template", description.lower())
        icon = BUNDLE / "icon.svg"
        self.assertLessEqual(icon.stat().st_size, 256 * 1024)
        self.assertTrue(icon.read_text(encoding="utf-8").lstrip().startswith("<svg"))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class HostModuleTests(unittest.TestCase):
    """Load the real Host modules with stub Harness packages."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="DSH bundle 中文 ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(BUNDLE, self.root / "bundle")
        shutil.copy(ROOT / "tests/dsh_probe.mjs", self.root / "probe.mjs")
        for name, source in (("dsh-tools", STUB_TOOLS), ("schemastery", STUB_SCHEMASTERY)):
            folder = self.root / "node_modules/@deepseek-ai" / name
            folder.mkdir(parents=True)
            (folder / "package.json").write_text(json.dumps(
                {"name": f"@deepseek-ai/{name}", "type": "module", "exports": "./index.js"}),
                encoding="utf-8")
            (folder / "index.js").write_text(source, encoding="utf-8")
        self.project = self.root / "project 中文"
        self.project.mkdir()
        init_project(self.project, "DSH 探针项目")

    def probe(self, payload):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.run(["node", str(self.root / "probe.mjs"), json.dumps(payload, ensure_ascii=False)],
                              cwd=self.root, capture_output=True, encoding="utf-8",
                              errors="replace", timeout=120, env=env)

    def test_registration_and_schemas(self):
        config = {"kitPath": str(ROOT), "pythonPath": sys.executable}
        done = self.probe({"config": config})
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        names = [tool["name"] for tool in result["tools"]]
        self.assertEqual(names, ["anchor_status", "anchor_doctor"])
        self.assertEqual(result["applied"]["tools"], names)
        self.assertEqual(result["applied"]["sections"], ["project-anchor:governance"])
        for tool in result["tools"]:
            self.assertTrue(tool["description"].strip())
            violations = []
            schema_violations(tool["schema"], tool["name"], violations)
            self.assertEqual(violations, [])
            parameters = tool["parameters"]
            self.assertTrue(0 < len(parameters) <= 8)
            for key, value in parameters.items():
                self.assertTrue(value.get("description"), f"{tool['name']}.{key}")
        self.assertIn("anchor_status", result["section"]["text"])
        self.assertTrue(0 < result["section"]["order"] < 1000)
        # P0 registers a section only; rewriting system-prompt/assemble is refused.
        self.assertIs(result["guard"]["assembleBlocked"], True)

    def test_status_tool_reads_the_real_ledger(self):
        before = (self.project / ".agent/state.json").read_bytes()
        config = {"kitPath": str(ROOT), "pythonPath": sys.executable}
        done = self.probe({"config": config, "run": {
            "tool": "anchor_status", "args": {"path": str(self.project)}, "cwd": str(self.project)}})
        self.assertEqual(done.returncode, 0, done.stderr)
        executed = json.loads(done.stdout)["executed"]
        value = executed["value"]
        self.assertEqual(value["name"], "DSH 探针项目")
        self.assertGreaterEqual(value["revision"], 0)
        self.assertEqual(value["tasks"], [])
        self.assertEqual(executed["blocks"][0]["type"], "text")
        self.assertIn("项目修订", executed["blocks"][0]["text"])
        self.assertEqual((self.project / ".agent/state.json").read_bytes(), before)

    def test_status_tool_fails_loudly_outside_a_project(self):
        stray = self.root / "stray"
        stray.mkdir()
        done = self.probe({"config": {"kitPath": str(ROOT), "pythonPath": sys.executable}, "run": {
            "tool": "anchor_status", "args": {"path": str(stray)}, "cwd": str(stray)}})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("未初始化", done.stderr)


class ContextCommandTests(unittest.TestCase):
    """The read-only injection source shared with the Codex hooks."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Context 中文 ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "项目"
        self.project.mkdir()
        init_project(self.project, "上下文项目")
        self.managed = self.root / "managed"

    def run_kit(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = kit.main(argv)
        return code, out.getvalue(), err.getvalue()

    def trust(self):
        state, _, _ = load(self.project)
        self.managed.mkdir(parents=True, exist_ok=True)
        (self.managed / "trusted-projects.json").write_text(json.dumps({
            str(self.project.resolve()): {
                "project_id": state["project_id"],
                "hashes": {name: state["hashes"][name] for name in ("GOAL.md", "CURRENT.md")},
            }}, ensure_ascii=False), encoding="utf-8")

    def test_untrusted_project_gets_guidance_not_content(self):
        code, out, err = self.run_kit(["context", str(self.project), "--json", "--managed-dir", str(self.managed)])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertFalse(payload["trusted_injected"])
        self.assertIn("未审核", payload["context"])
        self.assertNotIn("上下文项目", payload["context"])

    def test_trusted_project_injects_state_and_writes_nothing(self):
        self.trust()
        before = (self.project / ".agent/state.json").read_bytes()
        code, out, err = self.run_kit(["context", str(self.project), "--json", "--managed-dir", str(self.managed)])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["trusted_injected"])
        self.assertIn('"state_revision"', payload["context"])
        self.assertIn("不是新的行为规则", payload["context"])
        self.assertEqual((self.project / ".agent/state.json").read_bytes(), before)
        self.assertEqual(load(self.project)[0]["revision"], json.loads(before)["revision"])

    def test_limit_truncates_instead_of_failing(self):
        self.trust()
        code, out, err = self.run_kit(["context", str(self.project), "--json", "--managed-dir",
                                       str(self.managed), "--limit", "450"])
        self.assertEqual(code, 0, err)
        self.assertIn('"truncated": true', json.loads(out)["context"])

    def test_uninitialized_directory_is_a_failure(self):
        stray = self.root / "stray"
        stray.mkdir()
        code, out, err = self.run_kit(["context", str(stray), "--json"])
        self.assertEqual(code, 1)
        self.assertIn("未初始化", err)


if __name__ == "__main__":
    unittest.main()
