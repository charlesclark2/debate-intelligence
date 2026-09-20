#!/usr/bin/env python3
"""Turn a real debate `.docx` into a fixture that is safe to commit.

Team, caselist and camp files carry the names of real high-school students in three places at
once: the visible text ("Harker-JeCa-Aff"), the authorship metadata Word writes into every save
(`docProps/core.xml`, `<w:ins w:author=...>`, `word/people.xml`), and the comment threads a coach
left behind. A file is only allowed into `tests/fixtures/` once all three are gone, so this script
is the one gate every fixture in this repository passes through.

What it does, in order:

1. **Drops whole parts** that exist only to carry identity: comments and their companion parts,
   `word/people.xml`, `docProps/custom.xml` and every `customXml/` part. Their relationships and
   content-type overrides go with them, and comment markup is removed from the body so Word does
   not open the result complaining about a dangling reference.
2. **Blanks authorship fields**: `dc:creator`, `cp:lastModifiedBy`, the document title and
   keywords, `Company`, `Manager` and the `Template` path (which routinely contains a Windows
   user name), and every `w:author` / `w:initials` / `w:date` attribute on tracked changes.
3. **Replaces names and team codes** from a list the coach maintains **outside this repository**
   (see `--replacements`). Replacement is case-insensitive and works across run boundaries, so a
   name Word split into `Char` + `lie` is still caught — and the runs that do not overlap the
   match keep their formatting, because the point of a style fixture is its formatting.
4. **Verifies, and fails loudly.** The output package is re-opened and every part is searched with
   its XML tags stripped and its whitespace collapsed. If any string from the replacement list
   survives anywhere — in text, in an attribute, in a part name, or in the bytes of an embedded
   image — the script deletes the output and exits non-zero.

Nothing here is a runtime dependency: it is operator tooling, run by hand on files that stay on
the operator's machine. The replacement list is never committed; it names real students.

Usage::

    uv run python scripts/scrub_docx_fixture.py IN.docx --output OUT.docx \
        --replacements ~/.debate-intelligence/fixture-replacements.yaml

Owned by `v1-e31-t02-verbatim-style-profile`; reused by `v1-e31-t03-debate-docx-parser` and
`v1-e31-t05-parser-eval`.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import yaml
from lxml import etree

__all__ = [
    "REPLACEMENTS_SCHEMA_VERSION",
    "Replacement",
    "ReplacementList",
    "ScrubError",
    "ScrubResult",
    "load_replacement_list",
    "main",
    "scrub_package",
    "verify_scrubbed",
]

# --------------------------------------------------------------------------------------------
# OOXML namespaces and the parts that exist only to carry identity
# --------------------------------------------------------------------------------------------

W_NS: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CONTENT_TYPES_NS: Final = "http://schemas.openxmlformats.org/package/2006/content-types"
RELATIONSHIPS_NS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
CORE_PROPERTIES_NS: Final = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DUBLIN_CORE_NS: Final = "http://purl.org/dc/elements/1.1/"
EXTENDED_PROPERTIES_NS: Final = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

#: Parts removed outright. Comments carry a coach's name in every thread; `people.xml` is a
#: roster of everyone who has ever edited the file; custom XML and custom document properties are
#: where a school's document-management add-in stores whatever it likes.
DROPPED_PARTS: Final = frozenset(
    {
        "word/comments.xml",
        "word/commentsExtended.xml",
        "word/commentsIds.xml",
        "word/commentsExtensible.xml",
        "word/people.xml",
        "docProps/custom.xml",
    }
)

#: Every part under these prefixes is removed.
DROPPED_PART_PREFIXES: Final = ("customXml/",)

#: Comment markup left behind in the body once `word/comments.xml` is gone.
COMMENT_ELEMENTS: Final = frozenset(
    {"commentRangeStart", "commentRangeEnd", "commentReference", "annotationRef"}
)

#: Attributes that name a person or pin an edit to a moment. `w:author` is required wherever it
#: appears, so it is rewritten rather than removed; the rest are dropped.
AUTHOR_ATTRIBUTE_NAMES: Final = frozenset({"author", "oldAuthor"})
DROPPED_ATTRIBUTE_NAMES: Final = frozenset({"date", "oldDate", "initials", "userId", "providerId"})

#: What a tracked-change author becomes. Deliberately not a pseudonym: a reader of the fixture
#: should see that the field was emptied, not wonder who "J. Smith" is.
REDACTED_AUTHOR: Final = "Redacted"

#: Core and extended document properties blanked on every scrub. Titles and keywords are included
#: because Word seeds the title from the first heading, and debate files title themselves after
#: the team that cut them.
BLANKED_CORE_PROPERTIES: Final = (
    (DUBLIN_CORE_NS, "creator"),
    (DUBLIN_CORE_NS, "title"),
    (DUBLIN_CORE_NS, "subject"),
    (DUBLIN_CORE_NS, "description"),
    (CORE_PROPERTIES_NS, "lastModifiedBy"),
    (CORE_PROPERTIES_NS, "keywords"),
    (CORE_PROPERTIES_NS, "category"),
    (CORE_PROPERTIES_NS, "contentStatus"),
)
REMOVED_CORE_PROPERTIES: Final = ((CORE_PROPERTIES_NS, "lastPrinted"),)
BLANKED_EXTENDED_PROPERTIES: Final = ("Company", "Manager", "Template")

REPLACEMENTS_SCHEMA_VERSION: Final = 1

_TAG_PATTERN: Final = re.compile(r"<[^>]*>")
_WHITESPACE_PATTERN: Final = re.compile(r"\s+")


class ScrubError(RuntimeError):
    """The input is not a readable `.docx`, the replacement list is wrong, or scrubbing failed."""


def _qualified(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


# --------------------------------------------------------------------------------------------
# The replacement list (kept outside the repository)
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Replacement:
    """One string to remove and what to put in its place."""

    find: str
    replace: str

    @property
    def pattern(self) -> re.Pattern[str]:
        """Case-insensitive literal match, with any run of whitespace matching any other.

        Word splits a name across runs and sometimes across a non-breaking space; the whitespace
        relaxation is what makes `Jamie  Okafor` and `Jamie Okafor` the same string to this
        script.
        """
        parts = [re.escape(part) for part in self.find.split()]
        return re.compile(r"\s+".join(parts), re.IGNORECASE)


@dataclass(frozen=True)
class ReplacementList:
    """The coach-supplied list of names and team codes, and where it was read from."""

    replacements: tuple[Replacement, ...]
    source_path: Path | None = None

    def apply(self, text: str) -> str:
        """Return `text` with every listed string replaced."""
        for replacement in self.replacements:
            text = replacement.pattern.sub(replacement.replace, text)
        return text

    def survivors(self, text: str) -> list[str]:
        """Return the `find` strings still present in `text`, in list order."""
        return [item.find for item in self.replacements if item.pattern.search(text)]


def load_replacement_list(path: Path) -> ReplacementList:
    """Read and validate the replacement list.

    The file is YAML and looks like this. It lives outside the repository — it names real
    students — and is the one input to this script that must never be committed::

        version: 1
        replacements:
          - find: Jamie Okafor
            replace: Rowan Fields
          - find: WFB
            replace: Northside
    """
    if not path.is_file():
        raise ScrubError(
            f"replacement list not found: {path}. Keep it outside the repository "
            f"(for example ~/.debate-intelligence/fixture-replacements.yaml) and pass --replacements."
        )
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ScrubError(f"replacement list {path} is not valid YAML: {error}") from error
    if not isinstance(document, dict):
        raise ScrubError(f"replacement list {path} must be a mapping with `version` and `replacements`.")
    version = document.get("version")
    if version != REPLACEMENTS_SCHEMA_VERSION:
        raise ScrubError(
            f"replacement list {path} has version {version!r}; this script reads version "
            f"{REPLACEMENTS_SCHEMA_VERSION}."
        )
    entries = document.get("replacements")
    if not isinstance(entries, list) or not entries:
        raise ScrubError(f"replacement list {path} must carry a non-empty `replacements` list.")

    replacements: list[Replacement] = []
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ScrubError(f"replacement {position} in {path} must be a mapping with `find` and `replace`.")
        unknown = set(entry) - {"find", "replace"}
        if unknown:
            raise ScrubError(
                f"replacement {position} in {path} has unknown key(s): {', '.join(sorted(unknown))}."
            )
        find = entry.get("find")
        replace = entry.get("replace")
        if not isinstance(find, str) or not find.strip():
            raise ScrubError(f"replacement {position} in {path} needs a non-empty `find` string.")
        if not isinstance(replace, str):
            raise ScrubError(f"replacement {position} in {path} needs a `replace` string.")
        replacements.append(Replacement(find=find.strip(), replace=replace))

    for replacement in replacements:
        for other in replacements:
            if other.pattern.search(replacement.replace):
                raise ScrubError(
                    f"replacement for {replacement.find!r} writes text that still matches "
                    f"{other.find!r}; the scrub would never converge."
                )
    return ReplacementList(replacements=tuple(replacements), source_path=path)


# --------------------------------------------------------------------------------------------
# Scrubbing one package
# --------------------------------------------------------------------------------------------


@dataclass
class ScrubResult:
    """What one scrub did, in terms safe to print: counts and part names, never document text."""

    dropped_parts: list[str] = field(default_factory=list)
    blanked_properties: list[str] = field(default_factory=list)
    redacted_author_attributes: int = 0
    dropped_identity_attributes: int = 0
    removed_comment_elements: int = 0
    replaced_occurrences: int = 0
    parts_rewritten: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        return [
            f"parts dropped:                 {len(self.dropped_parts)}"
            + (f" ({', '.join(sorted(self.dropped_parts))})" if self.dropped_parts else ""),
            f"document properties blanked:   {len(self.blanked_properties)}"
            + (f" ({', '.join(self.blanked_properties)})" if self.blanked_properties else ""),
            f"tracked-change authors redacted: {self.redacted_author_attributes}",
            f"identity attributes dropped:   {self.dropped_identity_attributes}",
            f"comment markup removed:        {self.removed_comment_elements}",
            f"name/team-code replacements:   {self.replaced_occurrences}",
            f"parts rewritten:               {len(self.parts_rewritten)}",
        ]


def _is_dropped_part(name: str) -> bool:
    return name in DROPPED_PARTS or name.startswith(DROPPED_PART_PREFIXES)


def _parse_xml(data: bytes) -> etree._Element:
    """Parse an OOXML part with entity resolution and network access switched off."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    return etree.fromstring(data, parser=parser)


def _serialize_xml(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _resolve_relationship_target(rels_part_name: str, target: str) -> str:
    """Resolve a relationship target to a package part name."""
    base = Path(rels_part_name).parent.parent  # word/_rels/document.xml.rels -> word
    if target.startswith("/"):
        return target.lstrip("/")
    resolved = (base / target).as_posix() if str(base) != "." else target
    while "/../" in resolved:
        resolved = re.sub(r"[^/]+/\.\./", "", resolved, count=1)
    return resolved.lstrip("/")


def _strip_dropped_relationships(root: etree._Element, rels_part_name: str) -> int:
    removed = 0
    for relationship in list(root):
        if relationship.get("TargetMode") == "External":
            continue
        target = relationship.get("Target")
        if target is None:
            continue
        if _is_dropped_part(_resolve_relationship_target(rels_part_name, target)):
            parent = relationship.getparent()
            if parent is not None:
                parent.remove(relationship)
                removed += 1
    return removed


def _strip_dropped_content_type_overrides(root: etree._Element) -> int:
    removed = 0
    for override in list(root.findall(_qualified(CONTENT_TYPES_NS, "Override"))):
        part_name = (override.get("PartName") or "").lstrip("/")
        if _is_dropped_part(part_name):
            root.remove(override)
            removed += 1
    return removed


def _blank_core_properties(root: etree._Element, result: ScrubResult) -> None:
    for namespace, tag in BLANKED_CORE_PROPERTIES:
        for element in root.findall(_qualified(namespace, tag)):
            if element.text:
                result.blanked_properties.append(tag)
            element.text = None
            # `dcterms:` typed fields keep their xsi:type; plain ones have no attributes to keep.
    for namespace, tag in REMOVED_CORE_PROPERTIES:
        for element in list(root.findall(_qualified(namespace, tag))):
            root.remove(element)
            result.blanked_properties.append(tag)


def _blank_extended_properties(root: etree._Element, result: ScrubResult) -> None:
    for tag in BLANKED_EXTENDED_PROPERTIES:
        for element in root.findall(_qualified(EXTENDED_PROPERTIES_NS, tag)):
            if element.text:
                result.blanked_properties.append(tag)
            element.text = None


def _scrub_identity_attributes(root: etree._Element, result: ScrubResult) -> None:
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        for name in list(element.attrib):
            local = etree.QName(name).localname if name.startswith("{") else name
            if local in AUTHOR_ATTRIBUTE_NAMES:
                element.set(name, REDACTED_AUTHOR)
                result.redacted_author_attributes += 1
            elif local in DROPPED_ATTRIBUTE_NAMES:
                del element.attrib[name]
                result.dropped_identity_attributes += 1


def _remove_comment_markup(root: etree._Element, result: ScrubResult) -> None:
    for element in list(root.iter()):
        if not isinstance(element.tag, str) or not element.tag.startswith(f"{{{W_NS}}}"):
            continue
        if etree.QName(element).localname not in COMMENT_ELEMENTS:
            continue
        parent = element.getparent()
        if parent is None:
            continue
        parent.remove(element)
        result.removed_comment_elements += 1
        # A run that existed only to anchor a comment reference is now empty; drop it too.
        if etree.QName(parent).localname == "r" and not [
            child for child in parent if etree.QName(child).localname != "rPr"
        ]:
            grandparent = parent.getparent()
            if grandparent is not None:
                grandparent.remove(parent)


def _replace_in_attributes_and_stray_text(
    root: etree._Element, replacements: ReplacementList, result: ScrubResult
) -> None:
    """Apply replacements everywhere except `w:t`, which the run-spanning pass handles."""
    text_tag = _qualified(W_NS, "t")
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        for name, value in list(element.attrib.items()):
            replaced = replacements.apply(value)
            if replaced != value:
                element.set(name, replaced)
                result.replaced_occurrences += 1
        if element.tag != text_tag and element.text:
            replaced = replacements.apply(element.text)
            if replaced != element.text:
                element.text = replaced
                result.replaced_occurrences += 1
        if element.tail:
            replaced = replacements.apply(element.tail)
            if replaced != element.tail:
                element.tail = replaced
                result.replaced_occurrences += 1


def _replace_across_runs(root: etree._Element, replacements: ReplacementList, result: ScrubResult) -> None:
    """Replace listed strings in paragraph text, even when Word split them across runs.

    Matches are rewritten in place over the `w:t` nodes they cover, right to left so earlier
    offsets stay valid. Only the nodes a match actually touches are edited, so every run outside
    the match keeps its formatting — which is the entire value of a style fixture.
    """
    text_tag = _qualified(W_NS, "t")
    for paragraph in root.iter(_qualified(W_NS, "p")):
        nodes = [node for node in paragraph.iter(text_tag)]
        if not nodes:
            continue
        spans: list[tuple[etree._Element, int, int]] = []
        offset = 0
        for node in nodes:
            length = len(node.text or "")
            spans.append((node, offset, offset + length))
            offset += length
        joined = "".join(node.text or "" for node in nodes)
        matches: list[tuple[int, int, str]] = []
        for replacement in replacements.replacements:
            for match in replacement.pattern.finditer(joined):
                matches.append((match.start(), match.end(), replacement.replace))
        if not matches:
            continue
        matches.sort(key=lambda item: item[0])
        accepted: list[tuple[int, int, str]] = []
        for start, end, text in matches:
            if accepted and start < accepted[-1][1]:
                continue  # overlapping match; the first listed replacement wins
            accepted.append((start, end, text))

        for start, end, text in reversed(accepted):
            touched = [span for span in spans if span[1] < end and start < span[2]]
            if not touched:
                continue
            first_node, first_start, _ = touched[0]
            last_node, last_start, last_end = touched[-1]
            first_text = first_node.text or ""
            last_text = last_node.text or ""
            suffix = last_text[end - last_start :] if end <= last_end else ""
            if first_node is last_node:
                first_node.text = first_text[: start - first_start] + text + suffix
            else:
                first_node.text = first_text[: start - first_start] + text
                for middle_node, _, _ in touched[1:-1]:
                    middle_node.text = ""
                last_node.text = suffix
            result.replaced_occurrences += 1
        for node in nodes:
            if node.text:
                if node.text != node.text.strip():
                    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            else:
                _drop_or_empty(node)


def _drop_or_empty(text_node: etree._Element) -> None:
    """Tidy a `w:t` a replacement emptied.

    Its run is removed when nothing else in it carries content, and otherwise the node is given a
    null rather than an empty string. Both branches serialize the same way on a second pass, which
    is what makes a re-scrub of an already-scrubbed file a no-op.
    """
    run = text_node.getparent()
    if run is not None and etree.QName(run).localname == "r":
        remaining = [
            child for child in run if etree.QName(child).localname != "rPr" and child is not text_node
        ]
        if not remaining:
            parent = run.getparent()
            if parent is not None:
                parent.remove(run)
                return
    text_node.text = None


def _scrub_xml_part(part_name: str, data: bytes, replacements: ReplacementList, result: ScrubResult) -> bytes:
    root = _parse_xml(data)
    if part_name == "[Content_Types].xml":
        _strip_dropped_content_type_overrides(root)
    elif part_name.endswith(".rels"):
        _strip_dropped_relationships(root, part_name)
    elif part_name == "docProps/core.xml":
        _blank_core_properties(root, result)
    elif part_name == "docProps/app.xml":
        _blank_extended_properties(root, result)

    _scrub_identity_attributes(root, result)
    _remove_comment_markup(root, result)
    _replace_in_attributes_and_stray_text(root, replacements, result)
    _replace_across_runs(root, replacements, result)
    return _serialize_xml(root)


def _looks_like_xml(part_name: str, data: bytes) -> bool:
    return part_name.endswith((".xml", ".rels")) and data.lstrip()[:1] == b"<"


def scrub_package(source: Path, destination: Path, replacements: ReplacementList) -> ScrubResult:
    """Write a scrubbed copy of the `.docx` at `source` to `destination`.

    Raises :class:`ScrubError` if the input is not a readable zip package or if any listed string
    survives into the output; in the failure case `destination` is removed rather than left behind
    as a half-scrubbed file somebody might commit.
    """
    if not source.is_file():
        raise ScrubError(f"input file not found: {source}")
    result = ScrubResult()
    try:
        with zipfile.ZipFile(source) as archive:
            entries = [info for info in archive.infolist() if not info.is_dir()]
            payload: list[tuple[str, bytes]] = []
            for info in entries:
                if _is_dropped_part(info.filename):
                    result.dropped_parts.append(info.filename)
                    continue
                data = archive.read(info.filename)
                if _looks_like_xml(info.filename, data):
                    data = _scrub_xml_part(info.filename, data, replacements, result)
                    result.parts_rewritten.append(info.filename)
                payload.append((info.filename, data))
    except zipfile.BadZipFile as error:
        raise ScrubError(f"{source} is not a readable .docx package: {error}") from error

    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in payload:
            out.writestr(name, data)

    violations = verify_scrubbed(destination, replacements)
    if violations:
        destination.unlink(missing_ok=True)
        raise ScrubError(
            "scrub failed verification; the output was deleted. Still present after scrubbing:\n  "
            + "\n  ".join(violations)
        )
    return result


# --------------------------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------------------------


def _readable_text(data: bytes) -> str:
    """Decode a part and strip XML tags, so run-split text reads as one string."""
    text = data.decode("utf-8", errors="ignore")
    return _WHITESPACE_PATTERN.sub(" ", _TAG_PATTERN.sub(" ", text))


def verify_scrubbed(package: Path, replacements: ReplacementList) -> list[str]:
    """Return a human-readable violation for every listed string still present in `package`.

    Three views of each part are searched: the raw bytes as text (catches attributes and part
    names), the same text with XML tags stripped and whitespace collapsed (catches a name Word
    split across runs), and, for parts that are not XML, the bytes themselves — an embedded image
    or OLE object can carry a name too.
    """
    violations: list[str] = []
    with zipfile.ZipFile(package) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if _is_dropped_part(info.filename):
                violations.append(f"part {info.filename} should have been dropped")
            for survivor in replacements.survivors(info.filename):
                violations.append(f"part name {info.filename!r} still contains {survivor!r}")
            data = archive.read(info.filename)
            raw = data.decode("utf-8", errors="ignore")
            for survivor in set(replacements.survivors(raw)) | set(
                replacements.survivors(_readable_text(data))
            ):
                violations.append(f"{info.filename} still contains {survivor!r}")
    return sorted(set(violations))


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scrub_docx_fixture.py",
        description="Scrub a debate .docx so it can be committed as a test fixture.",
    )
    parser.add_argument("input", type=Path, help="The .docx to scrub. Never modified in place.")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Where to write the scrubbed copy. Deleted again if verification fails.",
    )
    parser.add_argument(
        "--replacements",
        type=Path,
        required=True,
        help=(
            "YAML list of names and team codes to replace. Kept outside this repository; "
            "see the module docstring for the format."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    try:
        replacements = load_replacement_list(arguments.replacements)
        result = scrub_package(arguments.input, arguments.output, replacements)
    except ScrubError as error:
        print(f"scrub_docx_fixture: {error}", file=sys.stderr)
        return 1
    print(f"scrubbed -> {arguments.output}")
    for line in result.summary_lines():
        print(f"  {line}")
    print(
        "  verification: no string from the replacement list survives in any part of the output.",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
