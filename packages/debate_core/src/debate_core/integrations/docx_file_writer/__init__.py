"""The lossless card writer: built evidence files whose cards are copied, never retyped (`v1-e33-t02`).

* :mod:`.base_template` generates the base document's style table from the E31 style profile.
* :mod:`.run_copier` copies one card's paragraphs out of its source document as OOXML.
* :mod:`.writer` assembles a whole file behind the
  :class:`~debate_core.application.ports.evidence_file_writer.EvidenceFileWriter` port, writes its
  provenance sidecar, and re-reads what it wrote before handing it back.

This is not the E06 DOCX renderer (v1.3), which renders newly cut cards from offsets: the two share
the style profile and nothing else, and nothing here imports it.
"""
