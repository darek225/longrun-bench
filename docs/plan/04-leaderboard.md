# 04 — Leaderboard Site: Architecture and Build Plan

## Decisions

- **Stack:** Next.js 16, Postgres, deployed on Vercel. Same stack as the owner's other projects; no learning curve.
- **Data first:** the site reads from a `scores` table populated by the ingestion API. No scores are ever hand-entered. If it is not in the database with a valid signature, it is not on the board.
- **Default view:** Marathon / `standard` profile. Tabs for every profile × level combination.
- **No login to view.** Login (GitHub OAuth) only for submitting community results and filing disputes.

## 1. Database schema

```sql
-- Every published score. Immutable: corrections are new rows, never updates.
CREATE TABLE scores (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name    TEXT NOT NULL,            -- e.g. "acme-agent"
  model         TEXT NOT NULL,            -- e.g. "acme-2.5", version pinned
  profile       TEXT NOT NULL CHECK (profile IN ('bare','standard','native')),
  level         TEXT NOT NULL CHECK (level IN ('sprint','marathon','ultra')),
  task_set      TEXT NOT NULL,            -- semver, e.g. "1.3.0"
  harness_hash  TEXT NOT NULL,            -- sha256 of harness image
  board         TEXT NOT NULL CHECK (board IN ('official','community')),
  mean_score    NUMERIC NOT NULL,
  ci_low        NUMERIC NOT NULL,
  ci_high       NUMERIC NOT NULL,
  median_score  NUMERIC NOT NULL,
  n_tasks       INT NOT NULL,
  n_runs        INT NOT NULL,
  gen_gap       NUMERIC,                  -- official only; NULL for community
  gap_flag      BOOLEAN DEFAULT FALSE,    -- generalization-gap flag raised
  provisional   BOOLEAN DEFAULT FALSE,    -- n<3 per task
  created_at    TIMESTAMPTZ DEFAULT now(),
  supersedes    UUID REFERENCES scores(id) -- previous row for same config
);

-- Per-task breakdown (powers the drill-down view).
CREATE TABLE task_scores (
  score_id   UUID REFERENCES scores(id),
  task_id    TEXT NOT NULL,
  mean_score NUMERIC NOT NULL,
  PRIMARY KEY (score_id, task_id)
);

-- Disputes and flags are public records.
CREATE TABLE disputes (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  score_id   UUID REFERENCES scores(id),
  status     TEXT CHECK (status IN ('open','resolved','frivolous')),
  resolution TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

- `supersedes` chains history: the board shows the latest row per (agent, profile, level, task_set MAJOR). Older rows remain queryable.
- No `UPDATE` or `DELETE` grants on `scores` for the app role. Corrections append.

## 2. Ingestion API

```
POST /api/scores/submit
  Auth: API key (vendors) or GitHub OAuth (community)
  Body: { agent_name, model, profile, level, task_set, harness_hash,
          run_manifests: [...] }   # per-run transcripts referenced by hash
  Server: verifies harness_hash matches the task_set version's pinned hash,
          replays deterministic checks from the transcripts (vendored checker),
          recomputes the means. Rejects on any mismatch.
  -> { score_id } or { error }

GET /api/scores?profile=standard&level=marathon&board=official
  -> ranked rows with CI, gaps, flags

GET /api/scores/{id} -> full row + task breakdown + transcript hashes
```

- The server never trusts client-computed scores. It recomputes from transcripts. This is the load-bearing integrity rule.
- Transcripts are stored content-addressed (sha256). Storage: R2/S3. Retention: forever for official, 1 year for community.

## 3. Pages

| Route | Contents |
|---|---|
| `/` | Default board (Marathon/standard/official). Tabs for profile × level × board. Each row: rank, agent, score ± CI, generalization gap, date, drill-down link. |
| `/scores/{id}` | Full breakdown: per-task scores, rubric criterion means, efficiency stats, transcript hashes, dispute history. |
| `/tasks` | The public task bank: every active task with its rubric (instances never shown). |
| `/methodology` | Plain-English how-it-works: rubrics, profiles, the canary, the judge. Links to SPEC.md. |
| `/disputes` | Public dispute log. |
| `/submit` | Community submission flow: upload run manifests, get a provisional score. |

## 4. Anti-tamper

- Scores table is append-only at the database role level.
- Every official score row links to content-addressed transcripts anyone can re-verify.
- The site's build is from this repo; the ingestion API's checker is the same code as `tasks/*/checks.py`. One source of truth.
- Generalization-gap flags cannot be hidden: `gap_flag` is a column, rendered unconditionally.

## 5. Build order

1. Schema + ingestion API with signature verification (week 1-2).
2. Public board page with tabs (week 2-3).
3. Drill-down + methodology + tasks pages (week 3-4).
4. Community submission flow (week 4-5).
5. Dispute flow (week 5).

Total: ~5 weeks for one builder with the spec in hand.
