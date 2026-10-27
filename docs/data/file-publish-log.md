<!-- docs-index: Every operator publish of built files to the evidence buckets: keys, counts and statuses, no team codes (v1-e33-t05) -->
# Built-file publish log

Each publish of built evidence files to a bucket, as `debate-research files publish` reported it.
Keys follow the layout in [built-file-metadata.md](built-file-metadata.md):
`files/<topic>/<side>/<position>/<slug>/<recipe hash 12>/`, five objects per file (the `.docx`, its
`.provenance.json` and `.quality.json`, `recipe.yaml` and `metadata.json`). No school, team code or
person's name is recorded here. Spec:
[`v1-e33-t05-file-publish`](../../plan_specs/v1/e33-file-builder/t05-file-publish.yaml), ac5.

## Dev, 2026-10-27: the synthetic samples

Run by the operator after the cloud cutover's step 9, from a scratch data directory, as the task's
operator follow-ups 1 to 3 give it. Recorded by the PM.

| Step | Result |
|---|---|
| Build | 3 files built from synthetic sources (the three `v1-e33-t01` examples), each quality report `PASS` |
| Dry run | 3 tables, each one `WOULD_PUBLISH` row, bucket `debate-dev-evidence-a7508de8` |
| Publish | 3 tables, each `1 PUBLISHED`; `store ls files/` lists 15 objects, five per file |
| Publish again | each `1 SKIPPED`; the same 15 objects |
| Scratch directory | removed after the step |

The three files' prefixes, to the position (each continues with the slug and the recipe hash):

| Topic / side / position | Objects |
|---|---|
| `files/data-center-moratorium/con/` | 5 |
| `files/nhi/aff/politics-da/` | 5 |
| `files/space-colonization/neg/` | 5 |

## Prod

Not yet published. The first real files are published after the coach approves them (quality
`PASS`, provenance read), and recorded here.
