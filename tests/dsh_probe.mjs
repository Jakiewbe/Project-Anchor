/**
 * Test harness for the DSH bundle's Host modules.
 *
 * It loads `bundle/` with stub Harness packages (no DSH installation needed),
 * reports every registered name/schema, and can execute one tool for real
 * against `kit.py`. Input arrives as one JSON argv; output is one JSON object.
 */

const input = JSON.parse(process.argv[2])
const base = new URL('./bundle/', import.meta.url)

const { createKit } = await import(new URL('kit.js', base))
const { createTools } = await import(new URL('tools.js', base))
const { SECTION_NAME, SECTION_ORDER, sectionText } = await import(new URL('prompt.js', base))
const index = await import(new URL('index.js', base))

const kit = createKit(input.config ?? {})
const tools = createTools(kit, { timeoutMs: input.timeoutMs ?? 20000 })

const result = {
  exports: Object.keys(index).sort(),
  section: { name: SECTION_NAME, order: SECTION_ORDER, text: sectionText() },
  prompt: SECTION_NAME,
  tools: tools.map((tool) => ({
    name: tool.name,
    description: tool.description,
    parameters: tool.parameters,
    schema: tool.output.schema,
  })),
  applied: { tools: [], sections: [] },
  guard: {},
}

// P0 只允许 systemPrompt.section；reaching assemble would silently rewrite the prompt.
const systemPrompt = new Proxy(
  { section: (section) => result.applied.sections.push(section.name) },
  {
    get(target, key) {
      if (key === 'assemble') throw new Error('P0 不得改写 system-prompt/assemble')
      return target[key]
    },
  },
)

index.apply(
  {
    tools: { register: (definition) => result.applied.tools.push(definition.name) },
    systemPrompt,
  },
  {
    pythonPath: input.config?.pythonPath ?? '',
    kitPath: input.config?.kitPath ?? '',
    toolTimeoutMs: input.timeoutMs ?? 20000,
  },
)

try {
  systemPrompt.assemble()
} catch (error) {
  result.guard.assembleBlocked = /assemble/.test(error.message)
}

if (input.run) {
  const selected = tools.find((tool) => tool.name === input.run.tool)
  if (!selected) throw new Error(`unknown tool ${input.run.tool}`)
  const value = await selected.execute(input.run.args, { cwd: input.run.cwd })
  result.executed = { value, blocks: selected.output.render(input.run.args, value) }
}

process.stdout.write(JSON.stringify(result))
