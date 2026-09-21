"""The ordered SQL that builds V1's local schema.

One `.sql` file per migration, named `<version>_<what it does>.sql`, applied in version order and
exactly once each by :func:`debate_core.integrations.local.sqlite_db.apply_migrations`. The files
are package data rather than Python string constants so that a schema change reads as a diff of
SQL and can be run by hand against a database with the `sqlite3` shell.

Rules for a new migration, which :func:`~debate_core.integrations.local.sqlite_db.load_migrations`
enforces:

* **Numbering is contiguous and starts at 1.** A gap means a migration file was lost.
* **A released migration is never edited.** Databases already carry its version, so the change
  would never be applied to them. Add the next migration instead.
* **Plain DDL and DML only.** No `BEGIN`/`COMMIT` — the runner owns the transaction — and no
  semicolon inside a string literal, because statements are split on semicolons.
"""
