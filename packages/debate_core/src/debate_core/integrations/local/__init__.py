"""V1's local adapters: the filesystem and SQLite, so the CLI runs with no cloud account at all.

Everything the platform stores locally lives under one data directory, and every adapter here
takes that directory (or the database opened from it) as a constructor argument rather than
reading settings. One environment is one directory, and `debate-research --env test` cannot reach
what `--env dev` wrote:

::

    <data_dir>/
      blobs/sha256/ab/cd/abcd1234…def0   immutable snapshot bytes, by digest (FsSnapshotStore)
      debate.sqlite3                     articles, snapshots, cards, searches (SqliteDatabase)

The split is the same one the cloud uses (architecture proposal §7): bytes in a content-addressed
blob store — S3 in V2, this directory in V1 — and records in a database, DynamoDB in V2 and this
SQLite file in V1. Entities are stored as the JSON their own Pydantic model produces, with a few
key columns copied out beside it for indexing, so nothing is stored here that V2 cannot store too.

## Wiring

The composition root builds them; no adapter reads settings and no use case names one::

    database = SqliteDatabase.open(settings.storage.data_dir)
    service = ArticleRegistrationService(
        articles=SqliteArticleRepository(database),
        clock=SystemClock(),
        id_generator=UlidGenerator(),
    )

The four repositories share one :class:`~debate_core.integrations.local.sqlite_db.SqliteDatabase`
so that one connection is opened, one set of pragmas is applied and the schema is migrated once.

## Blocking I/O inside `async def`

The port methods are `async` because their V2 implementations really are I/O-bound over a network.
These do their file and SQLite work synchronously and never await: on a local disk a read is tens
of microseconds, and a thread hop per call would cost more than it saved while forcing the SQLite
connection to be shared across threads. It also makes each call atomic with respect to other tasks
on the event loop, since none of them can interleave at an `await`. If a V1 surface ever fans out
enough of these to matter, the fix is a thread pool inside these adapters and no change anywhere
else — which is the point of the port.
"""

from debate_core.integrations.local.fs_blob_store import (
    BLOB_DIRECTORY,
    BLOB_FILE_MODE,
    FsSnapshotStore,
)

__all__ = [
    "BLOB_DIRECTORY",
    "BLOB_FILE_MODE",
    "FsSnapshotStore",
]
