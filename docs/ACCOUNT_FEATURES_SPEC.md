# Account features spec: Google OAuth wiring + forgot password (2026-11-04)

Written before the build, per the workspace standards. The evaluator
checks these criteria against the shipped code and the live site; the
builder does not self-certify.

## Problem

1. Google sign-in code exists end to end but reads its client id/secret
   only from process env. Production secrets live in
   `/opt/longrun-bench/.env.production` on the Oracle instance, and
   there is no write path into the instance (no SSH route, Oracle Run
   Command dead on this tenancy). Setting the env therefore needs an
   instance swap. The site also renders the Google button even when
   sign-in is unconfigured (the start route answers 501 JSON).
2. There is no forgot/reset-password flow at all: a user who forgets
   their password is locked out (verified 2026-11-01: routes 404).

## Design

- **Site settings in the DB** (`site_settings` table, key/value). Google
  credentials resolve DB first, env fallback, so existing deployments
  keep working. Mail credentials for the reset mailer live in the same
  table (`mail_api_key`, `mail_from`).
- **Admin bootstrap endpoint** (`POST /api/admin/settings`, session or
  upload-token auth). The first authenticated write claims the admin
  role (stored as `site_admin_user_id`); later writes are accepted only
  from that user. Only allowlisted keys are accepted. Responses report
  which keys are set, never their values. `GET /api/admin/settings`
  returns the same set/unset status.
- **Reset mailer** (`leaderboard/mailer.py`): sends via the mails.dev
  hosted API (`POST https://api.mails.dev/v1/send`, Bearer key from
  settings), the assistant-operated mailbox. One small function so tests
  stub it; the network call is the only part that cannot run offline.
- **Password reset**: `POST /api/auth/forgot-password` always answers
  200 with the same body whether or not the email exists (no account
  enumeration). For an existing account it stores a sha256-hashed,
  single-use token with a 60-minute expiry and emails a link to
  `<base>/#/reset-password?token=<token>`. `POST /api/auth/reset-password`
  validates the token, sets the new password (same 8+ rule), marks the
  token used, revokes all of the user's sessions, and signs the user in.
  Google-only accounts (no password yet) may set one this way.
- **Public config** (`GET /api/auth/config`): `{google_enabled,
  password_reset_enabled}` from server truth. The site shows the Google
  button only when enabled and the forgot link only when the mailer is
  configured.

## Criteria (evaluator checks each, PASS/FAIL with evidence)

1. Settings bootstrap: first authenticated POST claims admin and stores
   values; a second user's POST is rejected; unknown keys are rejected;
   no response ever contains a stored value.
2. Google sign-in resolves credentials from DB settings (a stubbed
   exchange completes the full start -> callback -> session flow with
   creds only in the DB), and env-only configuration still works.
3. Forgot password: identical 200 response for known and unknown
   emails; for a known email exactly one reset email is sent through
   the (stubbed) mailer containing the reset link.
4. Reset: a valid token sets the new password and signs the user in;
   the same token cannot be used twice; an expired token is rejected;
   all pre-reset sessions stop working.
5. `/api/auth/config` reflects reality in both states (unconfigured:
   both false; configured: both true).
6. Site UI: Google button hidden when `google_enabled` is false;
   forgot-password view posts and shows the generic confirmation;
   reset view reads the token from the URL and completes the flow.
7. Full leaderboard + harness test suites pass; schema.sql carries the
   two new tables for parity with the SQLite schema.
8. Live: after deploy, production `/api/auth/config` answers, the
   forgot/reset round trip works against a real mailbox, and Google
   sign-in completes end to end once the client is configured.
