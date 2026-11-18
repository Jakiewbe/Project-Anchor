# 工作流手册（按当前意图按需读取）

## 1. 范围、阶段与权限判断

依据当前用户请求与已确认授权判断，不用关键词脚本替用户推断权限；总目标批准、局部任务批准、执行阶段和治理写入四者分别判断。

| 用户意图 | 允许动作与停止位置 |
| --- | --- |
| 仅评估、全部只读、确认后再继续 | 只读查询与报告；不创建任务、不写治理或业务文件 |
| 只批准项目总目标 | `state update GOAL.md --approved`；不顺便生成任务或执行 |
| 制定计划，先不执行 | 按授权范围 `task add` 创建 `draft`；不转 `approved`/`doing`，不改业务 |
| 按刚才明确的方案实施 | 创建/更新草案 → `task approve` → `focus set` → 实施与验收；不重复确认、不扩大范围 |
| 路线已确定，先看某模板（如“路线改 JSON，先看看模板”） | 允许治理写入时当回合写 `DECISIONS.md`；只展示或核对模板，不开始实施 |
| 仅修改指定文件 | 按指定范围修改业务文件；不初始化项目，不额外写治理记录 |

- **局部任务独立推进**：总目标仍为待确认草案时，若用户明确授权了某个局部任务，可单独登记并在 `description` 与 `task approve --reason` 中记录授权来源与范围，不把该局部授权当成总目标获批。
- **未批准草案不得执行**：已有草案在未取得批准前不能转 `doing` 或修改对应业务代码。

---

## 2. 初始化项目管理（Onboarding）

1. **前置核查**：
   - 触发条件：用户明确要求启用项目管理，或可信全局规则授权在首次实际项目工作时接入。纯只读问答、代码解释或限定单文件修改不接入。
   - 目录定位：仓库子目录启动时先定位 Git 根目录；非 Git 目录只使用用户明确指向的项目目录，不扫描接管其他目录。
   - 旧约束辨析：结合原文与上下文判断。若旧约定说“继续已有工程，不要重新初始化项目、不要重构正常模块”是指保留业务骨架、依赖与正常模块，则可同时执行治理接入；若明确禁止新增 `.agent/`、禁止治理接入、禁止修改 `AGENTS.md`/`.gitignore`/`.gitattributes` 或仅限修改指定文件，则不接入。确实无法判断时先澄清。
   - 已有状态优先：若目标已存在 `.agent/state.json`，先 `status`，名称不同不得强行重接。
2. **执行写入**：
   - 调用 `init-project PATH --name NAME`，**不要传 `--git-init`**（除非用户明确要求初始化 Git）。
   - 实际写入范围固定为 4 处：创建 `.agent/`（含运行锁与事务目录），保留既有字节并追加 `AGENTS.md`、`.gitignore`、`.gitattributes`。不会修改业务源码、依赖或 Git 提交/分支；存在未知 `.agent/` 文件会拒绝覆盖。
   - 若工具审批被拒绝，禁止改换参数或路径绕过；可只读核查原因并如实等待用户澄清。
3. **收尾核对**：
   - 核对业务文件与 Git 状态未被意外修改；说明新增/追加了哪些文件；告知 `GOAL.md` 仍为待确认草案。

---

## 3. 只读进度、本轮接续与目标核对

1. **接续起点**：运行 `status PATH --brief --focus`，读取完整 `goal`、`current`、`current_alignment` 与本轮任务列表。
2. **指针缺失或关联变化**：
   - 若 `focus_missing=true`（未设置本轮指针），**不得按更新时间猜测历史任务**；可运行 `status PATH --brief`（或 `--all`）向用户汇报待办与历史状态，确认本轮任务后执行 `focus set`。
   - 若 `current_alignment` 为 `unknown` 或 `changed`，先按真实授权核对任务范围，不凭印象补猜。
3. **筛选与完整信息**：
   - `--brief` 折叠终结任务（`done`/`cancelled`）至 `summary.folded_final` 并省略长描述/长证据；查全量传 `--all`，查验收条件/证据细节不带 `--brief`。
   - 显式 `--task ID` 或 `--milestone NAME` 永不折叠已完成项，同时单列筛选范围外的直接依赖（`external_dependencies`）。
   - 只读查询严禁组合 `--rebuild`；重建视图须单独授权执行 `status PATH --rebuild`。
4. **目标偏离检查**：将当前任务与已确认决策逐项对照 `GOAL.md`，如实报告符合、偏离或资料不足，不凭完成率擅自改目标。

---

## 4. 任务规划、范围批准与闭环验收

1. **规划草案（Draft）**：
   - 全项目规划前须确保 `GOAL.md` 已确认；局部规划仅规划授权范围。
   - 每个任务须包含唯一 `task_id`、清晰 `description`、可核查 `acceptance_criteria`、`deliverables`（相对文件/目录，无本地交付显式填 `[]`）及逐条对应的 `checks`（`command` 或 `review`）。
   - **交付覆盖铁律**：`deliverables` 中每一项必须等于某个 `checks.inputs` 或位于其子目录下；不支持通配符、项目根目录、`.agent` 或 `.git`。
   - 存在依赖时先添加被依赖任务，后续任务逐次使用最新 `revision`。
2. **批准与锁定范围（Approve & Focus）**：
   - 取得用户批准或明确实施授权后，执行 `task approve PATH --task-id ID --source user|policy --expected-revision N --reason TEXT`。
   - 用 `focus set PATH --task ID --expected-revision N --reason TEXT` 设定本轮指针（设置指针不等于批准）。
   - 已批准任务的 `description`、`acceptance_criteria`、`dependencies`、`checks` 或 `deliverables` 任一发生实质改变，必须先 `task revise` 回到草案，修改后重新 `task approve`；禁止用 `task update` 篡改批准范围。
3. **实施与双轨验收（Execute & Verify）**：
   - 确认所有前置依赖及上游依赖链均处于有效 `pass` 状态后，通过 `task update` 将任务转为 `doing`。
   - **生成交付物后再验收**：`deliverables` 声明的文件/目录缺失时不得验收。
   - **command 型标准**：调用 `verify run` 执行批准的 `argv`，生成 `observed` 凭据。
   - **review 型标准**：Agent 亲自执行 Code Review（先查 Bug，再做第一性原理简化检查），再调用 `task review` 提交结构化自查结论，固定记录 `level=claimed, reviewer_kind=self`。未实际检查的图面、实机或生产环境不得列为通过。
   - 全部检查结果均对应当前材料指纹（`verification_state=pass`）后，再调用 `task update` 置为 `done`。
   - 完成汇报须分别说明：历史完成状态、当前验收状态、交付覆盖（`deliverable_coverage`）、`observed` 命令结果与 `claimed/self` 自查及未验缺项。

---

## 5. 迁移旧账本（Schema 1/2/3 → 4）

1. 先只读 `status` / `doctor` 确认当前 `task_schema` 与 `revision`。
2. 执行预检：`migrate PATH --expected-revision N --reason TEXT --dry-run`，确认待迁移任务数与格式兼容性（未知字段会在预检即报错，不会静默丢弃）。
3. 正式执行：`migrate PATH --expected-revision N --reason TEXT`。程序会自动备份所有受影响治理文件并生成清单，原任务状态、批准快照与证据完整保留：
   - schema 1/2 旧任务保留 `verification_legacy`（schema 1 另保留 `legacy_unverified`）。
   - schema 3 保留原执行凭据，但 `deliverable_coverage` 为 `undeclared`。
4. **旧任务继续规则**：未声明交付或处于 legacy 的旧任务，在重新执行、重新结项或作为新任务依赖前，须先 `task revise`、补齐 `deliverables` 与 `checks`、再重新 `task approve`。
5. 迁移中途崩溃只用 `recover` 排查；确需撤回且迁移后尚无新修改时，方可使用 `migrate --rollback`。

---

## 6. 保存决策、教训与目标修订

- 确认讨论已收敛为决定（非临时猜测），并在允许治理写入的当前回合落盘；全部只读或限定文件修改时不在本回合写入，而是向用户说明决定未落盘。
- 先完整读取原 `DECISIONS.md` / `LESSONS.md`，保留全部已有条目后追加新内容（`DECISIONS` 写清背景、选择、原因、适用范围；`LESSONS` 写清根因、证据、方法、局限），通过 `state update` 提交新全文。
- `GOAL.md` 的任何变更须先取得用户明确批准，再带 `--approved` 提交。

---

## 7. 主动会话交接（Handoff）

1. 先 `status PATH --brief --focus` 核对账本真实状态，不得将未验收任务口头或书面升级为 `done`。
2. 将本轮已确认但未落盘的决策/教训写入磁盘。
3. 编写 `CURRENT.md`（保留 7 个必要章节，总行数 ≤ 50 行），通过 `state update PATH CURRENT.md --task ID ...`（空闲无活动任务时用 `--no-task`）保存，同步目标版本、任务修订与焦点关联。
4. 运行 `snapshot PATH`，再运行 `status PATH --brief --focus` 与 `doctor PATH --json` 核对一致性。
5. 向用户返回：当前阶段、本轮任务及验收/覆盖状态、阻塞项、下一步动作、快照位置。

---

## 8. 规则与环境诊断（Doctor）

1. 先读 `runtime.json` 确认安装来源：
   - Codex 安装（含 `codex_home`）：执行 `doctor PATH --json --native-hooks --native-skills`。
   - 通用 / Claude / DSH 安装（含 `client`）：执行 `doctor PATH --json`（禁止附加 Codex 专属 `--native-*`）。
   - 本会话 Hook 漏触发核对：仅在客户端证据确认应触发某事件时，传 `--session-id ID --expect-event SessionStart|PreCompact`（`agents`/`dsh` 不支持生命周期检查）。
2. 如实区分 `PASS` / `WARN` / `FAIL` / `UNVERIFIED`：不把 `UNVERIFIED` 当失败或已执行；文件存在、Hook 配置、原生信任、脚本执行和模型遵守是五个独立层级。
3. 发现安装漂移或错误时只解释真实诊断结果；未获授权不自动重装或修改全局配置。

---

## 9. 项目复盘与知识入库

1. 执行 `retro PATH` 生成 `.agent/RETRO.md` 索引草案（若已存在会拒绝覆盖；补充内容时仅人工编辑 `RETRO.md` 保留原稿）。
2. 对照 `GOAL.md`、任务凭据索引、`DECISIONS.md` 与 `LESSONS.md`，由人工归纳有证据支撑的根因、经验与遗留未验项，不生成重复长文或把未验项标为完成。
3. 筛选可复用的跨项目经验候选（含标题、适用条件、证据、局限、来源项目），向用户展示具体内容并获得明确确认后，才执行 `knowledge-add --file JSON --approved`。
