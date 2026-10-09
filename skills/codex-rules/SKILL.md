---
name: codex-rules
description: "用自然语言进行首次项目接入、初始化项目管理、制定目标任务草案、查询进度、更新任务、保存决策与长期记忆、会话交接、检查目标偏离、诊断规则和 Hook、项目复盘。Use for first project onboarding under an authorized global policy, project governance initialization, task planning/status, project memory, session handoff, goal alignment, rules/hook diagnostics, and retrospectives. 适用于已启用项目的治理需求、明确初始化/诊断请求，或全局规则已授权的首次实际项目工作；只读代码解释、知识问答、指定单文件修改不触发初始化。"
metadata:
  version: "1.1.4"
---

# codex-rules

根据用户意图选择治理工作流，用既有工具箱执行。日常用户不需要输入命令。

1. 确认用户指向的项目目录，以当前工作目录为默认，不能把 Skill、工具箱、用户主目录或磁盘根目录当成目标项目。先查 `.agent/state.json` 和 Git 根目录；已有治理状态先只读加载。用户明确要求启用治理，或可信全局规则已授权首次实际项目工作接入时，调用 init-project 新增治理记录，不重建业务工程。依据原文区分“不要重新初始化业务项目”和“禁止新增治理记录”；明确禁止治理、禁止修改接入文件、只读及限定文件范围时不接入，含义无法确定才澄清。接入实际写入范围及审批说明见 [WORKFLOWS.md](references/WORKFLOWS.md) 首节。目标模板仍待用户确认，不猜测顶层目标。
2. 读取本 Skill 同目录 `runtime.json` 获取安装的 Python、kit.py 和 CODEX_HOME。用其中 `python` 的绝对路径启动 `scripts/run.py` 调用已有 CLI；不要依赖 PATH 中的默认 Python 或启动器。路径必须是独立参数；PowerShell 用 `&` 和参数数组，Python 用 `subprocess.run([...], shell=False)`。适配器定位失败就报告，不猜路径、不复制业务实现。
3. 已初始化项目先执行 `status <项目绝对路径>`，读取真实目标、断点、修订和任务。规划、记忆、交接、目标核对或复盘时按需读取相应决策/教训。状态损坏或修订冲突立即停止相关修改。
4. 按意图读取 [WORKFLOWS.md](references/WORKFLOWS.md) 中对应流程；需要参数和数据格式时读取 [COMMANDS.md](references/COMMANDS.md)。只读请求使用 status/doctor，不能顺便改变任务或初始化项目。
5. 用户明确要求的任务/状态操作可以执行；任务有歧义、缺验收证据、未批准重大目标变化时先澄清。写入前重新取得项目 revision，使用 task/state 程序修改，所有结果仍由 tasks.json 统一管理。不要直接编辑受保护状态、全局配置或 Hook 信任。
6. JSON/Markdown 输入草稿放入 `.agent/runtime/skill-input/`；未初始化项目使用系统临时目录。可用原生 `--json-input`/`--text-input` 从 stdin 提交，避免把 JSON 拼入 shell。CURRENT 更新保留必要章节并不超过 50 行。
7. 成功后核对程序退出码、重新读取状态和进度；报告实际变更、证据和必要限制。FAIL 与 UNVERIFIED 如实报告；程序不可用时说明 CLI 也可能受影响，不能宣称已校验。此 Skill 不取代 SessionStart/PreCompact，不自动提交或推送 Git，不替用户批准知识入库。

显式 `$codex-rules` 始终是可选入口；自动选择由 Codex 根据描述判断，没有确定性保证。
