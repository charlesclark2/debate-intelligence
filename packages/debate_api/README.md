# debate_api

FastAPI service (V2) exposing `debate_core` use cases over REST/JSON with Cognito JWT auth.
Routes only — **no business logic here**. First spec:
`plan_specs/v2/e12-identity-api/t02-fastapi-service.yaml`.

## The student search pilot (V1)

Before V2's service, `debate_api` serves the student evidence search pilot of
[ADR-0019](../../docs/adr/0019-student-search-pilot-stack-sign-in-and-hosting.md): server-rendered
pages from a plain ASGI app, which uvicorn serves and the Lambda Web Adapter forwards function URL
events to. `debate_api.app:create_app` is the app factory; `debate_api.container` is its
composition root, the only module that builds an adapter. Sign-in and the account pages are
`v1-e39-t05`'s; the search pages, the card page and Copy card are `v1-e39-t06`'s; the landscape
pages are `v1-e39-t17`'s.

| Module | What it holds |
|---|---|
| `access` | the gate in front of every route: which routes need a session, the coach check, CSRF |
| `routes` | the routes, and `ROUTE_ACCESS`, the access each needs |
| `search_pages` | the search page, its results, the card page and Copy card's copy, all `GET` |
| `landscape_pages`, `landscape_markdown` | the landscape report and its school view, rendered from the newest bundle with markdown-it, raw HTML escaped and every link checked |
| `copy_card` | Copy card's HTML and text, from a fixed table of emphasis, colour and size styles |
| `cookies` | the AES-GCM `__Host-` cookies and what each holds |
| `configuration` | the environment variables, and the cookie keys (the placeholder is refused) |
| `pages`, `templates/`, `static/` | server-rendered pages, the one first-party script and the one stylesheet |
| `container` | the composition root: Parameter Store, Cognito, the audit log and the search index holder |

The rules (lifetimes, who gets a session, the account changes) are in
`debate_core.application.tub`; the adapters in `debate_core.integrations.cognito`,
`cloudwatch_audit` and `parameter_store`. Search is `debate_core.application.evidence_search` over
the index `debate_core.application.search_index_holder` fetches from the evidence bucket the first
time a search needs it (`S3SearchIndexSource`), checks, and rechecks five minutes on. The tests in `tests/` run the real app over the real use
cases and the real OAuth adapter; `tests/conftest.py` stands in for managed login's HTTPS and the
token-authorized API only; the search pages run over a synthetic index the test world publishes in
memory. The accounts are the coach's, with `debate-research tub users`
([the accounts guide](../../docs/guides/evidence-search-accounts.md)).

`tests/browser/` drives the pages in Chromium (Playwright, with axe-core injected by the tests): the
keyboard journey at 1366x768, 1280x800 and 390x844, Copy card pasted and read back, and the edge's
CSP on every response. It is marked `slow`, so a plain `uv run pytest` skips it. Once per machine,
`uv run playwright install chromium`; then:

```bash
uv run pytest -m slow packages/debate_api/tests/browser
```

The image is built from [`Dockerfile`](Dockerfile) by `scripts/tub_deploy.sh`, never by hand
([docs/runbooks/evidence-search.md](../../docs/runbooks/evidence-search.md)).
