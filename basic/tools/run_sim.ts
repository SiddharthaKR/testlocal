import { tool } from "@opencode-ai/plugin"

// TOOL: compile a testbench with iverilog and run it with vvp. Returns a SHORT summary;
// the full log goes to sim_logs/ so the model's context is not flooded.
export default tool({
  description:
    "Compile and simulate Verilog with iverilog+vvp. Returns COMPILE/SIM status and the first " +
    "errors or FAIL lines. Full log is saved in sim_logs/.",
  args: {
    testbench: tool.schema.string().describe("Testbench file, e.g. tb.v"),
    sources: tool.schema.string().describe("Source files, space separated, e.g. 'red_pitaya_gain_block.v'"),
  },
  async execute(args, context) {
    const dir = context.directory
    const bin = process.env.IVERILOG_DIR ? process.env.IVERILOG_DIR + "/" : ""
    const files = args.sources.split(/\s+/).filter((s) => s)
    await Bun.$`mkdir -p sim_logs`.cwd(dir).nothrow()
    const comp = await Bun.$`${bin}iverilog -g2012 -o sim.vvp ${args.testbench} ${files}`.cwd(dir).nothrow().quiet()
    const cout = comp.stdout.toString() + comp.stderr.toString()
    let log = "=== COMPILE ===\n" + cout
    const out: string[] = []
    if (comp.exitCode !== 0) {
      out.push("COMPILE: FAIL")
      out.push(...cout.split("\n").filter((l) => l.trim()).slice(0, 15))
    } else {
      out.push("COMPILE: OK")
      const sim = await Bun.$`${bin}vvp sim.vvp`.cwd(dir).nothrow().quiet()
      const sout = sim.stdout.toString() + sim.stderr.toString()
      log += "=== SIM ===\n" + sout
      const lines = sout.split("\n").filter((l) => l.trim())
      const bad = lines.filter((l) => /error|fail/i.test(l))
      out.push(sim.exitCode === 0 && bad.length === 0 ? "SIM: OK" : "SIM: FAIL (exit " + sim.exitCode + ")")
      out.push(...bad.slice(0, 10))
      out.push("--- last lines ---", ...lines.slice(-8))
    }
    const logfile = `sim_logs/${Date.now()}.log`
    await Bun.write(`${dir}/${logfile}`, log)
    out.push(`(full log: ${logfile})`)
    return out.slice(0, 40).join("\n")
  },
})
