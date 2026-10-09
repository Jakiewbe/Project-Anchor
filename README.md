# Project Anchor · 项目锚

**为智能体的长期项目提供目标锚定、持久记忆和进度管理。**

长项目中，对话会被压缩，模型会切换，工作也会跨会话。Project Anchor 把目标、任务、决定和工作断点保存为可校验的项目文件，让智能体继续工作时有据可查，让用户看得见项目进度。

当前版本 **1.1.4**，已实现 Codex 的本地集成。项目名称采用 **Project Anchor**；为了保留现有安装兼容性，Python 工具、Skill 和配置目录暂时仍使用 `codex-rules`。面向其他智能体的通用 Skill 是后续方向，当前尚未实现对应适配，也没有 `$project-anchor` 调用入口。

运行程序只依赖 **Python 标准库**，不需要数据库、网页、后台服务或付费 API。要求 Python **3.11+**；克隆和版本管理需要 Git。Windows 是主要验证环境，安装 Hook 需要支持相应机制的本地 Codex 客户端。

## 为什么做这个项目

| 日常问题 | 当前提供的能力 |
| --- | --- |
| 长项目逐渐偏离最初目标 | 独立保存 GOAL、CURRENT 和 DECISIONS；接续时读取最新磁盘状态 |
| 代码改动没有版本检查点 | 检查 Git 状态，要求保留已有修改；提交和推送需授权 |
| 不知道任务完成到哪里 | 单一任务账本、依赖和验收记录，自动生成 PROGRESS |
| 不知道规则或 Hook 是否生效 | doctor 分层检查文件、配置、执行记录与未验证事项 |
| 规则积累后难以保存、迁移 | 文件式工具箱、安装清单、自动备份及重新安装流程 |
| 项目结束后经验没有沉淀 | 决策、已验证教训和复盘草案；用户确认后进入知识库 |

## 四部分如何配合

| 部分 | 负责什么 |
| --- | --- |
| Skill | 理解自然语言，选择工作流，调用程序，解释结果 |
| Python | 文件操作、校验、任务修改、锁、事务、备份、快照与诊断 |
| AGENTS.md | 长期行为约束、目标边界和授权要求 |
| Hook | 客户端支持的生命周期事件，不依赖模型是否选中 Skill |

所有入口共用同一套 Python 核心和任务账本，无第二套状态系统。

```text
.agent/
├── GOAL.md        # 已确认目标、约束、非目标与验收条件
├── CURRENT.md     # 当前阶段、断点、阻塞及下一步
├── DECISIONS.md   # 重要决定和原因
├── LESSONS.md     # 有证据的经验教训
├── tasks.json     # 唯一任务账本
├── PROGRESS.md    # 程序生成的进度视图
├── state.json     # 内容哈希、修订号与历史
└── runtime/       # 本地日志、输入草稿与快照，不提交 Git
```

复盘时另生成 RETRO.md 草案。受保护状态通过程序修改，不手工改账本。

## 实测结果与边界

自动测试、隔离模拟和真实客户端验收分别记录，不能相互替代。

| 实测项目 | 结果与限制 |
| --- | --- |
| 本次发布自动回归 | 首轮 121 项通过、1 项因沙箱拒绝 Git 通信管道而失败；该项在获准环境复测 1 项通过、0 项失败，原始失败保留 |
| Desktop 启动与手动压缩 | SessionStart、PreCompact(manual)、SessionStart(compact) 有实际执行证据；旧快照未覆盖最新状态 |
| 新会话治理记录盲测 | 6 项通过、0 项失败 |
| 五种自然决定当回合保存 | 4 项通过、1 项失败；一项在下一回合才补记 |
| 五个独立新会话读取已保存决定 | 5 项通过、0 项失败；延迟保存样本在补记后才测试 |
| 并发写入 | 冲突请求被明确拒绝，无返回成功但丢失的更新；不代表并发请求全部成功 |

详细方法和失败见 [Desktop 补充验收](docs/DESKTOP_ACCEPTANCE.md)、[自动与集成验证记录](docs/VALIDATION.md)、[Skill 验证记录](docs/SKILL_VALIDATION.md)。历史文档保留当时版本和环境，不作为当前客户端状态的证明；原始运行日志保留在本机，不上传仓库。

已知边界：

- 不保证模型每次遵守规则、选中 Skill 或立即保存决定。
- 未保存聊天决定的一次压缩保留，不证明跨会话或长期可靠。
- Desktop 自然发生的自动压缩、早期决定经历多轮压缩、两周真实使用及第二台电脑恢复尚未完成验收；CLI 受控压缩结果另行记录。
- 修订冲突要求重新读取、核对意图后再决定是否重试；不自动合并多会话意图。
- 1.1.4 显式重复提交相同任务状态仍可能成功并增加修订；最小修复尚未实施。
- 项目文件只读或无法安全写入时会失败并回滚，不自行解除保护。

## 自然语言使用

安装一次后，日常在目标项目中直接告诉 Codex：

- 帮我初始化项目管理。
- 根据我的项目目标制定任务草案。
- 现在项目进度如何？只查看，不修改。
- 把 T1 标记为完成，验收证据是……
- 记录我们确定的技术路线。
- 整理工作状态，准备切换会话。
- 检查当前工作是否偏离最初目标。
- 检查全局规则和 Hook 是否正常。
- 总结项目经验教训，生成复盘草案。

Skill 选择流程并调用现有 Python 程序，用户不需要记住命令。全局安装后，首次在明确项目目录开展实际工作时默认检查并接入项目管理；已有状态先读取，不重新初始化，不扫描批量修改其他目录。只读代码解释、知识查询或用户要求仅改指定文件时不初始化。新目标模板仍需用户确认，接入不授权自动 Git 初始化或提交。自动触发由 Codex 根据描述判断，不能保证每次成功；可显式输入 `$codex-rules` 再说明需求。

新增治理记录与重建业务项目分开：接入会创建 `.agent/`，保留并追加 `AGENTS.md`、`.gitignore`、`.gitattributes`，不改业务代码和依赖。旧要求“不要重新初始化项目”应根据原文判断是否针对业务工程；明确禁止治理文件或限定文件范围仍须遵守，审批拒绝也不能绕过。

Skill 不维护新账本，也不替代自动 Hook。任务完成仍需真实证据，目标变更和跨项目知识入库仍需用户确认。后面的 CLI 说明供排错及独立操作使用。

本机验证及限制见 [Skill 验证记录](docs/SKILL_VALIDATION.md)。本轮按补充材料完成 [现成方案隔离评估](docs/ALTERNATIVES_EVALUATION.md)，保留现有实现，不继续扩展或替换项目状态系统。

## Windows 安装和初始化

首次安装，在 PowerShell 克隆仓库：

```powershell
git clone https://github.com/Jakiewbe/Project-Anchor.git
Set-Location Project-Anchor
```

随后在工具箱目录执行：

```powershell
py -3 --version
py -3 kit.py --version
py -3 kit.py install-global
py -3 kit.py doctor
py -3 kit.py doctor --native-skills
py -3 kit.py doctor --native-hooks --native-skills
```

`install-global` 是你明确修改真实用户配置的操作。开发测试不会替你执行这个操作。默认使用环境变量 CODEX_HOME；未设置时使用用户目录下的 `.codex`。也可通过 `--codex-home "路径"` 安装到指定目录。安装只修改 AGENTS.md 管理块、hooks.json 和工具自身的安装清单，不修改 config.toml。

同时安装用户级 Skill 到用户目录下的 `.agents/skills/codex-rules/`，符合 [Codex 官方 Skill 目录说明](https://learn.chatgpt.com/docs/build-skills)。CODEX_HOME 与 Skill 目录分别解析；自定义 CODEX_HOME **不会**自动把用户 Skill 隔离。开发测试必须同时传入 `--skills-dir "临时父目录"`。相同命令可重复执行；更新前验证所有管理文件哈希，发现人工改动则拒绝覆盖并保留现场。其他 Skill 和后来新增的非管理文件不会被删除。

Skill 只安装说明、参考文档和一个轻量适配器；runtime.json 保存实际 Python、kit.py 和 CODEX_HOME 的绝对路径。调用不依赖 cwd，也不复制核心代码。换电脑克隆工具箱后重新安装会生成新的定位文件；程序迁移或版本不同会明确失败。

安装后重新启动本地 Codex，在支持 Hook 的 CLI 输入 `/hooks`，逐条审核并信任 SessionStart 和 PreCompact 的当前定义，见 [官方 Hook 文档](https://learn.chatgpt.com/docs/hooks)。**配置完成不等于已信任，信任不等于模型必定遵守。** 全局 AGENTS.override.md 可能覆盖全局 AGENTS.md，doctor 会提示。

Hook 是 Codex 在指定时机自动运行的本地脚本。一次审核启用后，进入/恢复/压缩后的会话提醒读取磁盘状态，压缩前保存已经落盘的状态快照，不依赖模型选择 Skill。重要决定仍需先保存，脚本不能替代聊天内容的总结。自然语言诊断会只读查询原生定义及信任状态；不会替用户写入信任数据库。初始化程序拒绝用户主目录和磁盘根目录，已有具体项目状态继续保留。

初始化一个新项目：

```powershell
$kit = (Resolve-Path .\kit.py).Path
$project = Join-Path $HOME "Documents\示例 项目"
py -3 $kit init-project $project --name "示例项目"
py -3 $kit status $project
py -3 $kit doctor $project
```

已有 Git 项目应在仓库根目录接入。`--git-init` 仅在用户明确授权初始化 Git 时使用。已有 AGENTS.md、.gitignore 和 .gitattributes 会保留并追加约定；其中只对 .agent 状态关闭 Git 换行转换，保证克隆后哈希仍有效。未知 .agent 状态文件不会覆盖。重复初始化不会覆盖现有状态。工具不会自动创建分支、提交或推送。

Linux/macOS/WSL 使用 Python 3.11+ 的 `python3 kit.py ...`。每个环境各自重新安装，不能复用 Windows 生成的 Hook 命令；当前真实客户端验收不能直接视为跨平台通过。

## 完整日常示例

日常主要用 `status`、`task`、`state`，里程碑可用 `snapshot`，收尾用 `retro`。所有任务与状态修改必须带 `status` 显示的**项目 revision**，不是 task_revision；过期修订会拒绝写入。

先确认真实目标。复制 .agent/GOAL.md 到一个编辑文件，填写所有章节，取得用户批准后保存：

```powershell
$goalFile = Join-Path $project "goal-review.md"
Copy-Item -LiteralPath (Join-Path $project ".agent\GOAL.md") -Destination $goalFile
# 编辑 goal-review.md，填写目标、背景、约束、非目标、验收标准及版本。
py -3 $kit state update $project GOAL.md --file $goalFile --expected-revision 0 --reason "用户确认初始目标" --approved
```

目标批准会登记为目标版本 2。state.json 的版本号为准；文档中的版本文字也应如实填写。`--approved` 是对已有用户批准的记录，不是授权工具或模型自行批准。

创建任务草案（此例项目 revision 已为 1）：

```powershell
$taskFile = Join-Path $project "task-change.json"
@'
{
  "task_id": "T1",
  "title": "交付首个可运行版本",
  "description": "实现已批准目标中的核心功能",
  "milestone": "v1",
  "plan": "draft",
  "acceptance_criteria": ["用户按说明操作成功"],
  "dependencies": []
}
'@ | Set-Content -LiteralPath $taskFile -Encoding UTF8
py -3 $kit task add $project --file $taskFile --expected-revision 1 --reason "根据目标提出任务草案"
```

用户批准任务后再开始：

```powershell
@'
{"task_id":"T1","plan":"approved","status":"doing"}
'@ | Set-Content -LiteralPath $taskFile -Encoding UTF8
py -3 $kit task update $project --file $taskFile --expected-revision 2 --reason "用户批准计划并开始"
```

取得真实验收证据后完成：

```powershell
@'
{
  "task_id":"T1",
  "status":"done",
  "evidence":[{"type":"manual","criterion":1,"detail":"用户已按 README 操作并确认成功；填写真实日期及结果"}]
}
'@ | Set-Content -LiteralPath $taskFile -Encoding UTF8
py -3 $kit task update $project --file $taskFile --expected-revision 3 --reason "实际验收通过"
py -3 $kit status $project
```

以上证据文字是格式示例，必须替换为实际结果。证据类型可为 test、file、review、manual、command；每条必须有 detail 和对应验收标准的 criterion（从 1 开始）。**程序校验证据结构和覆盖范围，不会代替用户执行或判断实际验收。** 禁止用虚构记录标记 done。

状态转移：todo → doing/blocked/cancelled；doing → done/blocked/todo/cancelled；blocked → doing/todo/cancelled；done → doing（清空旧证据重新验收）；cancelled → todo。草案不能 doing/done，依赖全部 done 才可开始/完成；blocked 需要 blocker。所有变更保存原因和历史，取消代替物理删除。

重要进展后及时更新 CURRENT，重要决策更新 DECISIONS，已验证教训更新 LESSONS：

```powershell
$currentFile = Join-Path $project "current-review.md"
Copy-Item -LiteralPath (Join-Path $project ".agent\CURRENT.md") -Destination $currentFile
# 编辑 current-review.md，保留必要章节，不超过 50 行。
py -3 $kit state update $project CURRENT.md --file $currentFile --expected-revision 4 --reason "更新已完成工作与下一步"
py -3 $kit status $project --rebuild
py -3 $kit snapshot $project
py -3 $kit retro $project
```

如果直接编辑了 .agent 中的 Markdown 文件，普通 status 会拒绝读取漂移状态。审核后使用 `state adopt ... --file 原文件 --expected-revision 原修订 --reason 原因` 登记单个已审阅文档；GOAL 仍需 `--approved`。一次多个文件漂移需要先整理到只有一个文档变化再登记，不能自动猜测合并。tasks.json 禁止手工修改。

PROGRESS.md 是唯一账本生成的视图。取消任务计入总任务，但不计入有效任务完成率；草案计入并显示为 draft。写入中视图生成失败会让操作失败并回滚，不能把旧视图称为已更新。

## 会话恢复和快照

Hook 绑定**会话工作目录**。在 A 项目的会话中操作 B 项目，不等于 B 的 Hook 已运行；应在对应项目目录打开会话。

初始化项目默认不会把文件内容注入高级上下文。审核 GOAL 和 CURRENT 后明确登记：

```powershell
py -3 $kit trust-project $project --approved
```

这是项目内容审核，和 Codex `/hooks` 的原生 Hook 信任是两件事。GOAL/CURRENT 内容变化后，直接注入摘要需要重新登记；日常接续不要求重新登记，Hook 和全局规则要求先用 Skill 的 status 读取最新磁盘状态。未审核时不注入文档内容，读取的项目资料不成为高权限规则。审核后摘要是带边界说明的 JSON 数据，最长 6000 字符。CURRENT 落后于任务修订或目标未确认，会给出警告。

核对某个实际会话的 Hook 时，使用 `doctor <项目路径> --session-id <会话ID>`。客户端证据确认某事件应触发时，再加 `--expect-event SessionStart` 或 `--expect-event PreCompact`；缺少该会话真实调用记录将报告 FAIL。未确认压缩发生时不要求 PreCompact，模拟记录不证明原生调用。普通 doctor 的“最近执行”只是历史记录。

PreCompact 只保存已经持久化的白名单状态，不解析聊天、不提交 Git、不修改业务代码，也不自动恢复。失败返回非零、stderr 和 systemMessage，并保持 continue=true；实际客户端对失败的呈现需手动验收。默认保留 20 个有效本项目快照，日志最大 64 KiB 加一份轮转。

初始化时可以用 `--snapshot-keep 10 --log-max-bytes 131072` 设置保留策略。未知、损坏或其他项目的快照不会删除，doctor 会提示人工处理。

```powershell
py -3 $kit snapshot $project --check "某个快照的完整路径"
```

该命令检查身份、完整性及是否旧于磁盘，不恢复文件。状态灾难恢复建议从经过验证的 Git 检查点或备份恢复；不要仅凭时间戳覆盖当前状态。

## doctor 与测试

`PASS` 是对应检查有证据通过；`WARN` 是存在风险或冲突；`FAIL` 是失败；`UNVERIFIED` 表示没有足够证据。出现 FAIL 时 doctor 退出码为 1；WARN/UNVERIFIED 不会伪装成“全部通过”。

```powershell
py -3 kit.py doctor $project --json
py -3 -X utf8 -m unittest discover -s tests -q
py -3 -X utf8 tests\native_probe.py
```

自动测试使用临时目录，原生探针只在 .test-runtime 下创建隔离配置和临时会话，不读取真实认证配置、不发出模型请求、不绕过 Hook 信任。运行结果和协议记录存于被 Git 忽略的 .test-runtime。

完整验收边界见 [VALIDATION.md](docs/VALIDATION.md)；模型切换后执行 [SMOKE_TEST.md](SMOKE_TEST.md)。

Skill 的原生发现和真实自然语言验收见 [SKILL_VALIDATION.md](docs/SKILL_VALIDATION.md)。`doctor --native-skills` 使用公开 skills/list 检查当前客户端是否发现实际安装路径，不发送模型请求；自动触发与完整工作流仍需真实模型测试。

## 安全卸载、备份和迁移

```powershell
py -3 kit.py uninstall-global
```

只删除清单中未被改动的全局管理块和工具 Hook 组，保留其他配置和后来新增规则；如果管理内容被修改则拒绝卸载。运行备份和项目信任登记保留供人工检查，不会清理整个 CODEX_HOME。备份位于 CODEX_HOME/codex-rules/runtime/backups，仅备份 AGENTS、hooks.json 和安装清单，不备份认证或 config.toml。

卸载也只删除清单中未被修改的 Skill 管理文件，保留其他 Skill、用户新增文件和空目录。备份增加 `skill/` 子目录。全局配置与 Skill 可在不同目录或磁盘，通过同一事务记录协调；中断恢复必须核对两边的范围。首次安装到自定义 Skill 目录时，恢复使用原 `--skills-dir`，不能让事务日志自行授权任意路径。

写入中断先检查事务记录，明确选择继续或回滚：

```powershell
py -3 kit.py recover $project
py -3 kit.py recover $project --rollback
py -3 kit.py recover --global
py -3 kit.py recover --global --rollback
```

recover 只接受仍等于记录旧值或新值的文件；遇到额外编辑拒绝覆盖。不会无条件拿备份覆盖用户新配置。初始化中断时传入初始化的根目录；知识入库中断可用 `recover --knowledge`。

工具箱及项目稳定状态通过 Git 备份；提交前检查实际 diff，只选择相关文件，避免提交日志、快照、密钥和输入草稿。不要把整个 CODEX_HOME 同步到远程。迁移时在另一台机器克隆工具箱仓库，安装 Python 3.11+、Git 和 Codex，再重新运行 install-global、doctor，审核当前 Hook；直接注入项目内容前重新 trust-project。目标项目的状态也需要单独备份，本仓库不包含每个使用项目的状态，不迁移认证或原生信任。绝对路径会在重新安装时更新，旧路径丢失前不要删除原工具箱。

## 项目复盘与知识

retro 生成 .agent/RETRO.md 草案，填入原目标、已完成任务及证据、决策和教训；根因、经验和建议需人工完善，重复执行不会覆盖。knowledge/INDEX.md 按需检索，不自动注入全部知识。

准备 UTF-8 JSON，包含 title、conditions、evidence、limitations、source_project、lesson 六个非空字段；用户确认后执行：

```powershell
py -3 kit.py knowledge-add --file "审核过的教训.json" --approved
```

知识条目及索引可由 Git 维护，不会自动复制到 Codex 自带记忆系统。不得将个人材料、密钥或未经验证的猜测写入。模型验证结果可人工记录到 knowledge/model-log.md。

更多实现边界见 [架构](docs/ARCHITECTURE.md) 和 [故障排查](docs/TROUBLESHOOTING.md)。

## 源码结构

```text
kit.py                    # 唯一 CLI 入口
core/                     # 状态、任务、事务、安装和诊断
skills/codex-rules/        # Skill、参考文档及轻量调用适配器
global/AGENTS.md          # 全局约束源文件
project-template/         # 项目治理模板
hooks/                    # SessionStart / PreCompact
knowledge/                # 经确认的跨项目经验
tests/                    # 自动测试及真实客户端探针
docs/                     # 架构、验证与排错记录
```

## 许可证

[MIT License](LICENSE)。
