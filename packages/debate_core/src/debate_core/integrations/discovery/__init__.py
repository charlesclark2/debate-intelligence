"""Discovery providers: the machinery every adapter is wrapped in, and later the adapters themselves.

Federated research asks scholarly, news and government sources the same question through one port,
:class:`~debate_core.application.ports.providers.SearchProvider` (architecture proposal §9).
v1-e07-t01-search-provider-contract put here what every adapter shares:

* :mod:`~debate_core.integrations.discovery.resilience` — :class:`ResilientProvider`, the per-call
  timeout, the clock-driven circuit breaker, the rate-limit hold and the health record.
* :mod:`~debate_core.integrations.discovery.registry` — :class:`ProviderRegistry`, which builds only
  the providers settings enable, wraps each one and reports their health.
* :mod:`~debate_core.integrations.discovery.http_failures` — the one mapping from an HTTP status and
  its `Retry-After` to a typed :class:`~debate_core.application.errors.ProviderError`.
* :mod:`~debate_core.integrations.discovery.redaction` — keeping credentials and the contact email
  out of messages, exceptions and log lines, httpx's included; and the one logger every module here
  writes to.

The adapters arrive with v1-e07-t02 to t07, each held to the shared contract kit in
:mod:`debate_core.testing.contracts.search_provider`:

* :mod:`~debate_core.integrations.discovery.openalex` — OpenAlex works search (v1-e07-t02).
* :mod:`~debate_core.integrations.discovery.feeds` — publisher RSS and Atom feeds per topic, and
  :mod:`~debate_core.integrations.discovery.google_news_rss` — Google News RSS search resolved to
  publisher URLs offline (v1-e07-t05). Their feed lists, safe parser and conditional-GET cache are
  :mod:`~debate_core.integrations.discovery.feed_config`,
  :mod:`~debate_core.integrations.discovery.feed_parsing` and
  :mod:`~debate_core.integrations.discovery.feed_cache`; the operator's live check of the feed lists is
  :mod:`~debate_core.integrations.discovery.feed_check`.

Crossref, Semantic Scholar, GDELT and government sources follow. Fan-out across providers
and deduplication of what they return are E08's.

Named `discovery`, not `search`: "search" is the student pilot's index (PM ruling, 2026-10-20).
This module imports nothing, so importing one submodule does not import the others.
"""
