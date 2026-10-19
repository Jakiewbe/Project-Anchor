<div align="center">
  <img src="docs/assets/hero.svg" alt="Project Anchor — Keep the goal. Carry the context." width="100%">

  <p><strong>让 AI 项目的目标、进度和重要决定，换个会话也能接着用。</strong></p>
  <p>File-based project memory and governance for AI agents.</p>

  <a href="https://github.com/Jakiewbe/Project-Anchor/releases/tag/v1.4.0"><img src="docs/assets/badge-version.svg" alt="Version 1.4.0"></a>
  <a href="pyproject.toml"><img src="docs/assets/badge-python.svg" alt="Python 3.11 or later"></a>
  <a href="pyproject.toml"><img src="docs/assets/badge-runtime.svg" alt="Python standard library runtime"></a>
  <a href="LICENSE"><img src="docs/assets/badge-license.svg" alt="MIT License"></a>

  <p>
    <a href="#why">为什么</a> ·
    <a href="#v14">1.4.0</a> ·
    <a href="#quick-start">安装</a> ·
    <a href="#usage">日常使用</a> ·
    <a href="#upgrade">升级</a> ·
    <a href="#clients">客户端</a> ·
    <a href="#docs">文档</a>
  </p>
</div>

---

Project Anchor 把项目治理从聊天记录里拿出来，写进仓库中的 `.agent/`。目标、约束、决定、断点和任务账本随项目保存，可以通过 Git 审查、回滚和交接；换一个会话、压缩上下文或换一个客户端，读到的仍是同一份磁盘事实。

它不替 Agent 思考，也不保证模型永远遵守规则。它做的是三件事：

1. **保存事实**：目标、范围、决定、断点和任务状态都有明确文件。
2. **约束写入**：修订号、哈希、锁和事务让冲突、损坏和覆盖显式失败。
3. **留下可复核的痕迹**：任务批准范围、证据绑定和失效历史都能被重新读取和审查。

**当前版本：1.4.0** · [发布说明](https://github.com/Jakiewbe/Project-Anchor/releases/tag/v1.4.0) · [更新记录](CHANGELOG.md)

<a id="why"></a>
## 为什么不是“再写一份 AGENTS.md”

长周期项目真正难的不是让模型记住一句话，而是让它在几十次会话后仍然分得清：

- 哪些目标是用户确认的，哪些只是讨论；
- 哪些任务已批准，哪些还是草案；
- 这次改动改变了范围，还是只是执行；
- 完成声明对应的是当前验收标准，还是旧版本；
- 另一个会话已经改过的状态，能不能直接覆盖。

Project Anchor 用文件保存这些区别，用程序检查状态转换。规则和 Skill 负责让 Agent 选择正确流程；程序负责让错误的状态转换失败，而不是靠提醒。

<a id="v14"></a>
## v1.4.0 的重点：批准范围成为程序不变量

1.4.0 把任务账本升级到 `schema 2`，把“已批准范围”从自然语言约定变成可校验的快照。

| 操作 | 程序行为 |
| :--- | :--- |
| `task add` | 只能创建草案；不能直接建立 approved 任务 |
| `task approve` | 独立批准入口；记录描述、验收标准、依赖、版本、哈希和批准声明来源 |
| `task revise` | 修改已批准任务的实质范围；回到草案并标记旧证据失效 |
| `task update` | 不能改 `plan`、批准范围或证据内部字段 |
| `done` | 只接受当前批准版本、标准文本匹配且未失效的证据 |

这意味着：

- 不能再用一次 update 同时“改验收标准 + 标记完成”；
- 不能删掉未完成依赖并同时开始任务；
- 验收条件重排或改写后，旧证据不能仅凭序号复用；
- Agent 可以调用 `task approve`，所以这仍是 L1/L2 的本地程序约束，不是 L3 身份认证；真正独立的批准来源需要 OS 权限边界或独立 runner。

旧 `schema 1` 账本可以只读；写入前必须执行显式迁移。迁移会备份状态、标记 `legacy_unverified`，不会替旧任务补造批准记录。旧版 v1.3 读取 `schema 2` 会拒绝，避免旧写入器静默降级。

<a id="quick-start"></a>
## 快速开始

主要验证环境是 **Windows + PowerShell**。需要 **Python 3.11+**、Git，以及支持 Skill 发现和本地 Python 执行的 Agent。项目运行时只依赖 Python 标准库。

### 0. 先准备 Git

Windows 用户可从 [Git 官方 Windows 安装页](https://git-scm.com/install/windows)下载安装包，安装时保留“加入 PATH”；也可以使用 WinGet：

```powershell
winget install --id Git.Git -e --source winget
```

安装后关闭并重新打开 PowerShell，确认：

```powershell
git --version
```

### 1. 获取工具箱

```powershell
git clone https://github.com/Jakiewbe/Project-Anchor.git
Set-Location Project-Anchor
py -3 --version
py -3 kit.py --version
```

### 2. 选择安装入口

**Codex 集成：**

```powershell
py -3 kit.py install-global
```

安装用户级 Skill、全局规则管理块和工具自身的 Hook。其他 Skill 与非管理配置保留，不修改 `config.toml`。在 Codex CLI 的 `/hooks` 中审核 **SessionStart**、**PreCompact** 当前定义，再检查：

```powershell
py -3 kit.py doctor --native-hooks --native-skills
```

**通用 Agent Skills：**

```powershell
py -3 kit.py install-client agents
py -3 kit.py doctor --client agents
```

安装同一份 Skill，不依赖 Codex，不配置客户端规则或 Hook。Agent 需要支持扫描 Skill 目录并执行本地 Python。

**DeepSeek Harness：**

```powershell
py -3 kit.py install-client dsh
py -3 kit.py doctor --client dsh
```

默认写入 `$DSH_HOME/skills/project-anchor/`，并在 `$DSH_HOME/AGENTS.md` 追加管理块。DSH 适配不配置生命周期 Hook；原生 Skill 发现、规则注入和脚本执行仍需在真实 DSH 会话中验收。

> 同一个 Skill 目录只选择一个管理方。Codex 集成默认也使用 `~/.agents/skills/project-anchor/`；扫描该目录的其他客户端可以直接复用，不必重复安装。同名目录归属冲突时安装器会拒绝覆盖。

`runtime.json` 记录实际 Python、`kit.py` 和安装来源的绝对路径，工具箱目录需要保留。`PASS`、`WARN`、`FAIL`、`UNVERIFIED` 分开报告；安装完成不等于模型行为已验收。

### 3. 在业务项目中启用

在 Agent 中打开业务项目目录，说：

```text
在当前项目启用 Project Anchor 项目管理，保留已有工程和改动。
```

接入会创建 `.agent/`，并保留、追加 `AGENTS.md`、`.gitignore`、`.gitattributes` 中的治理约定。目标模板仍待用户确认；接入不会重建业务工程、修改依赖或自动初始化 Git。

需要显式调用时，Codex 可用 `$project-anchor`；支持斜杠入口的客户端可用 `/project-anchor`，也可以直接点名技能。

<a id="usage"></a>
## 日常怎么用

![项目工作流：确认目标，批准任务草案，实施并保留证据，保存断点并交接](docs/assets/workflow.svg)

| 你想做什么 | 可以这样说 |
| :--- | :--- |
| 制定计划 | “根据目标制定任务草案，列出依赖和验收条件，先不执行。” |
| 处理局部任务 | “本次只修这个问题，我已批准这个范围，不扩大到其他模块。” |
| 查看进度 | “只查看里程碑 X 的任务、进度和阻塞，不修改状态。” |
| 保存决定 | “路线确定为 JSON，记录原因；这轮先看模板，不开始实现。” |
| 完成任务 | “将 T1 标记为完成，真实验收证据是……” |
| 切换会话 | “保存当前断点、已确认决定和下一步，准备换会话。” |
| 诊断或复盘 | “只检查安装与规则是否正常。”或“生成复盘草案，先不入库。” |

项目总目标与局部任务的批准分别记录。批准目标不等于要求生成计划，制定计划不等于批准实施；只读或限定文件修改时不额外写治理记录。程序检查证据结构和绑定，真实结果仍需核对。

### 常用命令

在工具箱目录运行，把示例路径与任务 ID 换成自己的：

```powershell
py -3 kit.py status "D:\Projects\my-app" --brief
py -3 kit.py status "D:\Projects\my-app" --brief --milestone "本轮里程碑"
py -3 kit.py status "D:\Projects\my-app" --task T1

py -3 kit.py task approve "D:\Projects\my-app" --task-id T1 --source user --expected-revision 2 --reason "用户批准计划"
py -3 kit.py task revise "D:\Projects\my-app" --task-id T1 --expected-revision 4 --reason "范围调整，重新批准"
```

`task approve` 的 `--source` 是调用者声明（user/policy），不是身份认证。已批准任务的描述、验收标准或依赖发生变化时，先 `task revise`，修改后重新 `task approve`；`task update` 只负责状态推进和证据登记。

<a id="upgrade"></a>
## 升级到 1.4.0

1.4.0 是**任务账本格式变更**，旧项目不能直接写入：

```powershell
py -3 kit.py status "D:\Projects\my-app" --brief
py -3 kit.py migrate "D:\Projects\my-app" --expected-revision <当前 revision> --reason "升级到 schema 2"
```

迁移会备份 `.agent/state.json`、`tasks.json`、`PROGRESS.md`，把旧批准任务标记为 `legacy_unverified`，不会自动补造批准记录。旧任务重新开始或完成前，先 `task revise` 或 `task approve`，旧证据会标记失效并重新验收。

**多台机器需要先统一升级。** 旧版 v1.3 读取 `schema 2` 会直接拒绝；这是为了避免旧写入器绕过新审批协议，不是兼容性故障。

获取新版本：

```powershell
git status --short
git pull --ff-only origin main
```

随后重新执行首次安装时选择的同一条命令，并运行对应 `doctor`。移动目录或换电脑后需要重新安装定位信息。

<a id="clients"></a>
## 客户端与能力边界

| 入口 | 安装与接续方式 | 范围 |
| :--- | :--- | :--- |
| 通用 Agent Skills | 同一 Skill 调用 `kit.py`，读取 `.agent/` | 需支持 Skill 发现、本地 Python 执行及相应权限 |
| Codex 集成 | `install-global`，Skill、规则和 Hook | 生命周期能力按真实客户端和事件证据声明 |
| DeepSeek Harness | `install-client dsh`，`$DSH_HOME/skills` 与 `$DSH_HOME/AGENTS.md` | 配置 Skill 与全局规则，不配置 Hook；原生发现和规则注入未验证 |
| Cursor / OpenCode | 通用 Skill 与项目规则 | 本工具不配置其生命周期 Hook；效果以对应验证记录为准 |
| Claude Code | 已提供 `install-client claude` 专用入口 | 真实客户端未完整验证，具体安装见使用手册 |
| WorkBuddy | 通用 Skill 入口 | 发现目录与脚本权限需按客户端确认，未完成真实验收 |

自动选择 Skill、及时保存决定和长期遵守规则仍依赖 Agent 的实际行为。文件存在、Hook 配置、信任、脚本执行和模型遵从是不同层级；不能将一项通过扩大为所有客户端、Desktop/IDE 或多轮压缩均可靠。

### 它能证明什么，不能证明什么

**能证明：**

- 状态文件与登记的哈希一致；
- 修订号、依赖、批准范围和状态转换符合程序约束；
- 证据绑定到某个批准版本和标准文本；
- 写入经过锁、事务和可恢复日志；
- 旧版写入器不能打开新的 schema 2 账本。

**不能证明：**

- `--source user` 确实来自真实用户；
- 测试或命令确实执行过（自动采集的 observed 证据尚未实现）；
- 模型每次都会遵守规则；
- 多个分支的账本可以自动合并；
- 本机有完全文件权限的恶意执行者无法绕过工具。

这些边界是产品的一部分，不应被隐藏。

<a id="architecture"></a>
## 工作记录如何保留

![Project Anchor 架构：Skill 调用 Python 核心，规则与 Hook 独立协作，共享项目状态](docs/assets/architecture.svg)

| 组件 | 职责 |
| :--- | :--- |
| **Skill** | 理解当前意图、选择治理流程、调用程序 |
| **Python 核心** | 校验修订、批准范围、状态、锁、事务、快照和诊断 |
| **项目规则** | 约束范围、授权和状态维护 |
| **Hook** | 在已有支持与执行证据的客户端事件中运行 |

项目的 `.agent/` 保存：

```text
.agent/
├── GOAL.md          # 目标、约束、非目标和验收条件
├── CURRENT.md       # 当前阶段、任务、阻塞和下一步
├── DECISIONS.md     # 已确认的决定及原因
├── LESSONS.md       # 已验证的教训
├── tasks.json       # 唯一任务账本（schema 2）
├── state.json       # 项目 UUID、修订、哈希和变更历史
├── PROGRESS.md      # 由账本生成，不手工编辑
└── runtime/         # 快照、日志、证据等本地运行数据
```

重要决定需先通过程序保存，Hook 无法恢复尚未落盘的聊天决定。压缩前的快照只保存已有状态；接续时以当前磁盘记录为准，不自动用旧快照覆盖新状态。Hook 绑定会话工作目录，不能把 A 项目的事件当成 B 项目的保护已执行。

<a id="docs"></a>
## 文档与验证

| 文档 | 内容 |
| :--- | :--- |
| [发布说明](https://github.com/Jakiewbe/Project-Anchor/releases/tag/v1.4.0) · [更新记录](CHANGELOG.md) | 当前版本及历史变化 |
| [使用手册](docs/USAGE.md) | 安装、任务批准、迁移、备份、卸载和恢复 |
| [Skill 工作流](skills/project-anchor/references/WORKFLOWS.md) · [CLI 参数](skills/project-anchor/references/COMMANDS.md) | 自然语言流程与命令输入 |
| [1.4.0 验证记录](docs/ITERATION_1_4_VALIDATION.md) · [客户端验证](docs/CLIENT_VALIDATION.md) | 实测范围、失败与未验证事项 |
| [架构说明](docs/ARCHITECTURE.md) · [故障排查](docs/TROUBLESHOOTING.md) | 实现约束及错误处理 |
| [冒烟检查](SMOKE_TEST.md) | 规则或客户端变更后的核对方法 |

所有入口复用 `kit.py` 和 `core/`，Skill 位于 `skills/project-anchor/`，自动化检查在 `tests/`。运行回归：

```powershell
py -3 -X utf8 -m unittest discover -s tests -q
```

开发改动需检查差异并执行相关验证。认证信息、密钥、原始会话日志和本地运行数据不应提交。

## 许可证

[MIT License](LICENSE)
