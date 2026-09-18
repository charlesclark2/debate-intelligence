# debate_core

The permanent domain platform: Pydantic entities, application services (use cases),
retrieval, evidence cutting/verification, argument graph, round state machine, and provider
interfaces. **No AWS SDK, Typer, or FastAPI imports** in `domain/` or `application/`.

Planned layout (src layout — see `plan_specs/v1/e02-domain-core/`):

```
src/debate_core/
  domain/        # Pydantic entities and enums
  application/   # use cases / services
  retrieval/     # article + source abstractions
  evidence/      # cutting, spans, verification
  arguments/     # graph extraction and coverage (V3)
  rounds/        # round state machine (V3)
  integrations/  # provider adapters behind ports
```
