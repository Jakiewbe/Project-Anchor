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
    '目标、断点、决策与任务账本保存在项目 `.agent/`；唯一程序是安装定位指定的工具箱 `kit.py`，不要求业务仓库包含它。',
    '',
    '- 接续先用 `anchor_status` 的 brief=true、focus=true 读取显式本轮范围；focus_missing 时不从历史未完成项猜任务。',
    '- 根据 current_stale、verification_state 和依赖核对当前结果，过期证据不能证明当前材料通过。',
    '- `.agent/` 是事实来源：`state.json`、`tasks.json` 与 GOAL/CURRENT/DECISIONS/LESSONS 由程序维护，不直接编辑。',
    '- 写入必须带 `expected_revision` 并走 `kit.py` 的 `task`/`state` 子命令；修订冲突时重新读取，不重试覆盖、不自动合并。',
    '- 当前可用工具以工具描述为准。没有对应工具时用 `kit.py` 子命令，不要绕过程序直接改文件。',
    '- 不替用户批准目标或扩大范围；`goal_approved=false` 时只处理用户已明确授权的局部任务。',
    '- 不自动提交、推送或创建分支；不把安装检查当作真实客户端验收。',
  ].join('\n')
}
