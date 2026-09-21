"""The OpenCaselist API client (v1-e34-t01-caselist-api-client).

The one adapter behind
:class:`~debate_core.application.ports.caselist_source.CaselistArchiveSource`, used only as
`docs/policies/caselist-data-use.md` permits: the operator's own caselist_token, one request at a
time, at most `caselist.downloads_per_minute` file downloads in any 60 seconds (never more than
the maintainer's 10), and off entirely until `caselist.api_enabled` is set.

| Module | What it is |
|---|---|
| `client.py` | `OpenCaselistClient`: the port, composed from the modules below, and the settings gate |
| `transport.py` | The shared base: token cookie for the API host only, pacing, backoff, typed errors |
| `pacing.py` | Minimum request interval and the rolling 60-second download window |
| `inbox_writer.py` | Streamed download → checked, fsynced, atomically named file in the inbox |
| `caselists.py`, `downloads.py`, `openev.py`, `auth.py` | One small module per resource group |
| `models.py` | The API's response bodies, tolerant of unknown fields |
| `token_store.py` | The caselist_token in the OS keychain or a 0600 file |
| `redaction.py` | The log filter that keeps the token and file paths out of every record |

V3 (v3-e24-t02) adds `schools`, `teams`, `rounds` and `cites` modules on the same transport.
"""

from debate_core.integrations.opencaselist.client import NetworkDisallowed, OpenCaselistClient
from debate_core.integrations.opencaselist.token_store import (
    CaselistTokenStore,
    StoredCaselistToken,
    default_secret_file,
)

__all__ = [
    "CaselistTokenStore",
    "NetworkDisallowed",
    "OpenCaselistClient",
    "StoredCaselistToken",
    "default_secret_file",
]
