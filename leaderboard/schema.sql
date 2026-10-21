-- LongRun Bench leaderboard schema (docs/plan/04-leaderboard.md §1).
-- Postgres is the production target; the reference implementation in
-- leaderboard/store.py mirrors this schema on SQLite for local/self-hosted
-- use. Scores are append-only: corrections are new rows linked by
-- `supersedes`, never updates to score values.

CREATE TABLE scores (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name    TEXT NOT NULL,            -- e.g. "acme-agent"
  model         TEXT NOT NULL,            -- e.g. "acme-2.5", version pinned
  profile       TEXT NOT NULL CHECK (profile IN ('bare','standard','native')),
  level         TEXT NOT NULL CHECK (level IN ('sprint','marathon','ultra')),
  task_set      TEXT NOT NULL,            -- semver, e.g. "0.1.0"
  harness_hash  TEXT NOT NULL,            -- sha256 of harness build
  board         TEXT NOT NULL CHECK (board IN ('official','community')),
  tier          TEXT NOT NULL DEFAULT 'checks' CHECK (tier IN ('checks','graded','verified')),
  status        TEXT NOT NULL DEFAULT 'provisional' CHECK (status IN ('provisional','verified','disputed')),
  mean_score    NUMERIC NOT NULL,
  ci_low        NUMERIC NOT NULL,
  ci_high       NUMERIC NOT NULL,
  median_score  NUMERIC NOT NULL,
  n_tasks       INT NOT NULL,
  n_runs        INT NOT NULL,
  gen_gap       NUMERIC,                  -- official only; NULL for community
  gap_flag      BOOLEAN DEFAULT FALSE,    -- generalization-gap flag raised
  provisional   BOOLEAN DEFAULT FALSE,    -- n<3 runs per task
  created_at    TIMESTAMPTZ DEFAULT now(),
  supersedes    UUID REFERENCES scores(id) -- previous row for same config
);

-- Per-task breakdown (powers the drill-down view).
CREATE TABLE task_scores (
  score_id   UUID REFERENCES scores(id),
  task_id    TEXT NOT NULL,
  mean_score NUMERIC NOT NULL,
  n_runs     INT NOT NULL DEFAULT 1,
  PRIMARY KEY (score_id, task_id)
);

-- The runs behind a score row. Transcripts are content-addressed: the board
-- stores hashes; submitters host the bytes (docs/plan/06-community-model.md).
CREATE TABLE run_manifests (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  score_id          UUID REFERENCES scores(id),
  run_id            TEXT NOT NULL,
  task_id           TEXT NOT NULL,
  seed              INT NOT NULL,
  transcript_sha256 TEXT NOT NULL,
  claimed_total     NUMERIC NOT NULL,
  replayed_total    NUMERIC NOT NULL,
  tier              TEXT NOT NULL DEFAULT 'checks',
  created_at        TIMESTAMPTZ DEFAULT now()
);

-- Disputes and flags are public records.
CREATE TABLE disputes (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  score_id   UUID REFERENCES scores(id),
  status     TEXT CHECK (status IN ('open','resolved','frivolous')),
  filer      TEXT,                        -- stakes 5 reputation (docs/plan/07 §4)
  outcome    TEXT,                        -- upheld | rejected | frivolous
  reason     TEXT,
  resolution TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Verification lottery (docs/plan/07 §2, docs/plan/15 §6).
CREATE TABLE verifiers (
  user_id    TEXT PRIMARY KEY,
  reputation INT DEFAULT 0,
  opted_in   BOOLEAN DEFAULT FALSE,
  org        TEXT                          -- for conflict exclusion
);
CREATE TABLE verification_jobs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  score_id    UUID REFERENCES scores(id),
  verifier    TEXT REFERENCES verifiers(user_id),
  state       TEXT CHECK (state IN ('assigned','submitted','expired')) DEFAULT 'assigned',
  priority    BOOLEAN DEFAULT FALSE,
  assigned_at TIMESTAMPTZ DEFAULT now(),
  due_at      TIMESTAMPTZ                  -- 7-day TTL; expiry re-draws and docks 2
);

-- Verification reproductions (docs/plan/06 §4, 07). A score is `verified`
-- after two independent reproductions land within its confidence interval.
CREATE TABLE verifications (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  score_id       UUID REFERENCES scores(id),
  verifier       TEXT NOT NULL,           -- agent/org identity of the reproducer
  org            TEXT,                    -- verifier's org (conflict exclusion)
  run_id         TEXT NOT NULL,           -- the reproduction run
  task_id        TEXT NOT NULL,
  seed           INT NOT NULL,
  reproduced_total NUMERIC NOT NULL,
  within_ci      BOOLEAN NOT NULL,
  created_at     TIMESTAMPTZ DEFAULT now()
);

-- Reputation ledger (docs/plan/06 §6): append-only points with reasons.
CREATE TABLE reputation (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject    TEXT NOT NULL,               -- agent/org/contributor identity
  points     INT NOT NULL,
  reason     TEXT NOT NULL,               -- task_authorship | verification | calibration | bug_report | verification_lottery_expiry
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Enterprise API keys (Phase 3, SPEC.md §9). Only the sha256 hash is stored;
-- the key itself is shown once at creation and never persisted.
CREATE TABLE api_keys (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key_hash   TEXT NOT NULL UNIQUE,
  label      TEXT NOT NULL,
  scope      TEXT NOT NULL DEFAULT 'enterprise',
  created_at TIMESTAMPTZ DEFAULT now(),
  revoked_at TIMESTAMPTZ
);

-- Paid-service orders (Phase 3, SPEC.md §9, docs/plan/05 §2). A public
-- ledger: orders can never alter a score, a flag, or a board position.
CREATE TABLE orders (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind            TEXT NOT NULL CHECK (kind IN ('evaluation','priority_verification')),
  requester       TEXT NOT NULL,
  level           TEXT,                        -- evaluation: sprint|marathon|ultra
  score_id        UUID REFERENCES scores(id),
  amount_usd      NUMERIC NOT NULL,
  fee_to_verifier BOOLEAN DEFAULT FALSE,       -- priority fee passes through to the verifier (plan 06 §4)
  status          TEXT NOT NULL DEFAULT 'quoted' CHECK (status IN ('quoted','invoiced','paid','fulfilled','cancelled')),
  payment_ref     TEXT,
  note            TEXT,
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

-- The app role gets no UPDATE or DELETE grants on scores (corrections append).
