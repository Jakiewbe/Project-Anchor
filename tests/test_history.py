"""Bounded state history and folded brief task views.

Program code never reads history content; it exists for audit and can be
recovered from git or snapshots. These tests pin the two degradation steps:
recent document text stays, older revisions keep only digests, and the entry
count is capped with a single rolling prune marker.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.memory import HISTORY_KEEP, DOC_CONTENT_KEEP, doc_change, init_project, load, prune_history, task_change
from core.tasks import task_view


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Anchor 历史 中文 ")
        self.project = Path(self.tmp.name) / "项目"
        init_project(self.project, "历史")
        self.current = (self.project / ".agent/CURRENT.md").read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def state(self):
        return load(self.project)[0]

    def save(self, marker):
        return doc_change(self.project, self.state()["revision"], "CURRENT.md",
                          self.current + "\n" + marker, "记录断点")

    def documents(self, state):
        return [entry for entry in state["history"] if entry.get("action") == "document-version"]

    def markers(self, state):
        return [entry for entry in state["history"] if entry.get("action") == "history:prune"]

    def test_defaults_stay_within_the_validated_range(self):
        self.assertGreaterEqual(DOC_CONTENT_KEEP, 1)
        self.assertGreater(HISTORY_KEEP, DOC_CONTENT_KEEP)

    def test_recent_document_text_survives_and_older_content_is_pruned(self):
        with patch("core.memory.DOC_CONTENT_KEEP", 3):
            for index in range(6):
                self.save(f"第 {index} 次")
            documents = self.documents(self.state())
        kept = [entry for entry in documents if "content" in entry]
        pruned = [entry for entry in documents if entry.get("content_pruned")]
        self.assertEqual(len(kept), 3)
        self.assertEqual(len(pruned), 3)
        self.assertEqual(kept[-1]["content"], self.current + "\n第 5 次")
        for entry in pruned:
            self.assertEqual(entry["file"], "CURRENT.md")
            self.assertIn("previous_sha256", entry)
            self.assertIn("timestamp", entry)

    def test_entry_count_is_capped_with_one_rolling_marker(self):
        with patch("core.memory.HISTORY_KEEP", 10), patch("core.memory.DOC_CONTENT_KEEP", 2):
            for index in range(12):
                self.save(f"第 {index} 次")
            state = self.state()
            self.assertLessEqual(len(state["history"]), 10)
            markers = self.markers(state)
            self.assertEqual(len(markers), 1)
            self.assertGreater(markers[0]["dropped"], 0)
            self.assertLess(markers[0]["dropped_revision_min"], markers[0]["dropped_revision_max"])
            self.assertEqual(state["history"][-1]["revision"], state["revision"])
            dropped = markers[0]["dropped"]
            for index in range(3):
                self.save(f"追加 {index} 次")
            state = self.state()
        self.assertLessEqual(len(state["history"]), 10)
        markers = self.markers(state)
        self.assertEqual(len(markers), 1)
        self.assertGreater(markers[0]["dropped"], dropped)
        self.assertEqual(state["history"][-1]["revision"], state["revision"])

    def test_prune_helper_leaves_a_short_history_untouched(self):
        state = self.state()
        before = json.dumps(state["history"], ensure_ascii=False)
        prune_history(state)
        self.assertEqual(json.dumps(state["history"], ensure_ascii=False), before)

    def test_no_new_state_schema_or_required_key_is_introduced(self):
        path = self.project / ".agent/state.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(value["schema"], 1)
        self.assertNotIn("history_keep", value)
        self.save("无需迁移")
        value = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(value["schema"], 1)
        self.assertEqual(load(self.project)[0]["revision"], value["revision"])


class BriefViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Anchor 视图 中文 ")
        self.project = Path(self.tmp.name) / "项目"
        init_project(self.project, "视图")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, action, payload, source=None):
        return task_change(self.project, load(self.project)[0]["revision"], action, payload, "测试", source=source)

    def add(self, task_id, **fields):
        self.write("add", {"task_id": task_id, "title": f"任务 {task_id}", "description": "范围",
                           "acceptance_criteria": ["完成"], **fields})
        self.write("approve", {"task_id": task_id}, source="user")

    def finish(self, task_id):
        self.write("update", {"task_id": task_id, "status": "doing"})
        self.write("update", {"task_id": task_id, "status": "done",
                              "evidence": [{"type": "test", "criterion": 1, "detail": "断言通过"}]})

    def view(self, **kwargs):
        return task_view(load(self.project)[2], **kwargs)

    def test_brief_folds_finished_tasks_but_keeps_counts(self):
        self.add("DONE")
        self.finish("DONE")
        self.add("OPEN")
        visible, summary, _ = self.view(brief=True)
        self.assertEqual([task["task_id"] for task in visible], ["OPEN"])
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["folded_final"], 1)
        self.assertEqual(summary["statuses"]["done"], 1)
        self.assertEqual(summary["approved_done"], 1)

    def test_include_final_returns_every_task(self):
        self.add("DONE")
        self.finish("DONE")
        self.add("OPEN")
        visible, summary, _ = self.view(brief=True, include_final=True)
        self.assertEqual(sorted(task["task_id"] for task in visible), ["DONE", "OPEN"])
        self.assertEqual(summary["folded_final"], 0)

    def test_explicit_selection_is_never_folded(self):
        self.add("DONE")
        self.finish("DONE")
        visible, summary, _ = self.view(brief=True, task_ids=["DONE"])
        self.assertEqual([task["task_id"] for task in visible], ["DONE"])
        self.assertEqual(visible[0]["status"], "done")
        self.assertEqual(summary["folded_final"], 0)
        visible, _, _ = self.view(brief=True, milestone="默认")
        self.assertEqual([task["task_id"] for task in visible], ["DONE"])

    def test_full_view_still_returns_every_field(self):
        self.add("DONE")
        self.finish("DONE")
        visible, summary, _ = self.view()
        self.assertEqual(summary["folded_final"], 0)
        self.assertIn("evidence", visible[0])


if __name__ == "__main__":
    unittest.main()
