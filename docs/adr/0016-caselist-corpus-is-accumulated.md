# ADR-0016: The caselist corpus is accumulated from windows, not captured

- Status: **Accepted, with decisions 2 and 3 under review since 2026-09-21**
- Date: 2026-09-21
- Deciders: Charlie Clark (coach, operator), PM

> **Under review.** The v1-e34-t01 session read the upstream OpenCaselist source and found three
> things this ADR did not account for. Nothing here is withdrawn, but **no task may implement
> decision 2 or 3 until this is settled**, and v1-e34-t02 must not be started meanwhile.
>
> 1. **A complete archive may exist.** The downloads listing carries two archives per caselist:
>    `<caselist>-weekly-<date>.zip`, which matches the measurements below, and
>    `<caselist>-all-<date>.zip`, described upstream as every open-source file still attached to a
>    round. If the deployed site publishes the second, the premise that no complete caselist can be
>    fetched is wrong, and with it the urgency behind decisions 2 and 3.
> 2. **The daily cadence contradicts an approved policy.** docs/policies/caselist-data-use.md,
>    approved with the maintainer, says "weekly cadence at most — no polling faster than archives are
>    published" (E34 gate 4, terms clause 6), and the maintainer's confirmation in clause 12 is scoped
>    to "scheduled downloads of the weekly archives". Decision 2 was written without checking that
>    clause. It does not override it. A daily sync needs either the maintainer's agreement or a
>    different justification, and until then the cadence stays weekly.
> 3. **The reasoning behind daily may not hold either.** Decision 2 argued that consecutive weekly
>    pulls overlap by about 6% of a week's files, so a slipped run loses the gap permanently. That
>    assumes a window not downloaded at the right moment is gone. If the listing exposes past dated
>    archives, a missed week is simply downloaded late, and the policy's own rationale applies: polling
>    faster than archives are published fetches the same file repeatedly and puts load on a
>    volunteer-run service for nothing.
>
> Also from the same source: the site limits a user to **5 bulk downloads per day**, which any cadence
> decision has to budget for across the three caselists.
>
> One authenticated listing call settles all of it. The measurements below are unaffected — they are
> what three real downloads contained, whatever the site offers alongside them.

## Context

E30 was planned on the assumption that an OpenCaselist download is a cumulative
archive: each week's file is a superset of the week before, so importing three
weeks and deduplicating by content yields the corpus, and most of the bytes are
saved by dedupe.

The v1-e30-t03 session imported the three real HS LD downloads (2026-09-01,
-09-08, -09-15) and the numbers did not behave that way. A direct measurement of
the three directories then established why. Counts only, as
docs/policies/caselist-data-use.md requires.

Overlap between consecutive downloads:

| | 09-01 -> 09-08 | 09-08 -> 09-15 |
|---|---|---|
| paths still present | 5 / 64 (8%) | 60 / 745 (8%) |
| distinct contents still present | 12 / 59 (20%) | 98 / 678 (14%) |
| schools still present | 4 / 10 | 37 / 47 |

Schools disappear and reappear: of the schools seen across the three downloads,
three are in all three, two are present on 09-01, absent on 09-08 and back on
09-15, and 101 appear only on 09-15. One school present in all three goes 25 ->
11 -> 52 files. A cumulative export cannot shrink, and a school cannot
un-disclose and then disclose again.

File modification times give the mechanism. Each download holds what was
modified in roughly the seven days before it, plus a thin lagging tail:

| download | files | modified <=7d before | 8-14d | older |
|---|---|---|---|---|
| 09-01 | 64 | 63 | 1 | 0 |
| 09-08 | 745 | 733 | 7 | 5 |
| 09-15 | 1,595 | 1,490 | 97 | 8 |

Downloads spaced seven days apart therefore tile adjacent windows rather than
nesting. The ~98 contents shared by 09-08 and 09-15 are the 97 stragglers dated
September 1-7, not a persisting corpus.

The maintainer has confirmed there is no endpoint that returns a complete
caselist.

## Decision

The corpus is something this project accumulates going forward, not something it
can capture. Specifically:

1. **A download is a window, and the store is the archive of record.** Nothing
   outside our own evidence store can be re-fetched. A file modified before the
   oldest window we ever pulled, and not edited since, is unreachable
   permanently.
2. **The sync runs daily, not weekly.** Consecutive weekly pulls overlap by
   about 6% of a week's files, so a run that slips two days loses everything
   modified in the gap with no way to recover it. Daily pulls overlap roughly
   six-sevenths, which tolerates six consecutive failed runs. The archive is one
   request rather than per-file, so the maintainer's 10-files-per-minute limit
   does not bind, and content-addressed storage means the redundancy collapses to
   nothing on disk: frequent syncing costs bandwidth, not storage.
3. **E34 ships before the backfill, not after it.** Until the scheduled sync is
   running, every day is a window nobody can recover. This reverses the order
   E30 and E34 were planned in.
4. **v1-e30-t06 is the first day of accumulation, not a backfill.**
   docs/data/caselist-backfill-2026-09.md states what its numbers are - three
   windows of editing activity, 2,374 members collapsing to 2,107 distinct files
   - and does not present them as a census of HS LD disclosure.
5. **REMOVED is not a takedown count, and there is no population to be absent
   from.** With adjacent windows rather than nested snapshots, "not in this
   archive" carries no information about whether a file still exists upstream.
   Reports name it for what it is.
6. **E32 denominators come from the accumulated store, not from a window.**
   "Share of the week's disclosing teams" computed over one download is a share
   of teams who edited something that week, which is a different quantity
   wearing the same label.

## Consequences

- The value of the platform now depends on sync uptime in a way it did not
  before. A missed week is a permanent hole in the record, so v1-e34-t03
  (sync monitoring) becomes load-bearing rather than operational polish.
- Early landscape reports cover a short and growing history. Any report that
  spans less than a full topic cycle says so.
- The three September windows remain worth importing: they are the oldest data
  we will ever have.
- If OpenCaselist later exposes a full export, this decision is revisited; the
  importer and the store need no change to absorb one, because identity is
  already content-addressed.

## Alternatives considered

**Keep weekly pulls.** Rejected: a 6% overlap is not a margin, and the failure is
silent and unrecoverable.

**Scrape per-file rather than take the archive.** Rejected: the maintainer's rate
limit is per file and the data-use policy's permitted uses are written around the
archive download. It would also not reach files that are not currently listed.

**Treat the three windows as the corpus and move on.** Rejected: it would put a
number in docs/data/ that reads as coverage of HS LD when it is three weeks of
edits, and E32's shares would inherit the error.
