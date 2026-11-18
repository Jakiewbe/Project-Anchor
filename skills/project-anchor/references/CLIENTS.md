# 客户端能力边界与安装入口

## 1. 通用架构原则

- **单一核心与账本**：项目状态始终保存在目标项目 `.agent/`；唯一业务程序为工具箱根目录 `kit.py`（仅依赖 Python 3.11+ 标准库）。任何客户端不得复制核心逻辑或维护第二份任务账本。
- **Agent Skills 规范**：`skills/project-anchor/` 遵循 [Agent Skills 规范](https://agentskills.io/specification)，通过 `SKILL.md` + `scripts/run.py` + `runtime.json` 跨客户端工作，支持从任意 `cwd` 传入目标项目绝对/相对路径。
- **严格隔离定位**：`runtime.json` 由安装器写入绝对路径。Codex 安装传入 `CODEX_HOME`；非 Codex 安装（`agents` / `claude` / `dsh`）传入 `PROJECT_ANCHOR_CLIENT` 与 `PROJECT_ANCHOR_CLIENT_HOME`，绝不读写 `~/.codex`。

---

## 2. 安装入口一览

| 命令 | 写入位置与管理物 | 适用场景 |
| --- | --- | --- |
| `install-global` | `~/.agents/skills/project-anchor/` + `CODEX_HOME/AGENTS.md` 管理块 + `hooks.json` | Codex 集成（含全局规则与 Hook） |
| `install-client agents` | 默认 `~/.agents/skills/project-anchor/`；清单在 `PROJECT_ANCHOR_HOME`（默认 `~/.project-anchor`） | 通用 Agent Skills（Cursor、OpenCode、Antigravity 等）；不写规则或 Hook |
| `install-client dsh` | `DSH_HOME/skills/project-anchor/` + `DSH_HOME/AGENTS.md` 管理块 | DeepSeek Harness（配合 `packages/dsh/` 只读插件，不配 Hook） |
| `install-client claude` | `CLAUDE_CONFIG_DIR/skills/project-anchor/` + `rules/project-anchor.md` + `settings.json` Hook 组 | Claude Code 适配代码（未完成真实客户端完整验收） |

**所有权保护**：同一 Skill 目录只允许一个管理方；若 `~/.agents/skills/project-anchor/` 已由 `install-global` 管理，Cursor / OpenCode 等可扫描该目录的客户端可直接使用，无需重复安装。跨管理方切换前须先执行原安装器的卸载命令。

---

## 3. 各客户端机制与真实边界

| 客户端 | Skill 发现机制 | 持久规则与生命周期 | 当前验证边界 |
| --- | --- | --- | --- |
| **Codex** | 扫描 `~/.agents/skills` 与项目 `.agents/skills`；支持 `$project-anchor` 显式调用 | 全局 `AGENTS.md` 管理块；`SessionStart` / `PreCompact` Hook（须用户在 `/hooks` 审核信任） | CLI 启动、手动/自动压缩及显式 Skill 读盘接续已实测；Desktop/IDE 长期自动遵守未完全验证 |
| **Cursor** | 扫描 `~/.agents/skills`、`~/.cursor/skills` 及项目同名目录；支持 `/project-anchor` | 依赖项目 `AGENTS.md`；不配置 Cursor Hook（协议与 Codex 不同） | 已有子代理与主聊天工作流实测；仅靠 `AGENTS.md` 无 Skill 恢复未单独验证 |
| **OpenCode** | 扫描 `.opencode/skills`、`.claude/skills`、`.agents/skills` 及用户目录 | 依赖项目 `AGENTS.md`；未提供 JS 生命周期插件 | 已有工作流与交替读盘实测；依赖原生 `skill` 工具权限设置 |
| **Antigravity** | 支持工作区 `.agents/skills` 或通过 `install-client agents --skills-dir` / `skills.json` 挂载 | 工作区 `AGENTS.md` 分层规则；可配合 `hooks.json`（需单独适配契约） | 按 Agent Skills 规范通用接入；生命周期自动化需按原生契约另行验证 |
| **DeepSeek Harness** | 原生扫描项目 `.dsh/skills`、`.agents/skills` 与 `$DSH_HOME/skills`（优先级高于 `~/.agents/skills`） | `$DSH_HOME/AGENTS.md` 全局规则 + 项目 `AGENTS.md`；`packages/dsh/` 提供只读工具 `anchor_status` / `anchor_doctor` | 桩件与 CLI 映射已测；真实 DSH 宿主会话发现、注入与调用仍未验证 |
| **Claude Code** | 扫描 `<配置目录>/skills` 与项目 `.claude/skills` | `rules/project-anchor.md` + `settings.json`（`SessionStart`/`PreCompact`） | 安装/卸载与本地 Hook 模拟已测；真实模型工作流因环境未验证，不作发布阻塞 |
| **WorkBuddy** | 工作区 `.codebuddy/skills/`；社区资料 `~/.workbuddy/skills/` | 可用 `install-client agents --home ... --skills-dir ...` 指定独立目录 | 本机未安装，全部能力未验证 |

---

## 4. 升级与安全边界

- **升级步骤**：工具箱代码更新后，先运行 `doctor` 查看模板差异，再重新执行原 `install-global` 或 `install-client <client>`。程序会校验旧文件哈希并自动备份，若用户手工改动了受管理文件则拒绝覆盖。
- **独立运行保障**：移除 Skill 目录后，`kit.py` 与已配置的 Hook 仍可独立工作；Skill 的 `runtime.json` 损坏或版本不符会立即失败并提示诊断命令，绝不静默降级或猜路径。
- **诚实边界**：规则与 Hook 能提醒读盘和拦截未批准/过期写入，但**模型是否自动选择 Skill 或始终遵从规则仍取决于具体客户端与模型能力**；关键操作建议显式触发 `$project-anchor` 或 `/project-anchor`。
