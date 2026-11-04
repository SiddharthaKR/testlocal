import { tool } from "@opencode-ai/plugin"

// TOOL: run a plain-assert Python test file and return a short summary.
export default tool({
  description: "Run a Python test file (plain asserts, no pytest). Returns exit status and the last output lines.",
  args: {
    testfile: tool.schema.string().describe("Test file, e.g. test_fixedpoint.py"),
  },
  async execute(args, context) {
    const py = (process.env.PYTHON_CMD || "python3").split(/\s+/)
    const r = await Bun.$`${py} ${args.testfile}`.cwd(context.directory).nothrow().quiet()
    const text = (r.stdout.toString() + r.stderr.toString()).split("\n").filter((l) => l.trim())
    const head = r.exitCode === 0 ? "TESTS: PASS (exit 0)" : `TESTS: FAIL (exit ${r.exitCode})`
    return [head, ...text.slice(-30)].join("\n")
  },
})
