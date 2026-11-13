# Accessibility statement

> **Where this applies.** This statement applies to the project's one official, write-enabled repository,
> which exists only on GitLab: <https://gitlab.com/Tyler-Meador/civ-v-linux-mcp>. Accessibility problems are
> reported there. The GitHub repository is a read-only mirror kept for visibility; issues and pull requests
> are switched off there.

This is an honest account of where the project stands, not a claim of conformance. **Nothing here has been
audited against WCAG or any other standard.**

## What the project is

- **A command-line harness and an MCP server.** Everything a seat reads and sends is structured text (JSON
  over standard input and output). How that text reaches a person depends on the MCP client and terminal
  you use, which are not part of this project.
- **Documentation in Markdown**, read through GitLab's or GitHub's own page rendering.
- **One web page**, the optional spectator view (`web/viz/`, see
  [`docs/VISUALIZATION.md`](docs/VISUALIZATION.md)).
- **The game is not ours.** Civilization V's own screens, sounds and controls belong to its publisher, and
  the harness changes none of them. A host still needs the game window on a display to set a game up.

## Known limits

- **The spectator view is visual only.** The map is a single canvas with a generic label; there is no text
  alternative for what it shows. The same information is in the call ledger it is drawn from
  (`scripts/ledger_report.py` prints it as a table).
- **Colour carries meaning there.** Each seat's attention and actions are told apart by colour alone, and
  the palette has not been checked for colour-vision deficiencies or contrast.
- **It animates.** Plots pulse as a seat reads them, and the page does not yet honour the browser's
  reduced-motion setting.
- **Its keyboard support is partial.** The replay scrubber answers Space (play or pause), Left and Right
  (previous and next turn), Home (start) and End (live). The rest of the page has not been tested with a
  keyboard alone or with a screen reader.
- **Tool replies are dense.** They are written for a language model to read, with long lines and nested
  data, and have not been reviewed for people reading them directly with assistive technology.
- **The documentation** gives the README's image a text alternative; its heading order, tables and long
  lines have not been reviewed with a screen reader.

## Reporting a barrier

If something here shuts you out, [open an issue on GitLab](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/new)
and say what you were trying to do, what you used (browser, terminal, assistive technology) and what
stopped you. Accessibility reports are treated as bugs. This is a spare-time project with one maintainer,
so there is no guaranteed response time.

Last reviewed: 2026-11-13.
