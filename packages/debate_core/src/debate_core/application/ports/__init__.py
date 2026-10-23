"""The boundaries debate_core talks through.

Every use case in the platform reaches storage, a search provider, the web and a model through the
Protocols in this package's modules, and through nothing else. That is the rule that lets V1 run on SQLite
and the local filesystem while V2 runs the same use cases on DynamoDB, S3 and Bedrock
(architecture proposal §2, §6, §17).

| Port | Module | What it hides |
|---|---|---|
| `ArticleRepository` | `persistence` | Article and snapshot-metadata records |
| `SnapshotStore` | `persistence` | Immutable, content-addressed blobs |
| `EvidenceObjectStore` | `evidence_store` | Evidence objects stored under a name: manifests, reports |
| `CardRepository` | `persistence` | Card records and their revision checks |
| `CardEditLog` | `card_edit_log` | The audit trail of accepted student edits to cards (`v1-e03-t05`) |
| `SearchRepository` | `persistence` | Searches and their ranked results |
| `CaselistRepository` | `caselist` | Imported caselist and camp-file records (E30) |
| `ArchiveMember` / `SkippedMember` | `archive` | What reading a weekly archive yields (E30) |
| `CaselistArchiveSource` | `caselist_source` | OpenCaselist archive and OpenEv listings and downloads (E34) |
| `CaselistLoginSession` | `caselist_session` | The operator's OpenCaselist login and stored token (E34) |
| `DebateFileParser` | `debate_files` | Reading a debate `.docx` into sections and cards (E31) |
| `ParsedStore` | `parsed_store` | The parsed card store `caselist parse` writes (E31) |
| `Notifier` | `notifier` | Telling the operator an unattended run needs attention (E34) |
| `SearchProvider` | `providers` | One discovery source |
| `DiscoveryProviders` | `providers` | The enabled discovery sources and their health (E08) |
| `ArticleFetcher` | `providers` | HTTP retrieval |
| `ContentExtractor` | `providers` | Readable-text extraction |
| `ModelRouter` | `model_router` | Every LLM call: structured generation, embeddings, rerank |
| `Clock` | `providers` | The current time |
| `IdGenerator` | `providers` | New entity ids |

They are :class:`~typing.Protocol` classes on purpose. An adapter conforms structurally — it never
subclasses, never imports this package at runtime, and therefore cannot drag a dependency of its
own back across the boundary. Conformance is checked statically by pyright and, for the fakes in
:mod:`debate_core.testing.fakes`, at the point where each is built as its port (the `build_fake_*`
functions, and :class:`~debate_core.testing.fakes.all_ports.FakePorts` for the ten every service
takes).

How a service takes its ports is written up in `docs/architecture/ports-and-adapters.md`, with
:class:`~debate_core.application.services.article_registration.ArticleRegistrationService` as the
worked example.

**This module defines and imports nothing** (`v1-e01-t30`). Import a port from the module the table
names: `from debate_core.application.ports.persistence import CardRepository`. Importing any port
module runs this file first, so a name re-exported here would make every caller of one port import
all of them; `tests/architecture/test_fakes_reach_only_their_port.py` keeps it empty.
"""
