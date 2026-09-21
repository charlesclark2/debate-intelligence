# tests/smoke

Checks that run against a **deployed** environment, not against this checkout. They are what
`validate-dev` runs before a `dev` → `main` promotion, and what an operator runs again after a
prod deploy (docs/process/branching-and-environments.md).

Most checks here need the network, and those are marked `live` and carry pytest-socket's
`enable_socket` marker. The default `pytest` run excludes `live` and disables sockets, so a
normal run collects them and skips them; only an explicit `-m live` (or `-m dev` / `-m prod`)
run reaches out.

**A check is marked `live` when it needs a deployed environment, not because it lives here.**
`test_caselist_import_smoke.py` is the first that does not: what it verifies is that the whole
`caselist import` path works when it is wired up the way an installation wires it — console
script, composition root, settings profile, SQLite file, blob store, manifest — and none of that
needs an account. It is unmarked and runs in the default suite, because the alternative is that
the one check covering a weekly operator command is skipped in CI *and* skipped before every
promotion.

| File | What it checks | Told where to look by |
|---|---|---|
| `test_site.py` | The public team website: every page in the sitemap, the HTTPS redirect, the security headers, `noindex` on the preview and not on prod, the commit in `version.json`, and the launch surfaces (the October 1 panel on the home page, the parent FAQ's disclosures, and no unfilled fact badge on prod) (`scripts/site_smoke.py`, `v1-e36-t05` and `v1-e36-t08`) | `SITE_SMOKE_URL`, `SITE_SMOKE_ENV`, `SITE_SMOKE_SHA` |
| `test_store_cli.py` | The evidence store, read-only: `debate-research store ls` reaches the environment's bucket, and `store sync --dry-run` plans against it with nothing mismatched and nothing written (`v1-e29-t05`) | `STORE_SMOKE_ENV`, and an SSO session for that environment's evidence profile |
| `test_caselist_import_smoke.py` | `debate-research caselist import`, offline: three synthetic weekly archives into a fresh data directory, with the counts, the manifests and the re-import no-op checked against `tests/fixtures/caselist/expected_summary.json` (`v1-e30-t03`) | Nothing. It builds its own archives and its own profile |

```bash
SITE_SMOKE_URL=https://dev.wfbdebate.com \
SITE_SMOKE_ENV=dev \
SITE_SMOKE_SHA=$(git rev-parse HEAD) \
uv run pytest tests/smoke -m dev
```

```bash
aws sso login --profile debate-dev-evidence
STORE_SMOKE_ENV=dev uv run pytest tests/smoke/test_store_cli.py -m dev
```

```bash
uv run pytest tests/smoke/test_caselist_import_smoke.py   # no flags: it needs nothing deployed
```

Importing the **real** weekly archives is an operator-run job (`v1-e30-t06`), not a check here:
it takes far longer than the CI budget allows, and no real caselist file may enter this
repository at all ([docs/policies/caselist-data-use.md](../../docs/policies/caselist-data-use.md)).

`test_store_cli.py` only reads and plans; it never writes to a bucket, so running it against prod
after a prod apply is safe. Publishing evidence is a deliberate `--apply` by a person
([docs/guides/evidence-store-cli.md](../../docs/guides/evidence-store-cli.md)).

A task that adds or changes a user-facing surface adds its checks here, and says so in its spec
(docs/process/working-agreements.md §5). Cloud-only checks move to `tests/smoke/cloud/` from V2.
