"""Who may reach which route, decided once for every request (ADR-0019 (d), gate item 2).

Every request passes the gate before any route sees it, and a path no route claims is treated as
needing a session, so a route that forgets to say what it needs is closed, not open.

| Access | Who | Routes |
|---|---|---|
| `PUBLIC` | anyone | `/healthz`, `/auth/callback`, `/signed-out`, `/static/...` and no others |
| `ENROLMENT` | a session, or a pending enrolment | the authenticator page, sign-out |
| `SIGNED_IN` | a session | every other page |
| `COACH` | a coach's session | coach pages |

:meth:`RouteAccess.register` refuses `PUBLIC` for any path but those four, so a fifth session-free
route cannot be added without changing this module.

**Without a session**, a `GET` is sent to managed login with a new sign-in transaction, and any
other method is answered `401`. **With a pending enrolment** only, every page sends the browser
to the authenticator page. **A student on a coach route** gets `403`.

**Every state-changing request** (anything but `GET` and `HEAD`) must also carry the session's CSRF
token in `X-CSRF-Token`, compared in constant time, an `Origin` equal to the pilot's own origin and
`Sec-Fetch-Site: same-origin` (ADR-0019 (d), CSRF). The body hash in `x-amz-content-sha256` is
CloudFront's origin access control's to enforce: Lambda refuses a POST without it before the
function runs, so no request without it reaches here in AWS.

The app sends no CORS headers anywhere, so a cross-origin script's preflight fails.
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable, Mapping
from enum import StrEnum
from typing import Final

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from debate_api.cookies import ENROLMENT_COOKIE, SESSION_COOKIE
from debate_api.state import PilotState, pilot_state
from debate_core.application.tub.identity import Role
from debate_core.application.tub.sessions import PendingEnrolment, Session
from debate_core.application.tub.sign_in import SessionEnded

__all__ = [
    "SAFE_METHODS",
    "SESSION_FREE_PATHS",
    "STATIC_PREFIX",
    "Access",
    "RouteAccess",
    "install_gate",
    "state_change_refusal",
]

SESSION_FREE_PATHS: Final = frozenset({"/healthz", "/auth/callback", "/signed-out"})
STATIC_PREFIX: Final = "/static/"
SAFE_METHODS: Final = frozenset({"GET", "HEAD"})
AUTHENTICATOR_PAGE: Final = "/account/authenticator"


class Access(StrEnum):
    PUBLIC = "public"
    ENROLMENT = "enrolment"
    SIGNED_IN = "signed-in"
    COACH = "coach"


class RouteAccess:
    """The access each route path needs. Unregistered paths need a session."""

    def __init__(self) -> None:
        self._by_path: dict[str, Access] = {}

    def register(self, path: str, access: Access) -> None:
        if access is Access.PUBLIC and path not in SESSION_FREE_PATHS and not path.startswith(STATIC_PREFIX):
            raise ValueError(
                f"{path} cannot be session-free: only {sorted(SESSION_FREE_PATHS)} and /static/ are"
            )
        self._by_path[path] = access

    def access_of(self, path: str) -> Access:
        if path.startswith(STATIC_PREFIX):
            return Access.PUBLIC
        return self._by_path.get(path, Access.SIGNED_IN)

    @property
    def registered(self) -> Mapping[str, Access]:
        return dict(self._by_path)


def state_change_refusal(headers: Mapping[str, str], *, csrf_token: str, public_origin: str) -> str | None:
    """Why a state-changing request is refused, or `None` when it passes every CSRF check."""
    if headers.get("origin") != public_origin:
        return "its Origin is not the pilot's"
    if headers.get("sec-fetch-site") != "same-origin":
        return "it was not sent from the pilot's own pages"
    sent = headers.get("x-csrf-token", "")
    if not hmac.compare_digest(sent.encode(), csrf_token.encode()):
        return "its CSRF token does not match the session's"
    return None


def install_gate(app: FastAPI, routes: RouteAccess) -> None:
    """Put the gate in front of every route of `app`."""

    async def gate(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        access = routes.access_of(request.url.path)
        if access is Access.PUBLIC:
            return await call_next(request)
        state = pilot_state(request)
        holder, ended = await run_in_threadpool(_holder_of, request, state)
        if holder is None:
            response = await run_in_threadpool(_not_signed_in, request, state)
            if ended:
                state.clear(response, SESSION_COOKIE, ENROLMENT_COOKIE)
            return response
        refused = _refused(request, access, holder, state)
        if refused is not None:
            return refused
        request.state.holder = holder
        response = await call_next(request)
        if isinstance(holder, Session) and not getattr(request.state, "cookies_written", False):
            state.write_session(response, holder)
        return response

    app.middleware("http")(gate)


def _holder_of(request: Request, state: PilotState) -> tuple[Session | PendingEnrolment | None, bool]:
    """The request's session (checked and perhaps revalidated) or pending enrolment, and whether one ended."""
    ended = False
    session = state.session_in(request)
    if session is not None:
        try:
            return state.services.sign_in.check(session), False
        except SessionEnded:
            ended = True
    elif request.cookies.get(SESSION_COOKIE):
        ended = True
    enrolment = state.enrolment_in(request)
    if enrolment is not None:
        try:
            return state.services.sign_in.check_enrolment(enrolment), ended
        except SessionEnded:
            ended = True
    return None, ended or bool(request.cookies.get(ENROLMENT_COOKIE))


def _not_signed_in(request: Request, state: PilotState) -> Response:
    if request.method not in SAFE_METHODS:
        return JSONResponse(
            {"message": "You are signed out. Sign in again.", "location": "/"}, status_code=401
        )
    return_to = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    transaction, authorization_url = state.services.sign_in.begin(return_to)
    response = RedirectResponse(authorization_url, status_code=302)
    state.write_transaction(response, transaction)
    return response


def _refused(
    request: Request, access: Access, holder: Session | PendingEnrolment, state: PilotState
) -> Response | None:
    if isinstance(holder, PendingEnrolment) and access is not Access.ENROLMENT:
        if request.method in SAFE_METHODS:
            return RedirectResponse(AUTHENTICATOR_PAGE, status_code=303)
        message = "Set up your authenticator app first."
        return JSONResponse({"message": message, "location": AUTHENTICATOR_PAGE}, status_code=403)
    if access is Access.COACH and holder.role is not Role.COACH:
        return state.renderer.render(
            "refused.html",
            holder=holder,
            status_code=403,
            heading="For the coach only",
            message="This page is for the coach's account.",
        )
    if request.method not in SAFE_METHODS:
        reason = state_change_refusal(
            request.headers, csrf_token=holder.csrf_token, public_origin=state.public_origin
        )
        if reason is not None:
            return JSONResponse({"message": "This request was refused. Reload the page and try again."}, 403)
    return None
