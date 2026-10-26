/**
 * Host entry for the Project Anchor bundle.
 *
 * Registration is deliberately minimal: two read-only tools and one prompt
 * section. Disposers come from the registries themselves, so unloading the
 * plugin removes exactly what it added.
 * @module project-anchor-dsh
 */

import z from '@deepseek-ai/schemastery'
import { createKit } from './kit.js'
import { createTools } from './tools.js'
import { SECTION_NAME, SECTION_ORDER, sectionText } from './prompt.js'

/** Loader row name; also the bundle row id in `cordis.patch.yml`. */
export const name = 'project-anchor-dsh'

/** Host services this plugin consumes; activation waits for all of them. */
export const inject = ['tools', 'systemPrompt']

/** Row configuration; the user's patch layer survives upgrades. */
export const Config = z.object({
  pythonPath: z.string().default('').description('Python 解释器绝对路径；留空则使用安装记录；缺失时明确失败。'),
  kitPath: z.string().default('').description('kit.py 文件或包含它的目录；留空则读 DSH 安装记录。'),
  toolTimeoutMs: z.number().default(20000).description('单次 kit.py 调用超时（毫秒）。'),
})

/**
 * Register the bundle's contributions on the loading context.
 * @param {any} ctx - Cordis plugin context.
 * @param {{ pythonPath?: string, kitPath?: string, toolTimeoutMs?: number }} config - resolved row config.
 */
export function apply(ctx, config) {
  const options = {
    pythonPath: config.pythonPath ?? '',
    kitPath: config.kitPath ?? '',
    toolTimeoutMs: config.toolTimeoutMs ?? 20_000,
  }
  const kit = createKit(options)

  for (const definition of createTools(kit, { timeoutMs: options.toolTimeoutMs })) {
    ctx.tools.register(definition)
  }

  ctx.systemPrompt.section({
    name: SECTION_NAME,
    order: SECTION_ORDER,
    text: sectionText(),
  })
}
