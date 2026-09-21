# ADR-0017: The caselist corpus is retrievable, and the sync stays weekly

- Status: Accepted
- Date: 2026-09-21
- Deciders: Charlie Clark (coach, operator), PM
- Supersedes: [ADR-0016](0016-caselist-corpus-is-accumulated.md)

## Context

ADR-0016 concluded that an OpenCaselist download is a seven-day window, that no complete caselist
could be fetched, and that a window not downloaded in time was lost for good. It decided a daily
sync and moved E34 ahead of the backfill on that basis.

Two of its three premises were wrong, and it should not have been written when it was.

The v1-e34-t01 session read the upstream source and found the downloads listing carries two archive
kinds. One authenticated listing call against the live site, run by the operator on 2026-09-21,
returned for `hsld26`:

```
WEEKLY 2026-07-07 … WEEKLY 2026-09-08   (ten consecutive weekly archives)
FULL   2026-09-15  hsld26-all-2026-09-15.zip
WEEKLY 2026-09-15  hsld26-weekly-2026-09-15.zip
```

- **A complete archive is published.** `hsld26-all-2026-09-15.zip` is described upstream as every
  open-source file still attached to a round. ADR-0016's central premise, that no endpoint returns
  a complete caselist, is false.
- **Weekly archives are retained.** Eleven dated weeklies are listed, the oldest 2026-07-07. A week
  that is not downloaded on the day can be downloaded later, so ADR-0016's permanent-loss argument
  does not hold.
- **The back-catalogue reaches further back than our own data.** ADR-0016 stated that anything last
  modified before 2026-08-24 was unreachable. Eight weekly archives older than that are listed right
  now.
- **Only one FULL archive is listed**, dated with the most recent weekly. The full archive appears to
  be regenerated rather than retained per date, so unlike the weeklies there is no back-catalogue of
  it.

ADR-0016's daily cadence also contradicted `docs/policies/caselist-data-use.md` E34 gate 4 —
"weekly cadence at most, no polling faster than archives are published" — which was approved with
the maintainer, whose clause 12 confirmation is scoped to the weekly archives. That clause was not
consulted when ADR-0016 was written. The policy governs.

What ADR-0016 got right stands: the three September downloads we already hold are adjacent seven-day
windows, 2,374 members collapsing to 2,107 distinct files, and path-keyed identity is unstable
because filenames carry a per-team sequence number that increments.

## Decision

1. **The full archive is the corpus, and the backfill starts there.** `v1-e30-t06` downloads
   `<caselist>-all-<date>.zip` first and imports it as the baseline. The three September weeklies we
   hold are imported alongside it for the history they carry, not as the corpus itself.
2. **The sync stays weekly**, at the cadence the archives are published and the policy permits. No
   daily polling. Nothing in this project overrides an approved data-use policy; where a decision
   here appears to, the policy wins and the decision is wrong.
3. **Missing a run is a delay, not a loss.** The weekly back-catalogue makes a late download
   equivalent to a timely one, so `v1-e34-t03`'s staleness alerting returns to its original weight:
   important operational hygiene, not a guard against unrecoverable damage.
4. **The back-catalogue is fetched once, soon.** Eight weekly archives older than anything we hold
   are available now. Retention is not documented, so they are fetched before we learn what ages out
   by losing them. This is the one piece of ADR-0016's urgency that survives, and it is a one-off
   operator job, not a reason to reorder a release.
5. **`REMOVED` becomes meaningful again**, measured against the full archive rather than against the
   previous window. A file in an earlier snapshot whose sha256 is absent from the current full
   archive is a genuine withdrawal. `v1-e30-t06` may report that; it still may not report
   window-to-window path changes as removals.
6. **E34 stays in v1.1**, but not for the reason ADR-0016 gave. The loss argument is gone; what
   remains is that `v1-e34-t01` is already built and accepted, the capture-first split of the
   scheduled run is good design on its own, and automating a weekly manual chore early is worth
   doing. The release files are corrected to say that instead.

## Consequences

- The corpus is larger and cheaper to obtain than ADR-0016 assumed. One full archive plus a
  back-catalogue fetch reaches more than a season of accumulation would have.
- Bulk downloads are capped at **5 per user per day** (upstream source, found by v1-e34-t01), so the
  back-catalogue fetch of eight weeklies plus one full archive spans two days and must be planned
  rather than scripted in one run.
- `v1-e32`'s denominators still come from the accumulated store rather than from a single window,
  which ADR-0016 got right for the wrong reason: a weekly archive is still a window even though the
  full archive is not.
- Only `hsld26` was listed. `hspolicy26` and `hspf26` are assumed to behave the same way and this is
  confirmed before the backfill runs, not after.
- This is the second ADR on the same subject in one day. The lesson recorded in
  `docs/process/working-agreements.md` §7 is the durable output: measure the source before writing a
  decision record on top of it.

## Alternatives considered

**Patch ADR-0016 in place.** Rejected. It was accepted, acted on, and drove spec changes across three
epics and two releases; editing it would hide that the project reordered work on a premise that one
listing call would have disproved.

**Move E34 back to v1.2.** Rejected as churn. The move to v1.1 was made for a reason that turned out
to be wrong, but the position is still defensible on its own merits and t01 has already shipped
against it. The justification is corrected rather than the membership.
