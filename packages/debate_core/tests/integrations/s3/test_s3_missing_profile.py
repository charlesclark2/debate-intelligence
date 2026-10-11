"""A profile the AWS config does not define, met by the real boto3 (`v1-e29-t07`).

`test_s3_error_mapping.py` checks the translation one exception at a time. This module lets boto3
raise its own `ProfileNotFound`: it is pointed at an AWS config written for the test, which defines
one profile, and asked for another. Nothing reads the config of the machine the suite runs on, and
nothing reaches AWS: a session for a profile that is not defined is refused before any request.

The error has to name the *setting* that held the profile's name, because that is what an operator
corrects, and the adapter is told which setting that is by whoever built it. So the second half of
this module is about the three adapters carrying that name to an error raised by one of their calls,
not only by the constructor.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from botocore.exceptions import ProfileNotFound

from debate_core.application.errors import DomainError, StoreCredentialsExpired, error_code_of
from debate_core.integrations.s3 import (
    S3EvidenceObjectStore,
    S3EvidenceVersionStore,
    S3SnapshotStore,
    build_s3_client,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

DEFINED_PROFILE = "debate-dev-evidence"
MISSPELT_PROFILE = "debate-dev-evidence-typo"
EVERYDAY_SETTING = "storage.s3.aws_profile"
TAKEDOWN_SETTING = "DEBATE_REMOVAL_PROFILE"


@pytest.fixture
def aws_config(fake_aws_credentials: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """An AWS config written for this test, defining one profile. Returns the file's path."""
    config = tmp_path / "an-aws-config-written-for-this-test"
    config.write_text(f"[profile {DEFINED_PROFILE}]\nregion = us-east-1\n", encoding="utf-8")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials-file"))
    return config


def refusal_of(build: Any) -> DomainError:
    """The error `build()` ends with, which has to be one of this project's own."""
    with pytest.raises(DomainError) as refused:
        build()
    return refused.value


class TestBuildingAClient:
    def test_a_profile_the_config_defines_builds_a_client(self, aws_config: Path) -> None:
        """The control: the config is read, and a profile that is in it is no error."""
        client = build_s3_client(
            region="us-east-1", profile=DEFINED_PROFILE, profile_setting=EVERYDAY_SETTING
        )

        assert client.meta.region_name == "us-east-1"

    @pytest.mark.parametrize("setting", [EVERYDAY_SETTING, TAKEDOWN_SETTING])
    def test_a_profile_the_config_lacks_is_a_configuration_error_naming_its_setting(
        self, aws_config: Path, setting: str
    ) -> None:
        refused = refusal_of(
            lambda: build_s3_client(region="us-east-1", profile=MISSPELT_PROFILE, profile_setting=setting)
        )

        assert isinstance(refused.__cause__, ProfileNotFound), "boto3 raised it, not a stub"
        assert not isinstance(refused, StoreCredentialsExpired)
        assert error_code_of(refused) == "STORE_PROFILE_NOT_CONFIGURED"
        assert f"{MISSPELT_PROFILE!r}, named by {setting}," in str(refused)
        assert setting in str(getattr(refused, "hint", ""))

    def test_the_error_names_no_path_of_the_config_and_offers_no_login(self, aws_config: Path) -> None:
        refused = refusal_of(
            lambda: build_s3_client(
                region="us-east-1", profile=MISSPELT_PROFILE, profile_setting=EVERYDAY_SETTING
            )
        )

        said = f"{refused} {getattr(refused, 'hint', '')}"
        assert str(aws_config) not in said
        assert aws_config.name not in said
        assert str(aws_config.parent) not in said
        assert "aws sso login" not in said
        assert "aws configure" not in said

    def test_a_name_from_aws_profile_names_that_variable(
        self, aws_config: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No profile is passed, so botocore's own chain chose the name, from `AWS_PROFILE`."""
        monkeypatch.setenv("AWS_PROFILE", MISSPELT_PROFILE)

        refused = refusal_of(lambda: build_s3_client(region="us-east-1"))

        assert error_code_of(refused) == "STORE_PROFILE_NOT_CONFIGURED"
        assert f"{MISSPELT_PROFILE!r}, named by AWS_PROFILE," in str(refused)


def raising_profile_not_found(client: S3Client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every request `client` makes from here on is answered by botocore's own `ProfileNotFound`."""

    def no_such_profile(*_: object, **__: object) -> None:
        raise ProfileNotFound(profile=MISSPELT_PROFILE)

    monkeypatch.setattr(type(client), "_make_api_call", no_such_profile)


class TestAnAdapterCarriesTheSettingToItsCalls:
    """Each adapter is told the setting its profile's name came from, and says so wherever the
    failure arrives. A call cannot meet this on a real machine once the client is built, but the
    translation is total, and a hint that named the wrong setting would send a takedown's operator
    to the everyday profile."""

    async def test_the_object_store(
        self, evidence_bucket: str, s3_client: S3Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = S3EvidenceObjectStore(
            bucket=evidence_bucket,
            client=s3_client,
            profile=MISSPELT_PROFILE,
            profile_setting=TAKEDOWN_SETTING,
        )
        raising_profile_not_found(s3_client, monkeypatch)

        with pytest.raises(DomainError) as refused:
            await store.list_objects("manifests/")

        assert error_code_of(refused.value) == "STORE_PROFILE_NOT_CONFIGURED"
        assert f"named by {TAKEDOWN_SETTING}," in str(refused.value)

    async def test_the_version_store(
        self, evidence_bucket: str, s3_client: S3Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = S3EvidenceVersionStore(
            bucket=evidence_bucket,
            client=s3_client,
            profile=MISSPELT_PROFILE,
            profile_setting=TAKEDOWN_SETTING,
        )
        raising_profile_not_found(s3_client, monkeypatch)

        with pytest.raises(DomainError) as refused:
            await store.list_versions("raw/")

        assert error_code_of(refused.value) == "STORE_PROFILE_NOT_CONFIGURED"
        assert f"named by {TAKEDOWN_SETTING}," in str(refused.value)

    async def test_the_snapshot_store(
        self, evidence_bucket: str, blob_prefix: str, s3_client: S3Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = S3SnapshotStore(
            bucket=evidence_bucket,
            prefix=blob_prefix,
            client=s3_client,
            profile=MISSPELT_PROFILE,
            profile_setting=EVERYDAY_SETTING,
        )
        raising_profile_not_found(s3_client, monkeypatch)

        with pytest.raises(DomainError) as refused:
            await store.exists("ab" * 32)

        assert error_code_of(refused.value) == "STORE_PROFILE_NOT_CONFIGURED"
        assert f"named by {EVERYDAY_SETTING}," in str(refused.value)
