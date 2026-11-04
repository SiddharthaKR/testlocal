# basic: skill, tool, harness in ~600 lines

A stripped-down companion of the full harness in `../harness`. It shows the three building
blocks of an LLM coding-agent setup with [opencode](https://opencode.ai), with no proxy,
no levels, no HTML reports. Output is PASS/FAIL plus wall time.

## SKILL: know-how the agent loads on demand
A markdown file with a short `name` + `description` header. opencode lists the
descriptions to the model; when a task matches, the model calls its built-in `skill` tool
and reads the body. Cheap on context until needed.
Files: `skills/verilog-fixed-point/SKILL.md`, `skills/python-tdd/SKILL.md`.
Rules: folder name == `name`, lowercase-with-hyphens.

## TOOL: an action the agent can call
A TypeScript file in `.opencode/tools/`; the filename is the tool name. It declares a
description and typed arguments, runs a command and returns SHORT text (full logs go to a
file). Small models do much better with a 10-line summary than with 500 lines of simulator
output. Files: `tools/run_sim.ts` (iverilog + vvp), `tools/run_tests.ts` (python asserts).
Tools read `IVERILOG_DIR` and `PYTHON_CMD` from the environment (set by the harness).

## HARNESS: clean workspace in, verdict out
`harness.py` (1) rebuilds the workspace from `tasks/<task>/agent/` plus skills, tools and a
generated `opencode.json`; (2) runs `opencode run` there with a timeout, logging to
`../../basic_runs/<ts>_<task>/agent.log`; (3) runs `tasks/<task>/judge.py`, which uses
HIDDEN tests (`tasks/<task>/hidden/`, never copied into the workspace). `selftest.py`
proves the judges first: the reference solution must pass, each broken variant must fail.

## Quickstart
```
py basic/selftest.py                 # judges work? (python3 on Linux)
py basic/harness.py py_func --setup-only   # inspect the workspace, no agent
py basic/harness.py py_func          # real run -> "py_func: PASS|FAIL - reason (agent X.X min)"
py basic/harness.py fpga_gain
```
Edit `config.yaml` for the model server, model name, timeout, python and iverilog paths.
Requires `opencode` on PATH, a running OpenAI-compatible server, Python 3 and iverilog.

## Add your own task in 5 steps
1. `tasks/<name>/agent/` : put `task.md` and anything the agent may see (specs, stubs).
2. `tasks/<name>/hidden/` : write the hidden tests, a `reference.*` solution and one or
   more `broken_*` variants (a wrong-but-plausible solution each).
3. `tasks/<name>/judge.py <workspace>` : check the workspace, print `PASS: ...` or
   `FAIL: <one sentence>`, exit 0 / 1.
4. Add the file name the agent must produce to `TARGET` in `selftest.py`; run it until
   `SELFTEST: OK`.
5. Add a skill or tool if the task needs one, then `py basic/harness.py <name>`.
