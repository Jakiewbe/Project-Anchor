# 命令与故障恢复参考

所有状态操作统一经由 Skill 目录的 `scripts/run.py` 转发给唯一 `kit.py`。先读取本 Skill 根目录 `runtime.json` 中的 `python` 绝对路径，再以参数数组调用 `scripts/run.py`（保留目标项目 `cwd`，不依赖 PATH）。

```powershell
# PowerShell 标准调用方式（使用参数数组，避免字符串拼接）
& $python '-X' 'utf8' $runner 'status' $project '--brief' '--focus'
```

**效率技巧**：每次写入成功均输出最新 `{"revision": N, ...}`，下一条连续写入可直接复用该 `N` 作为 `--expected-revision`，无需每次额外跑 `status`。

---

## 1. 全量命令速查

| 类别 | 命令与参数 | 说明 |
| --- | --- | --- |
| 定位 | `--locate` | 输出 `runtime.json` 内容，核对安装来源与路径 |
| 初始化 | `init-project PATH --name NAME [--git-init]` | 创建 `.agent/` 并追加 `AGENTS.md`/`.gitignore`/`.gitattributes` |
| 更名 | `rename-project PATH --name NAME --expected-revision N --reason TEXT` | 经用户授权更新项目显示名称及 `PROGRESS.md` |
| 状态查询 | `status PATH [--brief] [--all] [--focus] [--task ID ...] [--milestone NAME]` | 只读查询；`--brief --focus` 为接续默认入口 |
| 重建视图 | `status PATH --rebuild` | 独立重建 `PROGRESS.md`，禁止与筛选参数组合 |
| 本轮指针 | `focus set PATH --task ID [--task ID ...] --expected-revision N --reason TEXT` | 绑定显式本轮任务；清空用 `focus clear PATH ...`（不传 `--task`） |
| 任务草案 | `task add PATH (--file JSON \| --json-input) --expected-revision N --reason TEXT` | 创建 `draft` 任务；支持 stdin UTF-8 JSON |
| 任务更新 | `task update PATH (--file JSON \| --json-input) --expected-revision N --reason TEXT` | 更新状态/非冻结字段；不可修改 `plan` 或批准字段 |
| 任务批准 | `task approve PATH --task-id ID --source user\|policy --expected-revision N --reason TEXT` | 锁定 `approved_scope` 快照（`--source` 仅调用声明） |
| 任务修订 | `task revise PATH --task-id ID --expected-revision N --reason TEXT` | 将已批准任务退回 `draft/todo` 并使旧证据失效 |
| 命令验收 | `verify run PATH --task ID --criterion N --expected-revision N --reason TEXT` | 执行已批准 `argv`，保存 `observed` 凭据 |
| 自查验收 | `task review PATH --task-id ID (--file JSON \| --json-input) --expected-revision N --reason TEXT` | 提交结构化自查结论，固定记录 `claimed/self` |
| 查验凭据 | `verify show PATH --run-id ID` | 只读查询 `.agent/evidence/` 及日志完整性 `logs_available` |
| 状态文档 | `state update PATH GOAL.md\|CURRENT.md\|DECISIONS.md\|LESSONS.md (--file MD \| --text-input) --expected-revision N --reason TEXT [--approved] [--task ID ... \| --no-task]` | `GOAL.md` 变更须 `--approved`；`CURRENT.md` 必传 `--task` 或 `--no-task` |
| 外部采纳 | `state adopt PATH <DOC> (--file MD \| --text-input) --expected-revision N --reason TEXT [--approved] [--task ID ... \| --no-task]` | 审阅并登记磁盘单个被直接修改的 Markdown 文档 |
| 历史归档 | `history list PATH [--file NAME]` / `history show PATH --archive ID` | 只读查询 `.agent/history/` 持久归档 |
| 旧账迁移 | `migrate PATH --expected-revision N --reason TEXT [--dry-run \| --rollback BACKUP]` | schema 1/2/3 升级至 4；回退仅限迁移后无新改动 |
| 会话快照 | `snapshot PATH [--check SNAPSHOT_FILE]` | 保存或核对 `.agent/runtime/snapshots/` 只读校验 |
| 环境诊断 | `doctor PATH --json [--native-hooks] [--native-skills] [--session-id ID] [--expect-event SessionStart\|PreCompact]` | 非 Codex 适配器自动设置 `--client`，禁止传 `--native-*` |
| 项目复盘 | `retro PATH` | 生成 `.agent/RETRO.md` 索引草案（已存在时拒绝覆盖） |
| 跨项目知识 | `knowledge-add --file JSON --approved` | 须用户确认后入库至 `knowledge/` |

---

## 2. Schema 4 核心契约

### `status` 查询行为
- **只读不写锁**：`status`、`context`、`verify show` 与项目诊断不创建 `.lock` 或目录；读取前后比对 `state.json` 与事务标记，中途变化立即报错退出。
- **`--brief` 折叠规则**：无筛选参数时折叠 `done`/`cancelled` 任务，折叠条数计入 `summary.folded_final`；传 `--all` 或显式 `--task`/`--milestone`/`--focus` 时不折叠。
- **统计口径**：`summary.approved_active` 排除草案与取消任务；`external_dependencies` 单列筛选集外的直接依赖；`dependency_verification` 覆盖完整传递依赖链。
- **`current_alignment`**：比对 `CURRENT.md` 最近保存时绑定的 `goal_version`、`task_revision`、`task_ids` 与当前状态，返回 `unknown` / `changed` / `aligned`（仅证明关联记录一致，不证明文字语义）。

### `deliverables` 与 `checks.inputs` 规则
- `deliverables` 为批准范围内必填字段：填写项目相对文件或目录路径（统一使用 `/`），无本地文件交付显式填 `[]`。
- 每一项 `deliverables` 必须等于某条 `checks[].inputs` 或位于其目录下；不支持通配符（`*` `?` `[]`）、符号链接、越界路径、项目根目录、`.agent` 或 `.git`。
- 目录递归对所有文件列表和内容计算 SHA-256；Python 检查命令建议加 `-B`，防止在输入目录生成 `__pycache__` 触发 `stale`。
- 验收前校验 `deliverables` 存在；命令执行中交付物消失或输入/修订变化，凭据保留为未附加失败记录，不自动重跑。
- 默认 `timeout_seconds` 为 600（可配 1–86400），stdout+stderr 总上限 8 MiB；命令应在前台结束，不启动常驻后台进程。

### `verify run` vs `task review`
- `command` 标准只能用 `verify run`，程序记录 `level=observed`；`review` 标准只能用 `task review`，程序固定记录 `level=claimed, reviewer_kind=self`。两者不可互换，也不接受 `task update` 手填 `evidence`（仅允许有效空数组 `[]` 作为无变化测试）。
- 状态机：`todo → doing/blocked/cancelled`、`doing → done/blocked/todo/cancelled`、`blocked → doing/todo/cancelled`、`done → doing`、`cancelled → todo`。

### 历史归档（`.agent/history/`）
- 热历史上限 200 条，最近 10 条 `document-version` 保留全文。
- 剥离全文或裁剪条目前，先在同一事务中按内容哈希归档至 `.agent/history/`（校验 `project_id`）；归档失败则停止裁剪。

---

## 3. 故障排查与恢复手册

| 报错特征 | 真实原因 | 正确处理方式 |
| --- | --- | --- |
| `修订冲突: 当前 X，请求 Y` | 状态已被其他写入推进 | 重新运行 `status PATH --brief --focus` 读取新状态与变化，重新判断后再用新 `revision` 写入；禁止盲目覆盖 |
| `有未完成的写入。先检查并执行 recover` | 上次跨文件事务异常中断，残留 `.transaction.json` | 立即停止写入，向用户报告中断范围；核查后由授权执行 `recover PATH [--rollback]`（或 `--global` / `--client`） |
| `与状态修订不一致，禁止静默覆盖` | `.agent/` 中 Markdown 被外部直接编辑 | 只读核对 `git diff` 或磁盘内容确认无误后，单文档执行 `state adopt` 登记；若多文件同时漂移，先人工整理 |
| `交付物未被验收inputs完整覆盖` | `deliverables` 漏出所有 `checks.inputs` 范围 | `task revise`（若已批）→ 调整 `deliverables` 或 `checks.inputs` 使其包含前者 → 重新 `task approve` |
| `验收记录为 stale` | 上次验收后输入材料变化或交付物缺失 | 检查实际变更原因，按需重新执行 `verify run` 或 `task review` 更新当期凭据 |
| `旧任务账本只读` | 项目为 schema 1/2/3 | 先 `migrate --dry-run`，再显式 `migrate` 升级至 schema 4 |
| `installation/runtime.json 版本不匹配` | 工具箱已升级或脚本被移动 | 报告 `doctor` 真实差异，提示用户在工具箱目录重新运行原 `install-global` 或 `install-client` |
