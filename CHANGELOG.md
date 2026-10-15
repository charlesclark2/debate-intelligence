# Changelog

Each release of the Debate Research & Argument Intelligence Platform gets a section here when its
tag is cut from `main`. The release specs in [`plan_specs/releases/`](plan_specs/releases/) say
what each release is for, and the session reports in
[`docs/session-reports/`](docs/session-reports/) say how each task was done and checked. Dev
pre-releases (`vX.Y.Z-dev.N`) are not listed; each is a build of `dev` on the way to the next
version here.

## v1.0.0: Foundation and verified evidence core

The first release ([`plan_specs/releases/v1.0.yaml`](plan_specs/releases/v1.0.yaml)): the
repository and its delivery process, the domain core, and deterministic evidence verification,
before any language model is involved. Its three epics, E01, E02 and E03, are complete: 40 tasks,
each with a session report and a PM review.

### For students and coaches

* **`debate-research verify <manifest.json>`** re-cuts every card in a JSON card manifest from the
  source snapshot stored on this machine and compares it exactly. A card is `VERIFIED` only when its
  evidence reproduces character for character; anything else is `UNVERIFIED` and is listed as
  such, never presented as finished. Exit 0 means every card verified, 1 means at least one did not,
  and 2 is a usage error or a manifest that fails its schema.
* **`debate-research --version`** names the build, its channel, its environment and the commit it
  was built from, so a report of a problem can say exactly which build it came from.

### Evidence integrity (E03)

* Text normalization is deterministic and versioned, and covered by property-based tests.
* Every snapshot carries a SHA-256 provenance hash. Evidence on a card is addressed by character
  offsets into a stored snapshot, never stored as free text.
* An edit policy says what may change on a card (omissions, marked interpolations) and what may not,
  and the verifier enforces it.

### Domain core (E02)

* Pydantic models for articles, source snapshots, cards and their spans, citations, searches and
  results, matching the cloud data model, with owner and organization fields from the start.
* Every store and provider is reached through a port. The local filesystem and SQLite
  implementations pass a reusable contract suite that later cloud implementations must also pass.
* Settings and configuration per environment, with `dev` and `prod` kept apart.
* Import-boundary contracts keep cloud SDKs, HTTP clients and delivery frameworks out of the domain
  and application layers, checked in CI.

### Repository and delivery (E01)

* A uv workspace on Python 3.12 with ruff, pyright, pytest and spec validation, all run by CI on
  every pull request into `dev` or `main`.
* Two environments, `dev` and `main` (ADR-0013). Every merge to `dev` publishes a dev pre-release,
  which `validate-dev` installs and smoke-tests before a promotion into `main` may merge. Promotion
  guards, a sweep that re-runs them, and a back-merge job keep hotfixes on `main` from being lost.
* Installed builds carry every integration their commands need and run on a Python that uv manages.
  The install is the exact build that was checked.
* An unexpected error never prints its message on the command line, and a failure that may succeed
  on retry has its own exit code.
* The task workflow (`scripts/task`): a spec per task, a session report per session, a PM review
  before any pull request, and partial merges that can be resumed.
* The architecture proposal and ADR-0001 to 0009 under [`docs/`](docs/).

### Also on `main`, ahead of their releases

Work for later v1 releases merged before this tag and is in it, unfinished: the S3 evidence store
(E29), caselist ingestion (E30), debate file parsing (E31), the weekly caselist sync (E34), and the
team website and calendar (E36, E37). Each is described in its release's section when that release
is tagged; until then, [ROADMAP.md](ROADMAP.md) shows where each stands.
