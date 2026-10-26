# Project Anchor 作为 DeepSeek Harness 插件：设计（草案，未实现）

状态：P0 已落地并本地验证（`packages/dsh/`，任务 DSHP0）；P1 起仍为设计 · 未安装到任何 DSH profile · 无真实会话证据
范围：只覆盖 DeepSeek Harness（下称 DSH）客户端的宿主插件形态；`kit.py` 行为不变，另有一条最小新增读命令（已加：`kit.py context`）。
依据：DSH 1.x 自带 `cordis-plugin-development` 技能文档与本机安装包源码（`lib/index.js`）核对，非推测；未用 `cordis_inspect_query` 的项在第 10 节单列。

---

## 1. 结论

值得做，而且比"再写一份规则文本"更值：现有 DSH 适配只是 Skill 加一段被哈希管理的 `AGENTS.md` 规则块，能力边界里明确写着"原生发现、规则注入和脚本执行 UNVERIFIED"（`core/clients.py` 的 `client_doctor`）。插件把其中三件事从"模型自觉"变成"机制保证"，并额外补上一个架构文档已承认的缺口。

| 能力 | 现在（Skill + 规则块） | 插件形态 |
| :--- | :--- | :--- |
| 新会话读状态 | 规则要求模型自己先跑 `status --brief`，可能不读 | `agent.inject()` 在首步注入状态摘要，压缩后再注入 |
| 写受保护状态 | 规则说不要直接改；模型仍可 `write`/`edit` 绕过 | `ctx.tools.guard()` 直接拒绝写入 `.agent/` 受保护文件 |
| 调用核心程序 | 模型拼 bash 命令、自己解析 JSON、可能传错参数 | 5 个原生工具固定参数、固定解析、退出码即错误 |
| 批准来源 | `--source user` 只是调用者声明，架构文档承认"Agent 能调 `task approve` 就能自批" | 批准类调用走 `tools/pre-execute` 的 `ask`，用户确认后才以 `--source user` 执行 |
| 规则文本 | `AGENTS.md` 哈希块，升级靠字节比对 | `ctx.systemPrompt.section()`，版本随插件走，可开关、无重复注入 |

一句话：**插件不是把 Skill 翻译成 JS，而是给已有的 Python 不变量接上 DSH 的执行点。**

## 2. 现状与差距

- 安装面：`install-client dsh` 写 `$DSH_HOME/skills/project-anchor/`（Skill）与 `$DSH_HOME/AGENTS.md` 管理块，不配置 Hook（`core/clients.py`）。
- 机制面：DSH 没有 Codex 那样的 `SessionStart`/`PreCompact` 子进程 Hook；对应能力由插件事件承担，因此现有适配在这台客户端上"只能靠规则"。
- 信任面：`hook_runtime.context()` 已有"未审核不注入内容摘要"的逻辑，但只被 Codex Hook 使用；DSH 侧没有复用点。
- 身份面：`docs/ARCHITECTURE.md` 已写明批准协议不是身份验证，真正独立的批准来源需要 OS 权限边界或独立 runner。DSH 的用户审批弹窗正好是这样一个 seam，但当前无人接。

## 3. 设计原则

1. **唯一实现仍是 `kit.py`。** 插件只做四件事：解析参数、spawn、读 stdout JSON / 退出码、把结果渲染成工具输出。不在 JS 里重写任务、修订、哈希、锁或事务中的任何一条。
2. **磁盘是事实，会话日志只是可重建的派生缓存。** `.agent/` 永远是权威；投影、摘要、chip 都是缓存，可随时丢弃重建。
3. **用最弱的扩展点。** 能读就不写；能 guard 就不 waterfall；不改 `system-prompt/assemble`，只追加自己的 section。
4. **失败要响。** 修订冲突、`changed=false`、kit 退出码非 0 一律作为工具错误原样上报；不自动重试到成功，不静默回退。

## 4. 架构

```
DSH Host 进程
└── bundle: project-anchor-dsh (cordis.patch.yml 插入一行)
    └── plugin: project-anchor-dsh  (index.js → apply(ctx, config))
        ├── tools.js        5 个 defineTool → kit.js
        ├── kit.js          spawn(python, [kit.py, ...]) · UTF-8 · 参数数组 · 超时 · signal
        ├── prompt.js       ctx.systemPrompt.section()  规则与工具用法
        ├── guard.js        ctx.tools.guard()  on agent.ctx  受保护路径
        ├── inject.js       agent.inject()  首步 + compaction/end 后注入摘要
        ├── approve.js      tools/pre-execute → { kind:"ask" } → 批准来源落定
        ├── commands.js     ctx.commands.register()  /anchor*
        ├── projection.js   ctx.sessionProjections.register({ key:"anchor" })
        └── client.js       (可选) composer.dock chip + 面板
                              ↓ 唯一业务程序
                     Python  kit.py  ←→  <项目>/.agent/{state.json,tasks.json,*.md}
```

数据流：模型调 `anchor_task` → `kit.js` spawn `py -3 kit.py task add ...` → 退出码 0 则解析 JSON、更新投影、必要时刷新注入摘要；非 0 则把 `FAIL: ...` 作为工具错误返回，模型得到"必须处理"的信号而不是一段被忽略的文本。

## 5. 包结构与清单

仓库布局建议：本仓库新增 `packages/dsh/`（选项 A），与 Python 工具箱同仓同历史，但 `pyproject.toml` 声明的"仅标准库运行时"不受影响；发布面仍是独立 npm 私有包。备选 B（独立仓库）留到需要对外分发时再拆。

```
packages/dsh/
  package.json        # dsh.bundle.patch + exports + files + icon + locale
  cordis.patch.yml    # insert: id=project-anchor-dsh, name=@local/project-anchor-dsh, config={...}
  index.js            # apply(ctx, config) 装配上面各模块
  tools.js kit.js prompt.js guard.js inject.js approve.js commands.js projection.js
  client.js           # 可选 UI
  locale/en.json locale/zh.json   # meta.title / meta.description
  icon.svg
```

```json
{
  "name": "@local/project-anchor-dsh",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "exports": { ".": "./index.js", "./client": "./client.js",
               "./locale/*.json": "./locale/*.json", "./icon": "./icon.svg" },
  "dsh": {
    "bundle": { "patch": "./cordis.patch.yml" },
    "client": { "platform": "web", "immediately": false, "inject": [] }
  },
  "files": ["index.js", "tools.js", "kit.js", "prompt.js", "guard.js", "inject.js",
            "approve.js", "commands.js", "projection.js", "client.js",
            "cordis.patch.yml", "locale/*.json", "icon.svg"]
}
```

```yaml
# cordis.patch.yml
- insert:
    - id: project-anchor-dsh
      name: '@local/project-anchor-dsh'
      config:
        pythonPath: ''
        kitPath: ''
        injectContext: auto
        injectLimit: 4000
        guardProtectedState: true
        approvalGate: [task.approve, state.update.GOAL.md]
```

Host 入口形态（与 `dsh-tool-todo` 一致，已验证）：

```js
export const name = 'project-anchor-dsh'
export const inject = ['tools', 'systemPrompt', 'commands', 'sessionProjections']
export const Config = z.object({ /* 见第 7 节 */ })
export function apply(ctx, config) { /* 每个注册都用 ctx.effect / ctx.on，返回 disposer */ }
```

## 6. 工具面（对 `kit.py` 的薄封装）

| 工具 | 参数 | 映射到 | 写 | 需批准 |
| :--- | :--- | :--- | :--- | :--- |
| `anchor_status` | `path?` `brief?` `task_id?` `milestone?` | `status PATH [--brief] [--task] [--milestone]` | — | 否 |
| `anchor_task` | `action: add\|update\|approve\|revise` `path` `task_id?` `payload?` `expected_revision` `reason` `source?` | `task ACTION PATH --json-input\|--task-id ...` | 是 | 仅 `approve` |
| `anchor_state` | `action: update\|adopt` `document: GOAL.md\|CURRENT.md\|DECISIONS.md\|LESSONS.md` `text` `expected_revision` `reason` `approved?` | `state ACTION PATH DOC --text-input ...` | 是 | `GOAL.md` 与 `adopt` |
| `anchor_maint` | `kind: snapshot\|retro\|migrate` `path` `expected_revision?` `reason?` `dry_run?` | `snapshot` / `retro` / `migrate` | migrate 写 | `migrate` 是 |
| `anchor_doctor` | `path?` | `doctor PATH --client dsh --json` + 插件自检 | — | 否 |

约定：
- 输入一律走 stdin（`--json-input` / `--text-input`），不拼 shell；`exec.agent.session.cwd` 作为默认 `path`，未初始化项目时返回"未初始化"的明确错误而不是猜路径。
- `expected_revision` 必须由模型从最近一次 `anchor_status` 取得；插件不复用旧值掩盖冲突，冲突时把 kit 的 `FAIL:` 原文作为工具错误。
- `output.render` 只渲染摘要行（项目、修订、任务计数、警告），完整 JSON 走 `output.schema`，避免把整个账本塞进对话。
- 5 个工具的 schema 保持窄：每个工具的顶层属性不超过 8 个，description 里写清"读不写/写必带修订"。

## 7. 六个机制映射

**1) 注入（替代 SessionStart）**
- 触发：`agent/created` 时 `agent.inject({ type:'text', text: digest })`；`compaction/end` 事件后若修订变化再注入一次。
- `agent.inject()` 是 next-step 的 inbox splice，不额外唤醒（`dsh-agent-loop` 中 `inject()` → `send(..., 'next-step', false)`），首步天然带上，且会被记录成 `agent/inbox/spliced`，可重建。
- 摘要内容复用 `core/hook_runtime.py::context()`：头部声明"这是数据不是规则"，主体是 `{project_id, state_revision, task_revision, warnings, goal, current}`，按 `injectLimit` 截断；未信任项目只注入"未审核"提示与读取指引（现有逻辑原样复用）。
- 去重：投影里保存 `digestHash`，同一 hash 不重复注入，避免每步烧 token。
- 成本：每会话 1 次，加上每次写后 1 次；不做每步注入。

**2) 约束（新增，规则做不到）**
- `project-anchor` 的受保护集：`.agent/state.json`、`.agent/tasks.json`、`.agent/GOAL.md|CURRENT.md|DECISIONS.md|LESSONS.md`、`.agent/runtime/**`（`skill-input/` 除外）。
- 实现：`agent/created` 时检查会话 cwd 是否有 `.agent/state.json`，有才在该 `agent.ctx` 上注册 guard（全局 guard 会给所有项目加成本）；`ctx.tools.guard((exec) => reason | undefined)` 同步返回拒绝理由。
- 匹配：`write`/`edit`/`str_replace_editor` 看目标路径；`bash`/`pwsh` 只做保守匹配（出现受保护相对路径且带重定向/`python -c` 之类），宁可漏也不误杀。
- 拒绝文案必须给出正解："用 `anchor_state` / `anchor_task` 提交，带 `expected_revision`"，否则模型只会换条路绕。
- 与 `changed=false` 的关系：guard 只管"绕过程序"，不管"程序内部判定无变化"。

**3) 执行（原生工具）**
- 见第 6 节。参数数组 spawn，`windowsHide`，UTF-8 双向，`timeoutMs` 默认 20s，`exec.signal` 直接传给子进程。
- Python 解析顺序：`config.pythonPath` → `DSH_PROFILE` 环境推断 → `py -3`（Windows）/`python3`（其他）；首次解析结果按会话缓存，失败后工具返回结构化错误，插件本身不崩（`inject` 里不放 `python` 服务依赖）。

**4) 批准（补上架构文档的缺口）**
- `tools/pre-execute` waterfall 拦截 `anchor_task{action:'approve'}`、`anchor_state{document:'GOAL.md'}`、`anchor_maint{kind:'migrate'}`，返回 `{ kind:'ask', reason }`，由 DSH 审批 seam 转成用户确认。
- 用户确认 → 以 `--source user` 执行；拒绝 → 不执行，返回 `{ kind:'denied' }`；由常驻策略自动放行 → 以 `--source policy` 执行。
- 效果：`--source` 从"模型自称"变成"本次调用确实过了人"。**这是插件相对 Skill 最实质的一条收益**，也是 `ARCHITECTURE.md` 里"Agent 能调就能自批"在 DSH 上的收口方式。Kit 侧零改动。
- 注意：`tools/pre-execute` 是 waterfall，必须 `return next(...)` 保留他人决定；只在命中目标调用时改写。

**5) 命令（人用，不花模型 token）**
- `ctx.commands.register({ definitionId, name, description, handler })`（与 `dsh-command-compact` 同形，已验证）：`/anchor`（状态摘要）、`/anchor:task`（任务表）、`/anchor:snapshot`、`/anchor:doctor`。
- handler 直接 spawn kit.py，返回 `{ kind:'success'|'error', text }`；不触发模型轮次。

**6) 投影与 UI（可选，第二阶段）**
- `ctx.sessionProjections.register({ key:'anchor', stateSchema, init, apply, wire:{viewSchema, view}, stateVersion:1 })`：从 `anchor_*` 工具结果折叠出 `{revision, taskRevision, currentTask, goalApproved, stale, digestHash}`，纯 JSON、忽略即返回同引用。
- UI：`conversation.composer.dock` 放一个 chip（`PA r12 · CURRENT 落后`），点开面板列任务；面板里的"批准"按钮走与工具相同的 Host 调用，同样过审批 seam。样式只用 `--dsw-alias-*` token。
- 明确不做 iframe 页面、不自带 React、不读别的插件 DOM。

## 8. 核心侧最小改动（3 处，都不改状态格式）

1. **新增 `kit.py context PATH [--limit N] [--json]`**：把 `core/hook_runtime.py::context()` 暴露成正式读命令（受信任判定、截断、警告同源）。理由：插件和 Codex Hook 必须共用同一份注入语义，否则就是第二份实现。只读，无修订号。
2. **`install-client dsh --plugin`**：只装 Skill，不写 `AGENTS.md` 管理块，清单记 `rules: "plugin"`；`doctor --client dsh` 据此把"规则来源"报成 `plugin` 而不是比对块字节。目的：避免插件 section 与 `AGENTS.md` 块双重注入同一条规则。
3. **`doctor --client dsh` 增加插件检查项**：`PASS/FAIL` 报"规则来源唯一"、`UNVERIFIED` 报"插件是否激活"（doctor 读不到 DSH profile 组合，只能声明检查到哪一层）。`--plugin` 安装但插件未激活时给 `WARN`，因为此时治理规则整体缺席。

## 9. 配置 Schema（`cordis.patch.yml` 的 config）

| 键 | 类型 | 默认 | 说明 |
| :--- | :--- | :--- | :--- |
| `pythonPath` | string | `''` | 空则自动解析 |
| `kitPath` | string | `''` | 空则从 Skill `runtime.json` 或安装清单读 |
| `injectContext` | `auto\|always\|never` | `auto` | `auto`=仅在已初始化且（已信任或只发未审核提示）时注入 |
| `injectLimit` | number | `4000` | 摘要字符上限 |
| `guardProtectedState` | boolean | `true` | 关掉后仍然能用工具写，只是不再拦绕过 |
| `approvalGate` | string[] | `['task.approve','state.update.GOAL.md','maint.migrate']` | 需要用户确认的动作 |
| `autoSnapshot` | `off\|compaction` | `compaction` | `compaction/end` 后调 `snapshot`（与 Codex PreCompact 行为对齐） |
| `toolTimeoutMs` | number | `20000` | spawn 超时 |

用户层 `cordis.patch.yml` 可覆盖，升级不被冲掉。

## 10. 失败与边界

| 场景 | 行为 | 怎么证明 |
| :--- | :--- | :--- |
| 项目未初始化 | 工具返回"未初始化"，guard 不注册，不注入 | `anchor_status` 错误文本 + 无 section |
| Python 缺失/版本低 | 工具结构化错误，插件保持加载 | `anchor_doctor` + 会话内错误回放 |
| 修订冲突 | 原样返回 kit 的 `FAIL:`，不重试、不自动合并 | 两会话并发写同一任务的工具输出 |
| `changed=false` | 工具成功但明说"未写入"，不报告新增 | 重复同参数 `anchor_state` |
| 用户拒批 | 不执行，工具返回拒绝原因 | 审批弹窗 Cancel 后 `.agent/` 无变化 |
| guard 误判 | 配置可关；拒绝文案给正解 | 用 bash heredoc 写 `.agent/` 的对照 |
| 插件 unload/HMR | 所有注册走 `ctx.effect`，卸载即撤 | 停用插件后工具消失、guard 解除 |
| 替换已装包 | 需要重启（模块代际） | 安装结果里的 `restart-required` |

待 `cordis_inspect_query` 确认（本轮用不了该工具，故未定稿）：
- `Tool` 目录里 `write`/`edit`/`bash` 的实际工具名与 `exec` 参数形状（现在按 `dsh-tool-todo`、`dsh-tools` 的 `defineTool`/`register` 推断）。
- 审批 seam 的 decision 结构（`allow`/`deny`/`ask` 字段名）。
- `Slots.listSubTree` 里 `conversation.composer.dock` 的 props 与可用 slot 集合。
- `Config.listConfigs` 中本插件 row 的 `entry` 与 schema 回读。

## 11. 验证计划（每阶段都要"可判定的证据"）

- **P0 骨架**：bundle 装得上（`application: applied`）；`anchor_status` 返回真实修订；`systemPrompt` section 出现在组装结果里；`anchor_doctor` 读出 kit 版本。证据：安装结果 + 一次工具调用输出 + 组装快照。
- **P1 约束与注入**：新会话首步上下文里出现摘要且 `agent/inbox/spliced` 有记录；`write .agent/tasks.json` 被拒并给出正解；压缩后摘要刷新一次。证据：会话日志片段 + 拒绝记录。
- **P2 批准与命令**：`anchor_task approve` 弹审批，Cancel 不写、Confirm 写入且 `approved_scope.source=user`；`/anchor` 不出模型轮次。证据：tasks.json 的 `approved_scope` 与命令输出。
- **P3 收口**：`install-client dsh --plugin` 后 `AGENTS.md` 无块、规则只来自 section；doctor 三项状态明确；`docs/CLIENT_VALIDATION.md` 与 `skills/project-anchor/references/CLIENTS.md` 的 DSH 行从"UNVERIFIED"改写为实测结论（含未验证部分）。
- **静态回归**：`tests/test_dsh_plugin.py` 校验清单/patch/图标/locale 字段齐全，并把 `tools.js` 里的命令模板与 `kit.py` 的 argparse 定义做一致性比对（新增 kit 子命令却漏改包装时直接失败）。

## 12. 不做

- 不在 JS 里实现任何一条治理逻辑（无第二份 tasks.py）。
- 不把 `.agent/` 镜像进 DSH storage 或 session log 当事实源。
- 不替换 `system-prompt/assemble`，不动其他插件的贡献。
- 不自动批准、不自动提交、不自动迁移 schema。
- 不让插件成为"没装 Python 也能用"的独立实现。

## 13. 需要用户定的三件事

1. 仓库布局：A 本仓 `packages/dsh/`（推荐）还是 B 独立仓库。
2. 规则来源：装插件后是否退役 `$DSH_HOME/AGENTS.md` 管理块（推荐退役，避免双份规则）。
3. UI 是否进范围：P2 的 chip/面板属于可选，只做 Host 侧也能交付全部机制收益。

## 14. 量级

Host 侧 P0–P2 约 700–900 行（含 5 个工具、guard、注入、命令、审批、投影），UI 另 250–400 行；核心侧改动约 60 行（`context` 命令 + 安装分支 + doctor 两项）。P0 可在一轮内装出来验证，P1/P2 各自独立可验收。
