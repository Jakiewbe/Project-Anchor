"""Brand migration must preserve owned data, user files and crash recovery."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import kit
from core import atomic_io as io
from core.config import install, locations
from core.memory import init_project, load, rename_project


class RenameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='Project Anchor 改名 空格 ')
        self.root = Path(self.tmp.name)
        self.home = self.root/'配置'
        self.parent = self.root/'skills'
        self.target = self.parent/'project-anchor'
        self.legacy = self.parent/'codex-rules'
        install(self.home, self.parent)
        self.manifest = locations(self.home)[0]/'install.json'
        value = io.read_json(self.manifest)
        self.legacy.mkdir()
        for name in value['skill']['hashes']:
            source = self.target/name
            data = source.read_bytes()
            if name == 'SKILL.md':
                data = data.replace(b'name: project-anchor', b'name: codex-rules')
            target = self.legacy/name
            io.atomic_write(target, data)
            value['skill']['hashes'][name] = io.digest(data)
            source.unlink()
        value['version'] = '1.1.4'
        value['skill']['path'] = str(self.legacy)
        value['skill']['version'] = '1.1.4'
        io.atomic_write(self.manifest, io.encode_json(value))
        self.before = {p:p.read_bytes() for p in [self.manifest,self.home/'AGENTS.md',self.home/'hooks.json',
                         *(self.legacy/name for name in value['skill']['hashes'])]}

    def tearDown(self):
        self.tmp.cleanup()

    def assert_legacy_restored(self):
        self.assertTrue(all(p.read_bytes()==data for p,data in self.before.items()))
        self.assertFalse((self.target/'SKILL.md').exists())

    def test_migration_preserves_user_files_and_is_idempotent(self):
        note=self.legacy/'personal-notes.md'
        note.write_text('keep user content', encoding='utf-8')
        other=self.parent/'unrelated/SKILL.md'
        io.atomic_write(other,b'not ours')
        result=install(self.home,self.parent)
        self.assertEqual(io.read_json(self.manifest)['skill']['path'],str(self.target))
        self.assertIn(b'name: project-anchor',(self.target/'SKILL.md').read_bytes())
        self.assertFalse((self.legacy/'SKILL.md').exists())
        self.assertEqual(note.read_text(),'keep user content')
        self.assertEqual(other.read_bytes(),b'not ours')
        self.assertEqual((Path(result['backup'])/'legacy_skill/SKILL.md').read_bytes(),self.before[self.legacy/'SKILL.md'])
        self.assertFalse(install(self.home,self.parent)['changed'])

    def test_foreign_new_name_stops_without_overwriting_legacy(self):
        io.atomic_write(self.target/'SKILL.md',b'foreign skill')
        with self.assertRaises(io.KitError): install(self.home,self.parent)
        self.assertTrue(all(p.read_bytes()==data for p,data in self.before.items()))
        self.assertEqual((self.target/'SKILL.md').read_bytes(),b'foreign skill')

    def test_edited_legacy_stops_before_migration(self):
        path=self.legacy/'SKILL.md'
        path.write_bytes(b'user edit')
        with self.assertRaises(io.KitError): install(self.home,self.parent)
        self.assertEqual(path.read_bytes(),b'user edit')
        self.assertEqual(self.manifest.read_bytes(),self.before[self.manifest])
        self.assertFalse((self.target/'SKILL.md').exists())

    def test_migration_failure_rolls_back_both_skill_directories(self):
        original=io._put
        def fail(path,data):
            if Path(path)==self.legacy/'SKILL.md' and data is None:
                raise OSError('injected legacy removal error')
            return original(path,data)
        with patch('core.atomic_io._put',side_effect=fail):
            with self.assertRaises(OSError): install(self.home,self.parent)
        self.assert_legacy_restored()

    def crash_and_recover(self, when):
        original=io.atomic_write
        def crash(path,data):
            original(path,data)
            if Path(path)==when:
                raise KeyboardInterrupt()
        with patch('core.atomic_io.atomic_write',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt): install(self.home,self.parent)
        self.assertEqual(kit.main(['recover','--global','--codex-home',str(self.home),'--skills-dir',str(self.parent),'--rollback']),0)
        self.assert_legacy_restored()

    def test_migration_crash_before_manifest_recovers(self):
        self.crash_and_recover(self.target/'scripts/run.py')

    def test_migration_crash_after_manifest_recovers(self):
        self.crash_and_recover(self.manifest)

    def test_legacy_transaction_recovery_keeps_original_skill_scope(self):
        # A pending 1.1.4 transaction must not be mistaken for a rename migration.
        path=self.legacy/'SKILL.md'
        original=io.atomic_write
        def crash(target,data):
            original(target,data)
            if Path(target)==path:
                raise KeyboardInterrupt()
        with patch('core.atomic_io.atomic_write',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                io.transaction(self.home,locations(self.home)[2],{path:b'interrupted old update'},
                               additional_roots={'skill':self.legacy})
        self.assertEqual(kit.main(['recover','--global','--codex-home',str(self.home),'--rollback']),0)
        self.assert_legacy_restored()

    def test_project_rename_keeps_ledger_and_updates_progress(self):
        project=self.root/'项目'
        init_project(project,'old name')
        ledger=(project/'.agent/tasks.json').read_bytes()
        self.assertEqual(rename_project(project,0,'Project Anchor','用户授权改名'),1)
        self.assertEqual(load(project)[0]['name'],'Project Anchor')
        self.assertEqual((project/'.agent/tasks.json').read_bytes(),ledger)
        self.assertIn('Project Anchor',(project/'.agent/PROGRESS.md').read_text(encoding='utf-8'))

    def test_project_rename_stale_revision_preserves_all_state(self):
        project=self.root/'项目'
        init_project(project,'old name')
        rename_project(project,0,'Project Anchor','用户授权改名')
        before={p:p.read_bytes() for p in (project/'.agent').iterdir() if p.is_file()}
        with self.assertRaises(io.KitError): rename_project(project,0,'stale name','旧会话请求')
        self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
