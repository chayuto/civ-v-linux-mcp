# Contributing

> **Where this applies.** This guide applies to the project's one official, write-enabled repository, which
> exists only on GitLab: <https://gitlab.com/Tyler-Meador/civ-v-linux-mcp>. Issues, merge requests and
> milestones live there and nowhere else. The GitHub repository is a read-only mirror kept for visibility;
> issues and pull requests are switched off there, and a change proposed anywhere but GitLab is not seen.

Thank you for looking. This is a small project with one maintainer; the notes below are what makes a
report or a change easy to take.

## Ways to help

- **Report what a game showed you.** Most fixes in the changelog began as a play test: a reply that named
  nobody, a refusal that gave the wrong reason, an order the game's own screen would not have offered.
  [Open an issue](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/new) with the "Bug" template.
- **Propose a change** with the "Proposal" template before writing anything larger than a fix, so the design
  is agreed before the code exists.
- **Send a fix** as a merge request on GitLab (below).
- **Correct the documentation.** A stale number or a command that no longer works is a bug.

Security problems do not go in a public issue: see [`SECURITY.md`](SECURITY.md).

## The rules a change has to keep

These are the project's design, not preferences. A change that breaks one is declined however well it works.

- **A seat sees what a human in that seat sees, and no more.** No fogged units, no unmet civilizations, no
  AI plans, nothing about another seat's activity beyond what the game's own screens show. See "Fair play" in
  the [README](README.md), "The information boundary" in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
  [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).
- **Refusals mirror the UI.** If the stock game would not let a player click it, the harness refuses it and
  says why. The engine accepts many orders the UI never offers; the guard belongs in the harness.
- **No back door.** Nothing may hand a seat raw Lua, or widen what the nine tools reach, by default.
- **Replies say what can be done.** A reply that lists options carries the complete call for each.

## Setting up

```bash
sudo apt install lua5.4 liblua5.4-0   # luac for the runtime lint, liblua for the Lua tests
uv sync --group dev
scripts/check.sh                      # the whole suite; no game needed
```

Without `uv`, the venv route in [`docs/AGENT_INSTALL.md`](docs/AGENT_INSTALL.md) works too. To run against the
game you need your own copy of Civilization V with Brave New World, as the native Linux build.

## Tests

- `scripts/check.sh` must pass: the linter, the suite, then the nine-tool tests a second time with the old
  names switched off. The project runs **no CI pipeline**, on purpose, so the run on your machine is the
  only one before review. Say in the merge request that it passed and how many tests ran.
- A change comes with a test. The Lua runtime is tested as shipped, under `lupa`, against fake game objects;
  the Python layer against fake bridges. `tests/` has an example for every domain.
- Tests state the design. If a correct change breaks a test, change the test and say why.

## The Lua runtime

Everything the harness does inside the game is an `H.*` function under `harness/lua/runtime/`, one file per
game domain; [`harness/lua/runtime/README.md`](harness/lua/runtime/README.md) says which file owns what.
Any change to any of those files **bumps `RUNTIME_VERSION`** in `bootstrap.lua`, and the commit subject
carries it as `runtime vNNN`: a running game keeps the old runtime until a newer number arrives.

## Checked live, or not

The suite cannot tell you what the game does. Say in the merge request which of these is true:

- **Checked live**: against a running game, with the turn and what you saw.
- **Not checked live**: tests only. That is fine; the maintainer reads every change back in a real game
  before it is released, and it helps to know which ones still need it.

Take care with a game you want to keep. Engine calls the stock UI never makes have crashed the game process
more than once; copy your save first, and never send an untried `GAMEMESSAGE_*` or task enum to it.

## Merge requests

1. Fork on GitLab and branch from `main`.
2. One change per merge request, with its test.
3. Add a line under "Unreleased" in [`CHANGELOG.md`](CHANGELOG.md): what a seat or a host now sees, in a
   sentence a player would understand.
4. Fill in the merge request template and tick
   [Allow commits from members who can merge](https://docs.gitlab.com/user/project/merge_requests/allow_collaboration/).

The maintainer may land a change by cherry-pick rather than by the merge button, and may adjust it first.

### Work written with an AI model

This project was itself written by Claude under a human's direction (see "Authorship" in the README), and
contributions made the same way are welcome. The bar does not move: you ran `scripts/check.sh`, you read
the diff, and you say honestly what was and was not checked against the game.

## What must not be committed

The repository is public, and a pushed commit cannot be quietly taken back.

- No tokens, seat tables (`harness/seats.json`, `harness/tunerd-seats.json`), `.env` files or personal paths.
- No game assets. Short quotes of the stock UI Lua in `docs/` are there to document behaviour; the game
  belongs to Firaxis Games and Take-Two Interactive.

## Licence

The project is [MIT](LICENSE) licensed. By contributing you agree that your contribution is offered under
the same licence, and that you have the right to offer it.

## Conduct

Everyone taking part is expected to follow the [code of conduct](CODE_OF_CONDUCT.md).
