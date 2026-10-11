"""What a removal left in the bucket, as `caselist status` reports it (`v1-e30-t10`).

Every bucket state here is made in moto: by the real publisher, by a real removal whose takedown
credential loses the bucket part-way, or by a deliberate edit to the bucket that the test names.
Every count asserted is worked out by hand beside the edit that causes it, never read back from a
run (working agreements §6).

S3 decides what "left" looks like, so the two shapes are tested separately:

* A takedown deletes each version by its id. Deleting the current version that way makes the next
  one current, so a takedown that stops among an object's versions leaves a *current* object with
  the older versions beneath it.
* A delete without a version id hides an object under a delete marker and keeps every version. No
  plain listing shows that key again; only the version listing does.

Nothing in the fixture archives is real caselist content, and every digest is of a synthetic body.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import DOCUMENT_BODIES, SYNTHETIC_CASELIST
from tests.fixtures.caselist.publish_expectations import digest_of_body, expected_source_key
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES as CAMP_BODIES

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.removal_residue import CaselistResidue, ResidueFile
from debate_core.application.caselist.removal_service import (
    CaselistRemovalService,
    RemovalIncomplete,
    TakedownAccess,
)
from debate_core.application.caselist.status_service import CaselistStatusReport, CaselistStatusService
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.errors import StoreAccessDenied, StoreUnavailable
from debate_core.application.ports.evidence_versions import EvidenceVersionStore, ObjectVersion
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore, S3EvidenceVersionStore
from debate_core.testing.fakes import InMemoryAppendOnlyRecord, empty_suppression_list

from .conftest import REQUEST, RemovalWorld

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

WEEK = "2026-09-01"
#: A file only the first synthetic week's Harbor team holds.
REMOVED = digest_of_body("harbor-octas-neg")
REMOVED_KEY = expected_source_key("harbor-octas-neg")
#: Another file of the same week, which nobody asked to have removed.
KEPT = digest_of_body("harbor-aff")
KEPT_KEY = expected_source_key("harbor-aff")
NOON = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def entry(
    sha256: str, *, action: SuppressionAction = SuppressionAction.SUPPRESS, disclosure: str | None = None
) -> str:
    reason = (
        ReasonCode.REQUESTED_BY_TEAM if action is SuppressionAction.SUPPRESS else ReasonCode.REMOVED_IN_ERROR
    )
    return SuppressionEntry(
        action=action,
        sha256=sha256,
        disclosure=disclosure,
        recorded_at=NOON,
        reason=reason,
        request_id=REQUEST,
    ).to_line()


def listing(*lines: str) -> RecordedSuppressionList:
    return RecordedSuppressionList(InMemoryAppendOnlyRecord("suppression list", list(lines)))


class RecordingVersions:
    """The everyday profile's version store, recording what it is asked and refusing all but a listing."""

    def __init__(self, inner: EvidenceVersionStore) -> None:
        self._inner = inner
        self.location = inner.location
        self.listed: list[str] = []

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        self.listed.append(prefix)
        return await self._inner.list_versions(prefix)

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        raise AssertionError("caselist status downloaded an object version")

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        raise AssertionError("caselist status deleted something")


class RefusedVersions:
    """A profile that has not been granted `s3:ListBucketVersions`: every listing is refused."""

    location = "s3://refused"

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        raise StoreAccessDenied("ListObjectVersions", f"{self.location}/{prefix}")

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        raise AssertionError("caselist status downloaded an object version")

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        raise AssertionError("caselist status deleted something")


@pytest.fixture
def versions(evidence_bucket: str, s3_client: S3Client) -> RecordingVersions:
    return RecordingVersions(S3EvidenceVersionStore(bucket=evidence_bucket, client=s3_client))


@pytest.fixture
async def published(local: LocalEvidence, bucket: S3EvidenceObjectStore) -> None:
    """The first synthetic week, in the bucket as `caselist publish` leaves it: one version of each."""
    service = CaselistPublishService(local=local, remote=bucket, suppression=empty_suppression_list())
    assert (await service.execute(await service.plan(SYNTHETIC_CASELIST, WEEK))).succeeded


async def status(
    local: LocalEvidence,
    bucket: S3EvidenceObjectStore,
    versions: EvidenceVersionStore,
    suppression: RecordedSuppressionList,
    caselist: str = SYNTHETIC_CASELIST,
    snapshot: str | None = WEEK,
) -> CaselistStatusReport:
    service = CaselistStatusService(local=local, remote=bucket, suppression=suppression, versions=versions)
    return await service.status(caselist, snapshot, residue=True)


def all_versions(client: S3Client, bucket: str) -> list[tuple[str, str, str]]:
    """Every data version and delete marker in the bucket: what "changed nothing" is checked against."""
    listed = client.list_object_versions(Bucket=bucket)
    return sorted(
        [(str(v.get("Key")), str(v.get("VersionId")), "version") for v in listed.get("Versions", [])]
        + [(str(m.get("Key")), str(m.get("VersionId")), "marker") for m in listed.get("DeleteMarkers", [])]
    )


# ------------------------------------------------------------------------------------------------
# What counts
# ------------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("published")
class TestWhatIsResidue:
    async def test_with_nothing_suppressed_the_caselist_is_checked_and_nothing_is_found(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, versions: RecordingVersions
    ) -> None:
        report = await status(local, bucket, versions, empty_suppression_list())

        assert report.residue == (CaselistResidue(caselist=SYNTHETIC_CASELIST, checked=True),)
        assert not report.residue_found
        assert report.in_sync

    async def test_versions_hidden_under_a_delete_marker_are_found_where_the_plain_listing_sees_nothing(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        versions: RecordingVersions,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        """One version from the publish, one more put over it, then a delete with no version id.

        Two data versions, neither current, and one delete marker. The object is gone from every
        plain listing, so the current-object check finds nothing, and both versions can be restored.
        """
        s3_client.put_object(Bucket=evidence_bucket, Key=REMOVED_KEY, Body=b"a second version")
        s3_client.delete_object(Bucket=evidence_bucket, Key=REMOVED_KEY)

        report = await status(local, bucket, versions, listing(entry(REMOVED)))

        assert report.suppressed_objects == (), "no plain listing shows the key"
        (caselist,) = report.residue
        assert caselist.checked
        assert caselist.files == (
            ResidueFile(sha256=REMOVED, current_objects=0, noncurrent_versions=2, delete_markers=1),
        )
        assert (caselist.current_objects, caselist.noncurrent_versions, caselist.delete_markers) == (0, 2, 1)
        assert report.residue_found
        assert not report.in_sync

    async def test_a_current_object_with_versions_beneath_it_is_counted_as_one_and_the_rest(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        versions: RecordingVersions,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        """Three versions, the newest current: what a takedown that never reached the object leaves."""
        for body in (b"a second version", b"a third version"):
            s3_client.put_object(Bucket=evidence_bucket, Key=REMOVED_KEY, Body=body)

        report = await status(local, bucket, versions, listing(entry(REMOVED)))

        (caselist,) = report.residue
        assert caselist.files == (
            ResidueFile(sha256=REMOVED, current_objects=1, noncurrent_versions=2, delete_markers=0),
        )
        assert report.suppressed_objects == (REMOVED_KEY,), "the current object is still reported as one"
        assert not report.in_sync

    async def test_a_removed_files_parsed_cards_are_counted_with_it_and_the_aggregates_are_not(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        versions: RecordingVersions,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        """The raw object (one current version) and its parsed file, written twice (one current, one not).

        The caselist's index is written three times and names no file in its key, so none of its
        versions is counted: what it holds cannot be told from its key.
        """
        version = f"parsed/{SYNTHETIC_CASELIST}/2026.09.20-docx-1"
        parsed = f"{version}/sha256/{REMOVED[0:2]}/{REMOVED[2:4]}/{REMOVED}.jsonl"
        for body in (b"first parse\n", b"second parse\n"):
            s3_client.put_object(Bucket=evidence_bucket, Key=parsed, Body=body)
        for body in (b"one\n", b"two\n", b"three\n"):
            s3_client.put_object(Bucket=evidence_bucket, Key=f"{version}/index.jsonl", Body=body)

        report = await status(local, bucket, versions, listing(entry(REMOVED)))

        (caselist,) = report.residue
        assert caselist.files == (
            ResidueFile(sha256=REMOVED, current_objects=2, noncurrent_versions=1, delete_markers=0),
        )

    async def test_a_file_nobody_removed_is_never_residue_whatever_versions_it_has(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        versions: RecordingVersions,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        """The kept file gets a second version and a delete marker; the list names another file."""
        s3_client.put_object(Bucket=evidence_bucket, Key=KEPT_KEY, Body=b"a second version")
        s3_client.delete_object(Bucket=evidence_bucket, Key=KEPT_KEY)
        s3_client.delete_object(
            Bucket=evidence_bucket,
            Key=REMOVED_KEY,
            VersionId=s3_client.head_object(Bucket=evidence_bucket, Key=REMOVED_KEY)["VersionId"],
        )

        report = await status(local, bucket, versions, listing(entry(REMOVED)))

        assert report.residue == (CaselistResidue(caselist=SYNTHETIC_CASELIST, checked=True),)

    async def test_a_file_withdrawn_from_one_path_only_is_still_held_and_is_not_residue(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        versions: RecordingVersions,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        """An entry for one disclosure of a shared file leaves the file with its other holders."""
        s3_client.put_object(Bucket=evidence_bucket, Key=REMOVED_KEY, Body=b"a second version")
        one_path = disclosure_digest(SYNTHETIC_CASELIST, "a/withdrawn/path.docx")

        report = await status(local, bucket, versions, listing(entry(REMOVED, disclosure=one_path)))

        assert report.residue == (CaselistResidue(caselist=SYNTHETIC_CASELIST, checked=True),)

    async def test_a_suppression_that_was_lifted_leaves_no_residue(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        versions: RecordingVersions,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        s3_client.put_object(Bucket=evidence_bucket, Key=REMOVED_KEY, Body=b"a second version")
        lifted = listing(entry(REMOVED), entry(REMOVED, action=SuppressionAction.UNSUPPRESS))

        report = await status(local, bucket, versions, lifted)

        assert report.residue == (CaselistResidue(caselist=SYNTHETIC_CASELIST, checked=True),)

    async def test_files_are_listed_in_digest_order_and_named_by_a_twelve_character_prefix(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        versions: RecordingVersions,
    ) -> None:
        report = await status(local, bucket, versions, listing(entry(REMOVED), entry(KEPT)))

        (caselist,) = report.residue
        assert [one.sha256 for one in caselist.files] == sorted([REMOVED, KEPT])
        assert [one.sha256_prefix for one in caselist.files] == sorted([REMOVED[:12], KEPT[:12]])


# ------------------------------------------------------------------------------------------------
# Read-only, with the everyday profile's grant, and only when asked
# ------------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("published")
class TestItOnlyLists:
    async def test_it_lists_versions_under_the_caselists_raw_and_parsed_prefixes_and_changes_nothing(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        versions: RecordingVersions,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        """Both prefixes are under `raw/` and `parsed/`, where the everyday profile may list versions.

        :class:`RecordingVersions` fails the test if a version is downloaded or deleted.
        """
        s3_client.put_object(Bucket=evidence_bucket, Key=REMOVED_KEY, Body=b"a second version")
        s3_client.delete_object(Bucket=evidence_bucket, Key=REMOVED_KEY)
        before = all_versions(s3_client, evidence_bucket)

        await status(local, bucket, versions, listing(entry(REMOVED)))

        assert versions.listed == [f"raw/caselist/{SYNTHETIC_CASELIST}/", f"parsed/{SYNTHETIC_CASELIST}/"]
        assert all_versions(s3_client, evidence_bucket) == before

    async def test_a_status_that_does_not_ask_lists_no_versions(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, versions: RecordingVersions
    ) -> None:
        """What `caselist pull` calls: the comparison alone, with no version listing added to it."""
        service = CaselistStatusService(
            local=local, remote=bucket, suppression=listing(entry(REMOVED)), versions=versions
        )

        report = await service.status(SYNTHETIC_CASELIST, WEEK)

        assert versions.listed == []
        assert report.residue == ()

    async def test_asking_without_a_version_store_is_refused_rather_than_reported_clean(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore
    ) -> None:
        service = CaselistStatusService(local=local, remote=bucket, suppression=empty_suppression_list())

        with pytest.raises(ValueError, match="version"):
            await service.status(SYNTHETIC_CASELIST, WEEK, residue=True)


@pytest.mark.usefixtures("published")
class TestARefusedListingIsNotChecked:
    async def test_it_says_not_checked_with_the_refusals_code_and_never_none(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        """Versions of a removed file are there, under a delete marker, and this profile cannot see them."""
        s3_client.put_object(Bucket=evidence_bucket, Key=REMOVED_KEY, Body=b"a second version")
        s3_client.delete_object(Bucket=evidence_bucket, Key=REMOVED_KEY)

        report = await status(local, bucket, RefusedVersions(), listing(entry(REMOVED)))

        (caselist,) = report.residue
        assert not caselist.checked
        assert caselist.not_checked_reason == "STORE_ACCESS_DENIED"
        assert (caselist.current_objects, caselist.noncurrent_versions, caselist.delete_markers) == (
            None,
            None,
            None,
        ), "a count of zero would say there is none"
        assert report.residue_not_checked == (SYNTHETIC_CASELIST,)
        assert not report.residue_found

    async def test_an_unchecked_caselist_does_not_fail_a_comparison_that_otherwise_agrees(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore
    ) -> None:
        """An environment without the grant still gets its answer about the snapshots."""
        report = await status(local, bucket, RefusedVersions(), empty_suppression_list())

        assert report.in_sync
        assert report.residue_not_checked == (SYNTHETIC_CASELIST,)

    async def test_a_bucket_that_does_not_answer_is_an_error_not_an_unchecked_caselist(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore
    ) -> None:
        class Unavailable(RefusedVersions):
            async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
                raise StoreUnavailable("ListObjectVersions", f"{self.location}/{prefix}", "timed out")

        with pytest.raises(StoreUnavailable):
            await status(local, bucket, Unavailable(), empty_suppression_list())


# ------------------------------------------------------------------------------------------------
# Camp files
# ------------------------------------------------------------------------------------------------


class TestACampFile:
    async def test_a_removed_camp_files_versions_are_found_under_the_year_it_was_released_in(
        self, removal_world: RemovalWorld
    ) -> None:
        """`raw/openev/` holds every year below it. One version from the publish and one put over it."""
        camp_file = hashlib.sha256(CAMP_BODIES["orchard-kritik"]).hexdigest()
        key = f"raw/openev/2026/sha256/{camp_file[0:2]}/{camp_file[2:4]}/{camp_file}"
        removal_world.client.put_object(Bucket=removal_world.bucket_name, Key=key, Body=b"a second version")
        versions = RecordingVersions(
            S3EvidenceVersionStore(bucket=removal_world.bucket_name, client=removal_world.client)
        )

        report = await status(
            removal_world.local, removal_world.bucket, versions, listing(entry(camp_file)), "openev", None
        )

        assert versions.listed == ["raw/openev/", "parsed/openev/"]
        (openev,) = report.residue
        assert openev.caselist == "openev"
        assert openev.files == (
            ResidueFile(sha256=camp_file, current_objects=1, noncurrent_versions=1, delete_markers=0),
        )


# ------------------------------------------------------------------------------------------------
# A takedown that stopped, on a later upload (v1-e30-t11)
# ------------------------------------------------------------------------------------------------

#: The synthetic caselist's Round 2 negative: one path, first disclosed on 09-01 and revised in place
#: the week after. Removing the first version takes the revision down with it (`v1-e30-t11`).
FIRST_VERSION = hashlib.sha256(DOCUMENT_BODIES["grove-round-2-neg-first"]).hexdigest()
REVISION = hashlib.sha256(DOCUMENT_BODIES["grove-round-2-neg-revised"]).hexdigest()


def raw_key(sha256: str) -> str:
    return f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{sha256[0:2]}/{sha256[2:4]}/{sha256}"


class LosesTheBucketAmongTheVersionsOf:
    """The takedown's version store: it deletes the first version of one file's object, then nothing."""

    def __init__(self, inner: EvidenceVersionStore, sha256: str) -> None:
        self._inner = inner
        self._sha256 = sha256
        self.location = inner.location

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        return await self._inner.list_versions(prefix)

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        await self._inner.get_version_file(version, destination)

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        if not any(self._sha256 in version.key for version in versions):
            return await self._inner.delete_versions(versions)
        await self._inner.delete_versions(versions[:1])
        raise StoreUnavailable("DeleteObject", f"{self.location}/{versions[0].key}", "the connection dropped")


class TestATakedownThatStoppedOnALaterUpload:
    async def test_the_later_uploads_versions_are_reported_and_a_rerun_leaves_none(
        self, removal_world: RemovalWorld
    ) -> None:
        """The removal names the first version; the plan adds the revision as a later upload.

        The revision's raw object is given two more versions, so it has three. The run deletes the
        named file's object, then deletes the first, current, version of the revision's and loses
        the bucket. S3 makes the next version current, so the revision is left with one current
        object and one noncurrent version. The named file is left with nothing.
        """
        world = removal_world
        for body in (b"a second version", b"a third version"):
            world.client.put_object(Bucket=world.bucket_name, Key=raw_key(REVISION), Body=body)
        real = S3EvidenceVersionStore(bucket=world.bucket_name, client=world.client)

        def stopping() -> TakedownAccess:
            return TakedownAccess(
                versions=LosesTheBucketAmongTheVersionsOf(real, REVISION),
                objects=world.bucket,
                profile="debate-dev-evidence-removal",
                bucket=world.bucket_name,
            )

        async def remove(service: CaselistRemovalService) -> None:
            plan = await service.plan(
                SourceSelector(FIRST_VERSION), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
            )
            assert [source.sha256 for source in plan.sources] == [FIRST_VERSION, REVISION]
            await service.execute(plan)

        with pytest.raises(RemovalIncomplete):
            await remove(world.service(takedown=stopping))

        stopped = await status(
            world.local, world.bucket, RecordingVersions(real), world.suppression(), snapshot=None
        )

        (caselist,) = stopped.residue
        assert caselist.files == (
            ResidueFile(sha256=REVISION, current_objects=1, noncurrent_versions=1, delete_markers=0),
        ), "the later upload, and not the file the request named"
        assert not stopped.in_sync

        await remove(world.service())

        finished = await status(
            world.local, world.bucket, RecordingVersions(real), world.suppression(), snapshot=None
        )
        assert finished.residue == (CaselistResidue(caselist=SYNTHETIC_CASELIST, checked=True),)
        assert finished.in_sync
