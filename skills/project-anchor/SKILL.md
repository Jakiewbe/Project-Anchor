---
name: project-anchor
description: "用自然语言管理项目的长期目标(GOAL)、工作断点(CURRENT)、任务账本与交付验收(tasks/verify/review)、决策教训(DECISIONS/LESSONS)、会话交接(snapshot)、诊断(doctor)与复盘(retro)。Use for file-based AI project governance, planning/focus status, deliverable-bound verification, decisions, handoff and diagnostics. 当用户明确要求治理、规划、接续或可信全局规则授权首次实际项目工作时接入；纯只读问答、代码解释或仅改指定文件不初始化也不额外写治理记录。"
metadata:
  version: "1.6.0"
---

# Project Anchor

通过唯一 Python 核心 `kit.py` 维护项目磁盘事实（`.agent/`）。日常使用无需用户手输命令，不依赖 Codex 客户端，不复制核心逻辑或第二份账本。

## 1. 定位与调用

1. **确认目标项目根目录**：优先取用户指向的项目（有 `.git` 则核对仓库根），确认 `.agent/state.json`。严禁把 Skill 目录、工具箱目录、用户主目录或磁盘根目录当目标项目。
2. **读取安装定位**：读取本 Skill 根目录 `runtime.json`，取得 `python` 绝对路径。
3. **以独立参数调用 `scripts/run.py`**（保留目标项目工作目录，不依赖 PATH，不拼接 shell 字符串）：

```powershell
# Windows PowerShell
& $python '-X' 'utf8' $runner 'status' $project '--brief' '--focus'
```

```bash
# macOS / Linux
"$python" -X utf8 "$runner" status "$project" --brief --focus
```

4. **串联修订号**：每次成功写入都会返回最新 `revision`。可直接将返回的 `revision` 传入下一步 `--expected-revision`；遇冲突、损坏或未完成事务立即停止并重读状态，不自动重试覆盖。

## 2. 范围与阶段门禁

先按当前请求与已有明确授权判断停止位置，不用关键词硬猜权限：

| 用户意图 | 允许动作 | 停止边界 |
| --- | --- | --- |
| 只读问答 / 评估 / 确认后再继续 | `status` / `doctor` / `history` / `verify show` | 不初始化、不建任务、不写治理或业务文件 |
| 仅批准或变更总目标 | `state update GOAL.md --approved` | 不顺便拆任务、不开始实施 |
| 制定计划，先不执行 | `task add` 创建 `draft` | 不自动 `approve`、不转 `doing`、不改业务 |
| 明确局部任务授权（即使总目标待确认） | 登记局部任务、`task approve`、`focus set` 并执行 | `description`/`reason` 写清授权范围，不替用户批总目标 |
| 已确定技术路线（如“改用 JSON，先看模板”） | 允许治理写入时当回合写 `DECISIONS.md` | 停在所要求动作，不顺便实施代码 |
| 仅修改指定业务文件 | 按指定范围改文件 | 不初始化项目，不额外写 `.agent/` 记录 |
| 首次接入（用户要求或可信全局规则授权） | `init-project`（默认不传 `--git-init`） | 仅创建 `.agent/` 与追加 `AGENTS.md` / `.gitignore` / `.gitattributes` |

## 3. 接续与主链路

1. **接续必先读盘**：执行 `status PATH --brief --focus`，读取完整 `goal`、`current` 与 `current_alignment`（`unknown` / `changed` / `aligned`）。
   - `focus_missing=true` 时不按更新时间猜历史任务：先 `status PATH --brief`（或 `--all`）核对任务并确认本轮范围，再 `focus set`。
   - 关注 `verification_state`（`pass` / `stale` / `pending` / `failed` / `invalid` / `legacy`）与 `deliverable_coverage`（`covered` / `uncovered` / `undeclared`）。
2. **任务与验收闭环**：
   - `task add` 建草案（显式声明 `deliverables`——无本地文件填 `[]`，且每项须被 `checks.inputs` 覆盖）。
   - 用户批准或授权实施具体方案后，`task approve --source user|policy` 锁定批准快照，再 `focus set` 设为本轮任务。
   - 实施前 `task update` 转 `doing`；完成后按检查类型验收：`command` 走 `verify run`（程序采集 `observed` 凭据），`review` 先查 Bug 再做第一性原理简化自查后走 `task review`（固定记录 `claimed/self`）。
   - 全部当前检查通过且交付物存在，才 `task update` 转 `done`。
3. **交接与复盘**：
   - 更新 `CURRENT.md` 必须传 `--task ID`（可重复）或互斥 `--no-task`，保持 7 个必要章节且不超过 50 行；随后可 `snapshot` 留档。
   - 项目收尾用 `retro` 生成索引草案；跨项目经验需用户确认具体条目后才 `knowledge-add --approved`。

## 4. 核心铁律

- **不手改受保护状态**：禁止直接编辑 `tasks.json`、`state.json`、`PROGRESS.md`；外部编辑了 Markdown 文档需审核后 `state adopt`。
- **不混用证明层级**：`--source user` 只是调用声明；退出码 0 不自动等于语义满足；自查（`claimed/self`）与命令（`observed`）不可互换；未实测内容不能报通过。
- **不静默改范围或重写历史**：改已批准任务的描述、标准、依赖、`checks` 或 `deliverables` 必须先 `task revise` 再重新 `task approve`；schema 1/2/3 旧账本写入前先 `migrate`；旧任务继续或作依赖前须补齐声明并重批。
- **不擅自操作 Git**：未获用户明确要求，不提交、不新建分支或工作树、不推送。
- **核对真实写入**：写入后核对退出码与返回值；`changed=false` 表示内容和元数据无变化未写入，不能报告为新增保存。

## 5. 按需参考（渐进加载）

仅在需要对应细节时读取 `references/`：

| 需要什么 | 读取文件 |
| --- | --- |
| 各场景完整 SOP（初始化、规划、更新任务、迁移、交接、诊断、复盘） | [references/WORKFLOWS.md](references/WORKFLOWS.md) |
| 全部 CLI 参数、schema 4 约束、筛选规则与故障恢复手册 | [references/COMMANDS.md](references/COMMANDS.md) |
| 可直接复制的 JSON / Markdown 模板与 PowerShell UTF-8 输入写法 | [references/TEMPLATES.md](references/TEMPLATES.md) |
| 客户端能力边界、安装入口（Codex / 通用 / DSH / Claude）与信任说明 | [references/CLIENTS.md](references/CLIENTS.md) |
