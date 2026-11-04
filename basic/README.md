# basic: does giving a small coding agent skills and tools actually help?

This demo gives a local LLM coding agent ([opencode](https://opencode.ai)) a small engineering
task, once as a plain agent and once with extra help (a **skill** and a **tool**). A hidden
**harness** then grades the result, so you can measure whether the help matters. It is small on
purpose: no proxy, no HTML reports, just PASS/FAIL, a score and the coding time.

## The three building blocks

**SKILL = a handbook chapter.** A markdown file of general know-how with a `name` and a
`description`. opencode shows only the descriptions to the model; if the task matches, the model
loads the body (cheap on context until needed). Like a senior colleague's cheat sheet on the shelf.
Files: `skills/verilog-fixed-point/SKILL.md`, `skills/python-tdd/SKILL.md` (folder name == `name`).
```
---
name: python-tdd
description: Test-first workflow for small pure Python functions ... Load before implementing a Python function.
---
```

**TOOL = a power tool on the bench.** A TypeScript file; the file name is the tool name. It declares
a description and typed arguments, runs a command and returns a SHORT summary (full logs go to a
file), because small models cope far better with 10 lines than with 500 lines of simulator output.
Files: `tools/run_sim.ts` (iverilog + vvp), `tools/run_tests.ts` (plain-assert Python tests).
```ts
export default tool({
  description: "Run a Python test file (plain asserts, no pytest). Returns exit status and the last output lines.",
  args: { testfile: tool.schema.string().describe("Test file, e.g. test_fixedpoint.py") },
  async execute(args, context) { /* run it, return "TESTS: PASS|FAIL" + last lines */ },
})
```

**HARNESS = the exam hall.** `harness.py` builds a clean workspace, lets the agent work, then calls
a judge the agent never sees. `selftest.py` first proves the judges: the reference solution must
pass and every `broken_*` variant must fail.
```
tasks/<task>/agent/   -> copied to the workspace (task.md, stubs, spec)
tasks/<task>/hidden/  -> NEVER copied; used only by tasks/<task>/judge.py
```

## What happens in one run
1. Lock the workspace `../../basic_ws` (outside the repo) and recreate it from `tasks/<task>/agent/`.
2. Mode "with" (default): copy `skills/` and `tools/` to `<ws>/.opencode/`. Mode `--without`: no `.opencode` folder.
3. Write `opencode.json` pointing at your local model server. `task.md` gets one neutral line,
   "Skills and tools may be available...", **identical in both modes**.
4. Run `opencode run` with a timeout. The harness's own Python (`sys.executable`, first on PATH) and
   `iverilog_dir` are given to the agent and to the tools, so both modes can simulate from the shell.
5. Only after the agent stops, run the hidden judge: it prints `SCORE` (% of hidden samples/cases right) and PASS/FAIL.
   The `fpga_gain` judge also checks the bus contract (reset values, readback, sign extension,
   constant, unknown address, ack, no X).
6. Save `../../basic_runs/<ts>_<task>_<mode>/`: `result.json`, `agent.log`, and a copy of the workspace.

## Quickstart
Prerequisites: **opencode 1.17.x** (see Limits), **iverilog 12**, and an OpenAI-compatible model
server (default: Ollama at `http://localhost:11434/v1`). Edit `config.yaml`: `model`, `base_url`,
`context_limit`, `timeout_min`, `iverilog_dir` (empty = on PATH), `opencode_cmd` (empty = on PATH).
```
py basic/selftest.py                          # judges OK? (Linux: python3)
py basic/harness.py py_func --setup-only      # build the workspace only, no agent
py basic/harness.py py_func                   # one run WITH skills + tools
py basic/harness.py py_func --without         # one run, plain agent
py basic/harness.py fpga_gain --compare --runs 3   # A/B, then a table
```
A run prints `task [mode skills+tools]: PASS|FAIL (score N%) - reason (agent X.X min)`.

## With vs without
`--compare --runs N` runs N plain and N with-help runs, interleaved and alternating which goes
first, so warm-up and time-of-day effects hit both sides. The table:
```
                          passed   median score   coding time
plain agent               1 of 3            62%       12.0 min
agent + skill + tool      3 of 3           100%        7.5 min
```
- **passed**: runs whose hidden judge said PASS.
- **median score**: % of hidden samples/cases correct, so a near miss still shows (100% = all right).
- **coding time**: median wall time of the agent only (not the judge).

Fair because the model, the task text, the workspace, the PATH tools and the hidden judge are the
same; the only difference is whether `.opencode/skills` and `.opencode/tools` exist. With 3 runs it
is an anecdote, not statistics; use more runs before drawing conclusions.

## Add your own task in 5 steps
1. Create `tasks/<name>/agent/` with `task.md` (end it with the line `{HELP}`) and any stubs/specs.
2. Create `tasks/<name>/hidden/` with `reference.*` (a correct solution), several `broken_*` variants
   (each wrong in a different way) and your hidden tests.
3. Write `tasks/<name>/judge.py <workspace>`: print `SCORE: N% ...` and a final `PASS: ...`/`FAIL: ...` line; exit 0 only on PASS.
4. Add the task to `TARGET` in `selftest.py` (task -> the file name the agent must produce) and run it:
   the reference must pass and all broken variants must fail.
5. Run `py basic/harness.py <name> --setup-only`, read the workspace as the agent would, then do a real run.

## Limits
- **Isolation is limited.** The agent works in its own folder and opencode denies its file tools
  outside it, but its shell runs as your user and could read this repo (including `hidden/`). For
  real evaluations run the agent in a container or under a separate OS user. This is a teaching demo.
- **Small models are noisy.** Results vary run to run; they may ignore skills or loop. Use several runs.
- **opencode version.** Custom tools in `.opencode/tools/*.ts` are the 1.x format; opencode 2.x does
  not load them (skills still work there). The harness warns on 2.x and refuses `--compare`.
