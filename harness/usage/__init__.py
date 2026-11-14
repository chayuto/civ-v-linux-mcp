"""Token accounting, operator-side (docs/TOKEN_ACCOUNTING.md; GitLab milestone 2.15.0, #184).

An MCP server never sees what a request cost the model: the provider reports usage to the client, and the client
writes it to its own files. The readers here turn those files into one row per model request, the same shape for
every client (`rows.row`), so that a later stage can join them to the call ledger by time.

    from harness.usage import claude_code, codex, grok, rows
    usage = claude_code.read(open(transcript))      # or codex.read(rollout), grok.read(stream)
    rows.total(usage)                                # {"requests": 68, "new_in": ..., "cache_read": ..., ...}

Nothing in this package is imported by the server, and nothing it produces reaches a tool reply: a seat never
reads its own spend or another seat's. A reader takes counts, ids, tool names and times and no text.
"""
