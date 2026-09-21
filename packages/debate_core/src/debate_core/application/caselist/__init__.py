"""Turning a downloaded weekly archive into records: the parser, the importer and the manifest.

Three modules, in the order a file moves through them:

* :mod:`debate_core.application.caselist.path_parser` — one archive path in, a school, team code,
  side, tournament and round out, with warnings for everything it could not read.
* :mod:`debate_core.application.caselist.import_service` — classifies every member of one archive
  against the archives already imported, stores what is new, and reports the counts.
* :mod:`debate_core.application.caselist.manifest` — writes the per-snapshot JSONL record of what
  an import saw.

Nothing here touches a zip, a directory, a database or a bucket. Reading an archive is
:mod:`debate_core.integrations.local.archive_reader`'s job and storing what comes out of it is a
port's, which is what lets the same service run over a zip on a laptop and, in V2, over an object
in a bucket.
"""
