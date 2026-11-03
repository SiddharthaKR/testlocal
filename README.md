# AI-assisted FPGA development demo

A local LLM agent (opencode + a local model) does FPGA work on the PyRPL codebase. Every claim is checked by an independent, hidden judge.

| Track | Agent task | Checked by |
|---|---|---|
| H | Write a notch-filter block from a spec | bit-exact against a Python model on hidden signals |
| B | Make the PID block faster/smaller | bit-exact equivalence over 100k random cycles (+ Vivado timing) |
| C | Find seeded bugs in 4 modules | answer key (line ±3, and the explanation must name the bug) |

## Quickstart (server / office)

See [PORTING.md](PORTING.md) for the full checklist. In short:

```bash
git clone https://github.com/SiddharthaKR/testlocal.git ai_demo && cd ai_demo
bash harness/setup_vendor.sh          # fetch PyRPL at the pinned commit (read-only)
$EDITOR config/env.yaml               # fill in the TODOs: LM Studio URL, model id, context
bash harness/judge/judge_selftest.sh all
bash harness/run_demo.sh --track H    # or B, C; add --assist for track H
```

Each run writes `runs/<timestamp>_<track>/report.html`; `runs/summary.html` covers all runs.

## Layout
- `config/`: `env.yaml` (the only file to edit); `env.laptop.yaml` is the laptop/Ollama setup
- `harness/`: proxy, agent tools, task prompts, hidden judges, report generator, `run_demo.sh`
- `docs/laptop_results.md`: laptop results (Gemma 4 E4B, 32k vs 64k context)

The agent works in `workspace_dir` (outside this repo), so it cannot read the judges. Every hidden file carries a canary string, and a run is marked invalid if the canary reaches the model.

Requirements: Python 3 (numpy, matplotlib, pyyaml), iverilog 12, opencode, git; Vivado is optional (steps print SKIPPED without it).
