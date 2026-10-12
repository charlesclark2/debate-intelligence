# Stored parsed-store records

`written_by_schema_version_1/` is a small parsed card store exactly as the build before
`v1-e31-t09` wrote it: parser `2026.09.20-docx-1`, `"schema_version": 1`, and `"tag": ""` for a card
the file gave no tag. It is what the `2026.09.20-docx-1` directories on the operator's machine and
in both buckets look like, and it is here so that a reader is tested against bytes an old build
really wrote rather than against records a test made up.

Its three sources are synthetic: the structural fixture `team-verbatim-file.docx`, an invented file
of two cards under one tag, and one invented failure. It holds no disclosure path, school or team
code, as no parsed store does.

It was written once, with the source tree of the task's start commit checked out, through
`LocalParsedStore`. It is never regenerated: a later build cannot write version 1.
[`test_parsed_store_schema_versions.py`](../../../packages/debate_core/tests/integrations/test_parsed_store_schema_versions.py)
reads it.
