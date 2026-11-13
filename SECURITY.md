# Security policy

> **Where this applies.** This policy applies to the project's one official, write-enabled repository, which
> exists only on GitLab: <https://gitlab.com/Tyler-Meador/civ-v-linux-mcp>. Reports are taken there and
> nowhere else. The GitHub repository is a read-only mirror kept for visibility; issues, pull requests and
> private vulnerability reporting are not in use there, and a report made on GitHub is not seen.

## Supported versions

Only the latest release on `main` is supported. A fix ships as a new release; older versions are not
patched.

| Version | Supported |
| --- | --- |
| Latest release ([`CHANGELOG.md`](CHANGELOG.md)) | Yes |
| Anything older | No |

## Reporting a vulnerability

**Do not open a public issue.** Open a **confidential issue** on GitLab instead:

<https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/new?issue[confidential]=true>

Check that "This issue is confidential" is ticked before you submit. A
[confidential issue](https://docs.gitlab.com/user/project/issues/confidential_issues/) is visible only to
you and to the project's members.

Please include:

- the package version (`pyproject.toml`) and the Lua runtime version, or the commit;
- how the harness was run: solo or several seats, with or without a seat table (`--seats`), which MCP client;
- the steps, and what an attacker gains;
- no live tokens: describe where a secret leaks instead of pasting it.

This is a spare-time project with one maintainer, so there is no guaranteed response time. You will get an
answer on the issue, the fix is noted in the changelog, and you are credited there if you want to be.

## What counts

- A seat reading or changing another seat's game through a daemon that runs with a seat table.
- A seat token written to a log, a tool reply, the call ledger or the spectator page.
- A tool reply or order that lets the model behind a seat run raw Lua while that is switched off, or reach
  outside the game: files, commands, the network.
- The spectator server serving files outside its web directory, or accepting anything that changes the game.
- A secret committed to the repository.

A seat merely *seeing more than a human player would* (a fogged unit, an unmet civilization) is a fair-play
bug rather than a vulnerability: file it as an ordinary issue.

## Known properties, not vulnerabilities

These are how the game and the harness work. Plan around them rather than report them.

- **The game's tuner port has no authentication.** With `EnableTuner = 1` the game listens on TCP port 4318
  on every interface, and whoever connects can run Lua inside the game. That is the game's own debug
  interface, not the harness's. Run it on a network you trust, or firewall the port.
- **Without a seat table the daemon trusts every local client.** `harness.tunerd` started without `--seats`
  lets any process that can open its Unix socket run any Lua in the game. Use a seat table when the agents
  at the table should not be able to reach each other's seats, and keep the table file private (`chmod 600`).
- **The spectator page has no login.** It binds to `127.0.0.1` by default; `--host` on another address shows
  the game to everyone who can reach it.
- **The agent is whatever you connect.** The harness limits what a seat can do in the game; it does not
  sandbox the MCP client or the model you run.

Vulnerabilities in Civilization V itself belong with its publisher, not here.
