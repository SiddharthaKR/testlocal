# AI-assisted FPGA development demo

A local LLM agent (opencode + a local model) does FPGA work on the PyRPL codebase. Every claim is checked by an independent, hidden judge.

Three tasks, each at three difficulty levels (`--level easy|medium|hard`, default `hard`):

| Track | Easy | Medium | Hard | Checked by |
|---|---|---|---|---|
| H: new block from a spec | gain/offset block | 8-tap FIR | notch filter (biquad, 1-cycle feedback) | bit-exact against a Python model on hidden signals |
| B: optimize existing PyRPL block | IQ demodulator | IQ modulator | PID controller | bit-exact equivalence over 100k random cycles (+ Vivado timing) |
| C: bug hunt in PyRPL modules | 2 files, 3 bugs | 2 files, 5 bugs | 4 modules, 10 bugs | answer key (line ±3, and the explanation must name the bug) |

## Quickstart (server / office)

See [PORTING.md](PORTING.md) for the full checklist. In short:

```bash
git clone https://github.com/SiddharthaKR/testlocal.git ai_demo && cd ai_demo
bash harness/setup_vendor.sh          # fetch PyRPL at the pinned commit (read-only)
$EDITOR config/env.yaml               # fill in the TODOs: LM Studio URL, model id, context
bash harness/judge/judge_selftest.sh all
bash harness/run_demo.sh --track H --level easy    # tracks H|B|C, levels easy|medium|hard
bash harness/run_demo.sh --track H                 # hard (default); add --assist for a skeleton
```

Each run writes `runs/<timestamp>_<track>/report.html`; `runs/summary.html` covers all runs.

## Layout
- `config/`: `env.yaml` (the only file to edit). Profiles: `env.laptop.yaml` (laptop + Ollama), `env.aistudio.yaml` (Google AI Studio Gemma 4 26B; key read from `GEMINI_API_KEY`, never stored; the free tier's 16k input tokens/minute is too small for agent runs, so a paid tier is needed)
- `harness/`: proxy, agent tools, task prompts, hidden judges, report generator, `run_demo.sh`
- `docs/laptop_results.md`: laptop results (Gemma 4 E4B, 32k vs 64k context)

The agent works in `workspace_dir` (outside this repo), so it cannot read the judges. Every hidden file carries a canary string, and a run is marked invalid if the canary reaches the model.

Requirements: Python 3 (numpy, matplotlib, pyyaml), iverilog 12, opencode, git; Vivado is optional (steps print SKIPPED without it).
