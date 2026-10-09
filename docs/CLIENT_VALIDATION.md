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
