---
name: project-anchor
description: "用自然语言管理项目目标、任务、进度、决策、交接、规则诊断和复盘。Use for project governance, planning/status, decisions, handoff and rule/Hook diagnostics. 在用户要求治理或可信全局规则授权的首次实际项目工作时接入；只读问答和指定文件修改不初始化项目。"
metadata:
  version: "1.3.0"
---

# project-anchor

按用户当前意图调用唯一 `kit.py` 核心，项目事实来源是 `.agent/`。日常用户无需输入命令；不依赖 Codex 安装，客户端能力见 [CLIENTS.md](references/CLIENTS.md)。

1. **定位与读取。** 默认使用用户指向的当前项目，先核对 Git 根目录与 `.agent/state.json`。不能把 Skill、工具箱、主目录或磁盘根目录当目标项目。读取本 Skill 的 `runtime.json`，用其中绝对 Python 路径运行本目录 `scripts/run.py`；路径作为独立参数，不依赖 PATH、不猜安装位置。已有项目先 `status PATH --brief`，完整读取目标和断点；按明确任务 ID/里程碑查细节，按需读决策与教训。历史任务不凭更新时间升级为本轮任务。
2. **判断范围与阶段。** 用户已明确授权的局部任务可单独登记，不因总目标待确认而重复询问，也不替用户批准总目标。全项目规划或目标变更须有相应批准。批准目标不等于要求制定计划；只评估、只看、只做计划、确认后继续时停在指定阶段。路线已确定与允许执行是两件事：允许治理写入时当回合保存决定，明确全部只读或限定修改文件时不额外写记录。
3. **选择流程。** 初始化、计划、任务、决策、交接、诊断或复盘时，读 [WORKFLOWS.md](references/WORKFLOWS.md) 对应节；参数与输入格式见 [COMMANDS.md](references/COMMANDS.md)。只读请求不初始化或顺便写入。首次治理接入只在用户或可信全局规则授权且未被当前范围限制时执行；旧业务初始化限制与治理写入按原文区分。
4. **受控写入。** 写前取得最新项目 revision；task/state 复用程序的锁、校验和事务，不直接编辑受保护状态。任务草案未经批准不能开始，done 必须有真实验收证据。损坏、修订冲突或事务中断即停止相关写入，不自动重试到成功。优先用 UTF-8 stdin 的 `--json-input`/`--text-input`；需草稿文件时放 `.agent/runtime/skill-input/`，未初始化项目放临时目录。CURRENT 保留必要章节、50 行以内。
5. **核对结果。** 检查退出码并重新读状态；`changed=false` 表示内容无变化、未写入，不能报告新增保存。区分程序校验、真实客户端行为与未验证结果。安装版本不一致先查看具体差异，不自动重装或修改信任；程序不可用就如实说明，不绕过程序直接写文件。

本 Skill 不替代 Hook，不自动提交、推送或批准知识入库。自动选择没有确定性保证；可显式使用 `$project-anchor`（Codex）、`/project-anchor`（支持该入口的客户端）或点名该技能。
