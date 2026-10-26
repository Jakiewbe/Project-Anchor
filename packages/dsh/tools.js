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
  const tasks = Array.isArray(value.tasks) ? value.tasks : []
  const warnings = []
  if (value.goal_approved === false) warnings.push('项目总目标仍待确认；只处理用户已明确授权的局部任务。')
  if (value.current_stale === true) warnings.push('CURRENT 落后于任务修订，读到的断点可能过期。')
  return {
    project: String(value.project ?? ''),
    name: String(value.name ?? ''),
    revision: Number(value.revision ?? 0),
    task_revision: Number(value.task_revision ?? 0),
    task_schema: Number(value.task_schema ?? 0),
    goal_version: Number(value.goal_version ?? 0),
    goal_approved: value.goal_approved === true,
    current_stale: value.current_stale === true,
    tasks: tasks.map((task) => ({
      task_id: String(task?.task_id ?? ''),
      title: String(task?.title ?? ''),
      status: String(task?.status ?? ''),
      plan: String(task?.plan ?? ''),
      milestone: String(task?.milestone ?? ''),
    })),
    goal: String(value.goal ?? ''),
    current: String(value.current ?? ''),
    warnings,
  }
}

const STATUS_OUTPUT = {
  type: 'object',
  additionalProperties: false,
  properties: {
    project: { type: 'string' },
    name: { type: 'string' },
    revision: { type: 'integer' },
    task_revision: { type: 'integer' },
    task_schema: { type: 'integer' },
    goal_version: { type: 'integer' },
    goal_approved: { type: 'boolean' },
    current_stale: { type: 'boolean' },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          task_id: { type: 'string' },
          title: { type: 'string' },
          status: { type: 'string' },
          plan: { type: 'string' },
          milestone: { type: 'string' },
        },
        required: ['task_id', 'title', 'status', 'plan', 'milestone'],
      },
    },
    goal: { type: 'string' },
    current: { type: 'string' },
    warnings: { type: 'array', items: { type: 'string' } },
  },
  required: [
    'project', 'name', 'revision', 'task_revision', 'task_schema', 'goal_version',
    'goal_approved', 'current_stale', 'tasks', 'goal', 'current', 'warnings',
  ],
}

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
  const counts = new Map()
  for (const task of value.tasks) counts.set(task.status, (counts.get(task.status) ?? 0) + 1)
  const summary = [...counts].map(([status, count]) => `${status} ${count}`).join(' · ') || '无任务'
  const lines = [
    `${value.name || value.project} · 项目修订 ${value.revision} · 任务修订 ${value.task_revision}（schema ${value.task_schema}）`,
    `目标版本 ${value.goal_version} · 目标${value.goal_approved ? '已批准' : '待确认'} · 任务：${summary}`,
  ]
  for (const warning of value.warnings) lines.push(`WARN ${warning}`)
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
