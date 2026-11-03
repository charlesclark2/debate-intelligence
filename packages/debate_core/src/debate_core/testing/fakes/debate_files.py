"""Fakes of the debate file parser (`v1-e31-t03`): one that answers as told, one that misbehaves."""

from __future__ import annotations

import os
import time
from collections.abc import Iterable

from debate_core.application.ports.debate_files import DebateFileParser
from debate_core.domain.caselist import SnapshotDate, SourceDocument, SourceFormat
from debate_core.domain.debate_files import ParsedDocument, ParseFailure, ParseFailureReason

__all__ = ["FakeDebateFileParser", "MisbehavingDebateFileParser", "build_fake_debate_file_parser"]


class FakeDebateFileParser:
    """Answers with whatever a test registered for a file's SHA-256.

    It really does the part of the job that callers branch on: a source whose format is not DOCX
    is refused with `UNSUPPORTED_FORMAT`, empty bytes are refused with `NOT_A_ZIP`, and anything
    else it has not been told about comes back as a document it read and found no cards in —
    which is a real outcome for a file of nothing but page furniture, not a stand-in for one.
    A test that cares what is *in* a document registers it with :meth:`add`.

    The real reading lives in `debate_core.integrations.docx_parser`; tests of that adapter build
    `.docx` packages rather than using this.
    """

    def __init__(
        self, *, parser_version: str = "fake-docx-parser-1", profile_version: str = "fake-profile-1"
    ) -> None:
        self._parser_version = parser_version
        self._profile_version = profile_version
        self._results: dict[str, ParsedDocument | ParseFailure] = {}
        self.calls: list[tuple[str, str]] = []
        """Every `(sha256, source_path)` this parser was asked for, in order."""

    @property
    def parser_version(self) -> str:
        return self._parser_version

    @property
    def profile_version(self) -> str:
        return self._profile_version

    def add(self, sha256: str, result: ParsedDocument | ParseFailure) -> None:
        """Register what `parse` should return for one file's bytes."""
        self._results[sha256] = result

    def parse(
        self,
        content: bytes,
        source: SourceDocument,
        *,
        source_path: str,
        snapshot: SnapshotDate | None = None,
        camp: str | None = None,
    ) -> ParsedDocument | ParseFailure:
        self.calls.append((source.sha256, source_path))
        registered = self._results.get(source.sha256)
        if registered is not None:
            return registered
        if source.source_format is not SourceFormat.DOCX:
            return ParseFailure(
                source_sha256=source.sha256,
                source_path=source_path,
                reason=ParseFailureReason.UNSUPPORTED_FORMAT,
                detail=f"{source.source_format} is stored unparsed in V1",
                parser_version=self._parser_version,
            )
        if not content:
            return ParseFailure(
                source_sha256=source.sha256,
                source_path=source_path,
                reason=ParseFailureReason.NOT_A_ZIP,
                detail="the file is empty",
                parser_version=self._parser_version,
            )
        return ParsedDocument(
            source_sha256=source.sha256,
            source_path=source_path,
            parser_version=self._parser_version,
            profile_version=self._profile_version,
        )


def build_fake_debate_file_parser() -> DebateFileParser:
    """Build the in-memory :class:`DebateFileParser` (v1-e31-t03), typed as the port.

    The annotation is the point, as it is on :class:`FakePorts`: pyright strict checks the fake
    against the Protocol here, so a signature that drifts fails in this package rather than in a
    pipeline test months later.
    """
    return FakeDebateFileParser()


class MisbehavingDebateFileParser:
    """A parser that stalls, dies or raises on the digests it is told to, and otherwise defers.

    What the parse pipeline's pool (`v1-e31-t06`) has to survive, made reproducible: a parse that
    never returns (the per-file time limit), a worker process that dies mid-parse, and a parser
    that raises instead of returning a failure. Picklable, so a spawned worker can run it.
    """

    def __init__(
        self,
        inner: DebateFileParser,
        *,
        stall: Iterable[str] = (),
        crash: Iterable[str] = (),
        raise_on: Iterable[str] = (),
        stall_seconds: float = 3600.0,
    ) -> None:
        self._inner = inner
        self._stall = frozenset(stall)
        self._crash = frozenset(crash)
        self._raise_on = frozenset(raise_on)
        self._stall_seconds = stall_seconds

    @property
    def parser_version(self) -> str:
        return self._inner.parser_version

    @property
    def profile_version(self) -> str:
        return self._inner.profile_version

    def parse(
        self,
        content: bytes,
        source: SourceDocument,
        *,
        source_path: str,
        snapshot: SnapshotDate | None = None,
        camp: str | None = None,
    ) -> ParsedDocument | ParseFailure:
        if source.sha256 in self._stall:
            time.sleep(self._stall_seconds)
        if source.sha256 in self._crash:
            os._exit(70)  # noqa: SLF001 - the point is a process that dies without unwinding
        if source.sha256 in self._raise_on:
            raise RuntimeError("synthetic parser bug")
        return self._inner.parse(content, source, source_path=source_path, snapshot=snapshot, camp=camp)
