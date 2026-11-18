# 载荷模板与编码约定

本文件提供可直接复用的 JSON 与 Markdown 模板。**在 Windows PowerShell 中传递中文/UTF-8 载荷时**，优先写入项目内忽略目录 `.agent/runtime/skill-input/`（未初始化项目用系统临时目录）后传 `--file`，或确保以 UTF-8 字节流通过 stdin 传入，避免 PowerShell 管道编码失真或重复转换 CRLF。

```powershell
# PowerShell UTF-8 文件写入 + 调用示例（安全、无编码歧义）
$inputDir = Join-Path $project '.agent/runtime/skill-input'
New-Item -ItemType Directory -Force -Path $inputDir | Out-Null
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText((Join-Path $inputDir 'task.json'), $jsonText, $utf8NoBom)
& $python '-X' 'utf8' $runner 'task' 'add' $project '--file' (Join-Path $inputDir 'task.json') '--expected-revision' $rev '--reason' '创建任务草案'
```

---

## 1. 任务草案 JSON（`task add`）

所有路径均为项目相对路径（使用 `/`），`deliverables` 必须完全被 `checks[].inputs` 覆盖，无本地文件交付时显式填 `[]`：

```json
{
  "task_id": "T1",
  "title": "实现核心功能并完成验证",
  "description": "用户本轮明确授权的范围与目标",
  "milestone": "v1.0",
  "dependencies": [],
  "deliverables": [
    "src/module.py",
    "tests/test_module.py"
  ],
  "acceptance_criteria": [
    "单元测试全部通过",
    "代码经 Bug 与第一性原理简化审查"
  ],
  "checks": [
    {
      "criterion": 1,
      "kind": "command",
      "inputs": ["src/module.py", "tests/test_module.py"],
      "argv": ["C:/Python311/python.exe", "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-q"],
      "timeout_seconds": 600
    },
    {
      "criterion": 2,
      "kind": "review",
      "inputs": ["src/module.py", "tests/test_module.py"]
    }
  ]
}
```

> 注意：请将 `argv` 中的 Python 路径替换为 `runtime.json` 中的真实 `python` 路径；建议带 `-B` 防止生成 `__pycache__` 污染输入目录。

---

## 2. 状态流转 JSON（`task update`）

```json
{"task_id": "T1", "status": "doing"}
```

```json
{"task_id": "T1", "status": "blocked", "blocker": "缺少测试设备或外部授权"}
```

```json
{"task_id": "T1", "status": "done"}
```

---

## 3. Agent 自查 JSON（`task review`）

适用于 `kind: "review"` 的验收标准；程序固定记录 `level=claimed, reviewer_kind=self`：

```json
{
  "criterion": 2,
  "findings": "逐行核对边界条件与异常处理，未发现竞态或静默失败风险",
  "resolution": "已确认实现逻辑与文档一致，无需额外修复",
  "simpler": "复用现有原子写入与锁辅助函数，无重复分支或多余抽象",
  "result": "pass"
}
```

---

## 4. 项目目标文档（`GOAL.md`）

必须完整保留以下 **6 个二级标题**；首次批准或变更时须传 `--approved`：

```markdown
# <项目名称> 项目目标

## 核心目标
一句话说明最终交付物与核心价值。

## 项目背景
说明立项背景与现状约束。

## 关键约束
运行环境、技术栈、安全与授权边界。

## 非目标
明确本阶段不做的事项，防止范围蔓延。

## 验收标准
项目整体可客观核对的完成条件。

## 目标版本
1
```

---

## 5. 工作断点文档（`CURRENT.md`）

必须完整保留以下 **7 个二级标题**，总行数 **≤ 50 行**；保存时必须传 `--task ID`（可重复）或 `--no-task`：

```markdown
# 当前断点

## 当前阶段
当前所处里程碑或工作阶段。

## 当前任务
T1 doing（或无活动任务说明）。

## 已完成工作
简述已落盘并有证据支撑的成果与关键路径。

## 当前阻塞
无；或明确列出外部依赖、未验缺口与环境阻塞。

## 下一步动作
下一会话或下一步应立即执行的精确动作。

## 状态修订
以最新 state.json 与 tasks.json 为准；关键决定已写入 DECISIONS.md。

## Git 检查
当前分支、未提交改动说明（不擅自提交或推送）。
```

---

## 6. 跨项目知识入库 JSON（`knowledge-add --approved`）

```json
{
  "title": "简短经验标题",
  "conditions": "适用场景与前置条件",
  "evidence": "真实运行凭据、测试结果或复现日志位置",
  "limitations": "已知边界与不适用情况",
  "source_project": "来源项目名称",
  "lesson": "可复用的具体做法或避坑结论"
}
```
