-- Migration 3: what each provider returned for a federated search (v1-e08-t01-federated-search-service).
--
-- One row per call the search made: the provider's answer exactly as it came back, or the reason
-- there was none, as the `ProviderStatus` JSON its own Pydantic model produced. Like a ranking it is
-- part of its search rather than an entity of its own, so it takes the same foreign key and cascade
-- as `search_results`, and it is replaced as a whole set.
--
-- `position` is the call's place in the search's own order (query by query, provider by provider),
-- which is the order the port promises to return. There is no lookup by provider: an audit reads a
-- search's whole record, never one call of it.

CREATE TABLE search_provider_statuses (
    search_id TEXT NOT NULL REFERENCES searches (search_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    document TEXT NOT NULL,
    PRIMARY KEY (search_id, position)
) STRICT;
