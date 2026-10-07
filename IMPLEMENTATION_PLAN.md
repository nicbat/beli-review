# Local Beli ranking workshop — implementation plan

Updated: 2026-10-06 (America/Los_Angeles).

Status: phases 1–4 have been implemented as a first local release. This document
preserves the original design and build plan; `README.md` describes current usage.

Implemented: React/TypeScript UI, Python/SQLite backend, category bands, focused
comparison sessions (varied by default, focused when explicitly requested), reference
selection, provisional ordering, conflict review,
cleanup and deletion queues, original/latest/session/checkpoint diffs, repeat
imports, persistent undo/redo, checkpoints, and downloadable/restorable backups.

Deliberate first-release limits: reference selection happens in place details;
comparison selection uses deterministic heuristics rather than a learned model;
imports show source-change summaries and retained content; photo caching and a
minimum-move Beli checklist remain optional follow-ups. There are no Beli writes.

Validation includes synthetic import/merge and persistence tests, HTTP backup and
origin checks, exporter regression tests, and browser checks against disposable
workspaces. Personal exports and the local `HANDOFF.md` are excluded from Git.

## 1. Objective and agreed scope

Build a web app that runs locally and helps repair the user's existing Beli
rankings through short, guided sessions. Preserve useful existing order instead
of requiring a complete reranking of all 601 places.

The app must support:

- Separate Beli categories: restaurants, coffee, bakeries, desserts, and bars.
- Broad, editable quality bands within each category, followed by targeted comparisons.
- Notes, photo captions, and available photos as memory prompts.
- Before/after review against both the original export and the latest Beli export.
- Automatic missing-information flags and manual attention flags.
- A reversible “Need to delete” box.
- Automatic local saving, persistent undo/history, and resumable sessions.
- Repeated imports of newer Beli exports without losing local work.

The user prefers guided comparisons over using a full-list editor as the main
interaction. A searchable list remains useful as a secondary inspection tool.
Dish-level lists are excluded.

“New item import” means a place added in the Beli app and subsequently received
in a newer export. It does not mean writing new places into Beli through the API.

## 2. Existing inputs and constraints

Read `HANDOFF.md` for exporter details and known limitations. Initial input:
`data/export-20261006-dmf2sdtp/export.json`, with its sibling `report.json` and raw
responses retained as provenance.

The current export contains 601 ranking entries, 483 note records, and 682 photo
records. Category counts are RES 307, COF 161, DES 83, BAK 38, and BAR 12.

Observed missing content among ranked places:

- 153 have no photo records.
- 123 have no nonempty written note.
- 117 have neither a written note nor photos.
- All existing photo records have nonempty captions.

Important constraints:

- Preserve API response position, full-precision score, and ranking value separately.
- API response order is a baseline, subject to verification against Beli; preserve ties.
- Local ordering does not imply a particular Beli numeric score. Do not generate
  purported new Beli scores from local ranks or quality bands.
- Photos are currently URLs and metadata, not downloaded image files.
- Explicit visit dates and ranking-creation dates are distinct; never substitute
  one for the other without labeling it.
- Keep top-level notes/photos even when they do not join to a ranked place.
- Export consistency checks do not independently prove completeness.

## 3. Proposed technical structure

Use a React + TypeScript frontend and a small Python HTTP backend with SQLite.
This fits the existing Python exporter while keeping the review UI interactive.
Exact framework and dependency versions should be checked when implementation starts.

Production-style local use should need one documented launch command. The Python
server serves the built frontend and local API on loopback. A separate frontend
development server is only for development. No hosted service or account login is
needed to review existing exports.

Proposed project layout:

```text
app/
  backend/         # HTTP routes, import service, persistence, review engine
  frontend/        # React UI
  tests/           # Import, persistence, review, and end-to-end tests
data/
  workshop.sqlite3
  workshop-media/  # Optional cached photos
  workshop-backups/
IMPLEMENTATION_PLAN.md
HANDOFF.md
```

Keep existing exporter scripts usable independently. Store personal state under
the already ignored `data/` directory, using private file permissions. Check
parent/project instructions before implementation; the folder currently is not
a Git repository, despite containing a `.gitignore` file.

## 4. Data model: imported evidence and local decisions

Keep three separate layers:

1. **Immutable import snapshots:** original payload, content hash, import time,
   export time, account identity, report warnings, and normalized source records.
2. **Working state:** local ordered lists, band assignments, reference places,
   flags, deletion candidates, and new/unresolved items.
3. **Decision history:** saved comparisons, accepted moves, session boundaries,
   checkpoints, and undo/redo records.

Use Beli business ID for place identity and `(account, business ID, category)`
for ranking membership. Ranking record IDs are provenance, not durable place keys.
Store notes and photos by their own IDs and business ID rather than duplicating
them per category.

Suggested entities:

- Import snapshots and per-snapshot ranking/content records.
- Businesses and category memberships.
- Working category order, ordered bands, and per-place review state.
- Comparisons with outcome, timestamp, session, active/superseded status, and
  optional reason.
- Manual flags and deletion candidates, including previous working position.
- Sessions with current prompt, queued work, and resume state.
- Revisioned operations and checkpoints containing enough state to restore.
- Import discrepancies awaiting resolution.

Review state must distinguish unreviewed, provisionally placed, user-reviewed,
uncertain, and excluded pending deletion. A derived rank alone is not evidence
that the user has confirmed a place's position.

## 5. Guided ranking workflow

### Establish bands and reference places

Start one Beli category at a time. Offer editable starter bands such as Favorites,
Very good, Good, and Disappointing, plus an unassigned/unsure queue. These labels
are a starting proposal, not fixed score ranges.

Ask the user to select a few memorable reference places across the range and
confirm their relative order. Do not automatically promote current high-ranked
places into trusted references.

Allow band assignment in small batches. Users can begin comparisons before
classifying the entire category; no 601-place onboarding requirement.

### Short comparison sessions

Default to five comparisons, with continue, stop, and resume actions. Each prompt
shows two places with city, written notes, photo captions, photos when available,
and explicitly labeled visit dates. Keep imported scores hidden by default during
judgment to reduce anchoring, with a reveal option.

Actions: prefer left, prefer right, about equal, don't remember, skip, flag missing
information, and move to Need to delete. All actions save immediately.

Choose comparisons in this priority order:

1. Resume unresolved work in the current session.
2. Place newly imported items relative to reviewed references.
3. Resolve explicit user flags and conflicting judgments.
4. Refine uncertain positions within a band and near band boundaries.

Start with a deterministic, understandable scheduling heuristic. Avoid a learned
ranking model in the first version. Store preference evidence separately from
the displayed total order. Preserve existing order where evidence is absent.

For insertion, narrow the candidate interval using confirmed references, then
check proposed neighbors. Binary-search-style narrowing is appropriate only
within an ordered reference set; do not treat the entire imported list as verified.
If evidence points outside the current band, propose a band change.

“About equal” records a pair-level judgment without inventing a strict preference
or assuming that all such judgments are transitively equivalent. Preserve current
display order when needed and label unresolved precision. “Don't remember” and
skip do not become preference votes.

Detect contradictory preference cycles. Present a small conflict review or allow
the user to supersede an older judgment; never silently discard decisions. Avoid
repeating settled questions unless new evidence or an explicit review calls for it.

### Session review

Answers and provisional changes persist throughout the session. At its end, show
proposed moves and band changes with accept, revise, or discard controls. Saving
an answer and accepting a proposed order are separate states, so a crash cannot
lose either the user's judgment or whether they accepted it.

## 6. Main screens

- **Home / Resume:** category progress, current session, new-item inbox, cleanup
  counts, and latest save/import status. Count reviewed places separately from
  comparisons answered.
- **Guided review:** two memory cards, clear choices, keyboard shortcuts, progress,
  undo, and save status.
- **Library:** searchable category list with bands and filters; place details and
  targeted “review this place” action. Direct relocation is a secondary tool.
- **Cleanup:** missing content, manual attention flags, and Need to delete.
- **Changes:** before/after order, session review, checkpoints, and history.
- **Imports / Backups:** import preview, discrepancy resolution, and recovery.

A category change must not discard a session. Keep the layout practical for a
desktop browser, with readable notes, clear focus states, and keyboard navigation.

## 7. Missing information and Need to delete

Compute separate flags for no photos, no written note, any existing photo missing
a caption, and neither note nor photos. A broken or unavailable image URL is a
different state from having no photo metadata.

Provide a combined “missing information” view with selectable filters. Also allow
a manual “needs attention” flag and an optional reason. Automatic flags refresh
when source content changes; manual flags persist until explicitly cleared.

Need to delete is a reversible local exclusion queue. Keep all imported content,
reason, and placement history. Exclude candidates from comparison scheduling and
the proposed retained ranking. Restoring a place should use its prior neighbors
when possible and request placement review if those neighbors changed.

Deletion candidates appear separately in before/after review. No Beli deletion
request occurs when placing an item in this box.

## 8. Repeated export import and merge

Support selecting an export JSON file, optionally with its report, and selecting
existing export folders through the local app. Validate schema, identity, duplicate
keys, and referenced records before modifying working state.

The import sequence:

1. Parse and validate; reject a different account for this workspace.
2. Detect an already imported payload by content hash and treat it as a no-op.
3. Compare against the latest chronological source snapshot, not the working list.
4. Preview additions, content updates, changed source rankings, missing entries,
   category changes, and coverage warnings.
5. Create a checkpoint and apply the accepted import in a database transaction.
6. Record a durable summary and queue unresolved differences.

Merge rules:

- **Existing place:** refresh source content while preserving bands, local order,
  comparisons, manual flags, and session progress.
- **New membership:** send to New since last import. Its Beli position is context,
  not an instruction to overwrite the repaired order. Insert after guided review.
- **Beli order changed:** update the latest-source baseline and show the difference;
  do not automatically replace local order, even if no local edit is obvious.
- **Missing membership:** flag source absence for review. Do not assume deletion
  or remove local work, especially when export coverage is uncertain.
- **Category changed:** retain the old membership's history and flag a possible
  transfer; comparisons from the old category do not automatically apply in the new one.
- **Notes/photos changed or missing:** keep historical snapshots. Show the latest
  source view when coverage is credible; mark uncertain absence instead of
  destroying previously available material.
- **Previously excluded place reappears:** preserve Need to delete status.
- **Older export:** allow archival import without replacing the latest baseline.

Keep suspended session prompts stable across imports. If a prompt's category or
eligibility becomes invalid, explain why it was requeued and retain prior answers.

## 9. Before/after review

Offer three baselines:

- Original export versus current working ranking.
- Latest Beli export versus current working ranking.
- Session/checkpoint start versus current working ranking.

Show old and proposed positions, old/new neighbors, band changes, and supporting
decisions. Distinguish explicitly moved items from passive position shifts caused
by another move. Show additions, unresolved items, and proposed deletions separately.
Do not imply that an imported Beli score is a recalculated local score.

A later enhancement can generate a manual Beli update checklist using stable
place names/IDs and neighboring anchors. Longest-common-subsequence/LIS analysis
can minimize remove-and-reinsert operations for unique retained items if Beli's
actual controls allow unrestricted relocation. This does not minimize UI effort.
Validate those controls before promising a minimum-action workflow.

## 10. Saving, undo, and recovery

Use SQLite as the durable source of truth, not browser local storage. Commit each
decision and its history record atomically, then acknowledge Saved in the UI.
Display Saving and Save failed states; do not report a successful save early.

Use operation IDs for retry deduplication and revision checks to prevent two tabs
from silently overwriting each other. Save the current session prompt and pending
review state alongside decisions.

Provide persistent undo/redo for user actions and named checkpoints. Imports have
their own pre-import recovery point. Restoring a checkpoint creates a new recorded
revision rather than deleting the audit trail.

Provide a downloadable, versioned backup containing the database and necessary
source snapshots, plus optional cached media. Use SQLite's backup mechanism for
consistent live backups. A backup preview should explain whether images are included.
Verify restoration into a fresh local workspace before declaring recovery complete.

## 11. Photo handling

Render existing URLs with useful loading/error states. Show captions even when
an image is unavailable. Offline text/ranking work must function without images.

As a follow-up, offer explicit local image caching with progress and retry. Verify
actual URL access first; downloading has not been tested. Missing downloads must
not be interpreted as missing photos in the source export. Media storage remains
independent of decisions so it can be retried without affecting review progress.

## 12. Implementation phases and acceptance criteria

### Phase 1 — Local foundation, import, and persistence

Implement database migrations, immutable snapshots, first import, library/detail
views, and the one-command local launcher.

Acceptance: the initial export loads all five categories and source counts;
unjoined content is retained; restart preserves state; source files stay unchanged.

### Phase 2 — Guided bands and comparisons

Implement editable bands, reference selection, deterministic comparison scheduling,
provisional moves, session review, uncertainty, and persistent undo.

Acceptance: complete a five-comparison session, stop midway through another, close
the server/browser, and resume at the same prompt without losing answers. Check
conflicting judgments and band-boundary changes on controlled fixtures.

### Phase 3 — Cleanup and before/after

Implement missing-content filters, attention flags, Need to delete, restoration,
and the original/session change views.

Acceptance: flags match the current export counts; excluded items stop appearing
in comparisons; restoring them retains content; intentional moves and passive
rank shifts are distinguishable.

### Phase 4 — Refresh imports and backup recovery

Implement merge previews, idempotent imports, new-item placement, discrepancy
resolution, latest-source comparisons, and backup/restore.

Acceptance: a synthetic newer export with additions, updated notes, ranking
changes, missing places, and category transfers preserves local decisions and
queues the correct reviews. Reimport is a no-op. Older snapshots cannot silently
replace the latest baseline. A backup restores successfully into a fresh workspace.

### Phase 5 — Usability and optional enhancements

Polish keyboard flows, error messages, session length controls, and long notes.
Add optional photo caching and, after verification, a manual Beli update checklist.

The first complete release includes phases 1–4. Repeated imports and recovery are
core functionality, not optional polish.

## 13. Validation strategy

Use synthetic fixtures for automated tests rather than committing personal exports.
Prioritize invariants and failure modes:

- No lost or duplicated category memberships after moves or imports.
- Original snapshots remain immutable; tied source order is stable.
- Uncertain/equal responses never become fabricated strict preferences.
- Contradictions are surfaced and superseded judgments remain auditable.
- Failed writes/imports roll back cleanly; retries do not duplicate decisions.
- New imports preserve flags, exclusions, accepted order, and resumable sessions.
- Backup/restore and restart preserve equivalent working state.
- Account mismatches and malformed exports cannot corrupt the workspace.

Run browser-level checks for import → review → cleanup → restart → refresh import
→ before/after. Verify save-failure feedback, keyboard access, and unavailable
photos. Keep the existing exporter tests passing if shared code changes.

## 14. Deferred decisions and exclusions

Reasonable defaults can be used without blocking the build: five comparisons per
session, editable starter bands, imported scores hidden during comparisons, and
one account per local workspace.

Validate band names and comparison pacing through the first usable prototype.
No need to finalize every aesthetic choice before implementing the workflow.

Excluded from this implementation: dish-level lists, hosted deployment, social
features, automatic sentiment-based reranking, fabricated Beli scores, and direct
Beli API writes. API synchronization would be a separate future project requiring
verification of exact placement semantics and explicit user intent.
