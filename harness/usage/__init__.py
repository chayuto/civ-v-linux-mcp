"""Token accounting, operator-side (docs/TOKEN_ACCOUNTING.md; GitLab milestone 2.15.0, #184).

An MCP server never sees what a request cost the model: the provider reports usage to the client, and the client
writes it to its own files. The readers here turn those files into one row per model request, the same shape for
every client (`rows.row`), and `join` places each request in a game turn by matching its calls to the call ledger.

    from harness.usage import claude_code, codex, grok, join, rows
    usage = claude_code.read(open(transcript))      # or codex.read(rollout), grok.read(stream)
    rows.total(usage)                                # {"requests": 68, "new_in": ..., "cache_read": ..., ...}
    placed, groups = join.place(usage, join.ledger_of(ledger_rows, "codex/gpt-6.1-sol"))
    join.per_turn(placed)                            # the same total, per turn, plus `fixed`

`report` reads whole directories of those files for `scripts/ledger_report.py --usage`, and `prices` puts a list
price on a row where the model has one (`prices.json`, dated; an estimate of tokens spent, never money paid).

Nothing in this package is imported by the server, and nothing it produces reaches a tool reply: a seat never
reads its own spend or another seat's. A reader takes counts, ids, tool names and times and no text.
"""
