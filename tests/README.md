# tests

Cross-package tests. `fixtures/` holds recorded HTTP/model fixtures, `golden_cards/` holds
golden DOCX/JSON cards (invented files built by the test builders — no real team, caselist or camp
file or excerpt is committed anywhere in this repository, scrubbed or otherwise: see v1-e31-t02,
v1-e31-t03 and v1-e31-t05),
`integration/` holds end-to-end suites. Package unit tests live in `packages/<pkg>/tests/`.

`evals/` holds evaluation suites. `evals/parser/` measures the debate `.docx` parser against
hand-corrected labels of real files that stay on the operator's machine and are never committed;
`fixtures/debate_files/eval/MANIFEST.md` explains what is here instead. `evals/baselines/` holds
the scores the regression gates hold each suite to.

`pytest_plugins/` holds the one pytest plugin of our own, `run_in_parts.py`. It adds `--part K/N`,
which runs one of N parts of whatever pytest selected; the N parts together are the whole
selection. CI's `test` job is a matrix of those parts (working agreement 1), and
`scripts/test_ci_workflow_test_job.py` proves on every run that no test falls outside them.
`pyproject.toml` puts the directory on `sys.path` and loads the plugin, so the option is there in
every run and does nothing unless it is given.
