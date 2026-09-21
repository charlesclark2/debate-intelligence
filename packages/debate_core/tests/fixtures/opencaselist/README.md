# OpenCaselist API fixtures (synthetic)

Response bodies for the OpenCaselist API client's tests (`v1-e34-t01-caselist-api-client`). Every
value here is invented. No school, team code, debater, camp or disclosure path in this directory is
real, and none may ever be (`docs/policies/caselist-data-use.md`, prohibited use 9).

**Where the shapes come from.** Not from a real response. They follow the API's own OpenAPI
definitions in the upstream source, `ashtarcommunications/caselist` (read 2026-09-20):

| Fixture | Endpoint | Upstream definition |
|---|---|---|
| `caselists.json` | `GET /v1/caselists` | `server/v1/routes/definitions/schemas/Caselist.js`, plus the columns `controllers/caselists/getCaselists.js` returns with `SELECT *` (`display_name`, `level`, `team_size`) |
| `caselist.json` | `GET /v1/caselists/{caselist}` | same; the path parameter is matched against `name`, which is why the client treats `name` as the slug |
| `downloads.json` | `GET /v1/caselists/{caselist}/downloads` | `schemas/Download.js` (`name`, `url`) and `controllers/caselists/getBulkDownloads.js`, which lists `weekly/<caselist>/*.zip` in the site's object store. Archive names follow `controllers/download/weeklyArchives.js`: `<caselist>-weekly-<date>.zip` and `<caselist>-all-<date>.zip` |
| `openev.json` | `GET /v1/openev` | `schemas/File.js`, plus the `openev` table's `name` column that the controller's `SELECT *` returns; `tags` appears both as an object and as the JSON string the column stores |

Each file also carries a field no schema declares (`field_added_by_a_later_api_version`), because
the models are required to tolerate unknown fields, and `downloads.json` carries a name that follows
neither archive pattern (`testcl26-bundle.zip`), because the client has to say so rather than guess
a date.

**No token and no password are committed here.** The login response is built inside the tests
from a value generated at run time, so there is nothing token-shaped in the repository to leak.
The host `caselist-files.example.invalid` is reserved (RFC 2606) and resolves nowhere.
