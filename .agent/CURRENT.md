# 当前断点

## 当前阶段
通用Agent Skills适配已提交Draft PR #1 https://github.com/Jakiewbe/Project-Anchor/pull/1 ；真实集成验收未全部完成，不可直接发布。

## 当前任务
UNI1 blocked：Draft PR #1待审查，等待剩余人工真实客户端验收。BRAND1 blocked、DPL6 doing保持原状。

## 已完成工作
新增core/clients.py、global/CLIENT_RULES.md；kit.py增加install-client/uninstall-client及doctor/trust-project/recover的--client。
Hook运行时支持--managed-dir；run.py按runtime.json来源设置环境，非Codex安装不设CODEX_HOME。
Skill说明、CLIENTS/COMMANDS、项目模板改为客户端中立；README能力矩阵、USAGE、CHANGELOG、docs/CLIENT_VALIDATION.md已更新。
自动回归151通过0失败（原131+新增20）；含中文空格路径、幂等、配置保留、更新备份、拒绝覆盖、卸载、回滚恢复、双入口旧修订保护。
OpenCode 1.14.29真实运行第3次8/0；第1次4/3（模型下线）、第2次5/2（目标未批准，场景补步骤）原样保留。
Claude Code 2.1.153真实Hook：SessionStart startup/resume与PreCompact manual 3/0，init事件列出Skill。
Cursor 3.23.12：Agent子代理在合成项目10/0（反向2、启用、批准目标、/project-anchor加任务、决定、交接、恢复、同步CURRENT、旧修订被拒），与OpenCode双向交替2/0。
Cursor结果限制：子代理运行在本仓库工作区、受本仓库规则影响，使用Codex安装的1.2.0 Skill副本，不等同用户直接打开项目的新聊天。

## 当前阻塞
本机Claude Code所有模型请求401，Claude自然语言流程与Claude参与的交替未执行；不处理认证。
Codex CLI未安装；WorkBuddy未安装；Cursor直接打开项目的新聊天与项目AGENTS.md规则加载未测；压缩后接续与自动压缩未验证。
现有Codex安装需重新install-global（Hook脚本版本与Skill模板WARN），属用户操作。

## 下一步动作
用户审查PR #1并按docs/CLIENT_VALIDATION.md第6节完成剩余人工验收；未经确认不合并、不发布。

## 状态修订
以state.json/tasks.json为准；原始运行记录.agent/runtime/universal。

## Git 检查
feat/universal-agent-skills已推送；Cursor验收记录另行提交到同一分支；未推main、未强推、无工作树。
