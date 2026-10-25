"""What an alert may say: the run id, the stage, the code and the environment, and nothing else.

`v1-e40-t05`'s forbidden list: no school, team code, file name or card text in an alert. The PM's
test for it: plant a sentinel school, team and file name in a stubbed run's records, and look for
them in what reaches SNS. Each run here goes through the real :class:`SyncRunMonitor`, which writes
the record and builds the notifications, to the real :class:`SnsNotifier`, whose botocore client is
answered in-process; what is checked is each publish as SNS would have received it.

The sentinels are planted where a run's data does reach its record: a failed stage's reason, the
message of an error that stopped the run (an `OSError`-style quote of a disclosure's path), and an
archive's name. A notification is built from stage names, codes and this project's own hints
(`sync_runs.notifications_for`), so none of them should get through. The run ids, stages, codes and
environments the alerts must carry are read off the runs each test wrote (working agreement 6).

A failed login is checked the same way, with the Tabroom username as its sentinel: the login's alert
never names the account (ADR-0020 (6)).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from debate_core.application.caselist.run_lock import RunLockLost, RunTerminated
from debate_core.application.caselist_login import ScheduledLogin, TabroomPasswordSecret
from debate_core.application.caselist_sync import (
    ArchiveSelection,
    RunSummary,
    SelectionDecision,
    StageOutcome,
    StageRecord,
    SyncStage,
)
from debate_core.application.errors import StoreUnavailable
from debate_core.application.ports.caselist_source import ArchiveKind, CaselistLoginRejected
from debate_core.application.sync_runs import SYNC_RUN_LOG_FILENAME, SyncRunMonitor
from debate_core.integrations.sns import SnsNotifier

from .conftest import TOPIC_ARN, AnsweringSns, Published

pytestmark = pytest.mark.anyio

SCHOOL = "Quillfeather Academy"
TEAM_CODE = "QuAc"
FILE_NAME = "Quillfeather-QuAc-Aff-Glenbrooks-Round3.docx"
DISCLOSURE_PATH = f"{SCHOOL}/{TEAM_CODE}/{FILE_NAME}"
CARD_TEXT = "Quillfeather's sentinel card text: the impact outweighs on magnitude"
USERNAME = "quillfeather.coach@example.invalid"

SENTINELS = {
    "the school": SCHOOL,
    "the school's first word": "Quillfeather",
    "the team code": TEAM_CODE,
    "the file name": FILE_NAME,
    "the card text": "sentinel card text",
    "the Tabroom username": USERNAME,
}

STARTED = datetime(2026, 11, 4, 11, 0, 2, tzinfo=UTC)
RUN_ID = "20261104T110002Z"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def named_in(published: Published) -> list[str]:
    """What of the sentinels a publish names, by what it is; empty when it names none."""
    text = f"{published.subject}\n{published.message}".casefold()
    return [what for what, sentinel in SENTINELS.items() if sentinel.casefold() in text]


def monitor(tmp_path: Path, sns: AnsweringSns) -> SyncRunMonitor:
    return SyncRunMonitor(
        state_dir=tmp_path,
        environment="dev",
        notifier=SnsNotifier(TOPIC_ARN, environment="dev", client=sns.client),
        remote=None,
        aws_login_command="aws sso login --profile debate-dev-evidence",
        clock=lambda: STARTED,
    )


def a_week_whose_download_and_import_failed() -> RunSummary:
    """A stubbed run whose stages' reasons and archive name carry the sentinels."""
    archive = ArchiveSelection(
        caselist="hsld26",
        name=f"hsld26-weekly-2026-11-03-{FILE_NAME}.zip",
        kind=ArchiveKind.WEEKLY,
        archive_date=date(2026, 11, 3),
        decision=SelectionDecision.DOWNLOAD,
    )
    return RunSummary(
        run_id=RUN_ID,
        started_at=STARTED,
        finished_at=STARTED + timedelta(minutes=3),
        dry_run=False,
        caselists=("hsld26",),
        archives=(archive,),
        stages=(
            StageRecord(stage=SyncStage.SELECT, outcome=StageOutcome.COMPLETED, reason=f"1 archive listed for {SCHOOL}"),
            StageRecord(
                stage=SyncStage.DOWNLOAD,
                outcome=StageOutcome.FAILED,
                reason=f"could not fetch '{DISCLOSURE_PATH}' for {SCHOOL} ({TEAM_CODE}): {CARD_TEXT}",
                error_codes=("PROVIDER_UNAVAILABLE",),
            ),
            StageRecord(
                stage=SyncStage.IMPORT,
                outcome=StageOutcome.FAILED,
                reason=f"{FILE_NAME} could not be read",
                error_codes=("UNREADABLE_ARCHIVE",),
            ),
        ),
    )


async def run(monitor_: SyncRunMonitor, pull: Callable[[], Awaitable[RunSummary]]) -> None:
    try:
        await monitor_.watch(pull, caselists=("hsld26",), mode="run")
    except Exception:  # noqa: BLE001 - a stopped run raises again after it is recorded and announced
        return


async def test_a_failed_run_names_its_id_stages_codes_and_environment_and_nothing_planted(
    tmp_path: Path, sns: AnsweringSns
) -> None:
    async def pull() -> RunSummary:
        return a_week_whose_download_and_import_failed()

    await run(monitor(tmp_path, sns), pull)

    assert len(sns.sent) == 1
    alert = sns.sent[0]
    assert named_in(alert) == []
    for said in (RUN_ID, "(dev)", "download", "import", "PROVIDER_UNAVAILABLE", "UNREADABLE_ARCHIVE"):
        assert said in alert.message, said
    assert alert.subject is not None and alert.subject.startswith("debate dev: caselist pull failed")
    # The sentinels did reach the record, so the alert left them out rather than never seeing them.
    log = (tmp_path / SYNC_RUN_LOG_FILENAME).read_text(encoding="utf-8")
    assert SCHOOL in log and TEAM_CODE in log


async def test_a_run_stopped_by_an_error_quoting_a_disclosure_path_names_only_its_code(
    tmp_path: Path, sns: AnsweringSns
) -> None:
    async def pull() -> RunSummary:
        raise StoreUnavailable("PutObject", f"raw/hsld26/{DISCLOSURE_PATH}", f"SlowDown on {SCHOOL}")

    await run(monitor(tmp_path, sns), pull)

    assert len(sns.sent) == 1
    assert named_in(sns.sent[0]) == []
    assert RUN_ID in sns.sent[0].message and "(dev)" in sns.sent[0].message
    assert "a store did not answer" in sns.sent[0].message


@pytest.mark.parametrize(
    ("stopped", "code"),
    [(RunTerminated, "RUN_TERMINATED"), (RunLockLost, "RUN_LOCK_LOST")],
)
async def test_a_terminated_run_and_a_run_that_lost_the_lock_are_failed_runs_with_their_codes(
    tmp_path: Path, sns: AnsweringSns, stopped: Callable[[], Exception], code: str
) -> None:
    """v1-e40-t04's two endings: the PM's ruling that each is a failed run for the alert, by its code."""

    async def pull() -> RunSummary:
        raise stopped()

    await run(monitor(tmp_path, sns), pull)

    assert len(sns.sent) == 1
    assert code in sns.sent[0].message
    assert RUN_ID in sns.sent[0].message and "(dev)" in sns.sent[0].message
    assert named_in(sns.sent[0]) == []


class _PasswordSecret:
    """The password secret's document, as `TabroomPasswordSecret` reads it, naming the sentinel user."""

    secret_id = "debate-dev-caselist-tabroom-password"

    def read(self) -> str:
        return '{"username": "' + USERNAME + '", "password": "fixture-password-0f3a9c"}'


class _RefusingSession:
    async def __aenter__(self) -> _RefusingSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def login(self, username: str, password: SecretStr) -> Any:
        assert username == USERNAME
        raise CaselistLoginRejected(401)


class _NoTokens:
    location = "secretsmanager:debate-dev-caselist-token"

    def save(self, token: SecretStr, *, expires_at: datetime | None) -> Any:
        raise AssertionError("a refused login stores nothing")


async def test_a_failed_login_names_its_code_and_environment_and_never_the_account(sns: AnsweringSns) -> None:
    login = ScheduledLogin(
        credentials=TabroomPasswordSecret(_PasswordSecret()),  # pyright: ignore[reportArgumentType]
        session=_RefusingSession,  # pyright: ignore[reportArgumentType]
        tokens=_NoTokens,  # pyright: ignore[reportArgumentType]
        notifier=SnsNotifier(TOPIC_ARN, environment="dev", client=sns.client),
        environment="dev",
    )

    with pytest.raises(CaselistLoginRejected):
        await login.run()

    assert len(sns.sent) == 1
    assert named_in(sns.sent[0]) == []
    assert "CASELIST_LOGIN_REJECTED" in sns.sent[0].message
    assert "Login (dev)" in sns.sent[0].message
    assert sns.sent[0].subject == "debate dev: Weekly caselist login failed"
