"""Reading a debate `.docx`: the V1 adapter behind
:class:`~debate_core.application.ports.debate_files.DebateFileParser`.

Three modules, in the order a file passes through them:

* :mod:`~debate_core.integrations.docx_parser.package` opens the zip and the XML safely, and
  refuses what it will not read.
* :mod:`~debate_core.integrations.docx_parser.runs` turns paragraphs into text and
  character-offset formatting spans, copying the text exactly.
* :mod:`~debate_core.integrations.docx_parser.parser` classifies the paragraphs through the
  Verbatim style profile, groups them into cards and attaches provenance.

This is the only package in the repository that may import `lxml`, and the import-linter contract
in the workspace root enforces that. Everything else reaches a parsed file through the port.
"""

from debate_core.integrations.docx_parser.package import (
    DEFAULT_PACKAGE_LIMITS,
    DocxPackage,
    DocxPackageError,
    PackageLimits,
    open_debate_docx,
)
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser

__all__ = [
    "DEFAULT_PACKAGE_LIMITS",
    "DOCX_PARSER_VERSION",
    "DebateDocxParser",
    "DocxPackage",
    "DocxPackageError",
    "PackageLimits",
    "open_debate_docx",
]
