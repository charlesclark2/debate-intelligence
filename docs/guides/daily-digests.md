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

## What a digest asks: the digest templates

For the groups that have them, `daily` asks short **digest templates** in place of the long search
templates `search` asks, such as `Senate vote count Senate`. The publisher feeds keep a headline only
when it has every word of a query, and on 12 November 2026 none of the politics preset's ten long
queries kept any of the 42 headlines of the day before. A digest template is the preset's query and
one more word, from `config/daily_templates.yaml`:

| Group | Asks | Kept on 2026-11-12, 24 hours / 72 hours |
|---|---|---|
| Politics DA — Uniqueness | `bill Congress`, `Senate Congress`, `Senate Republicans` | 3 / 3 |
| Midterms DA — Uniqueness | `Senate election` | 2 / 4 |

`search` is unchanged: it still asks the reviewed templates in `config/argument_taxonomy.yaml`, and
nothing in that file changed.

**A group with no digest templates** (today, all three of the `nhi` preset's groups) asks the reviewed
templates of `config/argument_taxonomy.yaml`, exactly as it did before digest templates existed, and
the digest says so under the group's heading:

```text
> No digest templates for this pair in config/daily_templates.yaml: its searches asked the taxonomy's templates.
```

Those templates are long, so on the feeds they may keep little; on OpenAlex, Crossref and the
government sources, which search differently, they do their usual work. Whether a group's feeds are
starved can be counted with the script below before a digest template is proposed for it.

## Counting a template before adding it

`scripts/count_digest_feed_matches.py` counts, against the real feeds, how many of the day's headlines
a template would keep. It prints counts only, never a headline, summary or link, and writes nothing.
It runs with the installed build's own Python on the script in a source checkout of the repository,
from your home folder. Set `CHECKOUT` to that checkout's folder once in the terminal; this example is
the operator's main checkout:

```bash
export CHECKOUT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence"
```

Then count one or more candidates, each `PAIR=TEMPLATE`:

```bash
cd "$HOME" && env DEBATE_ENV=dev "$(uv tool dir)/debate-cli/bin/python" -I "$CHECKOUT/scripts/count_digest_feed_matches.py" politics --candidate "midterms-da/uniqueness={query} polls" --candidate "politics-da/uniqueness={query} filibuster"
```

It takes under a minute. For the 24 hours and the 72 hours before the run it prints, per filled query,
how many headlines each would keep: the `taxonomy` rows are what `search` asks, the `digest` rows what
`daily` asks now (the taxonomy's again for a group with no digest templates), and the `candidate`
rows yours. A candidate that keeps something is worth adding:
put it under its group in `config/daily_templates.yaml` with the date you measured it and its two
counts as a comment, the way the four there are. A template is always the query and one word; the
file refuses anything longer when `daily` starts.
