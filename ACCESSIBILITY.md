# Accessibility

> **Where this applies.** This statement applies to the project's one official, write-enabled repository,
> which exists only on GitLab: <https://gitlab.com/Tyler-Meador/civ-v-linux-mcp>. Accessibility problems are
> reported there. The GitHub repository is a read-only mirror kept for visibility; issues and pull requests
> are switched off there.

**This file is voluntary.** An accessibility statement is an optional item on GitHub's community standards
list, and nothing obliges this project to publish one: it is a command-line harness and an MCP server run on
your own machine, with no hosted website, no service and no accounts. We publish one anyway, for two reasons.
A person who meets a barrier should know where to say so and what to expect. And a short, true account of
where the project stands is more useful than no account, or a promise nobody has tested.

So this document makes **no claim of conformance** with WCAG or any other standard. Nothing here has been
audited. It follows the layout of the
[Accessibility Toolkit template](https://github.com/open-source-accessibility/accessibility-toolkit/blob/main/ACCESSIBILITY.md),
and where that template asks for a commitment the project cannot keep, the section says so.

## Priorities

There is no formal accessibility target. What the project does aim for:

- **Text first.** Everything a seat reads and sends is structured text (JSON over standard input and
  output). No part of playing through the harness needs a pointer, a colour or a sound.
- **Readable documentation.** Plain language, descriptive link text, and a text alternative for images.
- **No new barriers.** A change should not make the one web page (the optional spectator view, `web/viz/`)
  harder to use than it is today.

## Contributor expectations

The project has no CI pipeline and no automated accessibility checks, so these are asked of the author:

- **Documentation**
  - Keep headings in order and use real lists and tables with header rows.
  - Give an image a meaningful text alternative, and a diagram a description nearby.
  - Write link text that says where the link goes.
- **The spectator page**
  - Do not add meaning that only colour or only motion carries; if you must, add a second cue.
  - Any new control must work from the keyboard and show where the focus is.
  - Say in the merge request what you tried: keyboard only, a screen reader, a zoomed page.
- **Tool replies**
  - Keep them text. A reply that points at a picture or a screen position alone is a bug.

## Reporting accessibility issues

If something here shuts you out, please say so. A report is treated as a bug.

1. [Open an issue on GitLab](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/new). There is no
   separate accessibility template; the "Bug" template or a blank issue both work.
2. Include, when you can:
   - what you were trying to do and what stopped you;
   - the file, page or command;
   - your operating system, terminal or browser, and assistive technology;
   - a screenshot or recording, only if you are comfortable sharing one.

You never need to disclose a diagnosis or anything else about yourself.

### Severity

The maintainer assigns one of these when reading the report; you do not have to.

- **Critical:** you cannot complete a core task at all, such as installing the harness or reading a reply.
- **Serious:** the task is possible only with real difficulty or a workaround.
- **Moderate:** an annoyance or an inconsistent experience.
- **Minor:** little effect on use.

### How we respond

- The report is answered on the issue, respectfully, and without asking for personal information.
- The answer says what happens next, what is a known limit, and what depends on something outside the
  project (the game, your MCP client, your terminal).
- Where a workaround exists, it is given while the fix is open.
- You may be asked to confirm that a fix removes the barrier before the issue is closed.

### Resolution expectations

**There are no fixed timelines.** This is a spare-time project with one maintainer, and the 30, 60 and 90
day targets the template suggests would be a promise it cannot keep. Critical and serious barriers are
taken before other accessibility work; the issue is where progress, or the lack of it, is recorded.

## Ownership and maintenance

Accessibility is owned by the project's maintainer, Ty Meador
([@Tyler-Meador](https://gitlab.com/Tyler-Meador) on GitLab), who triages reports, keeps the limits below
current and reviews this file when a release changes the spectator page or the documentation's layout.

## Supported environments

Nothing has been tested with assistive technology, so nothing is listed as supported.

- **The harness and its tools:** Linux, in a terminal, through an MCP client. How their text reaches you
  depends on that client and terminal, which are not part of this project.
- **The spectator page:** developed against a current desktop Chrome. Not tested with VoiceOver, NVDA,
  JAWS, Orca or on mobile.
- **The documentation:** Markdown, read through GitLab's or GitHub's own rendering.
- **The game:** Civilization V's screens, sounds and controls belong to its publisher, and the harness
  changes none of them. A host still needs the game window on a display to set a game up.

## Known limitations

- **The spectator view is visual only.** The map is a single canvas with a generic label and no text
  alternative for what it shows. The same information is in the call ledger it is drawn from;
  `scripts/ledger_report.py` prints it as a table.
- **Its token counts are a table, their detail is hover-only.** The Tokens section is a table with row and
  column headers, but what a figure is made of (new input, cache reads, thinking) and the note on the price
  estimate are `title` texts a keyboard does not reach. `scripts/ledger_report.py --usage` prints the same
  counts in full.
- **Colour carries meaning there.** Each seat's attention and actions are told apart by colour alone, and
  the palette has not been checked for colour-vision deficiencies or contrast.
- **It animates.** Plots pulse as a seat reads them, and the page does not honour the browser's
  reduced-motion setting.
- **Its keyboard support is partial.** The replay scrubber answers Space (play or pause), Left and Right
  (previous and next turn), Home (start) and End (live). The rest of the page has not been tried with a
  keyboard alone.
- **Tool replies are dense.** They are written for a language model, with long lines and nested data, and
  have not been reviewed for people reading them directly with assistive technology.
- **The documentation** gives the README's image a text alternative; its heading order, tables and long
  lines have not been reviewed with a screen reader.

## Feedback

Suggestions for this statement or for the project's practice are welcome as an issue or a merge request on
GitLab. An active barrier goes through the reporting steps above.

Last reviewed: 2026-11-13.
