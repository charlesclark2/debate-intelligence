"""The pilot's routes: sign-in and the account (v1-e39-t05), and the search pages (v1-e39-t06).

Each route parses its input, calls a use case in `debate_core.application.tub`, and renders or
answers. The gate in :mod:`debate_api.access` has already decided who may reach it and checked a
state-changing request's CSRF token, so a route reads the holder from `request.state.holder` and
never checks a session itself.

A state-changing route is a POST that `app.js` sends with `fetch`, and it answers JSON: a
`location` to go to next, or, through the app's error handlers, a `message` to show.

The search pages' handlers are in :mod:`debate_api.search_pages`; every one is a `GET`. Download
(`v1-e39-t08`) is :mod:`debate_api.download`'s, a POST like the rest, answered with the file or JSON.
"""

from __future__ import annotations

from typing import Final, cast
from urllib.parse import parse_qs

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from debate_api.access import Access, RouteAccess
from debate_api.cookies import ALL_COOKIES, ENROLMENT_COOKIE, SESSION_COOKIE, SIGN_IN_COOKIE
from debate_api.download import card_download
from debate_api.pages import IMMUTABLE, qr_code_svg
from debate_api.search_pages import card_copy, card_page, search_page
from debate_api.state import pilot_state
from debate_core.application.tub.sessions import PendingEnrolment, Session
from debate_core.application.tub.sign_in import EnrolmentRequired, SignInRefusal, SignInRefused

__all__ = ["ACCOUNT_NOTICES", "ROUTE_ACCESS", "register_routes"]

ROUTE_ACCESS: Final = {
    "/healthz": Access.PUBLIC,
    "/static/{digest}/{name}": Access.PUBLIC,
    "/auth/callback": Access.PUBLIC,
    "/signed-out": Access.PUBLIC,
    "/auth/sign-out": Access.ENROLMENT,
    "/account/authenticator": Access.PENDING_ENROLMENT,
    "/": Access.SIGNED_IN,
    "/search": Access.SIGNED_IN,
    "/cards/{caselist}/{cluster_id}": Access.SIGNED_IN,
    "/cards/{caselist}/{cluster_id}/copy": Access.SIGNED_IN,
    "/download": Access.SIGNED_IN,
    "/account": Access.SIGNED_IN,
    "/account/email": Access.SIGNED_IN,
    "/account/email/verify": Access.SIGNED_IN,
    "/account/email/remove": Access.SIGNED_IN,
    "/coach": Access.COACH,
}
"""Every route's path and the access it needs. A route added without an entry here needs a session."""

ACCOUNT_NOTICES: Final = {
    "email-sent": "We sent a code to that address. Enter it below to confirm it.",
    "email-confirmed": "Your backup email is confirmed. When you sign in you can choose a code sent to it.",
    "email-removed": "Your backup email is removed.",
}
"""The account page's notices, chosen by a fixed key: the page never repeats what a URL says."""

_FORM_FIELDS_LIMIT: Final = 8


def register_routes(app: FastAPI, routes: RouteAccess) -> None:
    """Attach every route to `app`, and record the access each needs from :data:`ROUTE_ACCESS`."""
    app.add_api_route("/healthz", healthz, methods=["GET"], include_in_schema=False)
    app.add_api_route("/static/{digest}/{name}", static_asset, methods=["GET"], include_in_schema=False)
    app.add_api_route("/auth/callback", callback, methods=["GET"], include_in_schema=False)
    app.add_api_route("/signed-out", signed_out, methods=["GET"], include_in_schema=False)
    app.add_api_route("/auth/sign-out", sign_out, methods=["POST"], include_in_schema=False)
    app.add_api_route("/account/authenticator", authenticator_page, methods=["GET"], include_in_schema=False)
    app.add_api_route(
        "/account/authenticator", confirm_authenticator, methods=["POST"], include_in_schema=False
    )
    app.add_api_route("/", search_page, methods=["GET"], include_in_schema=False)
    app.add_api_route("/search", search_page, methods=["GET"], include_in_schema=False)
    app.add_api_route("/cards/{caselist}/{cluster_id}", card_page, methods=["GET"], include_in_schema=False)
    app.add_api_route(
        "/cards/{caselist}/{cluster_id}/copy", card_copy, methods=["GET"], include_in_schema=False
    )
    app.add_api_route("/download", card_download, methods=["POST"], include_in_schema=False)
    app.add_api_route("/account", account, methods=["GET"], include_in_schema=False)
    app.add_api_route("/account/email", add_email, methods=["POST"], include_in_schema=False)
    app.add_api_route("/account/email/verify", confirm_email, methods=["POST"], include_in_schema=False)
    app.add_api_route("/account/email/remove", remove_email, methods=["POST"], include_in_schema=False)
    app.add_api_route("/coach", coach, methods=["GET"], include_in_schema=False)
    for path, access in ROUTE_ACCESS.items():
        routes.register(path, access)


def _holder(request: Request) -> Session | PendingEnrolment:
    return cast(Session | PendingEnrolment, request.state.holder)


def _session(request: Request) -> Session:
    return cast(Session, request.state.holder)


def _enrolment(request: Request) -> PendingEnrolment:
    return cast(PendingEnrolment, request.state.holder)


async def _form(request: Request) -> dict[str, str]:
    """The urlencoded body `app.js` sent: the first value of each field, at most a handful of fields."""
    fields = parse_qs((await request.body()).decode("utf-8", "replace"), max_num_fields=_FORM_FIELDS_LIMIT)
    return {name: values[0] for name, values in fields.items() if values}


def _go(location: str) -> JSONResponse:
    return JSONResponse({"location": location})


# --------------------------------------------------------------------------------------------
# Session-free
# --------------------------------------------------------------------------------------------


async def healthz() -> JSONResponse:
    """The Lambda Web Adapter's readiness check, and the deploy script's check through CloudFront."""
    return JSONResponse({"status": "ok"})


async def static_asset(digest: str, name: str, request: Request) -> Response:
    """The pilot's script or stylesheet, at its content-hashed path; any other path is not found."""
    for asset in pilot_state(request).static_assets:
        if (asset.name, asset.digest) == (name, digest):
            return Response(asset.content, media_type=asset.media_type, headers={"Cache-Control": IMMUTABLE})
    return Response(status_code=404, headers={"Cache-Control": "private, no-store"})


def callback(request: Request) -> Response:
    """Managed login's answer: a session, the authenticator page, or a page saying it did not finish."""
    state = pilot_state(request)
    try:
        outcome = state.services.sign_in.complete(
            transaction=state.transaction_in(request),
            state=request.query_params.get("state"),
            code=request.query_params.get("code"),
            provider_error=request.query_params.get("error"),
        )
    except SignInRefused as refused:
        response: Response = state.renderer.render(
            "sign_in_failed.html", status_code=400, message=_why(refused)
        )
        state.clear(response, SIGN_IN_COOKIE)
        return response
    if isinstance(outcome, EnrolmentRequired):
        response = RedirectResponse("/account/authenticator", status_code=303)
        state.write_enrolment(response, outcome.enrolment)
        state.clear(response, SIGN_IN_COOKIE, SESSION_COOKIE)
        return response
    response = RedirectResponse(outcome.return_to, status_code=303)
    state.write_session(response, outcome.session)
    state.clear(response, SIGN_IN_COOKIE, ENROLMENT_COOKIE)
    return response


def _why(refused: SignInRefused) -> str:
    if refused.refusal in {SignInRefusal.NO_TRANSACTION, SignInRefusal.TOO_SLOW}:
        return "The sign-in took too long, or was started in another tab or browser."
    if refused.refusal is SignInRefusal.NO_ROLE:
        return "Your account is not set up for the search yet. Ask your coach."
    return "Something about the sign-in did not check out, so you were not signed in."


def signed_out(request: Request) -> HTMLResponse:
    """Where managed login's `/logout` returns to. Clears every pilot cookie again, in case."""
    state = pilot_state(request)
    response = state.renderer.render("signed_out.html")
    state.clear(response, *ALL_COOKIES)
    return response


# --------------------------------------------------------------------------------------------
# A session or a pending enrolment
# --------------------------------------------------------------------------------------------


async def sign_out(request: Request) -> JSONResponse:
    """Revoke the refresh token, clear every cookie, and go through managed login's `/logout`."""
    state = pilot_state(request)
    logout_url = await run_in_threadpool(state.services.sign_in.sign_out, _holder(request).refresh_token)
    response = _go(logout_url)
    state.clear(response, *ALL_COOKIES)
    request.state.cookies_written = True
    return response


def authenticator_page(request: Request) -> HTMLResponse:
    """A pending enrolment's QR page. The gate sends a full session to `/account` (PM ruling (d))."""
    state = pilot_state(request)
    enrolment = _enrolment(request)
    authenticator = state.services.account_page.begin_authenticator(enrolment)
    secret = authenticator.secret.reveal()
    return state.renderer.render(
        "authenticator.html",
        holder=enrolment,
        qr_svg=qr_code_svg(authenticator.uri),
        secret_groups=" ".join(secret[index : index + 4] for index in range(0, len(secret), 4)),
    )


async def confirm_authenticator(request: Request) -> JSONResponse:
    """Confirm the new authenticator; the pending enrolment becomes a session."""
    state = pilot_state(request)
    enrolment = _enrolment(request)
    code = (await _form(request)).get("code", "")
    await run_in_threadpool(state.services.account_page.confirm_authenticator, enrolment, code)
    session = state.services.sign_in.finish_enrolment(enrolment)
    response = _go(enrolment.return_to)
    state.write_session(response, session)
    state.clear(response, ENROLMENT_COOKIE)
    request.state.cookies_written = True
    return response


# --------------------------------------------------------------------------------------------
# A session
# --------------------------------------------------------------------------------------------


def coach(request: Request) -> HTMLResponse:
    state = pilot_state(request)
    return state.renderer.render(
        "coach.html", holder=_session(request), environment=state.services.configuration.environment
    )


def account(request: Request) -> HTMLResponse:
    session = _session(request)
    state = pilot_state(request)
    view = state.services.account_page.view(session)
    notice = ACCOUNT_NOTICES.get(request.query_params.get("done", ""))
    return state.renderer.render("account.html", holder=session, account=view, notice=notice)


async def add_email(request: Request) -> JSONResponse:
    email = (await _form(request)).get("email", "")
    await run_in_threadpool(
        pilot_state(request).services.account_page.add_backup_email, _session(request), email
    )
    return _go("/account?done=email-sent")


async def confirm_email(request: Request) -> JSONResponse:
    code = (await _form(request)).get("code", "")
    await run_in_threadpool(
        pilot_state(request).services.account_page.confirm_backup_email, _session(request), code
    )
    return _go("/account?done=email-confirmed")


async def remove_email(request: Request) -> JSONResponse:
    await run_in_threadpool(pilot_state(request).services.account_page.remove_backup_email, _session(request))
    return _go("/account?done=email-removed")
