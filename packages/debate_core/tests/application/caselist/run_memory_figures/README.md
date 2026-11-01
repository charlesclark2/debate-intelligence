# A weekly run's memory figures (`v1-e40-t31`)

`details_this_build_writes.json` is a run's details with each stage's memory figures, **written by
hand** from the stubs of `test_caselist_sync_memory_figures.py`: nine stages at one clock reading,
the search index stage seven minutes long, the container at 1 GiB and the main process at 200 MiB
until that stage ends and at 3 GiB and 900 MiB after it. That test shows it is what this build writes
for the run, and the same test checks it against the details schema the earlier builds print
(`../stored_run_records/`).

`../check_an_older_build_reads_the_run_memory_figures.py` reads it with an earlier build's own code:
its details file reader and its bucket reader, the bucket being the filesystem object store. It is
run by path with that build's Python, from the worktree:

```bash
"${VENV}/bin/python" -I packages/debate_core/tests/application/caselist/check_an_older_build_reads_the_run_memory_figures.py
```

`VENV` is a virtual environment holding that build's `debate_core` wheel, built offline from its
tag as `docs/session-reports/v1-e30-t31-openev-camp-word-on-the-manifest-row.md` describes, with a
plain-path `.pth` to the worktree's site-packages for third-party packages only. On 2026-11-01 both
`v1.1.0-dev.251` (`a21bb68`) and `v1.1.0-dev.200` (`761b571`) printed:

```text
its stage entry keeps the figures: False
details file: the run read True; 9 stage(s), as written: True
bucket: 1 run(s), its details read True; stages as written: True
PASS
```

That is: the run and its details are read from both places, every stage with its times, and the
figures are passed over. Given a path, the check reads that file instead, to try details a changed
build wrote.
