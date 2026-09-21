"""The boundary behind which a debate `.docx` is taken apart.

One Protocol, :class:`DebateFileParser`. The adapter that satisfies it in V1 is
`debate_core.integrations.docx_parser`, which reads OOXML with python-docx and lxml; the point of
the port is that nothing else in the platform has to know that. The caselist parse pipeline
(`v1-e31-t06`), the fingerprinter (`v1-e31-t04`) and V3's upload handler all ask this port for a
:class:`~debate_core.domain.debate_files.ParsedDocument` and never import a document library.

## Two conventions this port does not share with the others

*It is synchronous.* Every repository and provider port in this package is `async` because every
one of them waits on a socket or a disk. Parsing waits on nothing: it is arithmetic over bytes the
caller already has. Making it `async` would advertise a concurrency that is not there. A caller
that needs to parse a corpus in parallel runs this in a worker thread or a process pool, which is
what `v1-e31-t06` does.

*A refusal is a return value.* `parse` does not raise for a file it cannot read. A `.doc`, a PDF,
a macro-enabled package, a zip bomb and a truncated archive all come back as a
:class:`~debate_core.domain.debate_files.ParseFailure` naming the reason, because the caller is
usually a bulk import that has to record the failure and carry on. It raises only for a caller
error — bytes that are not bytes, a source whose format the caller has already mis-declared —
never for the contents of a file.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from debate_core.domain.caselist import SnapshotDate, SourceDocument
from debate_core.domain.debate_files import ParsedDocument, ParseFailure

__all__ = ["DebateFileParser"]


@runtime_checkable
class DebateFileParser(Protocol):
    """Turns the bytes of one imported file into sections, cards and provenance."""

    @property
    def parser_version(self) -> str:
        """Version recorded on every card this parser produces.

        It is part of a card's provenance claim: the same bytes, the same parser version and the
        same profile version produce the same cards. Bump it whenever the output changes.
        """
        ...

    def parse(
        self,
        content: bytes,
        source: SourceDocument,
        *,
        source_path: str,
        snapshot: SnapshotDate | None = None,
        camp: str | None = None,
    ) -> ParsedDocument | ParseFailure:
        """Read `content` as a debate `.docx`, or say why it could not be read.

        `source` supplies the identity and the origin: the SHA-256 the card's provenance records,
        whether the bytes came from a caselist archive or an OpenEv release, and which caselist.
        The parser does not re-hash the bytes to check them — that is the
        :class:`~debate_core.application.ports.persistence.SnapshotStore`'s job, and it has
        already done it by the time a file reaches here.

        `source_path` is the path inside the archive, which is what a person needs to find the
        file again. `snapshot` defaults to the source's `last_seen_snapshot`; a caller reading a
        file for a particular disclosure passes that disclosure's snapshot instead. `camp` is
        :attr:`~debate_core.domain.caselist.entities.CampFile.camp` for an OpenEv release, and
        None for a caselist disclosure.

        Returns a :class:`~debate_core.domain.debate_files.ParsedDocument`, or a
        :class:`~debate_core.domain.debate_files.ParseFailure` for a file that is not a readable
        `.docx`. Never a partially filled document.
        """
        ...
