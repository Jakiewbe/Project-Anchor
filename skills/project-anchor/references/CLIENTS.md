# 客户端能力边界

## 通用部分

项目目标、断点、决策、任务和进度都保存在 `.agent/`；唯一业务程序是 Python `kit.py`。能加载 Skill 并运行本地 Python 的助手可以调用安装定位信息中的同一程序；不得创建另一份账本或复制核心实现。

`status`、`task`、`state`、`snapshot`、`retro`、`rename-project` 不需要模型 API 或特定智能体 SDK。入口使用独立参数，明确传入目标项目路径。授权、目标变更和验收仍遵守当前用户与客户端要求。

## 当前已适配的部分

- Codex：用户级 Skill、AGENTS.md、SessionStart/PreCompact、原生发现/信任查询和会话执行记录。
- `install-global` 当前安装的是 Codex 集成；`CODEX_HOME` 和 `agents/openai.yaml` 属于该客户端。
- 其他智能体尚未做真实集成测试，不能宣称 Hook、自动触发或安装目录通用。

新客户端必须分别核对 Skill 加载方式、全局规则、生命周期事件、脚本权限和项目工作目录，再增加轻量适配；复用 Python 核心，不在 Skill 中复制状态逻辑。

## 1.1.4 安装升级

`install-global` 会校验旧清单，把自己管理的 Skill 文件迁移到同一父目录的 `project-anchor/`，备份旧文件；旧 Skill 目录中的用户文件保留。新目录已有其他来源的 Skill 时拒绝覆盖。

新显式入口为 `$project-anchor`。旧 `$codex-rules` 入口退役；全局路由随安装更新。`CODEX_HOME/codex-rules/` 和旧管理块标记保留为兼容的存储标识，避免分裂信任、日志、备份和锁；它们不是第二套业务逻辑。

改名后的 Hook 定义需在客户端重新核对当前信任，不继承模型自行声明的批准。现有项目 `.agent/` 内容不会因工具改名被覆盖。
