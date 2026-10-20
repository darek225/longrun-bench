from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .ingest import verify_and_replay
from .store import Store, aggregate

# docs/plan/07-trust-and-identity.md §2 and docs/plan/15-final-mile.md §6.
MIN_POOL_REPUTATION = 10  # stake required to enter the verifier pool
VERIFIERS_PER_SCORE = 2
JOB_TTL_DAYS = 7
REWARD_WITHIN_CI = 5
REWARD_OUTSIDE_CI = 10  # finding problems pays more
EXPIRY_DOCK = 2
DISPUTE_STAKE = 5

# docs/plan/06-community-model.md §6: reputation sources.
REPUTATION_AWARDS = {
    "task_authorship": 10,
    "calibration": 5,
    "bug_report": 3,
}


class TrustError(ValueError):
    pass


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def opt_in_verifier(store: Store, *, user_id: str, org: str | None) -> dict[str, Any]:
    balance = store.reputation_balance(user_id)
    if balance < MIN_POOL_REPUTATION:
        raise TrustError(
            f"verifier pool requires a reputation stake of {MIN_POOL_REPUTATION}; {user_id} has {balance}"
        )
    store.upsert_verifier(user_id=user_id, org=org, opted_in=True)
    return {"verifier": user_id, "org": org, "reputation": balance, "opted_in": True}


def _eligible_pool(store: Store, *, score: dict[str, Any], submitter_org: str | None, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    """Pool members who may verify this score: opted in, no org conflict with
    the submitter, not the submitter, and not already holding a live job."""
    busy = {
        job["verifier"]
        for job in store.list_jobs(score_id=score["id"])
        if job["state"] in ("assigned", "submitted")
    }
    pool = []
    for verifier in store.list_verifiers(opted_in_only=True):
        if verifier["user_id"] == score["agent_name"]:
            continue
        if exclude and verifier["user_id"] in exclude:
            continue
        if submitter_org and verifier.get("org") and verifier["org"] == submitter_org:
            continue
        if verifier["user_id"] in busy:
            continue
        pool.append(verifier)
    return pool


def request_verification(
    store: Store,
    *,
    score_id: str,
    submitter_org: str | None = None,
    priority: bool = False,
    rng: random.Random | None = None,
    now: datetime | None = None,
    exclude: set[str] | None = None,
) -> dict[str, Any]:
    """Draw verifiers uniformly at random from the pool (blind assignment:
    verifiers are never self-selected per score)."""
    score = store.get_score(score_id)
    if score is None:
        raise KeyError(f"unknown score_id: {score_id}")
    rng = rng or random.Random()
    moment = _now(now)
    pool = _eligible_pool(store, score=score, submitter_org=submitter_org, exclude=exclude)
    existing = [j for j in store.list_jobs(score_id=score_id) if j["state"] == "assigned"]
    needed = max(0, VERIFIERS_PER_SCORE - len(existing))
    drawn = rng.sample(pool, min(needed, len(pool))) if needed else []
    jobs = []
    for verifier in drawn:
        job_id = store.insert_job(
            score_id=score_id,
            verifier=verifier["user_id"],
            assigned_at=_iso(moment),
            due_at=_iso(moment + timedelta(days=JOB_TTL_DAYS)),
            priority=priority,
        )
        jobs.append(store.get_job(job_id))
    return {
        "score_id": score_id,
        "jobs": jobs,
        "pool_shortfall": needed - len(drawn),
        # What a verifier must reproduce: task + seed only. The original
        # transcript is never shown (blind reproduction, docs/plan/07 §4.3).
        "reproduce": [
            {"task_id": m["task_id"], "seed": m["seed"]} for m in score["run_manifests"]
        ],
    }


def apply_verification_outcome(store: Store, *, score_id: str) -> str:
    """Two independent reproductions inside the CI verify the score; two
    outside mark it disputed (docs/plan/06 §4)."""
    counts = store.verification_counts(score_id)
    score = store.get_score(score_id)
    if score is None:
        raise KeyError(f"unknown score_id: {score_id}")
    if counts["within"] >= 2 and score["status"] != "verified":
        store.set_status(score_id, "verified")
        store.set_tier(score_id, "verified")
        return "verified"
    if counts["outside"] >= 2 and score["status"] != "disputed":
        store.set_status(score_id, "disputed")
        return "disputed"
    return score["status"]


def submit_verification_job(
    store: Store,
    *,
    job_id: str,
    bundles: list[dict[str, Any]],
    tasks_root: str | Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """A verifier submits reproduction run bundles for their assigned job.

    Every bundle is replayed by the ingestion checker before it counts; the
    reproduction aggregate (mean of per-task means, same rule as the board)
    is compared against the original score's 95% CI.
    """
    job = store.get_job(job_id)
    if job is None:
        raise KeyError(f"unknown job_id: {job_id}")
    if job["state"] != "assigned":
        raise TrustError(f"job {job_id} is {job['state']}, not assigned")
    moment = _now(now)
    if job["due_at"] and _iso(moment) > job["due_at"]:
        expire_jobs(store, now=moment)
        raise TrustError(f"job {job_id} expired at {job['due_at']}; a replacement has been drawn")
    score = store.get_score(job["score_id"])
    if score is None:
        raise KeyError(f"unknown score_id: {job['score_id']}")

    expected = sorted((m["task_id"], int(m["seed"])) for m in score["run_manifests"])
    verified = [verify_and_replay(bundle, tasks_root=tasks_root) for bundle in bundles]
    got = sorted((run["task_id"], int(run["seed"])) for run in verified)
    if got != expected:
        raise TrustError(f"reproduction must cover the score's runs exactly: expected {expected}, got {got}")
    task_runs: dict[str, list[float]] = {}
    for run in verified:
        task_runs.setdefault(run["task_id"], []).append(run["replayed_total"])
    reproduced_mean = aggregate(task_runs)["mean_score"]
    outcome = store.record_verification(
        score_id=job["score_id"],
        verifier=job["verifier"],
        org=None,
        run_id=str(verified[0]["run_id"]),
        task_id="*aggregate*",
        seed=int(verified[0]["seed"]),
        reproduced_total=reproduced_mean,
    )
    store.set_job_state(job_id, "submitted")
    reward = REWARD_WITHIN_CI if outcome["within_ci"] else REWARD_OUTSIDE_CI
    store.award_reputation(subject=job["verifier"], points=reward, reason="verification")
    status = apply_verification_outcome(store, score_id=job["score_id"])
    return {
        "job_id": job_id,
        "within_ci": outcome["within_ci"],
        "reproduced_mean": reproduced_mean,
        "reputation_awarded": reward,
        "score_status": status,
    }


def expire_jobs(store: Store, *, now: datetime | None = None, rng: random.Random | None = None) -> dict[str, Any]:
    """Expiry sweep: past-due assigned jobs expire, the verifier is docked,
    and a replacement is drawn from the pool (docs/plan/15 §6)."""
    moment = _now(now)
    expired = []
    redrawn = []
    for job in store.list_jobs(state="assigned"):
        if job["due_at"] and _iso(moment) > job["due_at"]:
            store.set_job_state(job["id"], "expired")
            store.award_reputation(subject=job["verifier"], points=-EXPIRY_DOCK, reason="verification_lottery_expiry")
            expired.append(job["id"])
            result = request_verification(store, score_id=job["score_id"], rng=rng, now=moment, exclude={job["verifier"]})
            redrawn.extend(result["jobs"])
    return {"expired": expired, "redrawn": redrawn}


def file_dispute(
    store: Store,
    *,
    score_id: str,
    filer: str,
    reason: str,
    rng: random.Random | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Dispute filing (docs/plan/07 §4): stake 5 reputation, then the score's
    seeds go to the verification pool as priority, blind."""
    score = store.get_score(score_id)
    if score is None:
        raise KeyError(f"unknown score_id: {score_id}")
    balance = store.reputation_balance(filer)
    if balance < DISPUTE_STAKE:
        raise TrustError(f"filing a dispute stakes {DISPUTE_STAKE} reputation; {filer} has {balance}")
    store.award_reputation(subject=filer, points=-DISPUTE_STAKE, reason="dispute_stake")
    dispute_id = store.create_dispute(score_id=score_id, reason=reason, filer=filer)
    verification = request_verification(
        store, score_id=score_id, submitter_org=score["agent_name"], priority=True, rng=rng, now=now
    )
    return {"dispute_id": dispute_id, "stake": DISPUTE_STAKE, "verification": verification}


def resolve_dispute(store: Store, *, dispute_id: str, outcome: str, resolution: str) -> dict[str, Any]:
    """Panel resolution (docs/plan/07 §4.5-6). Outcomes:
    - upheld: the score is marked disputed and the filer's stake is refunded.
    - rejected: reproductions held; the stake is forfeited to the pool.
    - frivolous: dismissed as frivolous; the stake is forfeited.
    The decision and reasoning are public (they live on the dispute record).
    """
    if outcome not in ("upheld", "rejected", "frivolous"):
        raise TrustError(f"unknown dispute outcome: {outcome}")
    dispute = store.get_dispute(dispute_id)
    if dispute is None:
        raise KeyError(f"unknown dispute_id: {dispute_id}")
    if dispute["status"] != "open":
        raise TrustError(f"dispute {dispute_id} is already {dispute['status']}")
    status = "frivolous" if outcome == "frivolous" else "resolved"
    store.resolve_dispute(dispute_id, status=status, resolution=resolution, outcome=outcome)
    if outcome == "upheld":
        if dispute.get("filer"):
            store.award_reputation(subject=dispute["filer"], points=DISPUTE_STAKE, reason="dispute_stake_refund")
        store.set_status(dispute["score_id"], "disputed")
    return {"dispute_id": dispute_id, "outcome": outcome, "status": status}
