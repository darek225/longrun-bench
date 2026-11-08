# Leaderboard ops

## Run the reference implementation

```bash
PYTHONPATH=harness/src:. python3 -m leaderboard.api --db leaderboard.db --tasks-root tasks --port 8787
```

Serves the board site at `/` and the API under `/api/`. The default board
view is Marathon / standard profile (docs/plan/04).

## Accounts and sign-in

Viewing is public; uploading a score requires an account (email +
password, or Google). Agents submit with a personal upload token
(Account -> Upload tokens); tokens and passwords are stored only as
hashes and tokens are revocable.

Google sign-in takes its client id/secret from the DB site settings
(set through the admin bootstrap below); the environment variables
`LONGRUN_GOOGLE_CLIENT_ID` / `LONGRUN_GOOGLE_CLIENT_SECRET` still work
as a fallback for deployments that predate the settings table.

Create the OAuth client in Google Cloud Console with the authorized
redirect URI `https://<your-host>/api/auth/google/callback`. When
sign-in is not configured the site still runs: email/password accounts
work and the Google button is hidden (the site reads
`GET /api/auth/config`).

## Site settings (admin bootstrap)

Deployment config that cannot live in the public repo (Google OAuth
client, reset mailer) is stored in the `site_settings` table and set
through one endpoint. The first authenticated write claims the admin
role for that account; later writes are accepted only from the admin.
Responses report only which keys are set, never values.

```bash
# As the admin account (session cookie or X-Upload-Token):
curl -X POST https://<your-host>/api/admin/settings \
  -H 'X-Upload-Token: lru_...' -H 'Content-Type: application/json' \
  -d '{"settings": {"google_client_id": "...", "google_client_secret": "...",
       "mail_api_key": "...", "mail_from": "bot@mails.dev"}}'
curl https://<your-host>/api/admin/settings -H 'X-Upload-Token: lru_...'
```

Allowlisted keys: `google_client_id`, `google_client_secret`,
`mail_api_key`, `mail_from`. Password reset mail sends through the
mails.dev hosted API from `mail_from`; reset is enabled exactly when
`mail_api_key` and `mail_from` are both set (see
`GET /api/auth/config`).

Production deploys run the same API contract against Postgres using
`leaderboard/schema.sql`; the reference implementation uses SQLite with the
mirrored schema in `leaderboard/store.py`. Scores are append-only in both:
corrections are new rows linked by `supersedes`, never updates.

## Backup and restore

The board DB is backed up to the **private** OCI Object Storage bucket
`longrun-bench-backups` in Darek's tenancy. The DB contains password
and token hashes, so it must never be committed to this repo or any
public place; local snapshots land in `backups/`, which is gitignored.

```bash
# Snapshot (consistent while the server runs) + upload to the bucket.
# On the instance this runs as longrun-backup.service (daily timer)
# and authenticates as the instance itself (instance principal; the
# dynamic group may use objects in this one bucket only):
python3 scripts/backup-db.py --db leaderboard.db

# Local snapshot only:
python3 scripts/backup-db.py --db leaderboard.db --local-only

# Restore the newest backup (sha256 verified before anything is
# written). Runs from an operator machine with an OCI config
# (~/.oci/config); never from the leaderboard instance:
python3 scripts/restore-db.py --out leaderboard.db --force
```

Each backup is a gzipped snapshot plus a manifest (sha256, size, and
per-table row counts only: no emails, no hashes). Restore downloads
the archive and manifest, verifies the checksum, then
integrity-checks the database before placing it. The instance needs
the OCI Python SDK (`pip install oci`); install.sh provisions it. A
backup that has never been restored is a hope, not a backup: test a
restore quarterly. Transcripts are content-addressed and hosted by
submitters; the board stores hashes only, so there is no transcript
blob store to back up. (Pre-2026-11 backups went to GitHub releases on
`darek225/longrun-bench-data`; the newest of those is 2026-10-22. The
Oct 22 restore drill predates the transport switch.)

## Health checks

- `GET /api/health` returns `{"ok": true}`.
- `GET /api/tasks` should return the full task count (85 at task set 0.1.0).
- Board empty after a deploy: check you pointed `--tasks-root` and `--db` at
  the production paths, not fresh defaults.

## Production failure modes (learned 2026-11-06/07)

- **Auto-deploy silently dead:** `longrun-update.service` exited 128
  every 10 minutes because root's git refused the `longrun`-owned
  repo ("dubious ownership"). Fix on the instance:
  `git config --global --add safe.directory /opt/longrun-bench` as
  root. Check with `systemctl show longrun-update.service -p Result
  -p ExecMainStatus` and `git -C /opt/longrun-bench rev-parse HEAD`.
- **OAuth redirect_uri must be the public URL:** the request path
  crosses Vercel (rewrite) and Caddy, and Caddy rewrites
  `X-Forwarded-Host` to the origin IP, so header inference cannot
  work. `LONGRUN_PUBLIC_URL=https://longrun-bench.vercel.app` is
  pinned in `/opt/longrun-bench/.env.production` (install.sh writes
  it from the deploy domain); `_base_url` prefers it.
- **Reset mail 403s without a browser UA:** mails.dev is behind
  Cloudflare, which rejects the default Python-urllib user agent
  (error 1010). `mailer.send_email` sends a browser UA. The forgot
  endpoint swallows mail errors by design, so verify delivery with
  the reset round-trip, not the endpoint's 200.
- **Backups died on a missing credential path:** backups originally
  uploaded via the GitHub CLI, which instance #4 never had (nor a
  credential for it), so no backup landed between 2026-10-22 and
  2026-11-07. The transport is now OCI Object Storage with
  instance-principal auth (see the Backup section): no portable
  credential, nothing to expire. If the daily backup service fails,
  check `systemctl show longrun-backup.service -p Result` and that
  the `oci` SDK imports under the backup venv
  (`/opt/longrun-bench/.venv-backup/bin/python`).
- **OCI Run Command is not root:** commands run as `ocarun` with no
  passwordless sudo. Real instance access is SSH as `ubuntu` (the
  instance trusts the Muse VM's `~/.ssh/id_ed25519`; from the VM
  that route needs the egress destination approved by Darek).
  Instance metadata (incl. authorized keys) is readable from a run
  command via `http://169.254.169.254/opc/v2/instance/metadata/`
  with header `Authorization: Bearer Oracle` (the v1 path without
  the header returns error text).
