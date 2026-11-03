# PORTING: office server (.126, LM Studio + Gemma 4 26B-A4B)

Only `config/env.yaml` changes between machines. Do these steps in order.

## 1. Prerequisites on the server
- Python 3 with `numpy matplotlib pyyaml`
- iverilog 12 (`iverilog` and `vvp` on PATH, or set `iverilog_dir`)
- opencode (same major version as tested: v2.1.x)
- Vivado (optional; without it synthesis/timing print `SKIPPED (no vivado)`)
- LM Studio serving Gemma 4 26B-A4B through its OpenAI-compatible endpoint

## 2. Get the code and PyRPL
```bash
git clone https://github.com/SiddharthaKR/testlocal.git ai_demo && cd ai_demo
bash harness/setup_vendor.sh
```
This clones PyRPL into `vendor/pyrpl`, checks out `pyrpl_commit`, tags it `demo-baseline`, makes it read-only, and runs `check_vendor.sh`.
- It needs access to github.com. Without it, point it at a mirror: `PYRPL_URL=<git url> bash harness/setup_vendor.sh`.
- It is safe to rerun: a missing or half-cloned `vendor/pyrpl` is cloned again. On Windows it enables long paths, because some PyRPL notebook paths exceed Windows' path limit.

## 3. Edit `config/env.yaml` (fill in every TODO)
- `upstream_url`: the LM Studio endpoint, e.g. `http://<host>:1234/v1`
- `model`: the exact LM Studio model id (check `curl <upstream_url>/models`)
- `context_limit`: the context length LM Studio loads the model with. **It must match**: opencode compacts history at this size; a mismatch means silent truncation.
- `python_cmd: python3`, `iverilog_dir: auto`, `vivado: auto` (or a path)
- `fpga_part` if the board is a Z20 (`xc7z020clg400-1`)

`config/opencode.json` is generated from env.yaml on every run. Do not edit it.

To use the laptop/Ollama setup instead: `cp config/env.laptop.yaml config/env.yaml`. It uses `python_cmd: py` and `iverilog_dir: /c/iverilog/bin`.

## 4. Validate the judges (mandatory before any agent run)
```bash
bash harness/judge/judge_selftest.sh all
```
Expected: `SELFTEST: OK`. Every reference solution passes and every broken variant fails.

## 5. Track B baseline (needs Vivado)
On the Vivado machine, measure the original PID and set the target:
```bash
mkdir -p /tmp/b && cd /tmp/b
TOOLS=<repo>/harness/tools; RTL=<repo>/vendor/pyrpl/pyrpl/fpga/rtl
bash $TOOLS/run_impl.sh red_pitaya_pid_block 8.0 <repo>/harness/tasks/B/pid_ref.v $RTL/red_pitaya_filter_block.v $RTL/red_pitaya_lpf_block.v
```
Copy LUT/FF/DSP/WNS/Fmax from `impl.json` into `harness/tasks/B/baseline.json`, set `"status": "MEASURED"`, and set `T_target_ns = 1000 / (1.3 * Fmax_MHz)` so the baseline fails timing. (The tools read `tool_env.sh`; if it is missing, run once via `run_demo.sh --setup-only` and copy `tools/tool_env.sh` from the workspace.)

## 6. Run the demo
```bash
bash harness/run_demo.sh --track H            # notch filter (hero)
bash harness/run_demo.sh --track H --assist   # same, with a skeleton (marked ASSISTED, never counted)
bash harness/run_demo.sh --track B            # PID optimization
bash harness/run_demo.sh --track C            # bug hunt
bash harness/run_demo.sh --track H --interactive   # opencode TUI, for recording
```
Results: `runs/<ts>_<track>/report.html`; `runs/summary.html` across runs (real runs only, pass rate and medians).
Fill `config/engineer_estimates.yaml` to get the agent-vs-engineer time chart.

## Notes
- Runs whose model is not Gemma are marked PLUMBING TEST and excluded from the summary.
- The agent's workspace is `workspace_dir` (outside the repo). Never paste judge files into the agent's session.
- `agent_timeout_min` caps each agent run (default 40).
- Optional, not built: full-bitstream integration of the notch in slot 2 (PID2) via `harness/integration/red_pitaya_dsp_notch.v` with a wrapper tying off `sync_i`/`diff_dat_i`/`diff_dat_o`. Never edit `vendor/`.
