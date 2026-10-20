"""How a use case's failure reaches the browser: JSON for `app.js`, a page for a `GET`.

Each message is a fixed sentence chosen by the failure's type. None repeats what the student typed,
and none carries a library's own message.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from debate_api.cookies import ENROLMENT_COOKIE, SESSION_COOKIE
from debate_api.state import pilot_state
from debate_core.application.errors import DomainError
from debate_core.application.ports.tub import CodeRefused
from debate_core.application.tub.account_page import EmailIsTheOnlySecondFactor, InvalidEmail
from debate_core.application.tub.sign_in import SessionEnded

__all__ = ["install_error_handlers", "message_for"]

_UNAVAILABLE = "The sign-in service did not answer. Try again in a minute."


def message_for(error: DomainError) -> tuple[int, str]:
    """The status and the sentence a failure is answered with."""
    if isinstance(error, CodeRefused):
        where = "the email" if error.what == "email" else "the app"
        return 400, f"That code was not accepted. Check {where} and enter the newest code."
    if isinstance(error, InvalidEmail):
        return 400, "That is not an email address."
    if isinstance(error, EmailIsTheOnlySecondFactor):
        return 400, str(error).capitalize() + "."
    if isinstance(error, SessionEnded):
        return 401, "You are signed out. Sign in again."
    return 503, _UNAVAILABLE


def install_error_handlers(app: FastAPI) -> None:
    async def domain_error(request: Request, error: Exception) -> Response:
        assert isinstance(error, DomainError)
        status, message = message_for(error)
        state = pilot_state(request)
        if isinstance(error, SessionEnded):
            response: Response = (
                RedirectResponse("/", status_code=303)
                if request.method in {"GET", "HEAD"}
                else JSONResponse({"message": message, "location": "/"}, status_code=status)
            )
            state.clear(response, SESSION_COOKIE, ENROLMENT_COOKIE)
            request.state.cookies_written = True
            return response
        if request.method in {"GET", "HEAD"}:
            holder = getattr(request.state, "holder", None)
            heading = "Something went wrong" if status >= 500 else "That did not work"
            return state.renderer.render(
                "refused.html", holder=holder, status_code=status, heading=heading, message=message
            )
        return JSONResponse({"message": message}, status_code=status)

    app.add_exception_handler(DomainError, domain_error)
