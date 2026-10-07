# Beli Review

A local workshop for repairing your Beli rankings in small, guided sessions.
Import an export, assign broad quality bands, compare places you remember, and
review the difference before deciding what to change in Beli.

## Run locally

Requires Python 3.10+ and Node.js 20.19+ (or 22.12+). Node is needed to install and
build the frontend; the running app uses Python's standard library and SQLite.

```bash
python3 run.py
```

First launch installs locked frontend dependencies and builds the app. Open
[http://127.0.0.1:8765](http://127.0.0.1:8765). Subsequent launches reuse the build
unless source files changed. Stop the server with Ctrl+C and run the same command
when you want to return.

The server listens only on this computer. No Beli login is needed to review an
existing export. The app does not change your Beli account.

## Your first session

1. In **Imports & backups**, choose an `export.json` or an available local export
   folder. Review the preview and import it.
2. Select a Beli category. In **Your places**, assign a few broad quality bands and
   open places you remember well to mark them as references. Bands are editable;
   assigned bands appear first, followed by unassigned places in their prior order.
3. Start a short **Guided review** session. Normal sessions cover different places,
   avoid recent opponents, and use your reference places when available.
   **Review this place** runs a focused session for one placement instead. Each
   answer is saved, and the screen explains why the next pair was selected.
4. Review and accept the proposal. Answers are durable before acceptance; your
   accepted working order changes only when you accept the session. Band edits
   and manual moves are separate saved actions.
5. Use **Before & after** to compare with the original export, latest Beli export,
   current session, or a saved checkpoint. You can revisit an earlier comparison.
   Pure additions/removals do not label unchanged survivors as reordered.

Use **Back** to return to the previous screen and **Previous answer** to undo
your most recent comparison. If another edit followed that answer, undo that edit
first using the toolbar.

The toolbar’s moon/sun button toggles dark mode. It initially follows your system
preference and remembers an explicit selection in this browser.

Comparison shortcuts: **1** prefer left, **2** prefer right, **3** about equal,
**4** don't remember, **5** skip. Shortcuts do not fire while typing into fields.

A compared placement is **provisional**; **Looks right** explicitly confirms a
place. Equal and uncertain answers do not create strict preferences. Contradictory
preferences prompt you to keep the older decisions or supersede them.

## Cleanup and newer exports

**Cleanup** has separate filters for missing notes, missing photos, empty photo
captions, manual attention flags, and **Need to delete**. The deletion box excludes
places from comparisons without deleting their content. Restore them whenever you
want. It does not issue a deletion to Beli.

Keep using Beli normally. When you export again, import the new file here:

- Places are matched by account, business ID, and category, not their names.
- New places enter a review inbox; existing local order and decisions survive.
- New source notes/photos replace the source view. Missing older attachments stay
  accessible as historical content in the detail card.
- Source order changes update the latest baseline without replacing your work.
- Missing places and possible category transfers are flagged for review.
- Identical imports are recognized. Older exports are archived without replacing
  the latest source. An undone import can be recovered with Redo.

Images load from Beli's existing image URLs, with a fallback display when
unavailable. Text, captions, rankings, and review work function offline. Image
caching and direct Beli synchronization are not implemented.

## Saving and backups

Every edit is committed to `data/workshop.sqlite3` before the UI reports **Saved
locally**. Sessions, comparisons, flags, persistent undo/redo, immutable source
snapshots, and checkpoints live in that database. Browser storage is not required.
Revision checks prevent stale tabs from silently replacing newer decisions.

Use **Download workspace backup** for a consistent SQLite backup, including source
exports and review history. Photo image files are not included. Restore a backup
through the same screen; a recovery copy of the current workspace is saved under
`data/workshop-backups/` before replacement.

To run a separate workspace or choose a different port:

```bash
python3 run.py --db /absolute/path/to/another-workspace.sqlite3 --port 8766
```

Personal exports, databases, and the local handoff are ignored by Git. Do not put
exports elsewhere in the repository or commit backups. The implementation plan
is in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Development and validation

```bash
npm ci
npm run build
npm test
python3 -m unittest -v test_export.py
```

For frontend hot reload, run `python3 run.py --no-build` in one terminal and
`npm run dev` in another. Vite proxies API requests to port 8765. A build is needed
before serving the app directly through the Python server.

Frontend tests require Node.js 22.6+ for built-in TypeScript stripping.

The automated tests use temporary databases and synthetic exports. They cover
transactional state changes, account validation, repeat imports, partial exports,
category transfers, session resumption, conflict handling, retained content,
undo/redo, backups, stale revisions, and the local-only HTTP boundary.

## Create a Beli export

The existing read-only scripts remain independent of the web app:

```bash
python3 export_all.py
```

Log in through the terminal's hidden password prompt. Credentials and tokens stay
in memory. Exports go to a fresh `data/export-*/` directory containing `export.json`,
`report.json`, and raw responses. The exporter only permits allowlisted read routes
and the login request; it does not change rankings.

For a one-category, one-place diagnostic run:

```bash
python3 probe.py
```

The integration uses an unofficial API. Verify category totals and sample records
against Beli. Response position is retained as the imported baseline, and ties
are preserved; exact Beli score/reordering mechanics have not been established.

References: [observed API](https://github.com/ProjectBarks/beli-api) and
[endpoint reference](https://github.com/ProjectBarks/beli-api/blob/main/reference/beli-api-reference.md).
