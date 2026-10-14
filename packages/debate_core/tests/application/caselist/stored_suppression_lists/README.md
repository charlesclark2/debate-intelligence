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
| `written_by_this_build/` | This task's source | The same. It holds two more files in each place: `path-holds.jsonl` beside the list (`v1-e30-t13`) and `removal-scopes.jsonl` beside the log (`v1-e30-t15`). The scopes hold the version ids the bucket gave each rewritten manifest, which moto picks at random, so the test compares that file with those ids masked and every other byte as written |

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

## When these may change

The older builds' files may not. They are what those builds wrote, and a build that is installed
does not change. `written_by_this_build/` is rewritten only by a change that is meant to change
what the takedown's records hold, and then `suppression-list.jsonl` and `removal-log.jsonl` in it
must still be the older builds' files byte for byte: the test fails otherwise. When no machine
runs a build older than `v1-e30-t13`, the list's lines may be allowed to change again, and this
directory and the test that holds the list to it go together.
