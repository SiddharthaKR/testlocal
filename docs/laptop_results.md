# Laptop results: Gemma 4 E4B (Ollama), 32k vs 64k context

Run on 2026-11-04 with the same rules for both batches: opencode compaction limit set from `context_limit`, and the AGENTS.md rule "do not write the report until your test passes or after 5 fix attempts". Each run is a new opencode session in a fresh workspace, with no human hints.

| label | track | result | steps | tool calls | compile fail/fix/final ok | truncation | compaction | peak ctx % | gen tok/s | prompt tok/s | agent min |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 32k | C | found 0/10, FP 0 | 15 | 2 | 0/0/n/a | no | yes @6,7,8,9,10,11,12,13,14,15 | 60.3% | 87.4 | 2573.1 | 4.6 |
| 32k | H | FAIL | 43 | 11 | 2/0/FAIL | yes @33 | yes @7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43 | 52.6% | 92.9 | 5192.2 | 7.0 |
| 32k | H+assist | COMPILE_ERROR | 58 | 7 | 1/0/FAIL | yes @17,33,43,51,57 | yes @7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58 | 51.1% | 97.9 | 5514.7 | 12.5 |
| 32k | B | PASS | 14 | 7 | 0/0/n/a | yes @8 | yes @8,9,10,11,12,13,14 | 51.2% | 102.8 | 4765.0 | 2.3 |
| 64k | C | found 3/10, FP 0 | 10 | 9 | 0/0/n/a | no | no | 51.8% | 84.9 | 3485.9 | 2.1 |
| 64k | H | COMPILE_ERROR | 17 | 16 | 4/0/FAIL | no | no | 46.8% | 93.2 | 7360.1 | 4.0 |
| 64k | H+assist | FAIL | 24 | 24 | 7/0/FAIL | no | no | 49.1% | 90.8 | 8615.1 | 5.2 |
| 64k | B | COMPILE_ERROR | 15 | 14 | 0/0/n/a | no | no | 35.1% | 99.2 | 7233.3 | 2.4 |


## Reading the table
- **Results:** the small model mostly fails, as expected. One improvement since the first runs: the 32k H run and the 64k H+assist run now **compile**. They fail on the numbers, not on syntax.
- **Bug hunt (C):** 64k found 3/10 with no false alarms, the best result so far. 32k scored 0/10 because the agent took the report rule literally: a review task has no test, so it wrote no `bugs.json`. The rule has since been scoped to tasks that have a test.
- **B "PASS" at 32k is a rename only** (`error` → `error_reg`): equivalent, but not an optimization. Without Vivado, B can only show "kept the same behaviour".
- **Compaction:** with the limit set, opencode keeps 32k sessions at about 50–60% of the window by pruning history on almost every step, so the 32k agents ran longer (up to 58 steps). At 64k it never needed to.
- **Truncation:** the "truncation" flags at 32k are a heuristic (the prompt shrank while the request body grew). With peaks at 51–60%, Ollama could not have cut anything, so these reflect opencode pruning. The silent Ollama truncation seen before the limit was set (peaks of 99.5%) is gone.
- **Speed:** generation is about 85–100 tokens/s at both sizes. 64k is not slower on this laptop's RTX 5060 (8 GB).
- **Before the limit was set** (archived 32k runs): peaks were 76–99.5% of context, with confirmed silent truncation in Track C.

## Where the context goes
In the largest request of each run: opencode's own system prompt and tool definitions take 34–48%. The rest is whole-file reads (350-line modules, sometimes read twice) and full-file rewrites. No harness tool output exceeds 40 lines.

Possible follow-up: tell the agent in AGENTS.md to read line ranges and use edit instead of rewriting whole files.
