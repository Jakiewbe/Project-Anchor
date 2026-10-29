/**
 * Spawn adapter for the single business program.
 *
 * Project Anchor keeps every governance invariant in Python `kit.py`. This
 * module only resolves the interpreter and the kit path, runs one argv array,
 * and returns stdout/stderr/exit code. No task, revision, hash, lock or
 * transaction logic is implemented here on purpose.
 * @module project-anchor-dsh/kit
 */

import { spawn, spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { isAbsolute, join, resolve } from 'node:path'

/** Hard cap on captured output; kit writes JSON, so anything larger is a fault. */
const OUTPUT_LIMIT = 1 << 20

/** A failed or unreachable kit invocation, carrying the child's diagnostics. */
export class KitRunError extends Error {
  /**
   * @param {string} message - model-facing summary.
   * @param {{ code?: number | null, stderr?: string, kind?: string }} [detail] - process facts.
   */
  constructor(message, detail = {}) {
    super(message)
    this.name = 'KitRunError'
    this.code = detail.code ?? null
    this.stderr = detail.stderr ?? ''
    this.kind = detail.kind ?? 'exit'
  }
}

/**
 * Resolve the DSH home the way `install-client dsh` records it.
 * @param {NodeJS.ProcessEnv} env - process environment.
 * @returns {string} absolute DSH home.
 */
function dshHome(env) {
  const value = env.DSH_HOME
  if (value && !isAbsolute(value)) throw new KitRunError('DSH_HOME 必须是绝对路径')
  return value || join(homedir(), '.dsh')
}

/**
 * Read the installed skill locator written by `install-client dsh`.
 * @param {string} home - DSH home.
 * @returns {{ kit: string, python: string, home?: string } | undefined} locator, when present.
 */
function readLocator(home) {
  const manifestPath = join(home, 'project-anchor', 'install.json')
  let path = join(home, 'skills', 'project-anchor', 'runtime.json')
  if (existsSync(manifestPath)) {
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8').replace(/^\uFEFF/, ''))
    if (manifest.client !== 'dsh' || !isAbsolute(manifest?.skill?.path ?? '')) {
      throw new KitRunError('DSH 安装清单来源或路径无效')
    }
    path = join(manifest.skill.path, 'runtime.json')
    const recorded = JSON.parse(readFileSync(path, 'utf8').replace(/^\uFEFF/, ''))
    if (recorded.version !== manifest.version) throw new KitRunError('DSH 清单与定位版本不一致')
  } else if (!existsSync(path)) return undefined
  const value = JSON.parse(readFileSync(path, 'utf8').replace(/^\uFEFF/, ''))
  if (value.schema !== 1 || value.client !== 'dsh' || resolve(value.home ?? '') !== resolve(home)
      || !isAbsolute(value.kit ?? '') || !isAbsolute(value.python ?? '') || typeof value.version !== 'string') {
    throw new KitRunError('DSH 定位文件来源、版本或路径无效')
  }
  return value
}

/**
 * Turn a configured path into an absolute `kit.py` file.
 * @param {string} value - file or directory from configuration.
 * @returns {string | undefined} absolute kit path when it exists.
 */
function kitFromConfig(value) {
  if (!value) return undefined
  if (!isAbsolute(value)) throw new KitRunError('kitPath 必须是绝对路径')
  const path = value
  if (path.endsWith('.py')) {
    if (!existsSync(path)) throw new KitRunError('指定的 kit.py 不存在')
    return path
  }
  const file = join(path, 'kit.py')
  if (!existsSync(file)) throw new KitRunError('指定目录中没有 kit.py')
  return file
}

/**
 * Choose the interpreter argv prefix.
 * @param {string} configured - configured interpreter, possibly empty.
 * @param {string} recorded - interpreter recorded by the installer, possibly empty.
 * @returns {{ command: string, prefix: string[] }} executable and leading args.
 */
function interpreter(configured, recorded) {
  const command = configured || recorded
  if (!command || !isAbsolute(command) || !existsSync(command)) throw new KitRunError('Python 绝对路径无效，请配置或重新安装')
  return { command, prefix: [] }
}

/**
 * Build the resolver used by every tool of one activation.
 * @param {{ pythonPath?: string, kitPath?: string, toolTimeoutMs?: number }} config - plugin row config.
 * @param {NodeJS.ProcessEnv} [env] - environment, injectable for tests.
 * @returns {{
 *   run: (args: string[], options?: { cwd?: string, stdin?: string, signal?: AbortSignal, timeoutMs?: number }) => Promise<{ code: number, stdout: string, stderr: string }>,
 *   runJson: (args: string[], options?: { cwd?: string, stdin?: string, signal?: AbortSignal, timeoutMs?: number }) => Promise<any>,
 *   locate: () => { kit: string, command: string, prefix: string[] },
 * }} runKit facade.
 */
export function createKit(config = {}, env = process.env) {
  let located

  const locate = () => {
    if (located) return located
    const home = dshHome(env)
    const locator = config.kitPath && config.pythonPath ? undefined : readLocator(home)
    const kit = config.kitPath ? kitFromConfig(config.kitPath) : locator?.kit
    if (!kit) {
      throw new KitRunError(
        '找不到 kit.py：请在插件配置里设置 kitPath，或先执行 `install-client dsh` 生成 Skill 定位文件。',
        { kind: 'unresolved' },
      )
    }
    const chosen = interpreter(config.pythonPath ?? '', locator?.python ?? '')
    const version = spawnSync(chosen.command, ['-X', 'utf8', kit, '--version'], {
      encoding: 'utf8', windowsHide: true, timeout: 10000,
    })
    if (version.error) {
      throw new KitRunError(`无法启动工具箱版本查询: ${version.error.message}`, { kind: 'start' })
    }
    if (version.status !== 0) {
      throw new KitRunError(`工具箱版本查询失败 (${version.status}): ${(version.stderr || '').trim()}`, { kind: 'exit' })
    }
    if (version.stdout.trim() !== '1.5.1'
        || (locator && locator.version !== version.stdout.trim())) {
      throw new KitRunError('工具箱版本或安装版本不匹配，请检查安装')
    }
    located = { kit, command: chosen.command, prefix: chosen.prefix, home }
    return located
  }

  const run = (args, options = {}) => {
    if (options.signal?.aborted) return Promise.reject(new KitRunError('kit.py 调用已取消。', { kind: 'cancelled' }))
    const target = locate()
    const timeoutMs = options.timeoutMs ?? config.toolTimeoutMs ?? 20_000
    return new Promise((resolvePromise, rejectPromise) => {
      let settled = false
      let stdout = ''
      let stderr = ''
      const finish = (fn, value) => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        options.signal?.removeEventListener('abort', onAbort)
        fn(value)
      }
      const child = spawn(target.command, [...target.prefix, target.kit, ...args], {
        cwd: options.cwd ?? process.cwd(),
        env: { ...env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1',
          PROJECT_ANCHOR_CLIENT: 'dsh', PROJECT_ANCHOR_CLIENT_HOME: target.home },
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
      })
      const timer = setTimeout(() => {
        child.kill()
        finish(rejectPromise, new KitRunError(`kit.py 超过 ${timeoutMs}ms 未返回，已终止。`, { kind: 'timeout' }))
      }, timeoutMs)
      const onAbort = () => {
        child.kill()
        finish(rejectPromise, new KitRunError('kit.py 调用已取消。', { kind: 'cancelled' }))
      }
      if (options.signal?.aborted) onAbort()
      else options.signal?.addEventListener('abort', onAbort, { once: true })
      child.on('error', (error) => {
        finish(
          rejectPromise,
          new KitRunError(`无法启动 ${target.command}：${error.message}`, { kind: 'spawn' }),
        )
      })
      child.stdout.setEncoding('utf8')
      child.stderr.setEncoding('utf8')
      child.stdout.on('data', (chunk) => {
        stdout += chunk
        if (stdout.length > OUTPUT_LIMIT) {
          child.kill()
          finish(rejectPromise, new KitRunError('kit.py 输出超过上限，已终止。', { kind: 'output' }))
        }
      })
      child.stderr.on('data', (chunk) => {
        stderr += chunk
        if (stderr.length > OUTPUT_LIMIT) stderr = stderr.slice(0, OUTPUT_LIMIT)
      })
      child.on('close', (code) => {
        finish(resolvePromise, { code: code ?? 1, stdout, stderr })
      })
      if (options.stdin === undefined) child.stdin.end()
      else child.stdin.end(options.stdin, 'utf8')
    })
  }

  const runJson = async (args, options = {}) => {
    const result = await run(args, options)
    if (result.code !== 0) {
      const detail = (result.stderr || result.stdout).trim() || `退出码 ${result.code}`
      throw new KitRunError(detail.slice(0, 2_000), { code: result.code, stderr: result.stderr })
    }
    const text = result.stdout.trim()
    if (text === '') throw new KitRunError('kit.py 未返回 JSON。', { code: result.code, kind: 'empty' })
    try {
      return JSON.parse(text)
    } catch {
      throw new KitRunError(`kit.py 输出不是 JSON：${text.slice(0, 300)}`, { kind: 'json' })
    }
  }

  return { run, runJson, locate }
}
