# Stored camp manifests

The camp release manifest three builds' own pulls write after the same history, and the takedown's
records this build writes when it withdraws a camp path (`v1-e30-t14`). Nothing here is written by
hand, and nothing here is real camp content: the history is two pulls of the invented camp files
under `tests/fixtures/openev/`, against moto, at a fixed clock (`camp_manifest_scenario.py`).

`test_camp_manifest_is_read_by_every_build.py` reads these to show that a release manifest this
build writes is one an older build reads, and the reverse.

| File | Written by | What it is |
|---|---|---|
| `written_by_the_installed_build/2026-policy.jsonl` | The source of tag `v0.1.0-dev.122` (`d87febd`), the build the weekly agent is installed from | `manifests/openev/2026-policy.jsonl` after the history |
| `written_by_the_start_commit/2026-policy.jsonl` | The source of `53a8743`, the commit on `dev` this task started from | The same. Byte for byte the file above |
| `written_by_this_build/2026-policy.jsonl` | This task's source | The same rows, each with two more keys, `openev_id` and `upstream_path_sha256`, and the same summary row |
| `written_by_this_build/suppression/` | This task's source | `suppression-list.jsonl` and `withdrawals.jsonl` after the history goes on: 800 pulled into `2027-policy` with 640's bytes, then 512 removed by `--source`, so 640 is withdrawn from its camp path. The list's second line is that camp path's entry; the record's one line names `openev` |

The history is two pulls through the real sync: 512 first; then 640, 512 uploaded again at the same
path, and 700, another camp's file of the same name. It runs on the `removal_world` fixture, so the
release also holds the fixture's hand-imported camp files. It uses nothing a build from before
`v1-e30-t14` lacks, so the same function runs against all three sources. The installed build itself
was not opened or run: its source is the tag its version names, exported with `git archive`.

## How they were written

`BUILD` is a scratch directory holding one older build's source, so that no checkout or stash is
involved:

```bash
git archive v0.1.0-dev.122 packages/debate_core/src packages/debate_cli/src | tar -x -C "${BUILD}"
```

The manifests, by running the history against that source. The variable is `the-installed-build`,
`the-start-commit` or, with no `PYTHONPATH`, `this-build`, which also writes `suppression/`:

```bash
WRITE_STORED_CAMP_MANIFESTS=the-installed-build PYTHONPATH="${BUILD}/packages/debate_core/src:${BUILD}/packages/debate_cli/src" uv run --frozen pytest packages/debate_core/tests/application/caselist/write_stored_camp_manifests.py -p no:cacheprovider --no-cov -n 0
```

`write_stored_camp_manifests.py` is not a test module and is never collected; it runs only when
named. It refuses to run without the variable, because it overwrites these files.

## An older build's own code, reading what this build writes

`check_an_older_build_reads_this_builds_camp_manifests.py` is not collected either. Run against an
older build's source, it carries out the history with that source, puts this build's files where
that build keeps them, and does with them everything that build does with a release manifest and
with the takedown's records.

```bash
CHECK_AN_OLDER_BUILD_READS=this-builds-camp-manifests PYTHONPATH="${BUILD}/packages/debate_core/src:${BUILD}/packages/debate_cli/src" uv run --frozen pytest packages/debate_core/tests/application/caselist/check_an_older_build_reads_this_builds_camp_manifests.py -p no:cacheprovider --no-cov -n 0 -q
```

Run on 2026-10-14 against `v0.1.0-dev.122` and against the start commit, its first check printed the
same lines but for the source's name (`dev122`, `start-53a8743`):

```text
reader: the debate_core source at dev122
placed: this build's manifest; its rows are this source's own but for the two keys: True
publish: succeeded True; status in sync: True
next pull: openev-640 already_imported, openev-700 already_imported, openev-900 download
its merge: this build's rows kept byte for byte (16 row(s)); the new row True, with the keys False
metadata re-import: this build's rows kept the two keys as written: True; the same as its re-derive of its own manifest but for the two keys: True
removal of 512: completed True; later upload(s) openev-640; rows it kept kept byte for byte (15 row(s)); 512 and 640 gone True
publish again: succeeded True; status in sync: True
```

Its second check puts this build's `suppression/` files in place, on this machine and in the bucket,
and reads them the way that source does. The start commit printed:

```text
reader: the debate_core source at start-53a8743
placed, in both places: suppression-list.jsonl, withdrawals.jsonl
list read: 1 whole file(s) and 1 disclosure(s)
next pull: openev-640 already_imported, openev-700 already_imported
the same removal: COMPLETED; removed 2 file(s), withdrew 0
publish: succeeded True; status in sync: True
status with the residue check: completed; in sync True
the withdrawal record read by this source's own model: UnreadableAppendOnlyRecord at line 1; no command of this source reads it
the withdrawal record afterwards: this build's line kept True
```

`v0.1.0-dev.122` printed the same first six lines, then `status with the residue check: this source
reads no removal log`, `the withdrawal record: this source has no reader of it` and the last line as
above. The start commit's own model refuses the `openev` line because its `WithdrawalEntry` takes a
caselist slug alone. No command of it parses the record: it appends to it, which reads lines and
validates none, and its only readers, `withdrawals()` and the two joins, are called by tests alone.

## When these may change

The older builds' files may not: a build that is installed does not change. `written_by_this_build/`
is rewritten only by a change that is meant to change what a release manifest or a camp path's
withdrawal records hold, and then its rows less the two keys must still be the older builds' rows
byte for byte: the test fails otherwise.
