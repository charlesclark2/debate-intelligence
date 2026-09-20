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

## Implemented so far

### `domain/` — entities and enums (v1-e02-t01-domain-entities)

The V1 vocabulary as frozen, `extra="forbid"` Pydantic v2 models that already match the cloud data
model in architecture proposal §7, so V2 swaps storage rather than schemas.

| Module | Contents |
|---|---|
| `base.py` | `DomainModel`, `DomainEntity`, the `Ulid`/`UtcDatetime`/`Sha256Hex`/`HttpUrlStr`/`NonEmptyText` scalars, and the injectable id factory (`new_id`, `use_id_factory`) |
| `enums.py` | `AccessStatus`, `VerificationStatus`, `ProvenanceMode`, `SearchStatus`, `SourceType`, `SpanStyle`, `SpanPurpose`, `CitationFieldSource` |
| `article.py` | `Article`, `ArticleIdentifiers`, `SourceSnapshot` |
| `search.py` | `Search`, `SearchFilters`, `SearchResult` |
| `card.py` | `Card`, `CardSpan` |
| `citation.py` | `Citation`, `CitationField[T]` |
| `schema_export.py` | Renders the published JSON Schemas (no I/O; the script writes them) |

Things worth knowing before you add a field:

* **Models are frozen.** Produce a changed copy with `model.evolve(**changes)`, which revalidates,
  rather than `model_copy(update=...)`, which does not.
* **Entities declare their own `owner_id`/`organization_id`** instead of inheriting them, because a
  `Card` always belongs to a student while an `Article` describes a public source and may not.
* **`Card.provenance_mode` has no default.** Defaulting it would make the strongest provenance
  claim the platform can make the thing that happens when a caller says nothing.
* **Enum values are a wire format.** State enums are `SCREAMING_SNAKE_CASE`, label enums are
  `lower_snake_case`; both follow the tokens the PlanSpecs use. Changing one is a migration.

### `schemas/` — published JSON Schemas

One file per entity, generated and checked in:

```bash
uv run scripts/export_schemas.py          # regenerate after changing a model
uv run scripts/export_schemas.py --check  # exit 1 if a committed schema is stale
```

`tests/domain/test_schemas.py` fails when they drift, so a model change and its schema change
always land in the same commit.
