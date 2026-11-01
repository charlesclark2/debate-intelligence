"""Each camp file's OpenEv id, read from its release manifest, for the search index (`v1-e39-t16`).

The search index links a camp card to its file on OpenEv by the id the release manifest's rows carry
since `v1-e30-t14`. The rows here are written by hand in the manifest's own shape (working agreement
6); every id, digest, camp and file name is invented (data-use policy, rule 5).
"""

from __future__ import annotations

import json
from typing import Any, Final

from debate_core.application.caselist.openev_manifest import openev_ids_by_source, read_recorded_release
from debate_core.application.caselist.publish_plan import snapshot_manifest_key

KEY: Final = snapshot_manifest_key("openev", "2026-policy")


def sha(letter: str) -> str:
    return letter * 64


def member(path: str, sha256: str | None, **fields: Any) -> str:
    row: dict[str, Any] = {
        "schema_version": 1,
        "kind": "member",
        "path": path,
        "sha256": sha256,
        "classification": "NEW",
        "skip_reason": None,
        "openev_id": None,
        "upstream_path_sha256": None,
    }
    return json.dumps(row | fields)


def summary() -> str:
    return json.dumps(
        {"schema_version": 1, "kind": "summary", "caselist": "openev", "snapshot": "2026-policy"}
    )


def ids(*lines: str) -> dict[str, int]:
    return openev_ids_by_source(read_recorded_release(KEY, lines))


def test_a_stored_file_has_the_id_its_row_carries() -> None:
    assert ids(member("Invented Camp/one.docx", sha("a"), openev_id=4021), summary()) == {sha("a"): 4021}


def test_a_file_at_two_paths_has_the_smaller_id_whatever_order_the_rows_are_in() -> None:
    """The same bytes uploaded twice, under two ids: either is the file, and one rule picks the first."""
    first = member("Invented Camp/one.docx", sha("b"), openev_id=4030)
    second = member("Invented Camp/copy.docx", sha("b"), classification="DUPLICATE", openev_id=4025)
    assert ids(first, second) == ids(second, first) == {sha("b"): 4025}


def test_a_hand_imports_id_counts_without_a_path_digest() -> None:
    """A file named `openev-<id>-...` gives its row the id and no path digest; the id is still the file's."""
    row = member("openev-4040-invented.docx", sha("c"), openev_id=4040, upstream_path_sha256=None)
    assert ids(row) == {sha("c"): 4040}


def test_rows_that_carry_no_usable_id_give_none() -> None:
    no_key = json.loads(member("Invented Camp/older.docx", sha("d")))
    del no_key["openev_id"], no_key["upstream_path_sha256"]
    lines = (
        json.dumps(no_key),
        member("Invented Camp/null.docx", sha("e"), openev_id=None),
        member("Invented Camp/text.docx", sha("f"), openev_id="4021"),
        member("Invented Camp/bool.docx", sha("1"), openev_id=True),
        member("Invented Camp/zero.docx", sha("2"), openev_id=0),
        member("Invented Camp/negative.docx", sha("3"), openev_id=-4021),
        member("Invented Camp/float.docx", sha("4"), openev_id=4021.0),
    )
    assert ids(*lines) == {}


def test_a_row_that_stored_nothing_gives_no_id() -> None:
    """A skipped member (macOS junk) has no classification and is no camp file, whatever its row holds."""
    skipped = member("__MACOSX/._one.docx", sha("5"), classification=None, skip_reason="JUNK", openev_id=4050)
    no_digest = member("Invented Camp/none.docx", None, openev_id=4051)
    assert ids(skipped, no_digest) == {}


def test_a_release_with_no_manifest_gives_no_ids() -> None:
    assert ids() == {}
