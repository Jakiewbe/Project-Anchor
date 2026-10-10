# 通用 Agent Skills 适配验证记录

[返回项目首页](../README.md) · [客户端机制](../skills/project-anchor/references/CLIENTS.md) · [使用手册](USAGE.md)

记录日期 2026-10-09，Windows 10 19045，Python 3.11。自动化、模拟和真实客户端结果分开统计；结构检查和模拟不能代替真实客户端验收。原始运行记录保存在本机 `.agent/runtime/universal/`，不提交，不含认证信息。

## 1. 规范与官方文档

| 对象 | 来源（2026-10-09 查阅） | 本机版本 | 采用结论 |
| :--- | :--- | :--- | :--- |
| Agent Skills 规范 | https://agentskills.io/specification | — | `name` 1–64 位小写字母数字和单连字符，与目录同名；`description` 1–1024 字符；可选 license、compatibility、metadata、allowed-tools；渐进加载 |
| Cursor | https://cursor.com/docs/context/skills · https://cursor.com/docs/context/rules · https://cursor.com/docs/agent/hooks | 3.23.12 | 扫描 `.agents/skills`、`.cursor/skills` 及用户级同名目录（兼容读取 `.claude/skills`、`.codex/skills`）；`/skill-name` 显式调用；AGENTS.md 与 `.cursor/rules`；Hook 协议与 Codex/Claude 不同（sessionStart 无 cwd、preCompact 只观察） |
| Claude Code | https://code.claude.com/docs/en/skills · https://code.claude.com/docs/en/hooks · https://code.claude.com/docs/en/memory | 2.1.153 | `~/.claude/skills`、`.claude/skills`；`/skill-name`；`~/.claude/rules/*.md` 无 `paths` 时全局加载；SessionStart/PreCompact 命令 Hook 与 Codex 同组格式；AGENTS.md 自 2.1.277 才直接读取 |
| OpenCode | https://opencode.ai/docs/skills · https://opencode.ai/docs/rules · https://opencode.ai/docs/plugins | 1.14.29 | `.opencode/.claude/.agents` 的 `skills` 及用户目录；原生 skill 工具加载，受 `permission.skill` 控制；项目 AGENTS.md；生命周期只有 JS 插件 |
| WorkBuddy | https://cloud.tencent.com/document/product/1831/134516（官方，Enterprise）；社区资料 https://cloud.tencent.com/developer/article/2693324 | 未安装 | 官方：工作区 `.codebuddy/skills/`、SKILL.md 含 name/description；社区：用户级 `~/.workbuddy/skills/`。规则与生命周期未找到可依赖的官方说明 |

## 2. 能力矩阵

“已验证”只表示本记录中有真实客户端证据；“未验证”表示机制有官方说明或已配置但缺少真实证据；“不支持”表示本工具没有为该客户端提供此能力。

| 客户端 | Skill 发现 | 自然语言调用 | 持久规则 | 主动交接 | 生命周期自动化 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Codex | 已验证（历史 1.2.0 记录） | 已验证（历史，非 100%） | 已验证（全局 AGENTS.md 管理块） | 已验证（历史） | 启动、手动压缩：历史已验证；本版本 Hook 定义需重新审核，当前未验证 |
| Claude Code 2.1.153 | 已验证（项目级 `.claude/skills`，init 事件列出） | 未验证（本机 API 401） | 未验证（规则文件已安装，加载需模型回答证明） | 未验证（401） | SessionStart startup/resume、PreCompact manual：已验证；压缩后 SessionStart(compact)、自动压缩：未验证 |
| OpenCode 1.14.29 | 已验证（`opencode debug skill`，项目级 `.agents/skills`） | 已验证（1 次完整运行 8/8） | 已验证（项目 AGENTS.md；新会话按规则读盘） | 已验证 | 不支持（本工具未提供 JS 插件） |
| Cursor 3.23.12 | 已验证（本机 Cursor 会话列出 `~/.agents/skills/project-anchor`） | 部分验证（Cursor 子代理 10/0，限制见第 5 节） | 未验证（子代理在其他工作区运行，未加载合成项目 AGENTS.md） | 部分验证（同上） | 不支持（未配置 Cursor Hook） |
| WorkBuddy | 未验证 | 未验证 | 未验证 | 未验证 | 不支持 |

## 3. 自动化测试

`py -3 -X utf8 -m unittest discover -s tests`：**151 通过 / 0 失败**（原 131 项 + 新增 `tests/test_clients.py` 19 项 + `tests/test_skill.py` 1 项）。新增覆盖：

- Codex 适配器不受继承的 PROJECT_ANCHOR_CLIENT 影响（该修正在真实客户端运行之后加入，只改 Codex 分支）。

- SKILL.md frontmatter 符合 Agent Skills 规范字段与长度。
- `install-client agents`：runtime.json 不含 codex_home；不写 AGENTS.md 或 hooks.json；幂等；更新备份旧文件；人工修改后拒绝更新和卸载；与 Codex 安装互不接管同一 Skill 目录；中途崩溃后拒绝继续安装，`recover --client` 回滚。
- 适配器在去掉 CODEX_HOME、改写用户目录的子进程中完成 init、status、task、state、doctor，用户目录下不产生 `.codex`。
- `kit.py install-client / uninstall-client / recover --client` 命令行入口；无事务时恢复和重复卸载明确失败。
- `install-client claude`：保留用户 settings.json 的其他键和已有 Hook；幂等；卸载恢复原设置、删除自己创建的文件；拒绝覆盖同名规则文件和被修改的 Hook。

全部测试目录名含中文和空格。

## 4. 模拟验证（包含在上述自动测试中）

- Claude Hook：按 settings.json 中实际命令字符串执行，输入为 Claude 文档格式 JSON；SessionStart 返回 additionalContext，PreCompact 生成快照，日志写入 `<Claude 配置目录>/project-anchor/runtime`，不触碰 Codex 目录；trust-project 后注入审核过的摘要。
- 双入口交替：agents 与 claude 两个适配器操作同一项目；旧 revision 写入被拒绝且账本字节不变；用最新 revision 写入成功；旧快照 `--check` 报告 stale，不自动恢复。

模拟输入不能证明客户端会发出同样事件。

## 5. 真实客户端验收

隔离合成项目位于系统临时目录 `Anchor 实测 中文 空格 */合成 项目`，含 `hello.py` 并由测试器 `git init`（测试夹具，不是产品行为）。驱动程序：`tests/client_live.py`。

### OpenCode 1.14.29（`--pure`，模型 deepseek/deepseek-flash）

第 3 次运行 **8 通过 / 0 失败**：

| 步骤 | 结果 | 证据 |
| :--- | :--- | :--- |
| 未接入项目只读问答（反向） | 通过 | 未调用 Skill，文件不变 |
| 自然语言启用治理 | 通过 | 调用 skill 工具和 run.py；创建 `.agent/`、追加 AGENTS.md；hello.py 不变，无 Git 提交 |
| 自然语言批准目标 | 通过 | goal_approved 变为 true |
| 显式点名 Skill 添加任务 | 通过 | T1 状态 todo |
| 自然语言保存决定 | 通过 | DECISIONS.md 含 UTF-8 决定 |
| 主动交接 | 通过 | CURRENT 变化，revision 增加 |
| 新会话恢复 | 通过 | 回答含 T1 与 UTF-8，状态不变 |
| 已接入项目普通问答（反向） | 通过 | 未调用 Skill，状态不变 |

工具调用审计：未直接写受保护状态；目标批准步骤直接调用 runtime.json 中的 kit.py（未经 run.py），仍是同一程序；新会话恢复由项目 AGENTS.md 驱动读取 `.agent` 文件，未选中 Skill。

历史运行原样保留：

- 第 1 次（deepseek/deepseek-chat）：4 通过 / 3 失败。交接、新会话恢复和最后一次问答时客户端报告 `ProviderModelNotFoundError`（模型目录刷新后该模型下线），无回答。当时测试器只检查退出码，误把最后一步记为通过；之后改为同时要求无错误事件和非空回答。
- 第 2 次（deepseek/deepseek-flash）：5 通过 / 2 失败。目标未批准时模型拒绝添加任务（符合规则），新会话恢复如实回答“无任务”，因此“提到 T1”断言失败。测试场景随后补上目标批准步骤；断言未放宽。

### Claude Code 2.1.153

- 本机所有模型请求返回 `401 Missing API key`（不加任何覆盖设置也一样），自然语言工作流 **0 项可执行**。未修改或迁移认证信息。
- 不依赖模型的证据：项目级 `install-client claude --home <项目>/.claude` 后，`claude -p` 的 init 事件列出 project-anchor；真实客户端执行 Hook 记录 **3 通过 / 0 失败**：SessionStart(startup) PASS、SessionStart(resume) PASS、PreCompact(manual) PASS 并生成 1 个快照，session_id 与客户端一致。未接入项目上 SessionStart 记录为 SKIP。
- 测试时用 `--settings` 关闭用户的两个插件，避免合成会话进入其记忆库；`--allowedTools` 预先允许 Bash/Read/Write/Edit/Glob/Grep/Skill，只在临时项目中使用。
- 第一次驱动运行因测试器未关闭 stdin 导致 `claude -p` 等待输入，手动终止，不计入结果。

### Cursor 3.23.12（Cursor Agent 子代理）与 OpenCode 交替

另建合成项目 `Anchor Cursor 实测 中文 空格 */合成 项目`（含 hello.py，`git init`，0 次提交）。每步启动一个全新 Cursor 子代理（generalPurpose），提示中给出项目路径和一句用户请求，要求回报原样回答和实际读写、命令；每步后由独立脚本比对 `.agent` 指纹（revision、任务、CURRENT 哈希、决定、hello.py、提交数）。

| # | 客户端 | 请求类型 | 结果 | 指纹证据 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Cursor | 未接入项目只读问答（反向） | 通过 | 只读 hello.py；无 `.agent` |
| 2 | Cursor | 自然语言启用治理 | 通过 | 读取 `~/.agents/skills/project-anchor/SKILL.md`，经 run.py `init-project`；revision 0，hello.py 不变，0 次提交 |
| 3 | Cursor | 自然语言批准目标 | 通过 | `state update GOAL --approved`；goal_approved true |
| 4 | Cursor | 显式 `/project-anchor` 添加任务 | 通过 | T1 todo |
| 5 | Cursor | 自然语言保存决定 | 通过 | DECISIONS 含 UTF-8 决定，revision 5 |
| 6 | Cursor | 主动交接 | 通过 | CURRENT 更新、快照生成，revision 6 |
| 7 | OpenCode | 新会话恢复并把 T1 改为进行中 | 通过 | 回答含目标、T1、UTF-8 决定；T1 doing，revision 7，代码不变 |
| 8 | Cursor | 新会话只读恢复 | 通过 | 回答 T1 doing、revision 7，并指出 CURRENT 落后；状态不变 |
| 9 | Cursor | 已接入项目普通问答（反向） | 通过 | 只读 hello.py，未调用 Skill；状态不变 |
| 10 | Cursor | 同步 CURRENT | 通过 | revision 8，CURRENT 哈希变化，任务不变 |
| 11 | OpenCode | 新会话只读恢复 | 通过 | 回答 CURRENT 下一步、T1 doing、revision 8；状态不变 |
| 12 | Cursor | 按旧 revision 7 写 CURRENT（用户明确给出旧修订，禁止重试） | 通过 | 程序返回 `修订冲突: 当前 8，请求 7`，退出码 1；revision 与 CURRENT 哈希不变；客户端未自行改用新修订或直接改文件 |

合计 Cursor 10 通过 / 0 失败，OpenCode 交替 2 通过 / 0 失败（OpenCode 使用 deepseek/deepseek-flash、`--pure`，从用户级 `~/.agents/skills` 发现 Skill）。

限制，结论不外推：

- 这些是 Cursor Agent 子代理，运行在本仓库工作区，不是用户在合成项目中新开的聊天；本仓库规则（含 `global/AGENTS.md` 的“默认接入”约定）对其生效，会提高 Skill 被选中的概率；合成项目的 AGENTS.md 未作为 Cursor 规则加载，因此“持久规则”仍未验证。
- 使用的是 Codex `install-global` 安装到 `~/.agents/skills` 的 1.2.0 版 Skill（runtime 指向 codex_home），不是本分支的 `install-client agents`。
- 第 12 步的旧修订由请求直接给出，验证的是程序拒绝和客户端不绕过，不是两个会话自然并发。
- 子代理的文件搜索工具有两次返回本仓库工作区文件而非目标目录（只读，结果未被采用）。
- 观察到既有行为：`GOAL.md` 正文“目标版本 1”而 state.json 的 goal_version 为 2；与本次适配无关，未修改。
- 第 10、12 步按 Skill 说明在项目 `.agent/runtime/skill-input/` 留下草稿文件。

### 未执行

- Codex：本机没有 Codex CLI，原生 skills/list、Hook 信任与执行不能复验；只有自动回归。本仓库运行 `doctor` 对现有安装报告 0 FAIL，Hook 脚本版本和 Skill 模板版本 WARN，需要重新 `install-global`。
- Cursor：用户在合成项目中直接新开的聊天、合成项目 AGENTS.md 作为 Cursor 规则加载，没有执行。
- WorkBuddy：未安装。
- Claude 参与的交替：Claude 无法调用模型，未执行。

## 6. 需要人工完成的验收

在新的临时目录准备合成项目（路径含中文和空格，`git init`，放一个 hello.py），每项保存客户端原始回答和 `.agent` 前后哈希：

1. Claude Code：修复登录后运行 `py -3 -X utf8 tests/client_live.py --primary claude --secondary opencode --out <结果文件>`；或在用户级安装 `py -3 kit.py install-client claude` 后手动执行：未接入问答（反向）、“启用项目治理”、`/project-anchor 添加任务…`、保存决定、交接、新会话恢复、已接入普通问答（反向）、`/compact` 后检查 SessionStart(compact) 记录：`py -3 kit.py doctor <项目> --client claude --session-id <ID> --expect-event PreCompact`。
2. Claude 交替：第 1 项结束后用 OpenCode 新会话把 T1 改为进行中，再用 Claude 新会话只读询问 T1 状态（Cursor 与 OpenCode 的交替已在第 5 节完成）。
3. Cursor：用 Cursor 直接打开合成项目（不在本仓库工作区内），在合成项目内放 `.agents/skills/project-anchor`（`install-client agents --home <独立目录> --skills-dir <项目>/.agents/skills`），新开 Agent 聊天分别输入 `/project-anchor 查看进度，只读`、自然语言“启用项目治理”、接入后新聊天“继续这个项目”和与项目无关的问答，核对文件变化；确认新聊天会按项目 AGENTS.md 先读状态。
4. WorkBuddy：`install-client agents --home <独立目录> --skills-dir <项目>/.codebuddy/skills`（或社区资料中的 `~/.workbuddy/skills`），在技能面板确认出现 project-anchor，再执行与第 3 项相同的正反向请求。
5. Codex：合并后 `py -3 kit.py install-global`，在 `/hooks` 审核，运行 `doctor --native-hooks --native-skills`，并按 SMOKE_TEST.md 复验启动、压缩和接续。

<a id="independent-review"></a>
## 7. 独立复核与补充验收（2026-10-09）

本节由 Codex 在 `feat/universal-agent-skills`、原提交 `736faae` 上独立执行。前六节的历史结果、失败和限制保留；本节不把历史样本升级为本轮通过。用户授权同一分支提交、推送及更新 Draft PR #1，**未授权更新真实 Codex 安装**，也未授权处理任何客户端认证。

### 7.1 源码与历史声明核对

- 本轮使用 `origin/main...HEAD` 审查。仓库没有本地 main 分支，直接执行 `git diff main...HEAD` 返回 unknown revision；没有创建本地分支，而是读取已存在的远端 main。
- 对比 main 的程序输出及源文件：Codex Hook 命令字符串、Codex runtime.json 字节、全局 AGENTS.md 模板均一致，VERSION 仍为 1.2.0。核心状态与任务实现没有被另写一套。
- 原 **151 项自动回归独立复跑：151 通过 / 0 失败**。同时抽查安装所有权、卸载恢复、中断回滚、旧修订及旧快照保护的代码与测试，未发现本轮需要修改的新增业务核心缺陷。
- 本机 PATH 实际发现 **codex-cli 0.162.0-alpha.2**；第 5 节“本机没有 Codex CLI”的历史结论不适用于本轮运行环境。
- 历史 Cursor 合成项目只读指纹与记录一致：revision 8、T1 doing、hello.py 原样、0 次提交。该抽查不是新的 Cursor 模型测试，不能证明 Cursor 主聊天或规则加载。
- 项目初始 CURRENT 落后于任务修订，体检给出 WARN；收尾通过正式 state 程序同步，未手改账本。

发现并修正的验收/说明问题：

1. `tests/client_live.py` 原先只保存截断的工具参数、stderr 和整理后的回答，不能提供完整原始响应或全部 `.agent/` 文件哈希；失败检查也没有可靠的非零退出码。现保存逐请求完整 stdout/stderr、命令与 cwd、全目录 SHA-256、业务文件哈希及提交数；遇到失败先保存并停止依赖步骤。超时保留部分输出，不改成成功。
2. 新增 Codex 工作流测试入口，使用现有登录与临时项目级通用 Skill；本次调用关闭 Hook、使用 ephemeral 会话，不安装真实用户配置、不复制认证。这不是正式安装或生命周期验收。
3. COMMANDS 首段仍要求 codex_home，WORKFLOWS 诊断仍无条件附加 Codex `--native-*`，与新增通用安装冲突。已按 runtime.json 来源区分参数，补充任务 plan 的合法值及批准边界；未用重跑失败请求证明这些文字修改有效。
4. 关闭 Hook 与 ephemeral 会话仍不能保证 Codex 不写用户配置。收尾发现原生 CLI 自动在 config.toml 登记临时项目信任，首次配置保持检查失败。新测试器记录前后配置哈希，发现变化即判失败并停止，不自动覆盖未知用户修改；只记录哈希，不保存配置内容或认证值。

新增 6 项证据、异常回合与配置变化检查后，**最终完整回归 157 通过 / 0 失败**。初次 151 项、中间 155/156 项和最终 157 项输出分别保留，没有覆盖。超时/启动异常也会保存回合前后指纹并记为失败，不继续发送依赖请求。

### 7.2 自动化与模拟分别统计

| 层级 | 本轮结果 | 解释 |
| :--- | :--- | :--- |
| 完整自动化回归 | 157 通过 / 0 失败 | 包含原 151 项及 6 项完整响应、完整哈希、异常回合和真实配置变化检查 |
| 单独记录的模拟检查 | 3 通过 / 0 失败 | Claude startup/manual 输入、已审核摘要、双适配器交替与旧修订/旧快照保护；已包含在 157 项中，不另外累加 |
| Codex 兼容性程序核对 | 4 通过 / 0 失败 | 命令、runtime 字节、全局模板、版本；不等于客户端生命周期通过 |

### 7.3 真实客户端工作流与交替

本轮创建新的中文/空格路径合成项目，含 hello.py 与空 Git 仓库。通用 Skill 安装在项目 `.agents/skills`，清单位于独立临时目录；原生发现与实际命令确认使用这份新入口。没有重装真实用户 Skill。

首次 OpenCode 流程：**3 通过 / 1 失败**。

- 通过：未接入项目只读反向请求、自然语言启用治理、自然语言批准目标。
- 失败：显式添加 T1 时，模型尝试 grep 工具箱 kit.py，OpenCode 自动拒绝工作区外访问，最终没有回答，任务没有创建。客户端退出码为 0，但新测试器判定失败并返回 1；没有继续执行依赖此任务的原流程。
- 原文：`permission requested: external_directory (C:\Users\chs\Desktop\codex-plus\*); auto-rejecting`。工具事件另记录 `The user rejected permission to use this specific tool call.`；这不等同于用户实际在界面点击拒绝。
- 未放宽权限、未更换模型、未重跑这个失败请求。

随后用独立记录补做尚未执行的交替步骤，**5 通过 / 0 失败**：

| 客户端 | 步骤 | 证据 |
| :--- | :--- | :--- |
| Codex | 显式调用并读取 OpenCode 已保存的目标 | 加载项目级 SKILL/run.py，回答正确，全部项目状态哈希不变 |
| Codex | 将 T1 从 todo 更新为 doing | 通过正式程序写入，任务与进度变化，业务文件不变 |
| OpenCode | 新会话读取 Codex 更新的 T1 | 回答 doing，全部项目状态哈希不变 |
| OpenCode | 自然语言保存日志 UTF-8 决定及原因 | DECISIONS 与修订实际变化，经正式程序写入 |
| Codex | 新会话读取 OpenCode 保存的决定 | 回答 UTF-8、理由和 T1，状态哈希不变 |

**限制：T1 是测试器通过正式 kit.py 预置的任务，不能将 Codex 后续更新成功计为 OpenCode 添加任务通过。** 这五步证明指定场景的双向接续，不证明所有跨客户端操作或生命周期可用。工具调用原始记录已核对，未发现直接改写受保护状态；每步 hello.py 不变、Git 提交数为 0。

交替完成后另做一次 CLI 旧修订写入：被拒绝，全部 `.agent/` 哈希不变。原文仍为 `FAIL: 修订冲突: 当前 4，请求 3`；未重试，不把它计入模型工作流通过数。

本轮工作流合计 **8 通过 / 1 失败**：Codex 3/0，OpenCode 5/1。认证检查另计。

### 7.4 Codex 配置、原生查询与安装授权边界

- 真实现有安装只读体检（含原生 Skill/Hook 查询）：初始 **PASS 21、WARN 3、FAIL 0、UNVERIFIED 5**。WARN 原文分别为 Hook 脚本版本、Skill 模板版本、CURRENT 修订；原生现有命令的发现/信任查询有证据，但不能替代本分支脚本运行或压缩效果。
- 临时 CODEX_HOME **和临时 skills-dir 同时隔离**后，安装与原生查询完成：**PASS 22、WARN 3、FAIL 0、UNVERIFIED 6**。WARN 是目标草案、同名 Skill 来源、隔离 Hook 未审核；未调用模型或触发这些隔离 Hook。
- 没有运行真实 install-global、没有修改原生 Hook 信任。正式更新、启动/手动压缩和压缩后接续未验收。
- 首次收尾的 11 文件哈希比较发现 config.toml 变化，其他 10 文件不变。确认新增项是本轮合成项目的信任表；只删除这一个表即可与初始**完整文件 SHA-256 完全一致**，因此仅撤销该项，未覆盖其他用户设置或改变认证字段。最终 11 文件全部恢复初始哈希。
- 首次失败及精确恢复证据分别保存在本机 `real-config-comparison-before-restore.json`、`config-restore-plan.json`、`config-restore-result.json`、`real-config-comparison.json`。未重跑模型请求验证恢复，未把配置副作用隐去，也不把“未执行安装”写成“配置从未变化”。不保存配置正文或迁移认证信息。
- 同步 CURRENT 后的真实只读体检为 **PASS 22、WARN 2、FAIL 0、UNVERIFIED 5**；剩余 WARN 是 Hook 脚本版本和 Skill 模板版本。该复查后 11 文件仍与初始哈希相同。

### 7.5 Claude、WorkBuddy 与 Cursor 未执行项

- Claude Code 2.1.153：只执行一次“只回答 OK”认证检查（现有登录，命令级关闭两个会记录合成会话的用户插件）。原始事件连续出现 `error_status: 401`、`error: authentication_failed`，客户端内部重试后在 120 秒超时。**认证检查 0 通过 / 1 失败**；自然语言、Claude 参与的交替及压缩后 SessionStart(compact) 未执行。不将客户端内部重试描述为多次独立测试。
- WorkBuddy：未发现可调用命令、Windows 安装登记或开始菜单入口，未安装、未执行模型测试；保持未验证。
- Cursor：未启动子代理或替代用户主聊天。另准备了一个尚未治理初始化的独立临时项目及项目级通用 Skill，供人工验收；准备成功不是 Cursor 支持验证。

### 7.6 仍需用户执行的准确步骤

**Cursor 主聊天与项目规则：**

1. 本轮已准备的项目路径保存在本机 `cursor-manual-fixture.json`；读取该文件的 project 字段，用 Cursor“打开文件夹”打开此目录，不要作为工具仓库的附加目录。
2. 在 Customize → Skills 中确认 project-anchor 出现，并核对来源为本项目 `.agents/skills/project-anchor/SKILL.md`。这一步需要保存界面证据，不以模型自述替代原生发现。
3. 新开 Agent 聊天，先问“hello.py 的 add 返回什么？只读，不修改”。应没有 `.agent/`；再说“为当前项目启用 Project Anchor 治理，只接入治理，不改业务代码”。接入后核对治理文件、hello.py 和 0 次提交。
4. 提供并批准合成项目目标，显式输入 `/project-anchor 添加一个任务草案`，检查正式程序调用与账本。未批准草案不得开始。
5. 形成一个明确决定并要求记录，保存断点；**另开全新聊天，不显式点名 Skill**，只说“继续这个项目，只读告诉我目标、任务、最近决定和下一步”。保存实际读取项目 AGENTS.md/治理文件的证据，并核对状态哈希不变。这一步验证直接项目聊天与持久规则，不由本仓库子代理结果代替。

**Claude：**由用户处理登录；成功后先运行 `claude -p "只回答 OK"`，再运行第 6 节的真实工作流与 `/compact` 检查。不要在认证失败时反复运行整套流程。

**Codex 正式安装及生命周期：**只有用户另外授权真实 install-global 后，备份并更新真实配置，在 `/hooks` 审核当前定义，再按 SMOKE_TEST.md 检查 SessionStart、手动 PreCompact 和 SessionStart(compact)。本轮临时安装与关闭 Hook 的模型请求不替代这些步骤。

**OpenCode 完整任务添加：**保留本轮拒绝记录。若用户决定授予工具目录必要访问权限，先在 OpenCode 自身的权限机制中明确审核，再以新编号验收；不能自动放宽权限或绕过拒绝。WorkBuddy 保持未验证，本轮不安装。

上述步骤未全部完成，PR #1 保持 Draft，不建议直接发布。原始 stdout/stderr、逐请求命令与前后哈希在系统临时目录保留；本机指针为 `.agent/runtime/universal/independent_review_folder.txt`。不上传原始聊天、日志或私人配置。

## 8. 第 7 节之后的补充验收（2026-10-10）

用户授权：OpenCode 新编号复验、真实 install-global（先备份）、整理 Cursor 主聊天人工清单。第 7 节的失败记录不改写。

### 8.1 OpenCode 新编号复验

第 7.3 节失败原因核对：显式添加任务时，模型为确认 `plan` 合法值用 grep 工具读取工具箱 `kit.py`，该路径在测试项目外，OpenCode 非交互运行自动拒绝 `external_directory`，模型随后无回答结束。第 7.1 节已在 COMMANDS.md 补充 plan 合法值，未放宽 OpenCode 权限。

新合成项目、项目级 `install-client agents`、deepseek/deepseek-flash、`--secondary none`（避免原生 Codex 登记临时项目信任）：**8 通过 / 0 失败**。显式添加任务步骤读取 runtime.json、COMMANDS.md 后经 run.py 写入，T1 为 todo、plan approved（请求中明确“计划已获我批准”）；全部 8 步 stderr 无权限请求，文件工具无项目外路径。单次运行只说明本次未越界，不保证模型以后不会尝试读取工具箱源码。

### 8.2 真实 Codex 安装更新

- 执行前把 `~/.codex/AGENTS.md`、`hooks.json`、`config.toml`、`codex-rules/install.json` 和 `~/.agents/skills/project-anchor` 备份到用户目录 `.project-anchor-manual-backups/<时间>`，只记录哈希。
- `py -3 kit.py install-global`：changed=true，trust=UNVERIFIED，工具自身备份另存于 `codex-rules/runtime/backups`。
- 前后哈希：`AGENTS.md`、`hooks.json`、`config.toml` 不变；`install.json` 与 Skill 的 SKILL.md、CLIENTS.md、COMMANDS.md、WORKFLOWS.md、run.py 变化。
- `doctor . --native-hooks --native-skills`（Cursor 终端）：0 FAIL；此前的“Hook 脚本版本”“Skill 模板版本”WARN 变为 PASS。该终端 PATH 中没有 codex，原生 Skill 发现与 Hook 信任为 UNVERIFIED，需要在 Codex 环境内复查。
- Hook 命令字符串未变，但信任状态、启动和压缩执行都未复验，不能由本节推断。

### 8.3 Cursor 人工测试项目刷新

第 7.5 节准备的 Cursor 人工项目中，项目级 Skill 的 COMMANDS.md、WORKFLOWS.md 早于第 7.1 节修正。已对同一 home 和 skills-dir 重新 `install-client agents`（更新并备份旧文件），现与仓库一致；项目仍未接入治理，hello.py 未改，0 次提交。用户级 `~/.agents/skills/project-anchor` 也已是本分支版本，Cursor 可能同时发现两份同名 Skill，人工验收时需记录界面显示的来源。

### 8.4 仍需用户执行

- Cursor：按第 7.6 节在 Cursor 中直接打开人工项目执行。
- Codex：在 Codex 中打开本机记录于 `.agent/runtime/universal/codex_lifecycle_project.txt` 的合成项目（已 `init-project`、`git init`、0 次提交），`/hooks` 审核 SessionStart、PreCompact；新会话确认 SessionStart；`/compact` 后确认 PreCompact 快照和 source=compact 的 SessionStart；然后 `py -3 kit.py doctor <项目> --session-id <ID> --expect-event PreCompact` 与 `--native-hooks --native-skills`。
- Claude Code 登录与 WorkBuddy 安装仍由用户处理。

PR #1 保持 Draft。

## 9. Cursor 主聊天人工验收（2026-10-10）

Cursor 3.23.12。用户用 `cursor -n` 在新窗口直接打开第 8.3 节的人工项目（不在本仓库工作区内），每步在该窗口的 Agent 聊天中输入；每步后由本仓库终端运行 `cursor_setup.py fp` 记录指纹（revision、任务、CURRENT 哈希、决定、hello.py、提交数）。回答与工具调用由用户转述，截图仅有斜杠菜单一张。

| # | 请求 | 结果 | 指纹证据 |
| :--- | :--- | :--- | :--- |
| 0 | 基线 | — | initialized false |
| 1 | 新窗口打开 | 通过 | 不变 |
| 2 | 确认 Skill 出现 | 部分 | 斜杠菜单只出现一项 `/project-anchor`；未截 Settings 页，界面来源未确认 |
| 3 | 未接入只读问答（反向） | 通过 | 回答 `a + b`；initialized false |
| 4 | 自然语言启用治理 | 通过 | revision 0，新建 `.agent/`、AGENTS.md、.gitignore、.gitattributes；hello.py 不变，0 次提交 |
| 5 | 提供并批准目标 | 通过（流程提前） | goal_approved true。Agent 未经要求建 T1 草案；用户随后另发消息批准 T1，Agent 写 `test_hello.py`（6 例，`python -m unittest` 通过）并标 done，revision 6 |
| 6 | 显式 `/project-anchor` 添加草案（因 T1 已完成改为 T2，并要求只建不开始） | 通过 | revision 8，T2 todo；`test_hello.py` 修改时间与哈希不变 |
| 7 | 记录 UTF-8 决定并保存断点 | 通过 | revision 10，decisions_utf8 true，CURRENT 哈希变化，T2 仍 todo |
| 8 | 全新聊天、不点名 Skill：“继续这个项目，只读…” | 通过 | 回答含目标、T1 done、T2 草案、D1 UTF-8；指纹不变，项目内无新写入文件 |
| 9 | 全新聊天：“add(2, 3) 等于几？只回答数字。”（反向） | 通过 | 回答 5；指纹不变，项目内无新写入文件 |

第 8 步工具调用（Agent 自述，按顺序）：同时读取项目 `.agents/skills/project-anchor/SKILL.md` 并用文件搜索查找 `.agent/**`（后者报“系统找不到指定的路径”）；PowerShell `-LiteralPath` 列出 `.agent/` 并读项目 runtime.json；运行项目 Skill 的 `run.py status`，读取 GOAL、CURRENT、DECISIONS、tasks.json。未用工具读取 AGENTS.md，Agent 称项目与用户目录 AGENTS.md 已作为常驻规则注入上下文。

结论与限制：

- Cursor 主聊天可在新会话中不点名 Skill 恢复目标、任务和决定，且只读请求不改状态；反向请求未误触发治理。
- 项目规则注入与 Skill 自动调用在第 8 步同时发生，**不能单独证明项目 AGENTS.md 规则足以触发恢复**；规则注入只有 Agent 自述，无界面证据。需另做只放 AGENTS.md、不放 Skill 的对照。
- 两份同名 Skill（项目 `.agents/skills` 与用户 `~/.agents/skills`）的 SKILL.md 字节相同，界面无法区分；第 8 步实际运行项目那份 run.py 与 runtime.json（home 指向测试目录），用户级 `~/.codex` 无新写入。
- 文件搜索异常：第 8 步在中文/空格工作区根目录查找 `.agent/**` 报错，本仓库会话无法复现（工作区路径为英文）。另在本仓库会话中对照：Glob/Grep 指定工作区外目录时（中文空格路径与纯英文路径均如此）静默返回本仓库文件、不报错，与第 5 节子代理现象一致。Skill 说明不依赖文件搜索工具，未修改。
- 未执行：Settings → Rules/Skills 页截图；未经追加批准的 T1 草案边界（以第 6 步 T2“只建不开始”代替）。
