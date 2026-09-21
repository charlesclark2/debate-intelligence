"""The key layout and the publish plan: pure functions, asserted against hand-written values.

Every key below is spelled out by hand or built from a synthetic body's own bytes; nothing is read
back from the function under test and then asserted equal to itself (working agreements §6).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST
from tests.fixtures.caselist.publish_expectations import (
    digest_of_body,
    expected_publish,
    expected_source_key,
)

from debate_core.application.caselist.publish_plan import (
    InvalidPublishTarget,
    LocalSnapshot,
    ManifestAction,
    ManifestSource,
    SourceAction,
    UnreadableManifest,
    build_publish_plan,
    digest_of_local_blob_key,
    local_blob_key,
    remote_source_prefix,
    snapshot_manifest_key,
    snapshot_of_manifest_key,
    source_key,
    sources_in_manifest,
    validate_publish_target,
)

pytestmark = pytest.mark.anyio

DIGEST_A = hashlib.sha256(b"synthetic source a").hexdigest()
DIGEST_B = hashlib.sha256(b"synthetic source b").hexdigest()
DIGEST_C = hashlib.sha256(b"synthetic source c").hexdigest()


# ------------------------------------------------------------------------------------------------
# Key layout
# ------------------------------------------------------------------------------------------------


class TestKeyLayout:
    def test_a_caselist_source_key_is_the_digest_under_the_caselist_prefix(self) -> None:
        digest = "ab" + "cd" + "0" * 60

        assert source_key("hsld26", "2026-09-15", digest) == (
            "raw/caselist/hsld26/sha256/ab/cd/abcd000000000000000000000000000000000000000000000000000000000000"
        )

    def test_a_camp_file_key_is_filed_under_its_topic_year(self) -> None:
        digest = "1f9e" + "7" * 60

        assert source_key("openev", "2026-ndi", digest) == f"raw/openev/2026/sha256/1f/9e/{digest}"

    def test_a_source_key_has_no_extension_and_nothing_but_the_digest_after_the_prefix(self) -> None:
        key = source_key("hsld26", "2026-09-15", DIGEST_A)

        tail = key.removeprefix("raw/caselist/hsld26/")
        assert tail == f"sha256/{DIGEST_A[0:2]}/{DIGEST_A[2:4]}/{DIGEST_A}"
        assert "." not in key

    def test_manifest_keys(self) -> None:
        assert snapshot_manifest_key("hsld26", "2026-09-15") == "manifests/hsld26/2026-09-15.jsonl"
        assert snapshot_manifest_key("openev", "2026-ndi") == "manifests/openev/2026-ndi.jsonl"

    def test_a_manifest_key_reads_back_to_its_snapshot(self) -> None:
        assert snapshot_of_manifest_key("hsld26", "manifests/hsld26/2026-09-15.jsonl") == "2026-09-15"
        assert snapshot_of_manifest_key("openev", "manifests/openev/2026-ndi.jsonl") == "2026-ndi"

    @pytest.mark.parametrize(
        "key",
        [
            "manifests/hsld26/notes.jsonl",
            "manifests/hsld26/2026-09-15.json",
            "manifests/hsld26/nested/2026-09-15.jsonl",
            "manifests/hspf26/2026-09-15.jsonl",
            "manifests/_suppression/suppression-list.jsonl",
        ],
    )
    def test_keys_that_are_not_this_caselists_manifests_read_back_as_none(self, key: str) -> None:
        assert snapshot_of_manifest_key("hsld26", key) is None

    def test_listing_prefixes(self) -> None:
        assert remote_source_prefix("hsld26") == "raw/caselist/hsld26/"
        assert remote_source_prefix("openev") == "raw/openev/"

    def test_a_local_blob_key_round_trips(self) -> None:
        key = local_blob_key(DIGEST_A)

        assert key == f"sha256/{DIGEST_A[0:2]}/{DIGEST_A[2:4]}/{DIGEST_A}"
        assert digest_of_local_blob_key(key) == DIGEST_A

    @pytest.mark.parametrize(
        "key",
        ["sha256/ab/cd/not-a-digest", f"sha256/00/00/{DIGEST_A}", f"other/{DIGEST_A}", "sha256"],
    )
    def test_keys_that_are_not_blobs_state_no_digest(self, key: str) -> None:
        assert digest_of_local_blob_key(key) is None

    @pytest.mark.parametrize(
        ("caselist", "snapshot"),
        [
            ("Maple Grove", None),
            ("hsld", None),
            ("../hsld26", None),
            ("hsld26", "2026-9-15"),
            ("hsld26", "2026-09-15T06:00"),
            ("hsld26", "0915"),
            ("openev", "ndi-2026"),
            ("openev", "2026-NDI"),
        ],
    )
    def test_names_with_no_place_in_the_layout_are_refused(
        self, caselist: str, snapshot: str | None
    ) -> None:
        with pytest.raises(InvalidPublishTarget):
            validate_publish_target(caselist, snapshot)


# ------------------------------------------------------------------------------------------------
# Reading a manifest
# ------------------------------------------------------------------------------------------------


def _row(classification: str | None, digest: str | None, size: int | None = 10, kind: str = "member") -> str:
    return json.dumps(
        {"kind": kind, "classification": classification, "sha256": digest, "byte_size": size, "school": "Maple Grove"}
    )


class TestManifestSources:
    def test_only_stored_rows_are_sources_and_each_digest_counts_once(self) -> None:
        lines = [
            _row("NEW", DIGEST_A),
            _row("DUPLICATE", DIGEST_A),
            _row("UNCHANGED", DIGEST_B, 20),
            _row("REMOVED", DIGEST_C),
            _row("SUPPRESSED", DIGEST_C),
            _row(None, None, None),
            json.dumps({"kind": "summary", "members": 6}),
        ]

        assert sources_in_manifest("manifests/hsld26/2026-09-15.jsonl", lines) == tuple(
            sorted((ManifestSource(DIGEST_A, 10), ManifestSource(DIGEST_B, 20)))
        )

    @pytest.mark.parametrize(
        "line",
        [
            "not json at all, Maple Grove QX",
            "[1, 2]",
            _row("NEW", None),
            _row("NEW", "Maple Grove-QX-Aff.docx"),
            _row("CHANGED", DIGEST_A, None),
            _row("CHANGED", DIGEST_A, -1),
        ],
    )
    def test_an_unusable_row_is_refused_by_line_number_without_quoting_it(self, line: str) -> None:
        with pytest.raises(UnreadableManifest) as refused:
            sources_in_manifest("manifests/hsld26/2026-09-15.jsonl", [_row("NEW", DIGEST_B), line])

        assert "line 2" in str(refused.value)
        assert "Maple Grove" not in str(refused.value)
        assert "QX" not in str(refused.value)

    def test_one_digest_with_two_sizes_is_refused(self) -> None:
        with pytest.raises(UnreadableManifest, match="two different sizes"):
            sources_in_manifest("k", [_row("NEW", DIGEST_A, 10), _row("DUPLICATE", DIGEST_A, 11)])

    async def test_the_synthetic_manifests_name_the_expected_bodies(self, imported_data_dir: Path) -> None:
        """Each week's manifest, read as the publisher reads it, against the hand-written list."""
        for week in expected_publish()["snapshots"]:
            key = f"manifests/{SYNTHETIC_CASELIST}/{week['snapshot']}.jsonl"
            lines = (imported_data_dir / "objects" / key).read_text(encoding="utf-8").splitlines()

            sources = sources_in_manifest(key, lines)

            assert {source.sha256 for source in sources} == {digest_of_body(name) for name in week["sources"]}
            stored_rows = sum(
                1
                for line in lines
                if json.loads(line).get("classification") in {"NEW", "UNCHANGED", "CHANGED", "DUPLICATE"}
            )
            assert stored_rows == week["stored_member_rows"], week["snapshot"]


# ------------------------------------------------------------------------------------------------
# The plan
# ------------------------------------------------------------------------------------------------


def _snapshot(snapshot: str, *sources: ManifestSource) -> LocalSnapshot:
    return LocalSnapshot(caselist="hsld26", snapshot=snapshot, sources=sources, manifest_size=99)


class TestPublishPlan:
    def test_absent_sources_upload_and_the_manifest_is_new(self) -> None:
        plan = build_publish_plan(
            "hsld26",
            [_snapshot("2026-09-01", ManifestSource(DIGEST_A, 10))],
            local_blobs={DIGEST_A},
            remote={},
        )

        (snapshot,) = plan.snapshots
        assert [(source.key, source.action) for source in snapshot.sources] == [
            (f"raw/caselist/hsld26/sha256/{DIGEST_A[0:2]}/{DIGEST_A[2:4]}/{DIGEST_A}", SourceAction.UPLOAD)
        ]
        assert snapshot.manifest_key == "manifests/hsld26/2026-09-01.jsonl"
        assert snapshot.manifest_action is ManifestAction.UPLOAD

    def test_listed_sources_are_verified_not_skipped_outright(self) -> None:
        key_a = source_key("hsld26", "2026-09-01", DIGEST_A)

        plan = build_publish_plan(
            "hsld26",
            [_snapshot("2026-09-01", ManifestSource(DIGEST_A, 10))],
            local_blobs={DIGEST_A},
            remote={key_a: 10, "manifests/hsld26/2026-09-01.jsonl": 99},
        )

        (snapshot,) = plan.snapshots
        assert snapshot.sources[0].action is SourceAction.VERIFY
        assert snapshot.manifest_action is ManifestAction.VERIFY
        assert plan.uploads == ()

    def test_a_listed_source_of_another_size_is_mismatched_and_blocks_the_manifest(self) -> None:
        key_a = source_key("hsld26", "2026-09-01", DIGEST_A)

        plan = build_publish_plan(
            "hsld26",
            [_snapshot("2026-09-01", ManifestSource(DIGEST_A, 10), ManifestSource(DIGEST_B, 5))],
            local_blobs={DIGEST_A, DIGEST_B},
            remote={key_a: 11},
        )

        (snapshot,) = plan.snapshots
        assert [source.sha256 for source in snapshot.blocked] == [DIGEST_A]
        assert snapshot.counts == {
            "upload": 1,
            "verify": 0,
            "uploaded_earlier": 0,
            "mismatched": 1,
            "missing_locally": 0,
            "suppressed": 0,
        }

    def test_a_source_missing_from_the_local_store_blocks_the_manifest(self) -> None:
        plan = build_publish_plan(
            "hsld26",
            [_snapshot("2026-09-01", ManifestSource(DIGEST_A, 10))],
            local_blobs=set(),
            remote={},
        )

        assert [source.action for source in plan.snapshots[0].blocked] == [SourceAction.MISSING_LOCALLY]

    def test_a_suppressed_source_is_never_uploaded_and_does_not_block(self) -> None:
        plan = build_publish_plan(
            "hsld26",
            [_snapshot("2026-09-01", ManifestSource(DIGEST_A, 10))],
            local_blobs={DIGEST_A},
            remote={},
            suppressed={DIGEST_A},
        )

        (snapshot,) = plan.snapshots
        assert snapshot.sources[0].action is SourceAction.SUPPRESSED
        assert snapshot.blocked == ()
        assert plan.uploads == ()

    def test_a_source_shared_by_two_snapshots_is_uploaded_once_by_the_earlier(self) -> None:
        plan = build_publish_plan(
            "hsld26",
            # Out of order on purpose: the plan is made in snapshot order regardless.
            [
                _snapshot("2026-09-08", ManifestSource(DIGEST_A, 10), ManifestSource(DIGEST_B, 5)),
                _snapshot("2026-09-01", ManifestSource(DIGEST_A, 10)),
            ],
            local_blobs={DIGEST_A, DIGEST_B},
            remote={},
        )

        assert [snapshot.snapshot for snapshot in plan.snapshots] == ["2026-09-01", "2026-09-08"]
        assert [source.action for source in plan.snapshots[0].sources] == [SourceAction.UPLOAD]
        later = {source.sha256: source.action for source in plan.snapshots[1].sources}
        assert later == {DIGEST_A: SourceAction.UPLOADED_EARLIER, DIGEST_B: SourceAction.UPLOAD}
        assert [source.sha256 for source in plan.uploads] == [DIGEST_A, DIGEST_B]
        assert plan.bytes_to_upload == 15

    def test_a_snapshot_of_another_caselist_is_refused(self) -> None:
        with pytest.raises(ValueError, match="belongs to"):
            build_publish_plan(
                "hspf26",
                [_snapshot("2026-09-01", ManifestSource(DIGEST_A, 10))],
                local_blobs={DIGEST_A},
                remote={},
            )

    async def test_the_synthetic_weeks_plan_against_an_empty_bucket(self, imported_data_dir: Path) -> None:
        """ac1's plan: each distinct body uploaded once, by the first week that holds it."""
        expected = expected_publish()
        snapshots: list[LocalSnapshot] = []
        for week in expected["snapshots"]:
            key = f"manifests/{SYNTHETIC_CASELIST}/{week['snapshot']}.jsonl"
            path = imported_data_dir / "objects" / key
            snapshots.append(
                LocalSnapshot(
                    caselist=SYNTHETIC_CASELIST,
                    snapshot=week["snapshot"],
                    sources=sources_in_manifest(key, path.read_text(encoding="utf-8").splitlines()),
                    manifest_size=path.stat().st_size,
                )
            )
        every_body = {name for week in expected["snapshots"] for name in week["sources"]}

        plan = build_publish_plan(
            SYNTHETIC_CASELIST,
            snapshots,
            local_blobs={digest_of_body(name) for name in every_body},
            remote={},
        )

        for planned, week in zip(plan.snapshots, expected["snapshots"], strict=True):
            assert planned.snapshot == week["snapshot"]
            assert planned.counts["upload"] == week["first_publish"]["upload"], week["snapshot"]
            assert planned.counts["uploaded_earlier"] == week["first_publish"]["uploaded_earlier"]
            assert planned.manifest_action is ManifestAction.UPLOAD
        assert {source.key for source in plan.uploads} == {expected_source_key(name) for name in every_body}
        assert len(plan.uploads) == expected["totals"]["source_objects"]
