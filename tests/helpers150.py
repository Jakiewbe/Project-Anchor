"""Explicit fixtures for old workflow tests using the new self-review protocol."""
from core.memory import load
from core.verification import review


def checks_for(project, criteria):
    path = project / "验收材料.txt"
    if not path.exists():
        path.write_text("固定的独立验收材料，不是账本状态", encoding="utf8")
    return [{"criterion": i, "kind": "review", "inputs": [path.name]} for i, _ in enumerate(criteria, 1)]


def review_all(project, tid="T1", details=None):
    task = next(t for t in load(project)[2]["tasks"] if t["task_id"] == tid)
    for index, _ in enumerate(task["acceptance_criteria"], 1):
        review(project, load(project)[0]["revision"], tid,
               {"criterion": index, "findings": "检查fixture的预期结果", "resolution": "按此测试的验收依据核对通过",
                "simpler": "保留当前最小实现", "result": "pass"}, "旧工作流回归的显式自查步骤")
