"""Adapters: the concrete implementations of the ports in :mod:`debate_core.application.ports`.

Each subpackage is named for the technology it hides, never for the port it satisfies, because a
port has more than one adapter and the technology is what a reader needs to know:

* :mod:`debate_core.integrations.local` — the filesystem and SQLite, which is all V1 needs
  (v1-e02-t03-local-repositories).
* `debate_core.integrations.s3` and the DynamoDB adapters arrive with V2 and satisfy the same
  ports, so no use case changes when the platform moves to the cloud (architecture proposal §17).

This is the outermost layer of the core: it may import :mod:`debate_core.domain` and
:mod:`debate_core.application`, and nothing in those two layers may import anything here. The
composition root — a CLI command, an API route, a worker, a test — is the only place that names an
adapter. See `docs/architecture/ports-and-adapters.md`.
"""
