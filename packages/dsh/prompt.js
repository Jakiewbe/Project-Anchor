/**
 * System-prompt contribution.
 *
 * This section replaces nothing: it is registered under its own name and order,
 * so unloading the plugin removes exactly this text. `system-prompt/assemble`
 * is not rewritten.
 * @module project-anchor-dsh/prompt
 */

/**
 * Stable section identity; changing it is a visible contract change.
 */
export const SECTION_NAME = 'project-anchor:governance'

/**
 * Placement between team policy (600) and the PTC-only block (800): governance
 * reads before tool usage guidance and after deployment policy.
 */
export const SECTION_ORDER = 700

/**
 * The governance text. It states only what the installed mechanism can back up:
 * reading is a tool, writing still goes through `kit.py`, and the plugin never
 * approves anything on its own.
 * @returns {string} prompt section body.
 */
export function sectionText() {
  return [
    '## Project Anchor（项目治理）',
    '',
    '本项目的目标、断点、决策与任务账本保存在仓库内的 `.agent/`，唯一业务程序是项目自带的 `kit.py`。',
    '',
    '- 制定计划、执行任务或交接之前，先用 `anchor_status` 读取磁盘状态；不要凭对话记忆推断目标、批准范围或任务状态。',
    '- `anchor_status` 返回非空 `warnings` 时，先处理警告再继续（例如 CURRENT 落后于任务修订）。',
    '- `.agent/` 是事实来源：`state.json`、`tasks.json` 与 GOAL/CURRENT/DECISIONS/LESSONS 由程序维护，不直接编辑。',
    '- 写入必须带 `expected_revision` 并走 `kit.py` 的 `task`/`state` 子命令；修订冲突时重新读取，不重试覆盖、不自动合并。',
    '- 当前可用工具以工具描述为准。没有对应工具时用 `kit.py` 子命令，不要绕过程序直接改文件。',
    '- 不替用户批准目标或扩大范围；`goal_approved=false` 时只处理用户已明确授权的局部任务。',
    '- 不自动提交、推送或创建分支；不把安装检查当作真实客户端验收。',
  ].join('\n')
}
