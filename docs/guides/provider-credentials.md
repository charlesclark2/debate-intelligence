<!-- docs-index: Keeping the search providers' keys and the contact email in ~/.debate-research/<env>.env, so live searches run from any folder -->
# Provider keys and the contact email: the per-user file

`debate-research search` asks Crossref, OpenAlex, GovInfo and the other discovery providers. A few
of them work better, or at all, with a credential of your own:

| Variable | What it does without it |
|---|---|
| `DEBATE_PROVIDERS__CONTACT_EMAIL` | Crossref serves you from its public pool, one query a second instead of three, so a long search can leave some of its Crossref queries unasked. |
| `DEBATE_PROVIDERS__OPENALEX_API_KEY` | OpenAlex answers keyless, with a lower daily allowance. |
| `DEBATE_PROVIDERS__API_DATA_GOV_KEY` | GovInfo is not asked. The key is free from api.data.gov. |
| `DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar is not asked. A search that has it enabled names it `not configured` with the cure, request a key through the form on Semantic Scholar's API page (semanticscholar.org/product/api), and does not count it as partial. A search that names it with `--providers` gives the same cure and is partial; one that has no other provider to ask exits `1`, and its message names Semantic Scholar with the cure too (`v1-e07-t23`). The shared keyless pool refused every request in the operator's smoke of 2026-11-11 (`v1-e07-t20`). No profile enables Semantic Scholar yet. |
| `DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_INSECURE_HTTP` | Not a credential, and off unless you set it: Semantic Scholar is asked over HTTPS, like every other provider. See [Semantic Scholar over HTTP](#semantic-scholar-over-http-your-choice-for-your-own-key). |

**When a provider is held.** A provider that answers `429` is asking us to slow down, and a search
then holds it back (`v1-e07-t22`): its queries still waiting are skipped, never sent, the footer
names it `rate limited`, and the search is partial (exit `6`), or failed (`3`) when no other
provider answered. The hold lasts as long as the provider's `Retry-After` says, or else 2 seconds,
doubling with each `429` in a row up to a minute; a search a little later asks it again.

None of them goes in a committed file. Since `v1-e41-t22` each machine keeps them in one file of its
own, `~/.debate-research/dev.env` for the dev environment and `~/.debate-research/prod.env` for
prod, beside each environment's data folder. Every command reads it, whatever folder you run it in,
so live searches no longer have to be run from the one folder whose `.env` holds the keys (until
now, `~/Documents/debate/crossref-smoke`). No command writes it: you do, with the steps below.

## The rules the file follows

* **Those names only:** the four credentials and Semantic Scholar's HTTP opt-in. Any other line is refused, by the file's name and the line's number,
  and the command stops until it is fixed. That includes `DEBATE_ENV` and the OpenCaselist token:
  the token is kept by `debate-research caselist auth login`, never in this file. A line with no
  `=`, or whose name is not a setting name, is named by its line number alone, because it could be a
  pasted key. A name written twice is refused with both line numbers. No message ever shows a value.
* **Only you may have any permission on it** (`chmod 600`). If your group or anyone else can read
  or change it, it is not read at all, and every command that loads settings stops with the
  `chmod` that fixes it. An editor that saves by replacing the file can reset this; the message
  says so the next time you run a command. Windows cannot say who may read a file, so there the
  file is refused and the keys go in environment variables instead.
* **A key exported in your shell, or left in a `.env`, wins over the file.** The order, highest
  first, is: a command-line flag, a `DEBATE_*` variable exported in your shell, the `.env` of the
  checkout you run in (or, outside a checkout, of the folder you run in), this file, the
  environment's profile, the built-in defaults. So an old key left in a checkout's or a folder's
  `.env` is the one used there, and the file's is not. `debate-research config show` says which
  won: its Source column reads `user-env:~/.debate-research/dev.env` for the file,
  `dotenv:<path>` for a `.env`, and `env:DEBATE_...` for an exported variable. A variable exported
  empty also wins, which is how to force Crossref's public pool for one command.
* **The `test` environment never reads it.**

## Semantic Scholar over HTTP: your choice for your own key

On 2026-11-12 Semantic Scholar's HTTPS address answered every request carrying a valid key as if it
carried none (`429`, "apply for a key"), while its plain-HTTP address answered the same request, key
and minute with results. The operator has reported it to Semantic Scholar. Until they fix it, a person
who wants their own key to work can add this line to their own per-user file:

```text
DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_INSECURE_HTTP=true
```

What it does (`v1-e07-t20`):

* **Semantic Scholar alone is asked at `http://api.semanticscholar.org`**, so your key crosses the
  network unencrypted, readable by anyone on the path between you and Semantic Scholar. It is still sent
  only in its header, never in an address, a log line or any output. Every other provider is still asked
  over HTTPS.
* **No redirect is followed.** If Semantic Scholar starts sending HTTP requests to HTTPS, the search
  names it `error: HTTP 301: redirected to HTTPS at api.semanticscholar.org, not followed`, and nothing
  more is sent.
* **It is said wherever it applies.** `doctor --providers` adds a row, `Warning | Semantic Scholar asked
  over HTTP: the key is sent unencrypted`, and a search that asked Semantic Scholar prints the same
  sentence in its footer, under Semantic Scholar's line. With `--json`, both carry it as
  `asked_over_http`, the provider and the sentence; it is an empty list otherwise. Without a key,
  Semantic Scholar is not asked at all, so the line does not appear.
* **It is the operator's choice, for the operator's key.** It is the one name in the per-user file that
  is not a credential: it decides only how your own key is sent, and writing it is your consent to that,
  so it lives beside the key. No committed profile sets it, and a test fails if one does.
* **It comes out when HTTPS works.** Once Semantic Scholar answers keyed requests over HTTPS, the setting
  is removed in one change (`v1-e07-t26`), and a file that still sets it is refused by name, so you know to
  delete the line.

## On a machine that has no keys yet

Create the file, empty and private. This block makes no change if the file is already there.

```bash
mkdir -p ~/.debate-research
test -e ~/.debate-research/dev.env || (umask 077 && touch ~/.debate-research/dev.env)
chmod 600 ~/.debate-research/dev.env
nano ~/.debate-research/dev.env
```

In the editor, write one line for each credential you have, with your own address and keys where
these placeholders are, then save and quit (Ctrl-O, Enter, Ctrl-X):

```text
DEBATE_PROVIDERS__CONTACT_EMAIL=you@example.org
DEBATE_PROVIDERS__OPENALEX_API_KEY=<your key>
DEBATE_PROVIDERS__API_DATA_GOV_KEY=<your key>
```

For prod, do the same with `~/.debate-research/prod.env`. Then check it as in
[Checking which credentials are used](#checking-which-credentials-are-used).

## Moving the keys out of the smoke folder

On the operator's Mac the keys are in `~/Documents/debate/crossref-smoke/.env`. This block copies
only the lines that set the four names into `~/.debate-research/dev.env`, created private, and
prints how many lines it copied and never what they say. It does nothing, and says why, if a
`DEBATE_` variable is set in the shell (it would win over the file and make the check below
misleading) or if the file already exists (it never overwrites one).

```bash
if env | grep -q '^DEBATE_'; then
  echo "STOP: a DEBATE_ variable is set in this shell. Open a new terminal, or unset it, then paste this block again."
elif [ -e ~/.debate-research/dev.env ]; then
  echo "STOP: ~/.debate-research/dev.env already exists, and this block never overwrites it."
else
  mkdir -p ~/.debate-research
  (umask 077 && grep -E '^(export[[:space:]]+)?DEBATE_PROVIDERS__(CONTACT_EMAIL|OPENALEX_API_KEY|SEMANTIC_SCHOLAR_API_KEY|API_DATA_GOV_KEY)=' ~/Documents/debate/crossref-smoke/.env > ~/.debate-research/dev.env)
  chmod 600 ~/.debate-research/dev.env
  echo "copied $(wc -l < ~/.debate-research/dev.env | tr -d ' ') credential lines into ~/.debate-research/dev.env"
fi
```

It should say it copied one line for each credential the smoke folder's `.env` had, two or three
on the operator's Mac. `copied 0` means none of the four names was found there: look at the
smoke folder's `.env` in an editor rather than printing it. The smoke folder's own `.env` is left as
it was; commands run inside that folder go on using its copy, which `config show` names as
`dotenv:`.

## Checking which credentials are used

Run these from your home folder, where no checkout's `.env` can win over the file. Neither prints a
value: `config show` masks each credential as `***`, and `doctor --providers` names only where each
came from. In a source checkout, put `uv run` in front of each command.

```bash
cd ~
debate-research config show | grep -E 'providers\.(contact_email|openalex_api_key|semantic_scholar_api_key|semantic_scholar_insecure_http|api_data_gov_key)'
debate-research doctor --providers
```

Each credential you wrote should show `***` and the source `user-env:~/.debate-research/dev.env`,
and the `Credentials file` row should say `~/.debate-research/dev.env: read`. A provider without
its credential says what a search does without it, for example `Crossref | no contact email:
Crossref's public pool` or `GovInfo | no GovInfo key: GovInfo not asked`; `doctor --providers`
never fails for that. If you set Semantic Scholar's HTTP opt-in and its key, a `Warning` row says the key
is sent unencrypted. If a command stops instead, its message names the file, the line and the fix.

To check prod's file, put `DEBATE_ENV=prod` in front of each command: `DEBATE_ENV=prod
debate-research doctor --providers`.
