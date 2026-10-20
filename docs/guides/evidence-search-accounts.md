<!-- docs-index: For the coach and students: accounts for the team evidence search, first sign-in, the authenticator app, the backup email, resets and lost phones -->
# Signing in to the team evidence search: a guide for the coach and students

The team evidence search is at **<https://tub.wfbdebate.com/>**. It works in Chrome on a school
Chromebook and at home. You sign in with a username and password the coach gives you, and a code
from an authenticator app on your phone. There is no Google or school sign-in, and nobody can make
their own account: the coach makes every one.

How it is built: [ADR-0019](../adr/0019-student-search-pilot-stack-sign-in-and-hosting.md),
section (d). How it is set up in AWS: [the pilot's runbook](../runbooks/evidence-search.md).

- [For students](#for-students)
  - [Your first sign-in](#your-first-sign-in)
  - [Choosing an authenticator app](#choosing-an-authenticator-app)
  - [Every sign-in after that](#every-sign-in-after-that)
  - [The optional backup email](#the-optional-backup-email)
  - [A new phone, a lost phone, a forgotten password](#a-new-phone-a-lost-phone-a-forgotten-password)
- [For the coach](#for-the-coach)
  - [Before you start](#before-you-start)
  - [Adding a student](#adding-a-student)
  - [A student with no phone](#a-student-with-no-phone)
  - [Resetting a lost password or a lost phone](#resetting-a-lost-password-or-a-lost-phone)
  - [Suspending and removing accounts](#suspending-and-removing-accounts)
- [When something goes wrong](#when-something-goes-wrong)

## For students

### Your first sign-in

You need three things: the **username** and **temporary password** the coach gives you in person,
and your phone with an authenticator app on it ([which app](#choosing-an-authenticator-app)). The
temporary password works for seven days; after that, ask the coach for a new one.

1. Open <https://tub.wfbdebate.com/>. You are sent to the sign-in page, at `auth.tub.wfbdebate.com`.
2. Enter your username and the temporary password.
3. Choose your own password: at least 12 characters. A short sentence you will remember works well.
   Nobody else, the coach included, can see it.
4. Set up two-step sign-in. Choose the **authenticator app**. Open the app on your phone, choose to
   add an account by scanning a QR code, and scan the code on the screen. The app now shows a
   six-digit code that changes every 30 seconds. Type the code it shows.
5. You are signed in.

If at step 4 you chose to get codes by **email** instead, the search shows you its own *Set up your
authenticator app* page before anything else. Scan its QR code the same way and enter a code.
Email codes are only a backup; your account needs the app first.

**On a shared Chromebook, sign out when you finish**: the *Sign out* button at the top of every page.
The search also signs you out on its own after an hour without using it, and twelve hours after you
signed in.

### Choosing an authenticator app

Any authenticator app that scans a QR code works. Common free ones:

- **Google Authenticator** (iPhone and Android);
- **Microsoft Authenticator** (iPhone and Android).

The app stays on your phone. It needs no account, and the search never sees what else is on your
phone. If you do not have a phone, tell the coach: there is a [way for that](#a-student-with-no-phone).

### Every sign-in after that

Open <https://tub.wfbdebate.com/>, enter your username and password, then the six-digit code your
authenticator app shows for the team evidence search.

### The optional backup email

You can add an email address as a second way to get a sign-in code, for a day your phone is not with
you. It is optional. The search uses it only to send you codes.

1. Sign in and open **Your account** (the link at the top of the page).
2. Under *Backup email*, enter your address and choose **Send a code**.
3. Enter the six-digit code from the email and choose **Confirm**.

From then on, the sign-in page asks each time which you want: a code from the app or a code by
email. To stop using the address, choose **Remove the backup email** on the same page.

### A new phone, a lost phone, a forgotten password

- **A new phone, and you still have the old one** (or a backup email): sign in as usual, open **Your
  account**, choose **Set up a new authenticator app**, then **Start**, and scan the new code with
  the app on the new phone. The old phone stops working once you confirm the new one.
- **A lost phone and a backup email**: sign in, choose the email code when the sign-in page asks,
  then set up the app on your new phone from **Your account** as above.
- **A lost phone and no backup email**: ask the coach for a reset. You get a new temporary password,
  and at your next sign-in you choose a new password and set up the authenticator app again, as on
  your [first sign-in](#your-first-sign-in).
- **A forgotten password**: there is no "forgot password" link. Ask the coach for a reset.

## For the coach

You manage accounts from your Mac with `debate-research tub users`. Every command acts on one
environment: `--env prod` for students, `--env dev` for the maintainer's and synthetic test
accounts only (the dev pool never holds a student, ADR-0013). Each command writes one record to the
pilot's audit log, naming the account by its internal identifier and never by username.

| You want to | Command |
|---|---|
| Make an account | `tub users add` |
| See every account | `tub users list` (usernames and roles, nothing else) |
| Reset a lost password or phone | `tub users reset` |
| Suspend an account, and undo it | `tub users disable`, `tub users enable` |
| Delete an account and everything on it | `tub users remove` |
| Let a student with no phone use email | `tub users email-second-factor --allow` |

### Before you start

Sign in to AWS and tell the commands which user pool to use. The pool id comes from Terraform's
output for the environment; `WT` is the checkout holding the Terraform (the main clone once the
pilot has merged).

**Operator command** (expected runtime ~1 min)
Where: your Mac, in `$WT`
```bash
WT=/path/to/your/checkout
cd "$WT"
aws sso login --sso-session debate
export TUB_USER_POOL_ID="$(terraform -chdir=infrastructure/envs/prod output -raw evidence_search_user_pool_id)"
aws sts get-caller-identity --profile debate-prod-tub-accounts --query Arn --output text
```
Success looks like an ARN containing `AWSReservedSSO_DebateProdTubAccounts`. For dev, use
`infrastructure/envs/dev` and `debate-dev-tub-accounts`. The commands use the profile
`debate-<env>-tub-accounts` unless `--profile` names another.

### Adding a student

A username is 3 to 32 lowercase letters, digits and dots, such as `debater.2027`. It is never an
email address, and the command refuses one. The student types it at every sign-in, so pick one
they will remember; it does not have to be their full name.

```bash
STUDENT='debater.2027'
uv run debate-research tub users add "$STUDENT" --role student --env prod
```
Success looks like:

```text
Created debater.2027 (student).
Temporary password, shown this once: abcd-efgh-jkmn-pqrs
Give it to the student in person. It works for 7 days, and they choose their own at the first sign-in.
```

The temporary password is shown only here, once. It is not in the audit log, and nobody can look it
up later: if it is lost, run `reset`. Give it to the student in person, not by email or message. For
another coach, use `--role coach`.

`tub users list --env prod` shows every account's username and role and nothing else, not even
whether a student added an email.

### A student with no phone

A school Chromebook cannot run an authenticator app. For a debater with no phone, you can let a
verified email be their only second factor (PM ruling, 2026-10-19). Do it when you add them, or
later:

```bash
STUDENT='debater.2027'
uv run debate-research tub users add "$STUDENT" --role student --email-second-factor --env prod
```

```bash
STUDENT='debater.2027'
uv run debate-research tub users email-second-factor "$STUDENT" --allow --env prod
```

At their first sign-in, the student chooses **email** when the sign-in page asks how to get codes,
enters their address and confirms the code sent to it. From then on they sign in with a code by
email. On the account page they cannot remove that address, because it is their only second factor.
To withdraw the exception, run `email-second-factor` with `--withdraw`; at their next sign-in they
must set up an authenticator app.

Until AWS grants the pilot production email sending (the runbook's step 4), codes reach only
addresses the operator has verified, so check with the operator before relying on this.

### Resetting a lost password or a lost phone

```bash
STUDENT='debater.2027'
uv run debate-research tub users reset "$STUDENT" --env prod
```
Success looks like `Reset debater.2027 (student).` and a new temporary password, shown once. The reset
also removes the student's authenticator app and signs them out everywhere within five minutes. At
their next sign-in they choose a new password and set up the authenticator app again. A student with
a verified backup email can replace a lost phone themselves instead ([students' section](#a-new-phone-a-lost-phone-a-forgotten-password)).

### Suspending and removing accounts

`disable` stops an account signing in and ends any open session within five minutes; `enable`
undoes it. `remove` deletes the account and everything on it, the email included, and cannot be
undone (the student would need a new account).

```bash
STUDENT='debater.2027'
uv run debate-research tub users disable "$STUDENT" --env prod
```

```bash
STUDENT='debater.2027'
uv run debate-research tub users remove "$STUDENT" --env prod
```

At the end of the season, run `tub users list --env prod` and remove everyone who has graduated or
left the team.

## When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| *Sign-in did not finish* | The sign-in took more than five minutes, or was started in another tab | Choose *Start again* |
| *Your account is not set up for the search yet* | The account has no role | The coach checks `tub users list`; an account listed with role `none` needs removing and adding again |
| *That code was not accepted* | The code was old or mistyped | Enter the newest code the app shows; check the phone's clock is set automatically |
| You are sent back to the sign-in page | You were signed out: an hour without use, twelve hours since signing in, or the coach reset or disabled the account | Sign in again; if that fails, ask the coach |
| The page does not load on the school network | The school's web filter blocks it | Tell the coach; the request to school IT is the runbook's step 12 |
| `not a username: ...` (coach) | The name has capitals, an `@` or other characters | Use lowercase letters, digits and dots |
| `aws sso login --profile debate-prod-tub-accounts` (coach) | Your AWS sign-in expired | Run that command, then the one that failed |
| The audit record could not be written (coach) | The change was made but not recorded, and no password was shown | Run `reset` once AWS answers again |
