"""What a body's first bytes say it is, whatever the server declared (v1-e04-t02).

Servers mislabel documents: a PDF served as `application/octet-stream`, an article served as
`text/plain`, no `Content-Type` at all. The extractor (v1-e04-t04) has to choose a strategy, and the
access classifier (v1-e04-t03) has to tell an unsupported type from a mislabelled one, so the
fetcher records what the bytes look like beside what the server said, and replaces neither.

The signatures are a small subset of the WHATWG MIME Sniffing Standard (§7.1, "identifying a
resource with an unknown MIME type"): the document types the platform reads, and a few common
binary types so that an image or an archive is recognised as not being an article. Anything else
is `None`, which means "no opinion", not "unknown type".
"""

from __future__ import annotations

from typing import Final

__all__ = ["SNIFF_WINDOW_BYTES", "sniff_content_type"]

SNIFF_WINDOW_BYTES: Final = 1445
"""How much of the body is looked at: WHATWG's resource header length."""

_HTML_TAGS: Final = (
    b"<!doctype html",
    b"<html",
    b"<head",
    b"<script",
    b"<iframe",
    b"<h1",
    b"<div",
    b"<font",
    b"<table",
    b"<a",
    b"<style",
    b"<title",
    b"<b",
    b"<body",
    b"<br",
    b"<p",
    b"<!--",
)
"""WHATWG §7.1 step 2's HTML patterns, lower-cased. Each must be followed by a space or `>`."""

_TAG_TERMINATORS: Final = frozenset(b" \t\n\x0c\r>")

_BINARY_SIGNATURES: Final = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"PK\x03\x04", "application/zip"),
    (b"\x1f\x8b\x08", "application/gzip"),
)

_LEADING_WHITESPACE: Final = b" \t\n\x0c\r"
_UTF8_BOM: Final = b"\xef\xbb\xbf"


def sniff_content_type(body: bytes) -> str | None:
    """The media type `body`'s first bytes identify, or `None` when they match no signature.

    >>> sniff_content_type(b"%PDF-1.7\\n...")
    'application/pdf'
    >>> sniff_content_type(b"\\n  <!DOCTYPE html><html>")
    'text/html'
    >>> sniff_content_type(b"plain words") is None
    True
    """
    window = body[:SNIFF_WINDOW_BYTES]
    for signature, media_type in _BINARY_SIGNATURES:
        if window.startswith(signature):
            return media_type
    text = window.removeprefix(_UTF8_BOM).lstrip(_LEADING_WHITESPACE)
    if text.startswith(b"%PDF-"):
        return "application/pdf"
    lowered = text.lower()
    for tag in _HTML_TAGS:
        if lowered.startswith(tag) and len(lowered) > len(tag) and lowered[len(tag)] in _TAG_TERMINATORS:
            return "text/html"
    if text.startswith(b"<?xml"):
        return "application/xml"
    return None
