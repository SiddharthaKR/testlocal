# HANDOFF — AI-assisted FPGA Development Demo Kit

## 0. Context (read first)

I am building a demo for management showing that a **local, on-prem LLM agent** (opencode + local model) can do real FPGA engineering work on an existing codebase, with **every claim verified by an independent judge**, not by the agent itself.

- Codebase under test: **PyRPL** (public), FPGA sources in `vendor/pyrpl/pyrpl/fpga/rtl/`
- Agent: **opencode** (already installed)
- Phase 1 (now): build and validate everything on my **laptop** with **Ollama**
- Phase 2 (later): move unchanged to a shared server (`.126`) running **LM Studio** with Gemma 4 26B-A4B. Only the upstream URL and model name change.

Your job (Claude Code): **build the harness, tools, judges, reference solutions and report generator**. You are NOT the agent under test. The agent under test is opencode + the local model.

---

## 1. The three demos

| Track | Name | Agent task | Verified by | Management visual |
|---|---|---|---|---|
| **H (hero)** | Spec → new DSP block | Write `red_pitaya_notch_block.v` from a spec + Python golden model, test it, synthesize it | Hidden judge: bit-exact vs Python model on hidden stimulus | Noisy → clean time plot; spectrum spike removed; FPGA-vs-model overlay |
| **B** | Optimize existing design | Improve timing / reduce resources of PyRPL PID block without changing function | Hidden judge: latency-tolerant bit-exact equivalence + post-route QoR | Resource bar chart; Fmax "speed gauge" |
| **C** | Bug hunt | Find seeded bugs in 4 PyRPL modules | Answer key scorer | Scoreboard "found X/10" |

Out of scope: hardware-in-the-loop, GPU load benchmarking, onboarding Q&A, Python GUI class for the notch.

---

## 2. Environment

### Laptop (Phase 1)
- Ollama at `http://localhost:11434/v1` (OpenAI-compatible)
- Models available (use the **ctx32768** variants — Ollama's default context is too small for agents):
  - `gemma4-e4b-ctx32768:latest` ← **primary for demo plumbing**
  - `qwen3-8b-ctx32768:latest`, `qwen2.5-7b-ctx32768:latest` ← plumbing tests only
- **Policy constraint:** the final management demo must use a **non-Chinese model (Gemma)**. Qwen may be used only to debug plumbing on the laptop. Never hardcode Qwen anywhere in the demo path.
- **Expectation:** gemma4:e4b is small; it will likely FAIL the hero task. That is fine. Phase 1 validates the *pipeline and judges*, not model quality.
- Tools: `iverilog`/`vvp`, Python 3 (numpy, matplotlib, pyyaml). **Vivado may not be on the laptop** → every Vivado step must auto-detect and skip cleanly with a "SKIPPED (no vivado)" status.

### Server (Phase 2)
- LM Studio OpenAI-compatible endpoint (URL via config), model Gemma 4 26B-A4B
- iverilog + Vivado installed

### Config
Single file `config/env.yaml`:
```yaml
upstream_url: http://localhost:11434/v1     # Phase 2: LM Studio URL
model: gemma4-e4b-ctx32768:latest          # Phase 2: LM Studio model id
proxy_port: 8100
pyrpl_repo: ./vendor/pyrpl                 # read-only, pinned (pyrpl_commit), see §3
fpga_part: xc7z010clg400-1                 # Red Pitaya Z10 (xc7z020clg400-1 for Z20)
clk_period_ns: 8.0
vivado: auto                               # auto | /path/to/vivado | none
```
No hardcoded paths anywhere else.

---

## 3. Directory layout

```
ai_demo/
├── config/env.yaml  opencode.json
├── workspace/                  ← agent's ONLY area; recreated every run
│   └── pyrpl/                  ← fresh copy of vendor/pyrpl (no .git), tag demo-baseline
├── harness/                    ← agent must never see this
│   ├── proxy/llm_proxy.py
│   ├── tools/                  ← copied into workspace/tools at run start
│   ├── tasks/                  ← prompts + specs (copied in per track)
│   ├── judge/                  ← hidden; used only after agent finishes
│   │   ├── notch/  pid_equiv/  bughunt/
│   │   └── ref_solutions/      ← YOUR known-good solutions to validate judges
│   ├── report/make_report.py
│   └── run_demo.sh
└── runs/<timestamp>_<track>/   ← all artifacts per run
```

**Isolation rule:** the judge directory is never copied into `workspace/` before the agent finishes. The agent's cwd is `workspace/`.

---

## 4. Components

### 4.1 Logging proxy — `harness/proxy/llm_proxy.py`
OpenAI-compatible pass-through: `localhost:{proxy_port}` → `{upstream_url}`.
- Must support **SSE streaming** (opencode streams) and non-streaming.
- Inject `stream_options: {include_usage: true}` when streaming; if upstream omits usage, estimate tokens (chars/4) and flag `usage_estimated: true`.
- Log one JSON line per request to `runs/<id>/requests.jsonl`:
  `t_start, t_first_token, t_end, prompt_tokens, completion_tokens, usage_estimated, n_messages, status`.
- Save full request bodies to `runs/<id>/requests/` (for later analysis).
- Count user messages starting with `HINT:` → human interventions.
- **Accept:** opencode works through the proxy unchanged; a 3-turn session produces 3+ log lines with non-zero tokens.

### 4.2 opencode config — `config/opencode.json`
Point opencode at the proxy, e.g. (verify against the installed opencode version's docs):
```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "local": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Local via proxy",
      "options": { "baseURL": "http://localhost:8100/v1" },
      "models": { "gemma4-e4b-ctx32768:latest": { "name": "Gemma 4 E4B" } }
    }
  }
}
```
Generate this file from `env.yaml` so Phase 2 only edits `env.yaml`.

### 4.3 Agent tools — `harness/tools/` (copied into workspace)
| Tool | Behavior |
|---|---|
| `run_sim.sh <tb.v> <src.v...>` | `iverilog -g2012 -o sim.out ... && vvp sim.out`; nonzero exit on compile error; testbenches write CSV via `$fwrite` (no VCD parsing) |
| `plot_wave.py <csv> [cols]` | quick PNG for the agent's own inspection |
| `run_synth.sh <top> <files...>` | Vivado batch OOC synthesis → `synth.json` {LUT, FF, DSP, CARRY4, WNS} |
| `run_impl.sh <top> <period_ns> <files...>` | OOC synth + opt + place + route → `impl.json` incl. WNS, top-5 critical paths (source, dest, logic levels) |
| `run_equiv.sh` | agent-visible *mini* equivalence check for Track B (small stimulus, NOT the judge's) |

Vivado scripts: `synth_design -mode out_of_context -part {fpga_part}`, `create_clock -period {period}` on `clk_i`. Skip cleanly if no Vivado.

### 4.4 Agent rules — `harness/tasks/AGENTS.md` (copied into workspace)
1. Work only inside `workspace/`.
2. Never claim something works without running the relevant tool and showing output.
3. Do not change existing module ports, parameters or register maps (unless the task says so).
4. Finish by writing `AGENT_REPORT.md`: what you did, why, evidence (tool outputs), remaining issues.

### 4.5 Orchestration — `harness/run_demo.sh --track {H|B|C} [--interactive]`
1. Recreate `workspace/`, copy pinned PyRPL, `git init` + commit as baseline (for clean diffs).
2. Copy tools, AGENTS.md, track task files.
3. Start proxy, create `runs/<ts>_<track>/`.
4. Run agent: scripted `opencode run ...` (verify CLI flags for installed version) or interactive for recording.
5. Stop proxy; save `git diff`, `AGENT_REPORT.md`, agent-produced files.
6. Copy judge in → run judge → `judge.json`.
7. Run `make_report.py`.
Record wall time for: total, LLM time (from proxy), Vivado time (separately).

---

## 5. Track H — Notch filter from spec (HERO)

### 5.1 Golden model — `harness/tasks/H/notch_model.py`
Refactor the existing `notch_demo_viz.py` (provided by me) into:
- `notch_model.py`: pure bit-true model + coefficient generator (importable, CLI: reads stimulus file → writes output file). **This file IS given to the agent** as part of the spec.
- `harness/report/notch_viz.py`: the management plots (stays hidden).

Bit-true definition (must match exactly):
```
coeffs: b0,b1,b2,a1,a2 — signed 18-bit, Q2.16 (COEF_FRAC=16)
acc  = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]   (full precision)
y[n] = sat14( (acc + 2^15) >>> 16 )        # arithmetic shift; round half up
sat14 clamps to [-8192, 8191]; feedback uses the SATURATED y
x, y: signed 14-bit
```
Coefficients from f0, r: b=[1, -2cos w0, 1], a=[-2r cos w0, r^2], quantized round(c*2^16).

### 5.2 Spec given to agent — `harness/tasks/H/notch_spec.md`
Write this spec including:
- Module name `red_pitaya_notch_block`, ports identical in style to `red_pitaya_pid_block.v`:
  `clk_i, rstn_i, dat_i[13:0] signed, dat_o[13:0] signed, addr[15:0], wen, ren, ack, rdata[31:0], wdata[31:0]`
- Register map: `0x100 b0, 0x104 b1, 0x108 b2, 0x10C a1, 0x110 a2` (18-bit signed, sign-extended on readback), `0x114 bypass` (1 = dat_o follows dat_i delayed), `0x200` read-only `COEF_FRAC`.
- One output sample per clock (fs = clk). Output latency: any fixed latency ≤ 4 cycles is acceptable (state it in AGENT_REPORT.md).
- Must match `notch_model.py` bit-exactly. Must target 125 MHz (8 ns).
- Note to agent: the recursive path (y[n-1] → multiply → accumulate → round → saturate → y[n]) must complete every cycle.

Task prompt `harness/tasks/H/task.md`: "Implement the notch block per notch_spec.md, write a testbench comparing against notch_model.py, iterate until bit-exact, then run run_synth.sh and report resources/timing."

### 5.3 Hidden judge — `harness/judge/notch/`
- Stimuli (never shown to agent): (a) signal+interference like the viz, (b) random full-scale (exercises saturation), (c) chirp, (d) impulse; at ≥2 coefficient sets (different f0, r).
- Testbench writes registers via the bus, streams stimulus from file (`$fscanf`/`$readmemh`), writes output CSV.
- Compare to `notch_model.py`: find latency k ∈ [0,4] with bit-exact match after reset settle; PASS/FAIL per stimulus; first-mismatch report.
- Also check: register readback, bypass mode, no X/Z on dat_o after reset.
- Synth/impl QoR reported (not pass/fail if Vivado missing; on server: WNS ≥ 0 at 8 ns reported as "timing met").
- Output `judge.json` + data files for plots.

### 5.4 Judge validation (mandatory before any agent run)
In `ref_solutions/notch/`: write your own correct `red_pitaya_notch_block.v` → must PASS all. Create ≥3 broken variants (truncate instead of round; feedback uses unsaturated y; wrong sign on a1) → each must FAIL. Commit `judge_selftest.sh` that runs this.

### 5.5 Management visuals (from judge data)
1. Before (red, noisy) / After (green, clean) time plot with dashed "wanted signal" — reuse `notch_demo_viz.py` style.
2. Spectrum before/after with "interference −XX dB" annotation.
3. **FPGA output vs Python model overlay** (identical lines) captioned "Hardware matches design model exactly".
Plain-language titles; no jargon on plots.

---

## 6. Track B — Optimize PyRPL PID

### 6.1 Reference baseline — `harness/tasks/B/pid_ref.v`
Original `red_pitaya_pid_block.v` with ONE fix only: the module-level `kd_reg_s` is never driven (re-declared inside unnamed generate blocks), which gives X in simulation. Fix by declaring a single module-level `kd_term` driven from named generate blocks (`g_d` / `g_nod`); keep everything else bit-identical. Dependency: `red_pitaya_filter_block.v`.

### 6.2 Baseline QoR and target
On a Vivado machine: run `run_impl.sh` on `pid_ref.v` → baseline LUT/FF/DSP/WNS, Fmax ≈ 1/(T − WNS). Set `T_target = 1/(1.3·Fmax_base)` so baseline FAILS timing. Store in `harness/tasks/B/baseline.json`. On laptop without Vivado: skip, use a placeholder target.

### 6.3 Task prompt
"`red_pitaya_pid_block` fails timing at <T_target> ns. Close timing and reduce resources without changing function, ports, parameters or register map. Use run_impl.sh and run_equiv.sh. Report each change with measured effect."

### 6.4 Hidden judge — `harness/judge/pid_equiv/`
- Random stimulus, ≥1e5 cycles (1e6 on server): input, setpoint, Kp/Ki (Kd with DERIVATIVE=0 as instantiated), filter setting, out_min/out_max, `ival` writes, sync/pause bits, forced saturation episodes. Same parameters as the original instantiation (fixed in the judge TB).
- Reference = `pid_ref.v`; candidate = agent's file. Find lag k ∈ [0,8] with bit-exact output match → PASS, report Δlatency = k. Register readback must match with k = 0.
- Phase-margin cost: report Δφ = 360°·f_c·k·T_clk at f_c = 1 MHz.
- QoR table baseline vs candidate; changes < 3% LUT/FF or < 0.1 ns WNS marked "within noise".
- Self-test: `ref_solutions/pid/` — one correct optimized version (e.g. pause mux moved to operand + MREG pipelining, i.e. +1 latency) must PASS; broken variants (removed arbitrary saturation; changed saturation polarity) must FAIL.

### 6.5 Visuals
Resource bar chart before/after; "max speed X → Y MHz" gauge or bar; "functionally identical over N random cycles" badge.

---

## 7. Track C — Bug hunt

- Pick 4 modules from `vendor/pyrpl/pyrpl/fpga/rtl/` (e.g. pid, filter, iq, asg — use what exists in the pinned commit).
- Create ~10 single-bug patches in `harness/judge/bughunt/patches/` across classes: sign/width, slice off-by-one, saturation polarity flip, missing reset, blocking `=` in clocked block, removed pipeline register.
- `answer_key.yaml`: file, line, class, one-line description.
- Agent receives the patched files + prompt: "Review these modules for functional bugs. Output `bugs.json`: list of {file, line, description}."
- Scorer: match by file + line within ±3 → found; also count false positives. Output scoreboard + `bughunt.png` ("Found X of 10 bugs in N minutes").
- Note: PyRPL may be in model training data; seeded bugs avoid memorization effects.

---

## 8. Report — `harness/report/make_report.py`
Per run, produce `runs/<id>/report.md` + PNGs:
- Track visuals (§5.5, §6.5, §7)
- Metrics table: wall time, LLM time, Vivado time, total tokens, peak prompt tokens, #requests, #HINTs, judge result
- **Time comparison bar**: agent time vs engineer estimate. Engineer estimates come from `config/engineer_estimates.yaml` (I fill these in; label as "engineer estimate" on the chart).
- Aggregate script across multiple runs: median + pass rate (never best-run only).

---

## 9. Build order & acceptance

| # | Milestone | Acceptance |
|---|---|---|
| 1 | Config + proxy + opencode through proxy | Ollama chat via opencode logged in requests.jsonl |
| 2 | Tools (sim/plot; Vivado ones skip cleanly) | `run_sim.sh` runs a trivial TB; Vivado tools print SKIPPED on laptop |
| 3 | `notch_model.py` + Track H judge + ref solution | `judge_selftest.sh` H: ref PASS, all broken FAIL |
| 4 | `pid_ref.v` + Track B judge + ref solution | selftest B passes; pid_ref simulates with no X |
| 5 | Track C patches + scorer | applying all patches compiles; scorer gives 10/10 on answer key itself |
| 6 | `run_demo.sh` all tracks end-to-end with gemma4-e4b | each track produces runs/ dir, judge.json, report.md (judge FAIL is acceptable) |
| 7 | Report visuals | plots readable by non-engineers (plain titles, one message each) |
| 8 | Phase-2 checklist `PORTING.md` | lists exactly what changes for .126 (env.yaml only + vivado path) |

Work in this order; do not start a later milestone before the earlier acceptance passes.

---

## 10. Notes / pitfalls
- iverilog may reject zero-width replication `{0{...}}` present in the original PID (`IBW-16-ISR = 0`). If so, fix only in `pid_ref.v` in a behavior-preserving way and document it.
- Track H recursion must close in one cycle at 125 MHz — a known hard point; the judge does not require timing on the laptop.
- Keep every judge deterministic (fixed seeds); log seeds in judge.json.
- Never let the agent see `harness/`. Never let judge stimuli leak into workspace.
- All outputs must be reproducible with `run_demo.sh` alone.
