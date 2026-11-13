<!--
This is the project's one official, write-enabled repository. CONTRIBUTING.md has the rules.
-->

## What this changes

<!-- What a seat or a host now sees, in a sentence a player would understand. Link the issue. -->

## How it was checked

- [ ] `scripts/check.sh` passed (tests run: ...)
- [ ] Checked live against a running game (turn ..., what was seen), **or** not checked live: tests only

## Checklist

- [ ] One change, with its test
- [ ] A seat still sees only what a human in that seat sees; refusals still mirror the UI
- [ ] `RUNTIME_VERSION` bumped if anything under `harness/lua/runtime/` changed (`runtime vNNN` in the subject)
- [ ] A line under "Unreleased" in `CHANGELOG.md`
- [ ] No tokens, seat tables, personal paths or game assets
- [ ] "Allow commits from members who can merge" is ticked
