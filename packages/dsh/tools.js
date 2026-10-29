/**
 * Model-facing tools. Every tool is a thin projection over `kit.py`:
 * arguments in, one child process, JSON out. No governance rule is
 * re-implemented here.
 * @module project-anchor-dsh/tools
 */

import { defineTool } from '@deepseek-ai/dsh-tools'

/**
 * Resolve the project path for one call without guessing.
 * @param {{ path?: string }} args - model arguments.
 * @param {{ cwd?: string, agent?: { session?: { cwd?: string } } }} exec - execution context.
 * @returns {string} absolute project path.
 */
function projectPath(args, exec) {
  const explicit = args.path?.trim()
  if (explicit) return explicit
  const inherited = exec?.cwd ?? exec?.agent?.session?.cwd
  if (typeof inherited === 'string' && inherited.length > 0) return inherited
  throw new Error('缺少 path：请显式传入目标项目目录（不要依赖隐含工作目录）。')
}

/**
 * Keep only the facts a model needs to decide the next step.
 * @param {Record<string, any>} value - `kit.py status` JSON.
 * @returns {Record<string, any>} compact, schema-stable projection.
 */
function projectStatus(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('status 返回对象无效')
  for (const key of ['project', 'name', 'goal', 'current']) {
    if (typeof value[key] !== 'string') throw new Error(`status 缺少 ${key}`)
  }
  for (const key of ['revision', 'task_revision', 'task_schema', 'goal_version']) {
    if (!Number.isInteger(value[key])) throw new Error(`status 缺少整数 ${key}`)
  }
  for (const key of ['goal_approved', 'current_stale', 'focus_missing']) {
    if (typeof value[key] !== 'boolean') throw new Error(`status 缺少布尔 ${key}`)
  }
  if (!['unknown', 'changed', 'aligned'].includes(value.current_alignment)) {
    throw new Error('status 缺少有效断点关联')
  }
  if (!Array.isArray(value.tasks) || !Array.isArray(value.external_dependencies)
      || !value.summary || !Number.isInteger(value.summary.folded_final)) {
    throw new Error('status 缺少任务、依赖或折叠统计')
  }
  for (const task of [...value.tasks, ...value.external_dependencies]) {
    for (const key of ['task_id', 'title', 'status', 'plan', 'milestone', 'blocker', 'verification_state']) {
      if (typeof task[key] !== 'string') throw new Error(`status 任务缺少 ${key}`)
    }
    if (!Array.isArray(task.dependencies) || typeof task.legacy_unverified !== 'boolean') {
      throw new Error('status 任务依赖或旧批准状态无效')
    }
  }
  // Preserve every core field, including full criteria, checks and receipts.
  return value
}

const STATUS_OUTPUT = { type: 'object', additionalProperties: true }

const DOCTOR_OUTPUT = {
  type: 'object',
  additionalProperties: false,
  properties: {
    checks: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          status: { type: 'string', enum: ['PASS', 'WARN', 'FAIL', 'UNVERIFIED'] },
          check: { type: 'string' },
          detail: { type: 'string' },
        },
        required: ['status', 'check', 'detail'],
      },
    },
    failing: { type: 'integer' },
    unverified: { type: 'integer' },
  },
  required: ['checks', 'failing', 'unverified'],
}

/**
 * Render a status projection as short lines; the structured value stays in the
 * tool result, so the transcript does not receive the whole ledger.
 * @param {any} value - projected status.
 * @returns {Array<{ type: 'text', text: string }>} rendered blocks.
 */
function renderStatus(value) {
  const summary = Object.entries(value.summary.statuses)
    .filter(([, count]) => count > 0).map(([status, count]) => `${status} ${count}`).join(' · ') || '无任务'
  const lines = [
    `${value.name || value.project} · 项目修订 ${value.revision} · 任务修订 ${value.task_revision}（schema ${value.task_schema}）`,
    `目标版本 ${value.goal_version} · 目标${value.goal_approved ? '已批准' : '待确认'} · 任务：${summary}`,
  ]
  lines.push(`折叠 ${value.summary.folded_final} 项；本轮${value.focus_missing ? '尚未设置' : '查询见 selection'}。`)
  if (value.current_stale) lines.push('WARN CURRENT 落后于任务修订')
  lines.push(`断点关联：${value.current_alignment}；仅证明记录关联，不判断文字语义。`)
  for (const task of value.tasks) {
    lines.push(`${task.task_id}: 历史状态 ${task.status} · 当前验收 ${task.verification_state} · 交付覆盖 ${task.deliverable_coverage}`)
    for (const check of task.check_summary ?? []) {
      lines.push(`  标准${check.criterion}: ${check.kind} · ${check.level} · 记录结果 ${check.result}`)
    }
  }
  return [{ type: 'text', text: lines.join('\n') }]
}

/**
 * Build the read-only tool set for one activation.
 * @param {ReturnType<typeof import('./kit.js').createKit>} kit - spawn adapter.
 * @param {{ timeoutMs: number }} options - resolved limits.
 * @returns {Array<any>} registry-ready tool definitions.
 */
export function createTools(kit, options) {
  const status = defineTool({
    name: 'anchor_status',
    description:
      '读取 Project Anchor 的磁盘事实：项目修订、目标版本与批准状态、任务列表与断点。'
      + '在制定计划、执行任务或交接之前先调用；不要凭对话记忆推断目标、批准范围或任务状态。'
      + 'brief=true 时省略任务长描述与证据。此工具只读，不写任何文件。',
    parameters: {
      path: {
        type: 'string',
        description: '目标项目目录（含 .agent/state.json 的仓库根）；省略时用当前工作目录。',
      },
      brief: {
        type: 'boolean',
        description: '只保留目标与断点，省略任务长证据与描述。',
      },
      all: { type: 'boolean', description: '配合 brief 返回所有任务，包括已完成项。' },
      focus: { type: 'boolean', description: '仅查询显式本轮任务，不与 task_id 或 milestone 同用。' },
      task_id: {
        type: 'string',
        description: '按明确任务 ID 查询，不接受猜测。',
      },
      milestone: {
        type: 'string',
        description: '按里程碑精确查询。',
      },
    },
    output: {
      schema: STATUS_OUTPUT,
      render: (_args, value) => renderStatus(value),
    },
    async execute(args, exec) {
      const argv = ['status', projectPath(args, exec)]
      if (args.brief === true) argv.push('--brief')
      if (args.all === true) argv.push('--all')
      if (args.focus === true) argv.push('--focus')
      if (args.task_id) argv.push('--task', args.task_id)
      if (args.milestone) argv.push('--milestone', args.milestone)
      const value = await kit.runJson(argv, { signal: exec?.signal, timeoutMs: options.timeoutMs })
      return projectStatus(value)
    },
    presentCall: (args) => ({
      card: 'generic',
      title: 'Read Project Anchor status',
      kind: 'other',
      rawInput: { path: args.path ?? '(cwd)', brief: args.brief === true },
    }),
  })

  const doctor = defineTool({
    name: 'anchor_doctor',
    description:
      '检查 Project Anchor 的安装与规则状态（安装清单、规则来源、原生加载），'
      + '把已验证与未验证分开报告。只读，不改配置、不重新安装。',
    parameters: {
      path: {
        type: 'string',
        description: '目标项目目录；省略时用当前工作目录。',
      },
    },
    output: {
      schema: DOCTOR_OUTPUT,
      render: (_args, value) => [{
        type: 'text',
        text: value.checks
          .map((check) => `${check.status} ${check.check}: ${check.detail}`)
          .join('\n') || '没有检查项。',
      }],
    },
    async execute(args, exec) {
      const value = await kit.run(['doctor', projectPath(args, exec), '--client', 'dsh', '--json'], {
        signal: exec?.signal,
        timeoutMs: options.timeoutMs,
      })
      // doctor reports FAIL through its own rows and exit code; parse either way.
      const text = (value.stdout || '').trim()
      let rows = []
      if (text.startsWith('[') || text.startsWith('{')) {
        try {
          rows = JSON.parse(text)
        } catch {
          rows = []
        }
      }
      if (!Array.isArray(rows) || rows.length === 0) {
        const detail = (value.stderr || text).trim().slice(0, 500) || `退出码 ${value.code}`
        throw new Error(`doctor 未返回检查项：${detail}`)
      }
      const checks = rows.map((row) => ({
        status: String(row?.status ?? 'UNVERIFIED'),
        check: String(row?.check ?? ''),
        detail: String(row?.detail ?? ''),
      }))
      return {
        checks,
        failing: checks.filter((check) => check.status === 'FAIL').length,
        unverified: checks.filter((check) => check.status === 'UNVERIFIED').length,
      }
    },
    presentCall: (args) => ({
      card: 'generic',
      title: 'Check Project Anchor installation',
      kind: 'other',
      rawInput: { path: args.path ?? '(cwd)' },
    }),
  })

  return [status, doctor]
}
