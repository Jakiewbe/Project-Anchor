# codex-rules v1.1

本地、文件式的 Codex 项目治理工具箱。项目目标、当前断点、决策、任务和经验保存在磁盘；Python 执行校验和安全写入。无数据库、后台服务、网页或付费 API，仅用 Python 标准库。

当前项目目录名可以是 `codex-plus`，工具名称仍为 `codex-rules`；不需要改名。要求 Python **3.11+**，Git 可选；安装 Hook 需要支持相应机制的本地 Codex 客户端。

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

Skill 选择流程并调用现有 Python 程序，用户不需要记住命令。自动触发由 Codex 根据描述判断，不能保证每次成功；可显式输入 `$codex-rules` 再说明需求。未初始化项目中的普通代码解释、局部修改和知识查询不应触发治理。

Skill 不维护新账本，也不替代自动 Hook。任务完成仍需真实证据，目标变更和跨项目知识入库仍需用户确认。后面的 CLI 说明供排错及独立操作使用。

本机验证及限制见 [Skill 验证记录](docs/SKILL_VALIDATION.md)。本轮按补充材料完成 [现成方案隔离评估](docs/ALTERNATIVES_EVALUATION.md)，保留现有实现，不继续扩展或替换项目状态系统。

## Windows 安装和初始化

在工具箱目录打开 PowerShell：

```powershell
py -3 --version
py -3 kit.py --version
py -3 kit.py install-global
py -3 kit.py doctor
py -3 kit.py doctor --native-skills
```

`install-global` 是你明确修改真实用户配置的操作。开发测试不会替你执行这个操作。默认使用环境变量 CODEX_HOME；未设置时使用用户目录下的 `.codex`。也可通过 `--codex-home "路径"` 安装到指定目录。安装只修改 AGENTS.md 管理块、hooks.json 和工具自身的安装清单，不修改 config.toml。

现在还会安装用户级 Skill 到用户目录下的 `.agents/skills/codex-rules/`。CODEX_HOME 与 Skill 目录分别解析；自定义 CODEX_HOME **不会**自动把用户 Skill 隔离。开发测试必须同时传入 `--skills-dir "临时父目录"`。相同命令可重复执行；更新前验证所有管理文件哈希，发现人工改动则拒绝覆盖并保留现场。其他 Skill 和后来新增的非管理文件不会被删除。

Skill 只安装说明、参考文档和一个轻量适配器；runtime.json 保存实际 Python、kit.py 和 CODEX_HOME 的绝对路径。调用不依赖 cwd，也不复制核心代码。换电脑克隆工具箱后重新安装会生成新的定位文件；程序迁移或版本不同会明确失败。

安装后重新启动本地 Codex，在 CLI 输入 `/hooks`，逐条审核并信任 SessionStart 和 PreCompact 的当前定义。**配置完成不等于已信任，信任不等于模型必定遵守。** 全局 AGENTS.override.md 可能覆盖全局 AGENTS.md，doctor 会提示。

初始化一个新项目：

```powershell
$kit = (Resolve-Path .\kit.py).Path
$project = Join-Path $HOME "Documents\示例 项目"
py -3 $kit init-project $project --name "示例项目" --git-init
py -3 $kit status $project
py -3 $kit doctor $project
```

已有 Git 项目应在仓库根目录初始化，省略 `--git-init` 即可。已有 AGENTS.md、.gitignore 和 .gitattributes 会保留并追加约定；其中只对 .agent 状态关闭 Git 换行转换，保证克隆后哈希仍有效。未知 .agent 状态文件不会覆盖。重复初始化不会覆盖现有状态。工具不会自动创建分支、提交或推送。

Linux/macOS/WSL 使用 Python 3.11+ 的 `python3 kit.py ...`。每个环境各自重新安装，不能复用 Windows 生成的 Hook 命令。

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

初始化项目默认不会把文件内容注入高级上下文。审核 GOAL 和 CURRENT 后明确登记：

```powershell
py -3 $kit trust-project $project --approved
```

这是项目内容审核，和 Codex `/hooks` 的原生 Hook 信任是两件事。GOAL/CURRENT 的内容变化后需要重新登记；未审核时 Hook 只提供固定提醒，提示读取磁盘项目资料。审核后恢复摘要是带边界说明的 JSON 数据，最长 6000 字符；不能把数据中的指令当成规则。CURRENT 落后于任务修订或目标未确认，会给出警告。

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

工具箱及项目稳定状态通过 Git 备份；提交前检查实际 diff，只选择相关文件，避免提交日志、快照、密钥和输入草稿。不要把整个 CODEX_HOME 同步到远程。迁移时在另一台机器克隆你的私有工具箱仓库，安装 Python 3.11+ 和 Git，再重新运行 install-global、doctor，审核当前 Hook；项目恢复后重新 trust-project。绝对路径会在重新安装时更新，旧路径丢失前不要删除原工具箱。

## 项目复盘与知识

retro 生成 .agent/RETRO.md 草案，填入原目标、已完成任务及证据、决策和教训；根因、经验和建议需人工完善，重复执行不会覆盖。knowledge/INDEX.md 按需检索，不自动注入全部知识。

准备 UTF-8 JSON，包含 title、conditions、evidence、limitations、source_project、lesson 六个非空字段；用户确认后执行：

```powershell
py -3 kit.py knowledge-add --file "审核过的教训.json" --approved
```

知识条目及索引可由 Git 维护，不会自动复制到 Codex 自带记忆系统。不得将个人材料、密钥或未经验证的猜测写入。模型验证结果可人工记录到 knowledge/model-log.md。

更多实现边界见 [架构](docs/ARCHITECTURE.md) 和 [故障排查](docs/TROUBLESHOOTING.md)。
