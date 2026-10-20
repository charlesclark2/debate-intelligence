# debate_api

FastAPI service (V2) exposing `debate_core` use cases over REST/JSON with Cognito JWT auth.
Routes only — **no business logic here**. First spec:
`plan_specs/v2/e12-identity-api/t02-fastapi-service.yaml`.

## The student search pilot (V1)

Before V2's service, `debate_api` serves the student evidence search pilot of
[ADR-0019](../../docs/adr/0019-student-search-pilot-stack-sign-in-and-hosting.md): server-rendered
pages from a plain ASGI app, which uvicorn serves and the Lambda Web Adapter forwards function URL
events to. `debate_api.app:create_app` is the app factory. Today it holds `/healthz` and a
placeholder page (`v1-e39-t04`); sign-in and the search pages arrive with `v1-e39-t05` and
`v1-e39-t06`.

The image is built from [`Dockerfile`](Dockerfile) by `scripts/tub_deploy.sh`, never by hand
([docs/runbooks/evidence-search.md](../../docs/runbooks/evidence-search.md)).
