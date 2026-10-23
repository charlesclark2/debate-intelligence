"""What the app is built with, and the cookie reads and writes every part of it shares.

:class:`PilotServices` is what a composition root hands :func:`debate_api.app.create_app`: the
configuration, the cookie keys, the two sign-in use cases, the search index holder (`v1-e39-t06`),
the access audit (`v1-e39-t07`) and the clock. `debate_api.container` builds it
from the function's environment; a test builds it from fakes. :class:`PilotState` adds what the
app derives from it once, and lives on `app.state.pilot` for the gate and the routes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from fastapi import Request, Response

from debate_api.configuration import CookieKeys, PilotConfiguration
from debate_api.cookies import (
    ENROLMENT_COOKIE,
    SESSION_COOKIE,
    SIGN_IN_COOKIE,
    CookieSealer,
    enrolment_from_payload,
    enrolment_payload,
    session_from_payload,
    session_payload,
    transaction_from_payload,
    transaction_payload,
)
from debate_api.pages import PageRenderer, StaticAsset
from debate_core.application.search_index_holder import SearchIndexHolder
from debate_core.application.tub.access_audit import AccessAuditService
from debate_core.application.tub.account_page import AccountPageService
from debate_core.application.tub.sessions import (
    ENROLMENT_LIFETIME,
    SESSION_ABSOLUTE_LIFETIME,
    SIGN_IN_TRANSACTION_LIFETIME,
    PendingEnrolment,
    Session,
    SignInTransaction,
)
from debate_core.application.tub.sign_in import SignInService

__all__ = ["PilotServices", "PilotState", "pilot_state"]


@dataclass(frozen=True, slots=True)
class PilotServices:
    configuration: PilotConfiguration
    cookie_keys: CookieKeys
    sign_in: SignInService
    account_page: AccountPageService
    search_index: SearchIndexHolder
    access_audit: AccessAuditService
    clock: Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class PilotState:
    services: PilotServices
    sealer: CookieSealer
    renderer: PageRenderer
    app_script: StaticAsset
    app_stylesheet: StaticAsset

    @property
    def static_assets(self) -> tuple[StaticAsset, ...]:
        """Every file under `/static/`: the one script and the one stylesheet."""
        return (self.app_script, self.app_stylesheet)

    @property
    def public_origin(self) -> str:
        return self.services.configuration.public_origin

    # Reading --------------------------------------------------------------------------------

    def session_in(self, request: Request) -> Session | None:
        return session_from_payload(self.sealer.open(SESSION_COOKIE, request.cookies.get(SESSION_COOKIE)))

    def enrolment_in(self, request: Request) -> PendingEnrolment | None:
        return enrolment_from_payload(
            self.sealer.open(ENROLMENT_COOKIE, request.cookies.get(ENROLMENT_COOKIE))
        )

    def transaction_in(self, request: Request) -> SignInTransaction | None:
        return transaction_from_payload(self.sealer.open(SIGN_IN_COOKIE, request.cookies.get(SIGN_IN_COOKIE)))

    # Writing --------------------------------------------------------------------------------

    def write_session(self, response: Response, session: Session) -> None:
        remaining = session.started_at + SESSION_ABSOLUTE_LIFETIME - self.services.clock()
        self._write(
            response, SESSION_COOKIE, self.sealer.seal(SESSION_COOKIE, session_payload(session)), remaining
        )

    def write_enrolment(self, response: Response, enrolment: PendingEnrolment) -> None:
        remaining = enrolment.started_at + ENROLMENT_LIFETIME - self.services.clock()
        sealed = self.sealer.seal(ENROLMENT_COOKIE, enrolment_payload(enrolment))
        self._write(response, ENROLMENT_COOKIE, sealed, remaining)

    def write_transaction(self, response: Response, transaction: SignInTransaction) -> None:
        sealed = self.sealer.seal(SIGN_IN_COOKIE, transaction_payload(transaction))
        self._write(response, SIGN_IN_COOKIE, sealed, SIGN_IN_TRANSACTION_LIFETIME)

    @staticmethod
    def clear(response: Response, *names: str) -> None:
        for name in names:
            response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")

    @staticmethod
    def _write(response: Response, name: str, value: str, lifetime: timedelta) -> None:
        seconds = max(1, int(lifetime.total_seconds()))
        response.set_cookie(
            name, value, max_age=seconds, path="/", secure=True, httponly=True, samesite="lax"
        )


def pilot_state(request: Request) -> PilotState:
    """The app's :class:`PilotState`, as :func:`debate_api.app.create_app` stored it."""
    return cast(PilotState, request.app.state.pilot)
