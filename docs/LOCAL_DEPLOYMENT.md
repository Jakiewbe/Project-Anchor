# 本机全局部署记录

本文保留1.1.1的首次安装历史；本机已更新到1.1.4，接入歧义修复完成，两项Hook仍保留官方信任。真实手动和自动压缩在1.1.3验收，最新结果及限制见 [PURPOSE_REVIEW.md](PURPOSE_REVIEW.md)。下面的未信任、未验证表述仅记录首次安装时的状态。

日期：2026-10-09。工具版本：1.1.1。Windows、Python 3.11.5、Codex CLI 0.162.0-alpha.2。

## 安装与实际边界

- 全局规则：`C:\Users\chs\.codex\AGENTS.md`，保留原有内容并追加受管理规则。
- 用户 Skill：`C:\Users\chs\.agents\skills\codex-rules\`，包含实际 Python、kit.py 和 CODEX_HOME 定位信息。
- Hook：`C:\Users\chs\.codex\hooks.json`，SessionStart 与 PreCompact。
- 程序：`C:\Users\chs\Desktop\codex-plus\kit.py`，不能删除或移动后继续使用旧定位。
- 原规则备份：`C:\Users\chs\.codex\codex-rules\runtime\backups\8740ee63144341018a84d5c6bb650a6e\`。

已核对原有规则保留、config.toml 内容未变、其他 17 个用户 Skill 未变。安装不修改认证、不初始化其他已保存项目、不设置原生 Hook 信任、不提交或推送 Git。

首次进入明确项目开始实际工作时默认检查并接入；已有状态通过程序读取。只读问答、代码解释、限定单文件修改不创建项目记录。新建记录不等于目标已批准，也不授权自动 Git 初始化或提交。自动选择 Skill 仍由模型决定，不保证所有模型和每次请求都触发；保留 `$codex-rules` 显式入口。

## 本轮变更

默认接入规则与 Skill 入口保持一致；明确 Git 提交授权；未审核 Hook 摘要时要求读取最新磁盘资料，不要求日常反复登记内容审核。直接注入摘要仍保留精确哈希审核，未以静默扩展信任解决接续。

doctor 新增会话 ID 和预期事件核对，历史成功不能证明本次执行，模拟记录不能证明本次原生执行。没有证据证明压缩发生时不强制要求 PreCompact。

## 验证记录

- 隔离部署预检：8 通过，0 失败。
- 完整自动回归：109 通过，0 失败。首次受限环境出现 1 项 Git 本地克隆管道权限失败，在授权执行环境完整复测通过。
- Skill 官方格式校验：通过；所需验证依赖仅位于忽略的测试目录，不成为工具运行依赖。
- 原生 Hook 发现、未信任跳过和 Windows 命令协议：3 通过，0 失败；未证明已信任生命周期。
- 正式用户 Skill 的默认原生发现：通过，未使用临时 extraRoots。
- 真实 Codex CLI 使用核查：10 通过，0 项未解决失败；包括默认接入、任务草案、记忆、进度、交接、新会话读取、复盘、显式诊断及两项不应初始化的请求。已有任务实际完成及进度生成也在首次项目工作中核对。计划场景的原始测试器误报单独保留，按正确验收条件复核通过。

测试使用现有登录和真实用户配置，每项治理场景启动新的临时 Codex CLI 会话；使用合成项目，不处理业务项目。模型工作流测试关闭 Hook，独立核对 Skill 和全局规则，不冒充 Hook 生命周期或自动压缩测试。测试中出现 1 次断言误报：已有完成任务不应被要求改成草案；保留原始失败记录，按“已有任务保留、新任务为草案”的实际验收重新核对。

汇总记录：`.agent/runtime/deployment/result.json`；完整模型日志已复制到 `.agent/runtime/deployment/model-logs/`。真实模型合成项目：`C:\Users\chs\AppData\Local\Temp\codex-rules 正式安装实测 8n0kg4eh\`。这些运行资料保持 Git 忽略。

## 尚未完成的验收

原生接口明确显示两项 Hook 为 untrusted。必须由用户在 Codex CLI 的 `/hooks` 中审核当前定义；不能通过写信任数据库或跳过信任参数替代。实际命令及哈希见 `.agent/runtime/deployment/Hook审核说明.md`。

真实手动压缩、自动压缩后的持久化与恢复、已信任 Hook 生命周期，以及不同模型、Desktop/IDE 和其他机器均未验收。新会话读取磁盘通过，不等于自动压缩已通过。PreCompact 只保存已经落盘的状态，重要决定仍需及时通过 Skill 保存。

官方依据：[Skill](https://learn.chatgpt.com/docs/build-skills)、[Hook 审核](https://learn.chatgpt.com/docs/hooks)。本轮没有擅自提交、推送、创建分支或工作树。
