<div align="center">
  <img src="docs/assets/hero.svg" alt="Project Anchor — Keep the goal. Carry the context." width="100%">

  <p><strong>换个会话，接着做对的事。</strong></p>
  <p>File-based project memory and governance for AI agents.</p>

  <a href="CHANGELOG.md"><img src="docs/assets/badge-version.svg" alt="1.5.1"></a>
  <a href="pyproject.toml"><img src="docs/assets/badge-python.svg" alt="Python 3.11+"></a>
  <a href="pyproject.toml"><img src="docs/assets/badge-runtime.svg" alt="Python standard library"></a>
  <a href="LICENSE"><img src="docs/assets/badge-license.svg" alt="MIT License"></a>

  <p>
    <a href="#why">解决什么问题</a> ·
    <a href="#quick-start">安装</a> ·
    <a href="#usage">使用</a> ·
    <a href="#upgrade">升级</a> ·
    <a href="#clients">支持范围</a> ·
    <a href="#docs">文档</a>
  </p>
</div>

---

Project Anchor 把项目目标、任务、决定和工作断点保存在仓库的 `.agent/` 中。Agent 换会话或压缩上下文后，可以重新读取磁盘记录，明确本轮做什么、做到哪里，以及完成结论对应哪些检查。

**当前源码版本为 1.5.1。** [发布与下载](https://github.com/Jakiewbe/Project-Anchor/releases/tag/v1.5.1) · [更新记录](CHANGELOG.md) · [验证记录](docs/ITERATION_1_5_1_VALIDATION.md)。

<a id="why"></a>
## 把“记得做过”变成可以重新核对的记录

长周期项目容易丢失的，往往是这些区别：哪些决定已经确认，哪些任务获准执行，当前会话该接续什么，以及测试通过后成果是否又发生了变化。

Project Anchor 用项目文件保存事实，用一个 Python 核心检查写入。Skill 负责理解请求和调用程序；规则与 Hook 协助接续工作。

<a id="v14"></a>
<a id="v15"></a>
### 1.5.1 带来了什么

本版包含此前未正式发布的1.5.0接续/凭据/归档能力，并修正实际项目中断点关联和交付漏验的问题。

- 只读查询不创建锁、目录或日志；读取期间治理状态变化直接失败。
- CURRENT显式关联任务，报告unknown/changed/aligned；关联一致不证明文字语义。
- 交付物deliverables纳入批准范围，漏出验收inputs不能批准。
- 本轮查询只校验可见任务和完整依赖链，单次共享文件哈希。
- 历史完成、当前验收、交付覆盖、命令执行和自查分别展示；复盘仅生成证据索引。

| 需要解决的问题 | 对应能力 |
| :--- | :--- |
| 新会话接着做了历史遗留任务 | 显式设置本轮任务；没有指针时明确报告，不按更新时间猜测 |
| 写了“测试通过”，却找不到执行结果 | 执行已批准的检查命令，保存退出结果、日志摘要和材料指纹 |
| 审查结论没有依据 | Agent 记录查 Bug、修复依据和简化判断，来源始终标为自查 |
| 测试后文件又改了，仍沿用旧结果 | 输入内容变化后，结果显示过期；后续任务检查完整依赖链 |
| 状态变轻了，旧记录也丢了 | 先持久归档，再裁剪热记录；归档失败就停止裁剪 |
| 不同客户端对同一项目说法不一致 | CLI、Skill 与 DSH 只读工具共用核心查询结果 |

任务先建立草案，再记录已有批准。描述、验收标准、依赖和检查配置属于批准范围，改变范围需要修订并重新批准。

<a id="quick-start"></a>
## 安装：先准备 Git 和 Python

主要验证环境为 **Windows + PowerShell**。需要 **Git、Python 3.11+**，以及能够发现 Skill、执行本地 Python 的 Agent。工具运行时只依赖 Python 标准库。

### 1. 安装并检查环境

没有 Git 时，从 [Git 官方 Windows 安装页](https://git-scm.com/install/windows)下载安装，选择允许命令行使用 Git、加入 PATH 的选项；也可以在支持 WinGet 的 Windows 中运行：

```powershell
winget install --id Git.Git -e --source winget
```

安装后关闭并重新打开终端。准备好 Python 3.11 或更高版本，再检查：

```powershell
git --version
py -3 --version
```

两条命令都应显示版本号。找不到 `git` 时先检查安装与 PATH；找不到 `py` 时先完成 Python 安装。不要跳过这一步再继续排查 Skill。

### 2. 下载工具箱

```powershell
git clone https://github.com/Jakiewbe/Project-Anchor.git
Set-Location Project-Anchor
py -3 kit.py --version
```

保留这个目录：安装入口会记录实际 Python 和工具箱的绝对路径，移动或删除目录后需要重新安装定位信息。

### 3. 选择一种入口

**Codex 集成**：安装 Skill、全局规则管理块及工具自身的 Hook，保留其他技能和非管理配置，不修改 `config.toml`。

```powershell
py -3 kit.py install-global
```

**通用 Agent Skills**：安装同一份 Skill，不配置客户端规则或 Hook。

```powershell
py -3 kit.py install-client agents
```

同一个 Skill 目录只由一个安装入口管理。Codex 默认也使用 `~/.agents/skills/project-anchor/`，能扫描该目录的其他客户端可以复用；目录归属冲突时安装器会拒绝覆盖。

### 4. 在业务项目中启用

在 Agent 中打开业务项目目录，说：

```text
在当前项目启用 Project Anchor，保留已有工程和改动。
```

接入会创建 `.agent/`，并保留、追加 `AGENTS.md`、`.gitignore`、`.gitattributes` 中的治理约定；不会重建工程、修改依赖或自动初始化 Git。项目目标仍需按实际请求确认。

需要显式调用时，Codex 可用 `$project-anchor`，也可以直接点名技能。

<a id="usage"></a>
## 日常使用：直接说清楚这轮要做什么

![项目工作流：确认目标，批准任务，实施和检查，保存断点](docs/assets/workflow.svg)

| 场景 | 可以这样说 |
| :--- | :--- |
| 开始工作 | “本轮只处理 T1 和 T2，设置为本轮任务，不继续其他历史任务。” |
| 制定计划 | “根据目标列出任务草案、依赖和验收条件，先不执行。” |
| 批准实施 | “按刚才确认的范围实施，运行检查，再查 Bug 并检查是否能简化。” |
| 查看进度 | “只查看本轮任务、完成依据和阻塞，不修改状态。” |
| 保存决定 | “路线确定使用 JSON，记录原因；本轮先看模板，不开始实现。” |
| 换个会话 | “保存最新断点和已确认决定，接续时重新读取磁盘。” |

用户已授权的局部工作可以独立推进；批准目标、制定计划和批准实施分别判断。只读讨论不自动建任务，只改指定文件时不额外扩大治理写入范围。

### 查看本轮与检查结果

以下命令在工具箱目录运行，将路径和 ID 换成真实项目：

```powershell
py -3 kit.py status "D:\Projects\my-app" --brief --focus
py -3 kit.py status "D:\Projects\my-app" --task T1
py -3 kit.py history list "D:\Projects\my-app"
```

未设置本轮任务时，`--focus` 明确返回 `focus_missing`。它不会自动挑选未完成任务；已完成的本轮任务也会保留，直到显式切换或清空指针。

命令型标准由 `verify run` 实际执行；审查型标准由 `task review` 保存 Agent 自查。两者不能互相代替，也不能用文字手填程序执行证据。检查配置、批准与完整命令见[使用手册](docs/USAGE.md)和[命令参考](skills/project-anchor/references/COMMANDS.md)。

<a id="upgrade"></a>
## 从旧版本升级

**1.5.1 使用任务账本 schema 4。** 多台机器或多个客户端共用项目时，先统一工具箱版本，重新执行原安装命令，再迁移旧 schema 1/2/3 账本。

先获取源码更新并检查版本：

```powershell
git pull --ff-only
py -3 kit.py --version
```

如果 Git 提示本地有冲突或不能快进，先处理原因；不要强制覆盖工作区。确认已取得 1.5.1 后，重新执行原来选择的 `install-global` 或 `install-client` 命令。

读取项目修订号，再预检和迁移：

```powershell
py -3 kit.py status "D:\Projects\my-app" --brief

# 将 12 替换为刚读到的 revision；预检成功不会增加修订号。
py -3 kit.py migrate "D:\Projects\my-app" --expected-revision 12 --reason "升级到1.5.1" --dry-run
py -3 kit.py migrate "D:\Projects\my-app" --expected-revision 12 --reason "升级到1.5.1"
```

正式迁移前备份受影响的治理文件和清单，保留旧任务状态、批准快照与证据，不补造新版检查结果。schema1/2旧任务继续显示 `legacy`；schema3凭据仍按原范围判断，交付覆盖显示 `undeclared`。继续执行、重新结项或作为依赖前，需修订、显式声明deliverables（无本地交付填[]）、补齐检查并重新批准。旧版写入器会拒绝 schema 4，迁移后的保护回退见[使用手册](docs/USAGE.md#迁移与回退)。

<a id="clients"></a>
## 支持范围与验证边界

| 入口 | 当前范围 |
| :--- | :--- |
| Codex | 提供 Skill、规则和 Hook 安装；真实新会话与原生压缩后的显式 Skill 读盘接续已验收 |
| 通用 Agent Skills | 提供统一 Skill 与本地调用入口；发现目录和执行权限取决于客户端 |
| DeepSeek Harness | `install-client dsh` 安装 Skill 与规则；`packages/dsh/` 提供只读查询插件，真实宿主仍未验收 |
| Claude Code | 提供 `install-client claude`；真实客户端尚未完整验收 |
| Cursor / OpenCode / WorkBuddy | 可按通用 Skill 方式接入；以各客户端实际验证记录为准 |

Codex 的 Hook 需要在支持该入口的客户端中审核当前定义；Codex CLI 可使用 `/hooks`。可用以下命令分别核对安装与原生发现：

```powershell
py -3 kit.py doctor --native-hooks --native-skills
```

安装成功、Hook 已信任、脚本实际执行和模型遵守规则是不同层级。本轮真实接续验收关闭了 Hook，不代表自动注入已通过；远程 CI 与其他宿主的验证状态见[验证记录](docs/ITERATION_1_5_1_VALIDATION.md)。

程序能核对修订、批准范围、依赖、材料指纹和执行凭据。**它不能证明 `--source user` 是用户本人，不能把退出码为零等同于需求满足，也不能把 Agent 自查当成独立审核。** 拥有相同文件权限的工具仍能绕过本地流程；多个分支的治理账本不支持自动合并。

<a id="architecture"></a>
## 项目记录保存在哪里

![Skill、Python核心、规则和Hook共享项目记录](docs/assets/architecture.svg)

```text
.agent/
├── GOAL.md          # 目标、约束和验收条件
├── CURRENT.md       # 当前阶段、阻塞和下一步
├── DECISIONS.md     # 已确认决定及原因
├── LESSONS.md       # 经验证的教训
├── tasks.json       # 唯一任务账本
├── state.json       # 修订、哈希、本轮任务指针和热历史
├── PROGRESS.md      # 程序生成的进度视图
├── evidence/        # 持久检查凭据
├── history/         # 持久历史归档
└── runtime/         # 本地快照和原始日志，不提交Git
```

热历史最多保留 200 条记录，最近 10 条文档版本保留全文；裁剪前先归档到 `history/`，不依赖 Git 或运行快照才能查询。成果变化只让旧检查显示过期，不自动改写历史完成状态。原始运行日志清理后，`verify show` 会报告缺失，不承诺仍能查看全文。

决定需要先落盘，Hook 无法找回尚未保存的聊天内容；旧版已裁剪且没有备份的内容也不承诺恢复。

<a id="docs"></a>
## 文档

| 文档 | 内容 |
| :--- | :--- |
| [使用手册](docs/USAGE.md) | 安装、任务、检查、迁移、回退与卸载 |
| [命令参考](skills/project-anchor/references/COMMANDS.md) · [Skill工作流](skills/project-anchor/references/WORKFLOWS.md) | 参数与自然语言操作 |
| [更新记录](CHANGELOG.md) · [1.5.1验证记录](docs/ITERATION_1_5_1_VALIDATION.md) | 版本变化、实测范围与未验证事项 |
| [客户端验证](docs/CLIENT_VALIDATION.md) · [故障排查](docs/TROUBLESHOOTING.md) | 客户端差异、安装定位与恢复 |
| [架构说明](docs/ARCHITECTURE.md) · [冒烟检查](SMOKE_TEST.md) | 核心设计与维护检查 |

开发时运行回归：

```powershell
py -3 -B -X utf8 -m unittest discover -s tests -q
```

## 许可证

[MIT License](LICENSE)

发布准备与升级细节见[1.5.1发布说明](docs/RELEASE_1_5_1.md)及[批准计划](docs/plans/1.5.1.md)。固定提交、远程CI和下载包校验见发布资产中的验证清单。
