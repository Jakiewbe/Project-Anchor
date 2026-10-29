"""Opt-in local project-copy replay. Never execute copied business commands.

Copies stay in ignored runtime storage. Export only this script's aggregate JSON;
copied local research/production records are not release assets.
"""
import argparse
import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import kit
from core import memory, verification
from core.tasks import deliverable_coverage
from tests.test_migration import old_archive


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    sources = {
        "virtuals": Path(r"D:\Vibe_coding-Project\Virtualsalpha"),
        "origin": Path(r"C:\Users\chs\Desktop\OriginMaster"),
        "opeis": Path(r"D:\Vibe_coding-Project\OPEISMaster"),
        "eis": Path(r"D:\Vibe_coding-Project\EISMaster"),
    }
    checks, protections = [], {}
    def check(name, passed):
        checks.append({"case": name, "pass": bool(passed)})
        if not passed:
            raise AssertionError(name)
    for label, source in sources.items():
        target = output / label
        files = [source / ".agent" / name for name in ["state.json", *memory.FILES, "PROGRESS.md"]]
        for folder in ["evidence", "history"]:
            files += [p for p in (source / ".agent" / folder).rglob("*") if p.is_file()]
        if label == "origin":
            ledger = json.loads((source / ".agent/tasks.json").read_text(encoding="utf-8-sig"))
            for entry in {i for t in ledger["tasks"] for c in t.get("checks", []) for i in c["inputs"]}:
                path = source / entry
                files += [p for p in path.rglob("*") if p.is_file()] if path.is_dir() else [path] if path.is_file() else []
            # The old checks omitted these actual delivered artifacts.
            for entry in ["catalog/shared-library", "templates/shared/xy"]:
                files += [p for p in (source / entry).rglob("*") if p.is_file()]
        before = {}
        for path in sorted(set(files)):
            relative = path.relative_to(source)
            data = path.read_bytes()
            before[relative.as_posix()] = hashlib.sha256(data).hexdigest()
            dest = target / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        protections[label] = (source, before)
        state, content, ledger = memory.load(target)
        if label == "virtuals":
            check("virtuals-same-revision-not-semantic-proof", state["current_task_revision"] == ledger["revision"]
                  and memory.current_alignment(state) == "unknown")
        tasks_before = ledger["tasks"]
        memory.migrate(target, state["revision"], "authorized copy preflight", dry_run=True)
        migration = memory.migrate(target, state["revision"], "authorized copy only")
        s, _, upgraded = memory.load(target)
        check(label + "-tasks-preserved", tasks_before == upgraded["tasks"] if ledger["schema"] == 3 else
              [(t["task_id"], t["status"]) for t in tasks_before] == [(t["task_id"], t["status"]) for t in upgraded["tasks"]])
        if label == "virtuals":
            check("virtuals-unknown-despite-current-revision", not (s["current_task_revision"] == upgraded["revision"])
                  and memory.current_alignment(s) == "unknown")
            ids = [upgraded["tasks"][0]["task_id"]]
            memory.focus_change(target, s["revision"], ids, "explicit test focus")
            memory.doc_change(target, memory.load(target)[0]["revision"], "CURRENT.md", content["CURRENT.md"],
                              "explicit copy binding", task_ids=ids)
            check("virtuals-explicit-binding", memory.current_alignment(memory.load(target)[0]) == "aligned")
            memory.focus_change(target, memory.load(target)[0]["revision"], None, "different scope")
            check("virtuals-focus-mismatch", memory.current_alignment(memory.load(target)[0]) == "changed")
        if label == "origin":
            old = old_archive(output / "old-version", "090efe2cd70ac3dc9f32cd9b8536b51cfacc14e7")
            metrics = '''from pathlib import Path
import json,sys,time
from core.memory import load
from core.verification import state
p=Path(sys.argv[1]);s,c,l=load(p);start=time.perf_counter();count=[0];real=Path.read_bytes
def read(path):
 if path.is_relative_to(p) and not path.is_relative_to(p/'.agent'):count[0]+=1
 return real(path)
Path.read_bytes=read
values={t['task_id']:state(p,t) for t in l['tasks']}
print(json.dumps({'seconds':time.perf_counter()-start,'business_reads':count[0],'tasks':len(values)}))
'''
            # Baseline reader accepts schema3; run against the untouched source in read-only mode.
            p = subprocess.run([sys.executable, "-B", "-c", metrics, str(source)], cwd=old, capture_output=True, encoding="utf8", check=True)
            baseline = json.loads(p.stdout)
            reads = [0]
            original = Path.read_bytes
            def read(path):
                if path.is_relative_to(target) and not path.is_relative_to(target / ".agent"):
                    reads[0] += 1
                return original(path)
            stdout = io.StringIO()
            start = time.perf_counter()
            with patch.object(Path, "read_bytes", read), redirect_stdout(stdout):
                code = kit.main(["status", str(target), "--brief", "--focus"])
            elapsed = time.perf_counter() - start
            check("origin-focused-query", code == 0)
            view = json.loads(stdout.getvalue())
            check("origin-no-unrelated-fingerprints", reads[0] < baseline["business_reads"])
            (output / "performance.json").write_text(json.dumps({"old_all_before_filter": baseline,
                "new_focus": {"seconds": elapsed, "business_reads": reads[0], "tasks": len(view["tasks"])}}, indent=2), encoding="utf8")
            current = next(t for t in upgraded["tasks"] if t["task_id"] == "T15")
            check("origin-old-coverage-undeclared", deliverable_coverage(current) == "undeclared")
            revision = lambda: memory.load(target)[0]["revision"]
            memory.task_change(target, revision(), "revise", {"task_id": "T15"}, "copy test")
            deliverables = ["catalog/shared-library/theme.json", "templates/shared/xy"]
            memory.task_change(target, revision(), "update", {"task_id": "T15", "deliverables": deliverables}, "actual artifacts")
            try:
                memory.task_change(target, revision(), "approve", {"task_id": "T15"}, "uncovered", source="user")
            except Exception as exc:
                check("origin-uncovered-approval-rejected", "未被" in str(exc))
            else:
                check("origin-uncovered-approval-rejected", False)
            checks_config = [{**c, "inputs": c["inputs"] + deliverables} for c in current["checks"]]
            memory.task_change(target, revision(), "update", {"task_id": "T15", "checks": checks_config}, "bind actual artifacts")
            memory.task_change(target, revision(), "approve", {"task_id": "T15"}, "copy only", source="user")
            task = next(t for t in memory.load(target)[2]["tasks"] if t["task_id"] == "T15")
            check("origin-covered-approved", deliverable_coverage(task) == "covered")
            # Test the narrow artifact fingerprint without pretending to rerun Origin.
            original_hash = verification.fingerprint(target, deliverables)
            (target / "unrelated.txt").write_text("unrelated", encoding="utf8")
            check("origin-unrelated-file-stable", verification.fingerprint(target, deliverables) == original_hash)
            theme = target / deliverables[0]
            theme.write_bytes(theme.read_bytes() + b"\n")
            check("origin-theme-change-detected", verification.fingerprint(target, deliverables) != original_hash)
        if label in {"opeis", "eis"}:
            existing = target / ".agent/RETRO.md"
            body = memory.retro(target).read_text(encoding="utf8")
            check(label + "-retro-index-only", '"scope_version"' not in body and "GOAL.md" in body and "LESSONS.md" in body)
            check(label + "-goal-remains-unapproved", not memory.load(target)[0]["goal_approved"])
        check(label + "-backup-present", Path(migration["backup"]).is_dir())
    for label, (source, before) in protections.items():
        check(label + "-source-unchanged", all(hashlib.sha256((source / name).read_bytes()).hexdigest() == value
                                               for name, value in before.items()))
    result = {"passed": sum(c["pass"] for c in checks), "failed": sum(not c["pass"] for c in checks),
              "cases": checks, "scope": "Local copies and recorded artifacts only; no instrument, production or copied business commands executed."}
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output.resolve())
