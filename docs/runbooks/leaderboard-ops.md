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

Google sign-in is enabled by two environment variables on the server:

```bash
LONGRUN_GOOGLE_CLIENT_ID=<oauth client id> \
LONGRUN_GOOGLE_CLIENT_SECRET=<oauth client secret> \
  python3 -m leaderboard.api ...
```

Create the OAuth client in Google Cloud Console with the authorized
redirect URI `https://<your-host>/api/auth/google/callback`. Without the
variables the site still runs: email/password accounts work and the
Google button returns a clear "not configured" error.

Production deploys run the same API contract against Postgres using
`leaderboard/schema.sql`; the reference implementation uses SQLite with the
mirrored schema in `leaderboard/store.py`. Scores are append-only in both:
corrections are new rows linked by `supersedes`, never updates.

## Backup and restore

- SQLite: stop the server (or use a quiet moment), copy the `.db` file.
  `cp leaderboard.db backups/leaderboard-$(date +%F).db`
- Postgres: `pg_dump $DATABASE_URL > backups/leaderboard-$(date +%F).sql`
- Transcripts are content-addressed and hosted by submitters; the board
  stores hashes only, so there is no transcript blob store to back up.
- Restore: replace the db file / `psql $DATABASE_URL < backup.sql`, restart,
  then `GET /api/health` and spot-check `GET /api/scores`.

Keep at least the last 4 weekly backups. A backup that has never been
restored is a hope, not a backup: test a restore quarterly.

## Health checks

- `GET /api/health` returns `{"ok": true}`.
- `GET /api/tasks` should return the full task count (85 at task set 0.1.0).
- Board empty after a deploy: check you pointed `--tasks-root` and `--db` at
  the production paths, not fresh defaults.
