"""Constants shared by all judges (Track H notch, Track B pid_equiv)."""

# Output samples ignored after rstn_i is released. PyRPL's PID out_buffer has
# no reset (see harness/tasks/B/KNOWN_ISSUES.md K5), so dat_o is X at first.
SETTLE_CYCLES = 8

# Fixed seed so every judge run is deterministic; logged in judge.json.
DEFAULT_SEED = 20261103

# Marker present in every hidden judge/solution file. The leak check flags any
# run whose LLM traffic contains it (or a hidden path name).
CANARY = "CANARY-b81aed453118"
LEAK_MARKERS = [CANARY, "ref_solutions", "harness/judge", "harness\\judge","tb_notch_judge",
                "tb_pid_equiv", "gen_stimuli", "make_broken", "judge_selftest", "answer_key", "bughunt"]
