# Files built with the provenance line

Four built files and their sidecars, as the writer built them before `v1-e33-t08`
(`2026.10.19-file-writer-2`, at `c3b9dee` on `dev`, where the task started), when a built file still
wrote the provenance line below each cite. `test_built_files_without_the_line.py` builds the same
four requests again and checks that each file has lost exactly its provenance-line paragraphs and
its header's last sentence, which pointed to them, and that each sidecar is unchanged byte for byte,
apart from `docx_sha256`, the built file's own hash, and `builder_version`, now
`2026.10.22-file-writer-3` (PM ruling, 2026-10-22).

| File | What it holds |
|---|---|
| `disclosed-cards` | Four disclosed cards of two teams, one re-tagged by the coach, an analytic, a cite-only card |
| `camp-card-with-its-release-record` | A disclosed card, then a camp card whose release record is joined |
| `camp-card-without-a-release-record` | The same, with no release record for the camp card |
| `no-disclosure-on-record` | One card whose occurrence has no disclosure on record |

Every source is synthetic, built in memory by the test with `debate_core.testing.docx_builder`, and
every school, team code, tournament, camp and file title is the repository's invented one. These
files are a record of the old writer's output, not this writer's, so nothing regenerates them: the
paragraphs a test takes out, the lines they held and the header sentences are written by hand in
the test.
