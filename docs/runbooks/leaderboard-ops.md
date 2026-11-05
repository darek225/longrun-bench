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

The board DB is backed up to the **private** repo
`darek225/longrun-bench-data` as GitHub release assets (same pattern as
the Dowser data backups). The DB contains password and token hashes, so
it must never be committed to this repo or any public place; local
snapshots land in `backups/`, which is gitignored.

```bash
# Snapshot (consistent while the server runs) + upload to the data repo:
python3 scripts/backup-db.py --db leaderboard.db

# Local snapshot only:
python3 scripts/backup-db.py --db leaderboard.db --local-only

# Restore the newest backup (sha256 verified before anything is written):
python3 scripts/restore-db.py --out leaderboard.db --force
```

Each backup is a gzipped snapshot plus a manifest (sha256, size, and
per-table row counts only: no emails, no hashes). Restore downloads the
asset and manifest, verifies the checksum, then integrity-checks the
database before placing it. On the production host, run the backup from
a daily systemd timer and keep at least the last 4 weekly releases. A
backup that has never been restored is a hope, not a backup: test a
restore quarterly. Transcripts are content-addressed and hosted by
submitters; the board stores hashes only, so there is no transcript
blob store to back up.

## Health checks

- `GET /api/health` returns `{"ok": true}`.
- `GET /api/tasks` should return the full task count (85 at task set 0.1.0).
- Board empty after a deploy: check you pointed `--tasks-root` and `--db` at
  the production paths, not fresh defaults.
