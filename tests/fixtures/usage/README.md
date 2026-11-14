# Usage fixtures

Real client files, cut down to numbers by `scripts/cut_usage_fixture.py` (the commands are in its docstring).
They hold token counts, times, model names, civ5 tool names and renumbered ids. They hold no prompt, reply or
thought: `tests/test_usage_readers.py` fails on any key the script does not write and on any string longer than
one word. A cut call ledger keeps of each row its time, seat, label, kind, sizes, `ok` and turn.

| File | Cut from | What it is |
|---|---|---|
| `claude-code-transcript.jsonl` | a Claude Code 2.1.319 session of 2026-11-13 | 68 requests on 138 rows, 9 civ5 calls, the session's own total |
| `codex-rollout.jsonl` | the rollout of night cycle 41 (2026-09-27), Codex CLI 0.157.1 | 107 responses, 72 civ5 calls made from 70 scripts (a script's row keeps its time and nothing else) |
| `codex-exec.jsonl` | the same cycle's `codex exec --json` stream (`logs/night/codex-c41.jsonl`) | the 72 calls and one total, equal to the rollout's |
| `grok-stream.jsonl` | night cycle 1 (`logs/night/grok-c1.jsonl`), Grok CLI 1.0.41 | 78 responses, 108 civ5 calls, no time on any event |
| `cycles/` | one seat-loop cycle of each agent, one turn each, live on 2026-11-13 (Maya game, t242) | each agent's stamped stream between the loop's two rows; the record the loop kept beside it (`claude-c1.transcript.jsonl`, `codex-c1.rollout.jsonl`; Grok's stream is its own record); `calls.jsonl`, the 41 ledger rows of the three cycles (6, 23, 12) |
| `session/` | a Codex session of 2026-10-29 outside the seat loop (Codex CLI 0.166.0), and the ledger of the same hour | 68 responses, 69 civ5 calls, 69 ledger rows over eleven turns (t26 to t38) |

Do not edit them by hand. When a client changes its format, cut again from a new file and update the totals in
the test from the client's own total row.
