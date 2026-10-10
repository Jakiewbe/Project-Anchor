<div align="center">
  <img src="docs/assets/hero.svg" alt="Project Anchor — Keep the goal. Carry the context." width="100%">

  <p><strong>让长期项目的目标、记忆和进度，有据可查。</strong></p>
  <p>File-based project memory and governance for AI agents.</p>

  <a href="docs/RENAME_VALIDATION.md"><img src="docs/assets/badge-version.svg" alt="Version 1.2.0"></a>
  <a href="pyproject.toml"><img src="docs/assets/badge-python.svg" alt="Python 3.11 or later"></a>
  <a href="pyproject.toml"><img src="docs/assets/badge-runtime.svg" alt="Python standard library runtime"></a>
  <a href="LICENSE"><img src="docs/assets/badge-license.svg" alt="MIT License"></a>

  <p>
    <a href="#why">为什么需要它</a> ·
    <a href="#architecture">工作原理</a> ·
    <a href="#quick-start">快速开始</a> ·
    <a href="#usage">日常使用</a> ·
    <a href="#validation">能力边界</a>
  </p>
</div>

---

Project Anchor 为 AI 辅助开发提供一套**随项目保存、可以校验、可以通过 Git 维护的工作记录**。即使对话压缩、会话更换，智能体仍能从项目文件重新读取目标、任务、决策和工作断点。

你表达意图，通用 Skill 选择工作流并调用同一 `kit.py`；项目状态唯一来源是 `.agent/`，项目 AGENTS.md 提供行为约定。生命周期 Hook 仅按客户端和事件的真实执行证据声明可用。

> **当前定位 · v1.2.0 + 通用 Skill 适配**<br>
> 提供符合 [Agent Skills 规范](https://agentskills.io/specification) 的同一份 `SKILL.md` 与 `scripts/run.py`，共享 Python 核心和项目账本，不需要安装 Codex。兼容扫描 `.agents/skills` 及用户级同名目录、可运行本地 Python 且获得权限的 Agent 可以发现并调用；不等于所有客户端已实测。Claude、WorkBuddy 本轮范围外、未验证，不作发布阻塞；各客户端证据见[能力矩阵](#clients)。

<a id="why"></a>
## 为长项目保留六个锚点

| 你遇到的问题 | Project Anchor 提供的机制 |
| :--- | :--- |
| 对话变长，项目逐渐偏离初衷 | 将目标、约束、非目标和验收条件固定在 `GOAL.md`，接续时读取最新磁盘记录 |
| 改动不断积累，却缺少版本检查点 | 检查 Git 工作区，保留既有修改；提交、推送由用户授权 |
| 看不清任务做到了哪里 | 用唯一任务账本保存状态、依赖和证据，生成可阅读的 `PROGRESS.md` |
| 不知道规则和自动保存是否生效 | 用 `doctor` 分别检查文件、配置、原生发现、信任与执行记录 |
| 规则和经验难以保存、迁移 | 使用文件、安装清单、备份和可重复安装流程；不迁移认证信息 |
| 项目结束，走过的弯路又被遗忘 | 保存决策与已验证教训，生成复盘草案；确认后进入跨项目知识库 |

<a id="architecture"></a>
## 一套核心，四种职责

![Project Anchor 架构：自然语言经 Skill 调用 Python，规则与 Hook 独立协作，所有入口共享项目状态](docs/assets/architecture.svg)

| 组件 | 职责 | 边界 |
| :--- | :--- | :--- |
| **Skill** | 理解意图、选择流程、调用程序、说明结果 | 按需使用，不要求每条回复调用 |
| **Python 核心** | 校验、写入、任务管理、锁、事务、快照和诊断 | 所有入口复用 `kit.py`，不建立第二份账本 |
| **AGENTS.md** | 持续约束目标、质量、授权和状态维护 | 规则是约束，不能证明模型始终遵守 |
| **Hook** | 在已验证客户端的启动与压缩事件中运行 | 需审核当前定义；仅在真实执行证据覆盖的范围声明可用 |

项目状态保存在目标项目的 `.agent/` 中：

```text
.agent/
├── GOAL.md        已确认目标、约束、非目标与验收条件
├── CURRENT.md     当前阶段、工作断点、阻塞与下一步
├── DECISIONS.md   重要决定及原因
├── LESSONS.md     有证据的经验和失败教训
├── tasks.json     唯一任务账本
├── PROGRESS.md    从账本生成的进度视图
├── state.json     内容哈希、修订号与变更历史
└── runtime/       本地日志、输入草稿和快照，不提交 Git
```

复盘时另生成 `RETRO.md` 草案。受保护状态通过程序修改；`PROGRESS.md` 是展示文件，`tasks.json` 才是任务事实来源。

<a id="quick-start"></a>
## 快速开始

### 1. 安装工具箱

主要验证环境为 **Windows + PowerShell**。准备 Python **3.11+**、Git 和支持 Agent Skills、本地脚本执行的 Agent。下面先演示 Codex 集成；通用 Skill 安装见“不使用 Codex 时”，不要求客户端具有 Hook。

```powershell
git clone https://github.com/Jakiewbe/Project-Anchor.git
Set-Location Project-Anchor
py -3 --version
py -3 kit.py install-global
```

安装会合并全局规则、配置工具自身的 Hook，并安装用户级 Skill。管理文件更新前会校验、备份；其他 Skill 和非管理配置会保留。当前安装器不修改 `config.toml`。

| 安装内容 | 默认位置 |
| :--- | :--- |
| 用户级 Skill | `~/.agents/skills/project-anchor/` |
| Codex 规则与 Hook 配置 | `CODEX_HOME`；未设置时为 `~/.codex/` |
| 安装清单、备份与运行记录 | `CODEX_HOME/codex-rules/`，保留旧标识以兼容既有安装 |

工具目录需要继续保留：Skill 中的 `runtime.json` 指向实际 Python 和 `kit.py`，没有复制核心程序。移动目录或换电脑后需要重新安装。

**不使用 Codex 时**，优先使用通用入口，复用同一 `kit.py` 和项目 `.agent/`：

```powershell
py -3 kit.py install-client agents   # 通用 Skill：~/.agents/skills，Cursor、OpenCode 可发现；不写规则或 Hook
```

Claude 专用安装与 Hook 适配代码保留，操作方式见[使用手册](docs/USAGE.md)；Claude、WorkBuddy 本轮不做真实客户端验收，不声明已验收，也不要求安装或登录。

已用 `install-global` 安装到 `~/.agents/skills` 时，Cursor、OpenCode 可直接使用这份 Skill，不要再装 agents。同一目录只允许一个管理方，冲突时拒绝覆盖。卸载用 `uninstall-client`，中断后用 `recover --client`。细节见 [客户端机制](skills/project-anchor/references/CLIENTS.md)。

### 2. 核对安装（Codex 集成另需审核 Hook）

重新打开 Codex 会话，在支持 Hook 的 CLI 中输入 `/hooks`，审核当前 **SessionStart** 和 **PreCompact** 定义，然后运行：

```powershell
py -3 kit.py doctor --native-hooks --native-skills
```

`PASS`、`WARN`、`FAIL`、`UNVERIFIED` 分开报告。文件存在、配置完成、已信任和实际执行是不同的检查层级；出现未验证项不代表全部通过。

### 3. 在目标项目里开始工作

打开你的**业务项目目录**，直接说：

```text
帮我初始化项目管理。
```

确认目标后继续：

```text
根据我的项目目标制定任务草案。
```

自动选择没有确定性保证，需要时可以显式输入（Codex 用 `$project-anchor`，Claude Code、Cursor 用 `/project-anchor`，OpenCode 点名 project-anchor skill）：

```text
$project-anchor 查看当前项目进度，只读，不修改。
```

安装后的全局策略会在明确项目目录首次开展实际工作时检查接入。已有治理记录先读取；只读问答、用户主目录、磁盘根目录和限定单文件工作不自动初始化。接入只创建 `.agent/` 并保留、追加治理约定，**不重建业务工程，不修改业务源码或依赖，不自动初始化 Git**。明确禁止治理写入时不接入。

<a id="usage"></a>
## 用自然语言推进项目

![项目工作流：确认目标，批准任务草案，实施并保留证据，保存断点并交接](docs/assets/workflow.svg)

| 场景 | 你可以这样说 |
| :--- | :--- |
| 规划 | “根据目标制定任务草案，列出依赖和验收条件。” |
| 查看进度 | “现在项目进度如何？还有哪些阻塞？” |
| 完成任务 | “将 T1 标记为完成，验收证据是……” |
| 保存决定 | “记录我们刚才确定的技术路线和原因。” |
| 检查目标 | “对照最初目标，检查当前工作是否跑偏。” |
| 切换会话 | “整理工作状态，保存断点，准备切换会话。” |
| 诊断环境 | “检查全局规则、Skill 和 Hook 是否正常。” |
| 项目复盘 | “生成复盘草案，总结已验证的经验和失败原因。” |

任务草案批准后才能开始；完成需要覆盖验收条件的真实证据。顶层目标变更和跨项目知识入库需要用户确认。Python 检查证据的结构与覆盖范围，**不会替你执行验收，也不能判断模型提供的证据是否真实**。

### 会话变更时，记忆如何保留？

以下 Hook 行为只适用于有对应真实执行证据的客户端；通用 Skill 与项目规则要求接续时读取状态，不承诺生命周期自动化。

- **重要决定发生时**：由智能体识别，并通过程序保存到 `DECISIONS.md`；Hook 无法读取和判断未落盘的聊天决定。
- **压缩前**：受信的 `PreCompact` 保存已经落盘的项目状态快照。
- **启动、恢复或压缩后**：`SessionStart` 提醒读取当前磁盘状态；内容审核有效时才注入项目摘要。
- **继续工作时**：以最新项目文件为准；快照用于检查，不自动覆盖当前状态。

Hook 绑定会话工作目录。在 A 项目的会话里处理 B 项目，不能据此认定 B 的生命周期保护已执行。模型自动选择 Skill、及时记录决定以及长期遵守规则，仍需要实际使用检验。

<a id="clients"></a>
## 客户端与入口

优先使用通用 Skill；客户端特定能力复用同一核心和项目状态。

| 入口 | 接续方式 | 能力边界 |
| :--- | :--- | :--- |
| 通用 Agent Skills | 同一 Skill 调用 `kit.py`，读取项目 `.agent/` | Agent 需支持 Skill 发现、本地 Python 执行及相应权限 |
| Codex 集成 | Skill、全局与项目 AGENTS.md、生命周期 Hook | Hook 仅按真实执行证据声明；不承诺 Desktop/IDE 的生命周期效果 |
| Cursor / OpenCode | 通用 Skill 加项目 AGENTS.md | 本工具不配置其生命周期 Hook |
| Claude / WorkBuddy | 保留相关适配代码与安装能力 | 本轮范围外、未验证，不作发布阻塞 |

安装目录和机制差异见[客户端机制](skills/project-anchor/references/CLIENTS.md)。

<a id="validation"></a>
## 能力边界

- 不保证所有 Agent 永久遵守规则，或每次都自动选择 Skill、及时保存决定。
- 项目 AGENTS.md 提供行为约定，不单独承诺没有 Skill 也能自动恢复项目状态。
- Hook 需要当前定义受信，并以真实客户端和事件证据为准；未验证能力不作为可用性承诺。

## 文档与源码导航

| 文档 | 内容 |
| :--- | :--- |
| [使用与维护手册](docs/USAGE.md) | CLI 示例、任务证据、快照、备份、迁移、卸载和恢复 |
| [Skill 工作流](skills/project-anchor/references/WORKFLOWS.md) · [CLI 参数](skills/project-anchor/references/COMMANDS.md) | 自然语言意图到正式程序的执行路径 |
| [客户端机制](skills/project-anchor/references/CLIENTS.md) · [通用适配验证](docs/CLIENT_VALIDATION.md) | 各客户端安装位置、规则与生命周期差异，及验证证据 |
| [架构说明](docs/ARCHITECTURE.md) · [故障排查](docs/TROUBLESHOOTING.md) | 实现约束与错误处理 |
| [验证记录](docs/VALIDATION.md) · [Skill 验证](docs/SKILL_VALIDATION.md) · [冒烟检查](SMOKE_TEST.md) | 不同阶段的测试方法与证据 |

```text
kit.py                    唯一 CLI 入口
core/                     状态、任务、事务、安装与诊断
skills/project-anchor/    Skill、参考资料与轻量执行入口
global/AGENTS.md           全局行为约定
project-template/         项目治理模板
hooks/                    Codex 与 Claude Code 共用的生命周期脚本
knowledge/                经确认的跨项目知识
tests/                    自动测试与客户端验收工具
docs/                     使用、架构、验证与排错文档
```

运行自动回归：

```powershell
py -3 -X utf8 -m unittest discover -s tests -q
```

提交前检查差异、执行相关检查，并保留失败证据。运行时日志、快照、认证信息和密钥不应提交。兼容 Agent Skills 发现与本地脚本执行的 Agent 可使用同一通用入口；客户端实际效果仅按已记录证据声明，不承诺所有 Agent 永久遵守规则。

## 许可证

[MIT License](LICENSE)
