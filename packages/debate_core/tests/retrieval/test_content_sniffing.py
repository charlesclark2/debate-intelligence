"""What a body's first bytes say it is, by WHATWG's signatures."""

from __future__ import annotations

import pytest

from debate_core.retrieval.content_sniffing import SNIFF_WINDOW_BYTES, sniff_content_type


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b"%PDF-1.7\n1 0 obj", "application/pdf"),
        (b"\xef\xbb\xbf\n  %PDF-1.4", "application/pdf"),
        (b"<!DOCTYPE html><html>", "text/html"),
        (b"\n\t <!doctype HTML>", "text/html"),
        (b"<html lang='en'>", "text/html"),
        (b"<p>first paragraph", "text/html"),
        (b"<!-- generated -->", "text/html"),
        (b"<?xml version='1.0'?><rss>", "application/xml"),
        (b"\x89PNG\r\n\x1a\n....", "image/png"),
        (b"\xff\xd8\xff\xe0JFIF", "image/jpeg"),
        (b"GIF89a....", "image/gif"),
        (b"PK\x03\x04docx", "application/zip"),
        (b"\x1f\x8b\x08\x00", "application/gzip"),
    ],
)
def test_a_known_signature_is_recognised(body: bytes, expected: str) -> None:
    assert sniff_content_type(body) == expected


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"plain words about grid storage",
        b"<paragraph>not an html tag</paragraph>",
        b"<pre>",
        b"see %PDF- in the text",
        b'{"json": true}',
    ],
)
def test_anything_else_is_no_opinion(body: bytes) -> None:
    assert sniff_content_type(body) is None


def test_only_the_window_is_read() -> None:
    assert sniff_content_type(b" " * SNIFF_WINDOW_BYTES + b"<html>") is None
