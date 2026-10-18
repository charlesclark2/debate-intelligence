# Stored suppression lists

What builds before `v1-e30-t13` say a line of the suppression list is, and the takedown's records as
each build left them after the same history. Nothing here is written by hand, and nothing here is
real caselist content: the history is three removals over the invented archives under
`tests/fixtures/`, against moto, at a fixed clock.

`test_suppression_list_is_read_by_every_build.py` reads these to show that the list this build
writes is one an installed build reads, and the reverse.

| File | Written by | What it is |
|---|---|---|
| `line_schemas_of_the_installed_build.json` | The source of tag `v0.1.0-dev.60` (`ec7b95e`), the commit the weekly agent's build `0.1.0.dev60` reports | `SuppressionEntry.model_json_schema()` and `RemovalLogEntry.model_json_schema()`: every field, type and limit of a line, and that no other field is allowed |
| `line_schemas_of_the_start_commit.json` | The source of tag `v0.1.0-dev.119` (`7efe8c6`), the commit on `dev` this task started from | The same, printed by that build's own code. Byte for byte the file above |
| `written_by_the_installed_build/` | The source of `v0.1.0-dev.60` | `local/`: every file under `<data_dir>/suppression/`. `bucket/`: every object under `manifests/_suppression/` |
| `written_by_the_start_commit/` | The source of `v0.1.0-dev.119` | The same |
| `written_by_this_build/` | This task's source | The same. It holds three more files in each place: `path-holds.jsonl` beside the list (`v1-e30-t13`), `removal-scopes.jsonl` beside the log (`v1-e30-t15`), and `withdrawals.jsonl` beside both, the caselist each withdrawn copy was taken from (`v1-e30-t16`). The scopes hold the version ids the bucket gave each rewritten manifest, which moto picks at random, so the test compares that file with those ids masked and every other byte as written |
| `held_digests_written_by_this_build/` | This build's source (`v1-e30-t23`) | `local/held-digests.jsonl` and `bucket/held-digests.jsonl`: the held-digest record after the history below and one more step, an upload held at the removed path and the removal run again (`held_digest_scenario.py`). One line in each place. The history alone writes no such record, which is why it is not in `written_by_this_build/`. `test_removal_held_digest_files_are_this_builds.py` holds it to what this build writes |

The history is `suppression_list_scenario.py`, which uses nothing a build from before `v1-e30-t11`
lacks, so the same file runs against all three sources: a `--team` removal, a `--source` removal of
a file with one version at one path, and an `unsuppress`. The list ends with every kind of line it
has.

The installed build itself was not opened or run. Its source is the tag its version names, exported
with `git archive`.

## How they were written

`BUILD` is a scratch directory holding one older build's source, so that no checkout or stash is
involved:

```bash
git archive v0.1.0-dev.60 packages/debate_core/src packages/debate_cli/src | tar -x -C "${BUILD}"
```

The schemas, by the build they describe:

```bash
PYTHONPATH="${BUILD}/packages/debate_core/src" uv run --frozen python -c 'import json,sys; from debate_core.application.ports.suppression import SuppressionEntry, RemovalLogEntry; sys.stdout.write(json.dumps({"suppression_list_line": SuppressionEntry.model_json_schema(), "removal_log_line": RemovalLogEntry.model_json_schema()}, indent=2, sort_keys=True) + "\n")'
```

The records, by running the history against that source. The variable is `the-installed-build`,
`the-start-commit` or, with no `PYTHONPATH`, `this-build`:

```bash
WRITE_STORED_SUPPRESSION_LISTS=the-installed-build PYTHONPATH="${BUILD}/packages/debate_core/src:${BUILD}/packages/debate_cli/src" uv run --frozen pytest packages/debate_core/tests/application/caselist/write_stored_suppression_lists.py -p no:cacheprovider --no-cov -n 0
```

`write_stored_suppression_lists.py` is not a test module and is never collected; it runs only when
named. It refuses to run without the variable, because it overwrites these files.

## An older build's own code, reading what this build writes

`check_an_older_build_reads_this_builds_files.py` is not collected either. Run against an older
build's source, it carries out the history with that source, puts `written_by_this_build/` where
that build keeps the records, on the machine and in the bucket, and then does what the weekly agent
does with a suppression list: reads it, imports the next week's archive, publishes, and asks for
the status.

```bash
CHECK_AN_OLDER_BUILD_READS=this-builds-files PYTHONPATH="${BUILD}/packages/debate_core/src:${BUILD}/packages/debate_cli/src" uv run --frozen pytest packages/debate_core/tests/application/caselist/check_an_older_build_reads_this_builds_files.py -p no:cacheprovider --no-cov -n 0 -q
```

Run on 2026-10-12 against each, it printed the same five lines but for the source's name
(`dev60`, `dev119`):

```text
reader: the debate_core source at dev60
placed: suppression/path-holds.jsonl, suppression/removal-log.jsonl, suppression/suppression-list.jsonl, s3://<bucket>/manifests/_suppression/path-holds.jsonl, s3://<bucket>/manifests/_suppression/removal-log.jsonl, s3://<bucket>/manifests/_suppression/suppression-list.jsonl
list read: 3 whole file(s) and 2 disclosure(s) suppressed
knows of path holds: False
import of the next week: SUPPRESSED 4, completed
publish: succeeded True; status in sync: True
```

Its second check writes the path entry into the list itself, as a line, and reads the list with
the same source. That is the design this task did not take, and each build printed why:

```text
reader: the debate_core source at dev60
a path entry written into the list: UnreadableAppendOnlyRecord at line 8
the whole list is refused, and an import against it fails with nothing stored
```

`v1-e30-t15` ran the same check against `v0.1.0-dev.122`, the build the weekly agent was reinstalled
from on 2026-10-14, over `written_by_this_build/` with its scope file. Its first line named the
eight files placed, the scope file in both places among them, and the four after it were the
lines above.

`v1-e30-t16` ran it again, with two more checks, against two sources on 2026-10-14: its start
commit (`686b9b1`, two commits after tag `v0.1.0-dev.129`) and `v0.1.0-dev.122`, the build the
weekly agent is reinstalled from, which predates `v1-e30-t13` and `v1-e30-t15`. For each, the first
check placed ten files, `withdrawals.jsonl` in both places among them, and printed the four lines
above but for `knows of path holds`, which is `True` for the start commit. The second printed what
it prints above.

The third check is why a withdrawal's caselist is a file of its own and not part of
`removal-scopes.jsonl`. It writes the last scope line the source wrote again with one more field,
then instead a line of a new kind, and asks that source's log reader and its status for the scopes.
The start commit printed:

```text
reader: the debate_core source at start-686b9b1
a withdrawal's caselist in the scope record, as one more field of its line: UnreadableAppendOnlyRecord at line 3
a withdrawal's caselist in the scope record, as a line of its own: UnreadableAppendOnlyRecord at line 3
so `caselist status` with the residue check fails on every run until the line is gone
```

and `v0.1.0-dev.122` printed `removal scopes: this source reads no removal-scope record, so nothing
added to one is read`. The fourth puts this build's files in place and runs the source's own
`caselist status` with the residue check, its only reader of the removal log and the scopes. The
start commit printed `status with the residue check: completed; caselists checked: openev,
testcl26` and `removals not checked: 0`; `v0.1.0-dev.122` reads no removal log.

## The held-digest record beside them (`v1-e30-t23`)

`held_digests_written_by_this_build/` is written by this build alone, since no earlier build writes
the record, with no `PYTHONPATH`:

```bash
WRITE_HELD_DIGEST_FILES=this-build uv run --frozen pytest packages/debate_core/tests/application/caselist/write_held_digest_files.py -p no:cacheprovider --no-cov -n 0
```

From `v1-e30-t23` the check above places these two files as well, in every check, and its last check
runs the removal again beside them: the `--source` removal under `RM-2026-02` is planned without the
record, then with it in place, and executed. Run on 2026-10-18 against `v1.1.0-dev.18` (`0268cf7`,
the build the weekly agent runs), its first check placed twelve files, `held-digests.jsonl` in both
places among them, and printed the four lines above with `knows of path holds: True`. The second,
third and fourth printed what they print above. The last printed:

```text
reader: the debate_core source at dev18
placed: suppression/held-digests.jsonl, s3://<bucket>/manifests/_suppression/held-digests.jsonl
removal of RM-2026-02 run again beside the record: 1 source(s) planned; the same plan as without it: True
executed: completed True; the record as placed, both copies: True
```

`v1-e30-t23`'s start commit (`3ebeaab`) printed the same. This build prints `2 source(s) planned` and
`the same plan as without it: False`: it lists the held upload.

## When these may change

The older builds' files may not. They are what those builds wrote, and a build that is installed
does not change. `written_by_this_build/` is rewritten only by a change that is meant to change
what the takedown's records hold, and then `suppression-list.jsonl` and `removal-log.jsonl` in it
must still be the older builds' files byte for byte: the test fails otherwise. When no machine
runs a build older than `v1-e30-t13`, the list's lines may be allowed to change again, and this
directory and the test that holds the list to it go together.
