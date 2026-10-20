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
`v1-e39-t05`'s; the search pages arrive with `v1-e39-t06`.

| Module | What it holds |
|---|---|
| `access` | the gate in front of every route: which routes need a session, the coach check, CSRF |
| `routes` | the routes, and `ROUTE_ACCESS`, the access each needs |
| `cookies` | the AES-GCM `__Host-` cookies and what each holds |
| `configuration` | the environment variables, and the cookie keys (the placeholder is refused) |
| `pages`, `templates/`, `static/app.js` | server-rendered pages and the one first-party script |
| `container` | the composition root: Parameter Store, Cognito and the audit log |

The rules (lifetimes, who gets a session, the account changes) are in
`debate_core.application.tub`; the adapters in `debate_core.integrations.cognito`,
`cloudwatch_audit` and `parameter_store`. The tests in `tests/` run the real app over the real use
cases and the real OAuth adapter; `tests/conftest.py` stands in for managed login's HTTPS and the
token-authorized API only. The accounts are the coach's, with `debate-research tub users`
([the accounts guide](../../docs/guides/evidence-search-accounts.md)).

The image is built from [`Dockerfile`](Dockerfile) by `scripts/tub_deploy.sh`, never by hand
([docs/runbooks/evidence-search.md](../../docs/runbooks/evidence-search.md)).
