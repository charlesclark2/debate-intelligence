"""The student search pilot's accounts and sign-in (ADR-0019 (d) and (e), `v1-e39-t05`).

Everything here is a rule or a use case; nothing here talks to Cognito, CloudWatch or a browser.
The ports these services are built with are in :mod:`debate_core.application.ports.tub`, and their
adapters in `debate_core.integrations.cognito`, `cloudwatch_audit` and `parameter_store`.

* :mod:`.identity`: usernames, roles and the pool's groups, and the two secrets that must never be
  logged (a temporary password and an authenticator's secret).
* :mod:`.audit`: the one record shape every account change is written in.
* :mod:`.accounts`: the coach's `tub users` commands.
* :mod:`.sessions`: what a session holds and the lifetimes ADR-0019 sets for it.
* :mod:`.sign_in`: the authorization-code flow with PKCE, from the redirect to the session.
* :mod:`.account_page`: the student's own changes: the backup email and the authenticator.
"""
