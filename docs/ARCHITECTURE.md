# Codex-Rules v1.0 架构

核对日期：2026-10-08；开发环境：Windows、Python 3.11.5、Git 2.52.0、Codex CLI 0.162.0-alpha.2。

## 机制与来源

按 [官方 AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) 分层加载规则；覆盖文件和大小上限由 doctor 检查。按 [官方配置优先级](https://learn.chatgpt.com/docs/config-file/config-basic) 检查项目层、用户层及 profile，命令行和管理层无法仅从项目磁盘完整确定。

按 [官方 Hooks](https://learn.chatgpt.com/docs/hooks) 使用 hooks.json、SessionStart、PreCompact；压缩后通过 SessionStart 的 compact 来源恢复，不重复配置 PostCompact。输入为 stdin JSON，恢复使用 hookSpecificOutput.additionalContext；快照只回报状态，默认 continue=true。Windows 使用 commandWindows。安装不会代替用户信任 Hook。

## 文件与写入

- GOAL/CURRENT/DECISIONS/LESSONS 保存人可读状态；tasks.json 是唯一任务来源。
- state.json 保存项目 UUID、全局修订、任务修订、文件 SHA-256、目标版本及变更历史。CURRENT 落后于任务修订会警告。
- 写入持有 OS 文件锁，在同目录写临时文件并 fsync 后 replace。多文件更新先写事务记录；普通异常回滚，强制终止保留事务。读取发现事务未完成则拒绝；recover 校验每个文件仍是旧值或新值，再完成或回滚。新编辑冲突时拒绝覆盖。
- 状态修改必须给出期望修订号；直接修改 Markdown 通过 state adopt 显式登记。tasks.json 不允许 adopt。
- PROGRESS 是可重建视图；账本和视图一同更新。视图单独被改动可以 rebuild。
- 初始化对 .agent/** 设置 Git -text 属性，保持状态的原始字节，避免 Windows 自动换行转换导致克隆后哈希失效；保留现有 .gitattributes 其他规则。

## 信任与边界

SessionStart 默认只注入固定提醒，不读取未审核项目内容作为高级指令。用户执行 trust-project 后，在 CODEX_HOME 中登记真实根目录、项目 UUID 和 GOAL/CURRENT 的精确哈希；文件变化需要重新审核。摘要以 JSON 数据呈现，限制长度，并声明不是规则。此措施不能数学上阻止模型误读数据，仍需人工冒烟验收。

快照只含白名单治理文件，带 UUID、版本和校验信息，永不自动覆盖当前磁盘。默认保留 20 个有效本项目快照；损坏和不明文件保留并由 doctor 报警。日志默认最大 64 KiB，另保留一份轮转文件。状态中禁止放入敏感内容；工具不读取认证文件、transcript 或业务源码。

## 安装

只合并全局 AGENTS 管理块和 hooks.json 中工具拥有的完整组，不写 config.toml。安装清单保存管理块、Hook 定义和安装路径；已有目标文件备份在运行目录。升级先校验旧管理内容，卸载只移除未被修改的管理内容并保留其他新增配置。事务覆盖安装清单本身。

只依赖 Python 3.11 标准库；tomllib 避免猜测 TOML。复制/克隆后重新 install-global 更新脚本路径及解释器；不自动携带 API Key、Hook 信任或项目信任。

## 并发与兼容

适用于本地磁盘、配合工具的单项目写入。锁不约束外部编辑器；校验用于发现外部变化，不支持多会话自动合并。网络盘的锁及原子性未验证。不支持共享 Windows/WSL 安装命令；各环境单独安装。旧版本缺少 Hook 能力时基础 CLI 仍能运行，doctor 必须标记未验证或失败，禁止伪装自动集成成功。
