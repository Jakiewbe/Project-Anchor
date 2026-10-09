# 客户端能力边界

## 通用部分

项目目标、断点、决策、任务和进度都保存在 `.agent/`；唯一业务程序是 Python `kit.py`。能加载 Skill 并运行本地 Python 的助手可以调用安装定位信息中的同一程序；不得创建另一份账本或复制核心实现。

`status`、`task`、`state`、`snapshot`、`retro`、`rename-project` 不需要模型 API 或特定智能体 SDK。入口使用独立参数，明确传入目标项目路径。授权、目标变更和验收仍遵守当前用户与客户端要求。

## 安装入口

| 命令 | 写入位置 | 用途 |
| :--- | :--- | :--- |
| `install-global` | `CODEX_HOME` 规则块与 hooks.json；Skill 默认 `~/.agents/skills` | Codex 集成，原有行为不变 |
| `install-client agents` | Skill 默认 `~/.agents/skills`，清单在 `PROJECT_ANCHOR_HOME`（默认 `~/.project-anchor`） | 不依赖 Codex 的通用 Skill；不写规则或 Hook |
| `install-client claude` | `CLAUDE_CONFIG_DIR`（默认 `~/.claude`）下的 `skills/`、`rules/project-anchor.md` 与 `settings.json` 中两个 Hook 组 | Claude Code 适配 |

同一个 Skill 目录只能有一个管理方。`~/.agents/skills` 已由 Codex 安装时，Cursor、OpenCode 可直接发现同一 Skill，不需要再装；runtime.json 记录实际 Python 与 kit.py。各安装的清单、备份和事务彼此独立，项目 `.agent/` 只有一份。

## 各客户端机制

- Codex：用户级 Skill、全局 AGENTS.md、SessionStart/PreCompact、原生发现与信任查询。
- Claude Code：扫描 `<配置目录>/skills` 与项目 `.claude/skills`，`/project-anchor` 显式调用；`rules/*.md` 无 `paths` 时每次会话加载；SessionStart（startup/resume/clear/compact）与 PreCompact（manual/auto）命令 Hook。2.1.277 之前不读取 AGENTS.md，所以持续约束由规则文件承担。
- Cursor：扫描 `.agents/skills`、`.cursor/skills` 及用户级 `~/.agents/skills`、`~/.cursor/skills`；`/project-anchor` 显式调用；项目 AGENTS.md 为持续规则。Cursor Hook 的输入输出协议与 Codex/Claude 不同，本工具未配置 Cursor Hook。
- OpenCode：扫描 `.opencode/skills`、`.claude/skills`、`.agents/skills` 及对应用户目录，经原生 skill 工具加载；项目 AGENTS.md 为持续规则。生命周期只能通过 JS 插件实现，本工具未提供。
- WorkBuddy：官方文档说明工作区 `.codebuddy/skills/`；用户级 `~/.workbuddy/skills/` 来自社区资料。可用 `install-client agents --home <独立清单目录> --skills-dir <该目录>` 安装。本机未安装，全部能力未验证。

项目规则来自 `init-project` 追加的 AGENTS.md，所以读取 AGENTS.md 的客户端在已接入项目中都有持续约束；Claude Code 旧版本依赖 `install-client claude` 写入的规则文件。生命周期 Hook 只在有真实执行证据的客户端声明可用；未配置的客户端由规则要求在新会话、压缩后先读状态，但不能保证自动执行。

新客户端必须分别核对 Skill 加载方式、全局规则、生命周期事件、脚本权限和项目工作目录，再增加轻量适配；复用 Python 核心，不在 Skill 中复制状态逻辑。

## 1.1.4 安装升级

`install-global` 会校验旧清单，把自己管理的 Skill 文件迁移到同一父目录的 `project-anchor/`，备份旧文件；旧 Skill 目录中的用户文件保留。新目录已有其他来源的 Skill 时拒绝覆盖。

新显式入口为 `$project-anchor`。旧 `$codex-rules` 入口退役；全局路由随安装更新。`CODEX_HOME/codex-rules/` 和旧管理块标记保留为兼容的存储标识，避免分裂信任、日志、备份和锁；它们不是第二套业务逻辑。

改名后的 Hook 定义需在客户端重新核对当前信任，不继承模型自行声明的批准。现有项目 `.agent/` 内容不会因工具改名被覆盖。
