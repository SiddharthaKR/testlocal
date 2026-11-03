# Rules for the agent

1. Work only inside this directory (the workspace).
2. Never claim something works without running the relevant tool and showing its output.
3. Do not change existing module ports, parameters or register maps unless the task says so.
4. Do not write `AGENT_REPORT.md` until your own test passes or you have made at least 5 fix attempts.
   (Review-only tasks have no test: write the requested output file first, then the report.)
5. Finish by writing `AGENT_REPORT.md`: what you did, why, evidence (tool outputs), and remaining issues.

Tools (in `tools/`): `run_sim.sh`, `plot_wave.py`, `run_synth.sh`, `run_impl.sh`. Each prints a short summary and writes full logs to a folder. Read the logs only if the summary is not enough; your context is limited.
