"""A cloud run stopped on a token code, or refused its token secret, emails a cure to act on (`v1-e40-t50`).

`v1-e40-t40` gave `CASELIST_TOKEN_MISSING` and `CASELIST_TOKEN_UNREADABLE` the Wednesday-login cure in a
bucket-mode command's output and in a failed stage's notice. Two notices were left, measured on moto before
anything changed (the session report, "Measured before any change"):

* A bucket-mode run that **stopped** on either token code emailed "caselist pull failed: needs a person",
  "A person should look: at least one failure here will be the same on the next scheduled run", and
  `v1-e40-t28`'s "the next cloud run … the weekly run, or one started by hand". The Wednesday login comes
  before that run and cures it, and a run by hand before it stops again. The PM's ruling (2026-11-14, 1)
  gives it a title of its own, no verdict sentence, and the table's cure (`CLOUD_TOKEN_CURES[code]`).
* A bucket-mode run whose **token secret refused its read** (`STORE_ACCESS_DENIED` at `GetSecretValue`,
  an IAM or a decrypt refusal alike) emailed "caselist pull failed: will be retried" and "this machine or
  the bucket refused it", with the same fix. A person is needed. The ruling (2, 4) gives it a title of
  its own, the escalation to the PM with the code, and no exception's class anywhere in it. It is told
  apart by the error's structured `operation`, never its message, so a bucket's refusal keeps its notice.

On the Mac every word stays: these pins were written, and passed, before anything changed. The run's own
environment names the run in each message, so both `dev` and `prod` are run here (the ruling, 1).

Each stopped run is built as the run monitor builds it (`SyncRunMonitor.monitored`): `record_for_failure`
and `details_for_failure` from the error, with the details' `bucket_run` set in bucket mode, and then
`notifications_for` with the command's rule for a retry. Every expected sentence is written out by hand.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist_sync import fix_for
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.ports.caselist_source import CaselistTokenMissing
from debate_core.application.ports.notifier import Notification
from debate_core.application.sync_runs import (
    BucketRunDetails,
    SyncRunDetails,
    SyncRunRecord,
    banner_words,
    details_for_failure,
    notifications_for,
    record_for_failure,
)
from debate_core.integrations.opencaselist.token_store import CaselistTokenUnreadable

from .retry_rule import a_retry_may_cure

REPO_ROOT: Final = Path(__file__).resolve().parents[5]
CLOUD_RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "caselist-cloud-run.md"
ALERTS_RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "caselist-run-alerts.md"

RUN_ID: Final = "20261118T120000Z"
STARTED: Final = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)

# ------------------------------------------------------------------------------------------------
# What each notice says, by hand
# ------------------------------------------------------------------------------------------------

NO_READABLE_TOKEN_TITLE: Final = "caselist pull stopped: no readable caselist_token"
"""The ruling's title for a cloud run stopped on either token code."""

THE_NO_TOKEN_CURE: Final = (
    "the next Wednesday 03:00 login writes a new caselist_token to the token secret, and the run after it "
    "takes up what this run did not finish, from the run state saved in the bucket; a backfile import "
    'refused for it starts again after Thursday 00:00 (caselist-cloud-run.md, "A run with no readable '
    'caselist_token"); never a login by hand, which would be a second login'
)
"""`v1-e40-t40`'s cure for both token codes, as its table holds it."""

REFUSED_SECRET_TITLE: Final = "caselist pull stopped: token secret refused, needs a person"

THE_REFUSED_SECRET_CURE: Final = (
    "send the PM the run's id and its code, STORE_ACCESS_DENIED; the error class is in caselist runs "
    '--remote --json (caselist-cloud-run.md, "A run refused its token secret"); never an IAM or key-policy '
    "change by hand"
)
"""The ruling's fix line for a refused token secret, worded for its item 4: the code, never the class."""

THE_UNFINISHED_RUN_CURE: Final = (
    "the next cloud run takes up what this run did not finish, from the run state saved in the bucket: the "
    'weekly run, or one started by hand (caselist-cloud-run.md, "A failed or stopped run"); never a publish '
    "from the operator's Mac"
)
"""`v1-e40-t28`'s fix line for any other stopped cloud run: unchanged."""

PULL: Final = "debate-research caselist pull"
PERSON_TITLE: Final = "caselist pull failed: needs a person"
RETRY_TITLE: Final = "caselist pull failed: will be retried"
FIX_FIRST_TITLE: Final = "caselist pull failed: retried once fixed"
PERSON: Final = "A person should look: at least one failure here will be the same on the next scheduled run."
RETRY: Final = "The next scheduled run should retry it: every failure here is one a later run may not meet."
FIX_FIRST: Final = (
    "The next scheduled run retries it, and is refused the same way until the fix that follows is made."
)
LOG_IN_AGAIN: Final = (
    "No caselist_token is stored on this machine for the environment: log in again with "
    "`debate-research caselist auth login`."
)
LOG_OUT_AND_IN: Final = (
    "The caselist_token stored on this machine for the environment cannot be read: log out with "
    "`debate-research caselist auth logout`, then log in again with `debate-research caselist auth login`."
)

ENVIRONMENTS: Final = [pytest.param("dev", id="dev"), pytest.param("prod", id="prod")]


def where(environment: str) -> str:
    return f"Run {RUN_ID} ({environment})"


def refused_secret(environment: str, *, hint: str | None = None) -> StoreAccessDenied:
    """What `ManagedSecret.read` raises for `AccessDeniedException` and `DecryptionFailure` alike."""
    return StoreAccessDenied("GetSecretValue", f"secret debate-{environment}-caselist-token", hint=hint)


def refused_bucket_read(environment: str, *, hint: str | None = None) -> StoreAccessDenied:
    """What the S3 run-state adapter raises for a refused `GetObject`: the bucket, not the secret."""
    return StoreAccessDenied(
        "GetObject",
        f"object reports/sync/run-state/bundle.tar in bucket debate-{environment}-evidence",
        hint=hint,
    )


# ------------------------------------------------------------------------------------------------
# A stopped run, as the monitor records and announces it
# ------------------------------------------------------------------------------------------------


def stopped(error: Exception, *, environment: str, bucket_mode: bool) -> tuple[SyncRunRecord, SyncRunDetails]:
    record = record_for_failure(
        error,
        run_id=RUN_ID,
        started_at=STARTED,
        finished_at=STARTED,
        environment=environment,
        mode="run",
        caselists=("hspolicy26",),
        bucket_mode=bucket_mode,
    )
    details = details_for_failure(error, run_id=RUN_ID, bucket_mode=bucket_mode)
    details = details.model_copy(update={"bucket_run": BucketRunDetails() if bucket_mode else None})
    return record, details


def the_notice(error: Exception, *, environment: str = "dev", bucket_mode: bool) -> Notification:
    record, details = stopped(error, environment=environment, bucket_mode=bucket_mode)
    [notification] = notifications_for(
        record,
        details,
        aws_login_command="aws sso login --profile debate-dev",
        credentials_expired=False,
        may_succeed_on_retry=a_retry_may_cure,
    )
    return notification


def the_banner_words(error: Exception, *, bucket_mode: bool) -> str | None:
    record, details = stopped(error, environment="dev", bucket_mode=bucket_mode)
    return banner_words(record, details, may_succeed_on_retry=a_retry_may_cure)


def said(notification: Notification) -> tuple[str, str, str, str | None]:
    return notification.title, notification.message, notification.fix_command, notification.hint


# ------------------------------------------------------------------------------------------------
# The Mac: every word as it was
# ------------------------------------------------------------------------------------------------


def test_a_mac_run_stopped_by_token_missing_keeps_its_notice_word_for_word() -> None:
    assert said(the_notice(CaselistTokenMissing(), bucket_mode=False)) == (
        PERSON_TITLE,
        f"{where('dev')} stopped: no caselist_token was stored on this machine. {PERSON}",
        PULL,
        LOG_IN_AGAIN,
    )
    assert the_banner_words(CaselistTokenMissing(), bucket_mode=False) is None


def test_a_mac_run_stopped_by_token_unreadable_keeps_its_notice_word_for_word() -> None:
    assert said(the_notice(CaselistTokenUnreadable("file"), bucket_mode=False)) == (
        PERSON_TITLE,
        f"{where('dev')} stopped: the caselist_token stored on this machine could not be read. {PERSON}",
        PULL,
        LOG_OUT_AND_IN,
    )
    assert the_banner_words(CaselistTokenUnreadable("file"), bucket_mode=False) is None


def test_a_mac_run_its_token_secret_refused_keeps_its_notice_word_for_word() -> None:
    """The Mac's pull builds its token store with no profile, so the refusal carries no hint."""
    record, details = stopped(refused_secret("dev"), environment="dev", bucket_mode=False)
    assert record.error_class == "StoreAccessDenied"
    assert details.hint is None
    assert said(the_notice(refused_secret("dev"), bucket_mode=False)) == (
        RETRY_TITLE,
        f"{where('dev')} stopped: this machine or the bucket refused it. {RETRY}",
        PULL,
        None,
    )
    assert the_banner_words(refused_secret("dev"), bucket_mode=False) is None


def test_a_mac_run_its_token_secret_refused_with_a_login_hint_keeps_its_notice_word_for_word() -> None:
    """A secret signed by a profile (`caselist auth login --token-backend secretsmanager`) keeps its hint."""
    error = refused_secret("dev", hint="run `aws sso login --profile debate-dev`")
    assert fix_for(error, bucket_mode=False) == (
        "The bucket refused GetSecretValue: run `aws sso login --profile debate-dev`."
    )
    assert said(the_notice(error, bucket_mode=False)) == (
        FIX_FIRST_TITLE,
        f"{where('dev')} stopped: this machine or the bucket refused it. {FIX_FIRST}",
        PULL,
        "The bucket refused GetSecretValue: run `aws sso login --profile debate-dev`.",
    )
    assert the_banner_words(error, bucket_mode=False) == "retry once fixed"


def test_fix_for_gives_no_access_denied_escalation_on_the_mac() -> None:
    assert fix_for(refused_secret("dev"), bucket_mode=False) is None


# ------------------------------------------------------------------------------------------------
# Bucket mode: a run stopped on a token code
# ------------------------------------------------------------------------------------------------

THE_TWO_TOKEN_CODES: Final = [
    pytest.param(CaselistTokenMissing(), "CASELIST_TOKEN_MISSING", id="token-missing"),
    pytest.param(
        CaselistTokenUnreadable("secretsmanager"), "CASELIST_TOKEN_UNREADABLE", id="token-unreadable"
    ),
]


@pytest.mark.parametrize("environment", ENVIRONMENTS)
@pytest.mark.parametrize(("error", "code"), THE_TWO_TOKEN_CODES)
def test_a_bucket_mode_run_stopped_by_a_token_code_names_the_wednesday_login(
    error: Exception, code: str, environment: str
) -> None:
    assert said(the_notice(error, environment=environment, bucket_mode=True)) == (
        NO_READABLE_TOKEN_TITLE,
        f"{where(environment)} stopped: an error recorded as {code}, so it fetched nothing from "
        "OpenCaselist.",
        THE_NO_TOKEN_CURE,
        None,
    )


@pytest.mark.parametrize(("error", "code"), THE_TWO_TOKEN_CODES)
def test_a_bucket_mode_run_stopped_by_a_token_code_offers_no_run_by_hand(error: Exception, code: str) -> None:
    notification = the_notice(error, bucket_mode=True)
    assert "started by hand" not in notification.text
    assert "auth login" not in notification.text
    assert PERSON not in notification.text
    assert the_banner_words(error, bucket_mode=True) is None


# ------------------------------------------------------------------------------------------------
# Bucket mode: a run its token secret refused
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_a_bucket_mode_run_its_token_secret_refused_access_denied_needs_a_person(environment: str) -> None:
    assert said(the_notice(refused_secret(environment), environment=environment, bucket_mode=True)) == (
        REFUSED_SECRET_TITLE,
        f"{where(environment)} was refused its read of the caselist_token secret (GetSecretValue) and "
        "fetched nothing. A person is needed: the next login does not cure it, and every run is refused "
        "the same way until the run role can read the secret again.",
        THE_REFUSED_SECRET_CURE,
        None,
    )


def test_a_bucket_mode_run_its_token_secret_refused_records_the_escalation_as_its_hint_access_denied() -> (
    None
):
    """The record's hint is the same escalation (the ruling, 5), from `fix_for`."""
    assert fix_for(refused_secret("dev"), bucket_mode=True) == THE_REFUSED_SECRET_CURE
    record, details = stopped(refused_secret("dev"), environment="dev", bucket_mode=True)
    assert record.error_class == "StoreAccessDenied"
    assert record.error_message == "not allowed to GetSecretValue secret debate-dev-caselist-token"
    assert details.failure_codes == ("STORE_ACCESS_DENIED",)
    assert details.hint == THE_REFUSED_SECRET_CURE
    assert the_banner_words(refused_secret("dev"), bucket_mode=True) is None


def every_exception_class_name() -> set[str]:
    """Every exception class this process has loaded, botocore's among them, and the error codes AWS gives."""
    names: set[str] = {"AccessDeniedException", "DecryptionFailure", "ClientError"}
    pending: list[type[BaseException]] = [BaseException]
    while pending:
        kind = pending.pop()
        names.add(kind.__name__)
        pending.extend(kind.__subclasses__())
    return {name for name in names if re.fullmatch(r"[A-Z]\w*[a-z]\w*", name) and len(name) > 4}


def test_a_bucket_mode_access_denied_notice_names_no_exception_class() -> None:
    """v1-e34-t19's rule stands (the ruling, 4): the code `STORE_ACCESS_DENIED`, never `StoreAccessDenied`."""
    notification = the_notice(refused_secret("dev"), bucket_mode=True)
    words = set(re.findall(r"\w+", notification.text + " " + notification.title))
    assert "StoreAccessDenied" in every_exception_class_name()
    assert words & every_exception_class_name() == set()
    assert "STORE_ACCESS_DENIED" in notification.fix_command


@pytest.mark.parametrize(
    ("hint", "title", "verdict"),
    [
        pytest.param(None, RETRY_TITLE, RETRY, id="no-hint"),
        pytest.param("the PM grants it", FIX_FIRST_TITLE, FIX_FIRST, id="its-own-hint"),
    ],
)
def test_a_bucket_mode_run_the_bucket_refused_keeps_its_access_denied_notice(
    hint: str | None, title: str, verdict: str
) -> None:
    """Told apart by the error's `operation`: a refused `GetObject` keeps today's notice word for word."""
    error = refused_bucket_read("dev", hint=hint)
    assert said(the_notice(error, bucket_mode=True)) == (
        title,
        f"{where('dev')} stopped: this machine or the bucket refused it. {verdict}",
        THE_UNFINISHED_RUN_CURE,
        None if hint is None else f"The bucket refused GetObject: {hint}.",
    )
    assert fix_for(error, bucket_mode=True) == (
        None if hint is None else f"The bucket refused GetObject: {hint}."
    )


# ------------------------------------------------------------------------------------------------
# The runbooks say what the notices say
# ------------------------------------------------------------------------------------------------


def section(heading: str) -> str:
    text = CLOUD_RUNBOOK.read_text(encoding="utf-8")
    assert f"\n## {heading}\n" in text, f"the section a cure names: {heading}"
    return " ".join(text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0].split())


def test_the_no_readable_token_section_quotes_the_token_notice() -> None:
    no_token = section("A run with no readable caselist_token")
    assert f"`{NO_READABLE_TOKEN_TITLE}`" in no_token
    assert f"> Fix: {THE_NO_TOKEN_CURE}" in no_token
    assert "The alert email is still a stopped run's" not in no_token
    assert "[A run refused its token secret](#a-run-refused-its-token-secret)" in no_token


def test_the_refused_token_secret_section_quotes_the_access_denied_notice_and_keeps_the_rule() -> None:
    refused = section("A run refused its token secret")
    assert f"`{REFUSED_SECRET_TITLE}`" in refused
    assert f"> Fix: {THE_REFUSED_SECRET_CURE}" in refused
    assert "the run stops on `STORE_ACCESS_DENIED`, error class `StoreAccessDenied`" in refused
    assert "`error_class` from `debate-research caselist runs --remote --json`" in refused
    assert "Never change an IAM policy or the key policy by hand" in refused


def test_the_alerts_runbook_says_what_to_do_for_the_token_and_access_denied_emails() -> None:
    rows = [
        line for line in ALERTS_RUNBOOK.read_text(encoding="utf-8").splitlines() if line.startswith("| `")
    ]
    no_tokens = [row for row in rows if row.startswith(f"| `{NO_READABLE_TOKEN_TITLE}`")]
    assert len(no_tokens) == 1, "one row for the no-readable-token email"
    [no_token] = no_tokens
    assert "(caselist-cloud-run.md#a-run-with-no-readable-caselist_token)" in no_token
    assert "Never log in by hand" in no_token
    refusals = [row for row in rows if row.startswith(f"| `{REFUSED_SECRET_TITLE}`")]
    assert len(refusals) == 1, "one row for the refused-secret email"
    [refused] = refusals
    assert "(caselist-cloud-run.md#a-run-refused-its-token-secret)" in refused
    assert "`STORE_ACCESS_DENIED`" in refused
    assert "never an IAM or key-policy change by hand" in refused
