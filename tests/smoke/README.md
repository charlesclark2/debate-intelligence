# tests/smoke

Checks that run against a **deployed** environment, not against this checkout. They are what
`validate-dev` runs before a `dev` → `main` promotion, and what an operator runs again after a
prod deploy (docs/process/branching-and-environments.md).

Everything here needs the network, so every test is marked `live` and carries pytest-socket's
`enable_socket` marker. The default `pytest` run excludes `live` and disables sockets, so a
normal run collects these and skips them; only an explicit `-m live` (or `-m dev` / `-m prod`)
run reaches out.

| File | What it checks | Told where to look by |
|---|---|---|
| `test_site.py` | The public team website: every page in the sitemap, the HTTPS redirect, the security headers, `noindex` on the preview and not on prod, and the commit in `version.json` (`scripts/site_smoke.py`, `v1-e36-t05`) | `SITE_SMOKE_URL`, `SITE_SMOKE_ENV`, `SITE_SMOKE_SHA` |
| `test_store_cli.py` | The evidence store, read-only: `debate-research store ls` reaches the environment's bucket, and `store sync --dry-run` plans against it with nothing mismatched and nothing written (`v1-e29-t05`) | `STORE_SMOKE_ENV`, and an SSO session for that environment's evidence profile |

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

`test_store_cli.py` only reads and plans; it never writes to a bucket, so running it against prod
after a prod apply is safe. Publishing evidence is a deliberate `--apply` by a person
([docs/guides/evidence-store-cli.md](../../docs/guides/evidence-store-cli.md)).

A task that adds or changes a user-facing surface adds its checks here, and says so in its spec
(docs/process/working-agreements.md §5). Cloud-only checks move to `tests/smoke/cloud/` from V2.
