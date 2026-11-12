<!-- docs-index: For the coach: what a `debate-research daily` digest covers, the hours it searches, the time zone it is dated in, and what --date and --window change -->
# Daily digests: a guide for the coach

`debate-research daily <preset>` writes one digest of new research for a preset in
`config/daily_presets.yaml`, such as `politics` or `nhi`. It runs the preset's searches, leaves out
what an earlier digest of the same preset already listed, and writes `digests/<preset>-<date>.md`,
grouped by argument and need. The command's own reference is the `daily` section of
[`packages/debate_cli/README.md`](../../packages/debate_cli/README.md); this page is about which
hours a digest covers and which date it carries.

## With no `--date`: the 24 hours before you run it

```console
$ debate-research daily politics
```

A digest run with no `--date` searches the **24 hours before the moment you run it**, and is dated by
**today's date in your time zone**. Run at 23:00 in Chicago on 11 November, it covers 23:00 on the
10th to 23:00 on the 11th, and it is `digests/politics-2026-11-11.md`. Run at 07:00 the next morning,
it covers 07:00 on the 11th to 07:00 on the 12th, and it is the 12th's digest.

The digest's `Window` line says exactly which hours it searched, in your zone:

```text
- Window: 2026-11-10 23:00 to 2026-11-11 23:00 America/Chicago (the 24 hours before the run)
```

The 24 hours are real hours. On the night the clocks change, a run at 23:00 covers the 24 hours
before it, which on the clock reads as 23 or 25.

**Running twice on one date.** A morning run and an evening run on the same date write the same file:
the evening's replaces the morning's and lists again what the morning's listed, plus anything newer.
Results a digest of an earlier date listed are left out, as before.

## The time zone

The date comes from the setting `daily.time_zone`, an IANA time zone name. Both committed profiles,
dev and prod, set `America/Chicago`. To date digests somewhere else on one machine, set it in that
machine's environment or `.env` file, for example:

```bash
export DEBATE_DAILY__TIME_ZONE=America/Los_Angeles
```

A name the time zone database does not know, such as `Central` or a misspelling, stops every command
when it starts, with a message naming `daily.time_zone`. `debate-research config show` prints the zone
in use and where it came from.

## With `--date`: whole days in UTC

```console
$ debate-research daily politics --date 2026-11-11
```

`--date` means exactly what it always has: the whole of that day in UTC, from midnight to midnight
UTC, which is 18:00 the evening before to 18:00 that evening in Chicago in winter. Use it to rebuild a
particular day's digest.

## `--window`: more days

`--window 3d` widens either kind of digest to three days. With no `--date` that is the 72 hours before
the run; with `--date` it is the three UTC days ending on that date. A window is 1 to 31 days.

## Digests written before this change

Before v1-e08-t25 a digest with no `--date` took the UTC date, so a digest run in the evening in
Chicago (from 18:00 in winter, 19:00 in summer) was named for the next day and searched only the hours
since UTC midnight. Nothing about those files changes, and they stay readable where they are. Two
things happen once, on the first evening after you install a build with this change:

* If you ran an evening digest the night before with the older build, it was named for today's date.
  Today's run has that same name, so it replaces that file. That file held last night's results, and
  today's digest lists again those of them still inside its 24 hours, because the older build
  recorded them under today's date and a digest lists again what its own date listed. If you want to
  keep that file, rename it before today's run.
* From the next day on, every digest is named and recorded by your local date, and nothing is listed
  twice.

## Which results a feed contributes

The publisher feeds keep an item only when every word of a filled search template is in its title or
summary, so a template such as `bill vote count Senate` keeps only headlines that use all four words.
How many results that leaves on a real day is being measured (v1-e08-t25); until the PM rules on
that measurement, a quiet digest may mean the templates are too long, not that nothing happened.
