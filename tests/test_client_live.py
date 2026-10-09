"""Evidence completeness checks; no model requests or user configuration changes."""
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_live import capture_client, fingerprint, codex, main


class ClientEvidenceTests(unittest.TestCase):
    def test_failed_request_preserves_full_raw_output(self):
        with tempfile.TemporaryDirectory(prefix="证据 中文 空格 ") as directory:
            project = Path(directory) / "项目"
            project.mkdir()
            source = "import sys; sys.stdout.buffer.write(b'A'*5000); sys.stderr.buffer.write(b'B'*3000); sys.exit(7)"
            result = capture_client([sys.executable, "-c", source], project, "fixture")
            evidence = Path(result.evidence)
            self.assertEqual(result.returncode, 7)
            self.assertEqual((evidence / "stdout.jsonl").read_bytes(), b"A" * 5000)
            self.assertEqual((evidence / "stderr.txt").read_bytes(), b"B" * 3000)
            self.assertEqual(json.loads((evidence / "request.json").read_text(encoding="utf-8"))["returncode"], 7)

    def test_fingerprint_includes_full_file_hashes_before_initialization(self):
        with tempfile.TemporaryDirectory(prefix="哈希 中文 空格 ") as directory:
            project = Path(directory)
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            draft = project / ".agent/runtime/draft.json"
            draft.parent.mkdir(parents=True)
            draft.write_bytes(b"original")
            before = fingerprint(project)
            draft.write_bytes(b"changed")
            after = fingerprint(project)
            self.assertFalse(before["initialized"])
            self.assertEqual(before["agent_hashes"]["runtime/draft.json"], hashlib.sha256(b"original").hexdigest())
            self.assertNotEqual(before["agent_hashes"], after["agent_hashes"])

    def test_timeout_preserves_partial_output_and_propagates(self):
        with tempfile.TemporaryDirectory(prefix="超时证据 中文 空格 ") as directory:
            project = Path(directory) / "项目"
            project.mkdir()
            failure = subprocess.TimeoutExpired(['client'], 1, output=b'partial', stderr=b'error')
            with patch('client_live.subprocess.run', side_effect=failure):
                with self.assertRaises(subprocess.TimeoutExpired):
                    capture_client(['client'], project, 'fixture', timeout=1)
            folder = next((project.parent / 'raw-client').iterdir())
            self.assertEqual((folder / 'stdout.jsonl').read_bytes(), b'partial')
            self.assertEqual((folder / 'stderr.txt').read_bytes(), b'error')

    def test_start_failure_keeps_original_exception_and_request(self):
        with tempfile.TemporaryDirectory(prefix="启动证据 中文 空格 ") as directory:
            project = Path(directory) / "项目"
            project.mkdir()
            with patch('client_live.subprocess.run', side_effect=FileNotFoundError('missing')):
                with self.assertRaises(FileNotFoundError):
                    capture_client(['client'], project, 'fixture')
            folder = next((project.parent / 'raw-client').iterdir())
            record = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
            self.assertIn('FileNotFoundError', record['error'])

    def test_codex_reports_config_changes_without_logging_config_content(self):
        with tempfile.TemporaryDirectory(prefix="配置守卫 中文 空格 ") as directory:
            home = Path(directory)
            config = home / 'config.toml'
            config.write_text('private-placeholder',encoding='utf-8')
            def changed(*args):
                config.write_text('private-placeholder\nadded-project',encoding='utf-8')
                return SimpleNamespace(stdout='{"type":"turn.completed"}\n',stderr='',returncode=0,evidence='fixture')
            with patch.dict(os.environ,{'CODEX_HOME':str(home)}), patch('client_live.shutil.which',return_value='codex'), \
                 patch('client_live.capture_client',side_effect=changed):
                result = codex(home,'fixture')
            self.assertTrue(result['user_config_changed'])
            self.assertNotEqual(result['user_config_before_sha256'],result['user_config_after_sha256'])
            self.assertNotIn('private-placeholder',json.dumps(result))

    def test_workflow_timeout_keeps_before_and_after_fingerprints(self):
        with tempfile.TemporaryDirectory(prefix="回合证据 中文 空格 ") as directory:
            project = Path(directory)
            subprocess.run(['git','init','-q',str(project)],check=True)
            (project/'hello.py').write_text('def add(a, b):\n    return a + b\n',encoding='utf-8')
            result_file = project/'result.json'
            failure = subprocess.TimeoutExpired(['client'],1)
            failure.evidence = 'partial-raw-response'
            arguments = ['client_live.py','--primary','claude','--secondary','none','--out',str(result_file)]
            with patch.object(sys,'argv',arguments), patch('client_live.setup',return_value=(project,{})), \
                 patch('client_live.claude',side_effect=failure):
                with self.assertRaises(SystemExit) as stopped:
                    main()
            self.assertEqual(stopped.exception.code,1)
            record = json.loads(result_file.read_text(encoding='utf-8'))
            self.assertEqual(len(record['steps']),1)
            step = record['steps'][0]
            self.assertEqual(step['before'],step['after'])
            self.assertEqual(step['raw'],'partial-raw-response')
            self.assertFalse(step['checks']['ok'])
