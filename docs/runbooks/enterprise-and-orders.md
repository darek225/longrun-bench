# Enterprise API and paid-service orders (Phase 3)

Process: SPEC.md §9, DECISIONS.md #36-38, docs/plan/05 §2, docs/plan/06 §4.
Code: `leaderboard/enterprise.py`, `leaderboard/orders.py`, price list at
`leaderboard/prices.json` (public at `GET /api/pricing` and on the board's
pricing page).

## Enterprise API

Paid access to score history, CI data, and head-to-head comparisons for
buyers choosing agent platforms. Authenticated with an `X-API-Key` header.
Only the sha256 hash of a key is stored; the key is shown once at creation.

```bash
# Issue a key (operator action; the response contains the key, once)
curl -X POST localhost:8787/api/admin/api-keys -d '{"label": "buyer-co"}'
# List issued keys (metadata only, never key material)
curl localhost:8787/api/admin/api-keys
# Revoke (takes effect immediately)
curl -X POST localhost:8787/api/admin/api-keys/<id>/revoke

# Buyer calls
curl -H "X-API-Key: lrk_..." "localhost:8787/api/enterprise/history?agent_name=acme-agent"
curl -H "X-API-Key: lrk_..." "localhost:8787/api/enterprise/compare?left=<score_id>&right=<score_id>"
curl -H "X-API-Key: lrk_..." "localhost:8787/api/enterprise/scores?board=official"
```

Compare refuses cross-profile and cross-level pairs (scores are never
compared across either, DECISIONS.md #20). Cross task-set comparisons are
returned marked `approximate` (SPEC.md §7.2). Unauthenticated or revoked
keys get 401.

The admin endpoints are operator actions. The reference implementation
serves them on the same local API as the existing admin expiry endpoint;
a hosted deployment puts them behind operator auth. That is a deployment
requirement, not a code path.

## Orders

The public ledger of paid services (`GET /api/orders`). Lifecycle:
`quoted -> invoiced -> paid -> fulfilled`, or `cancelled` from any
non-terminal state. Payment is recorded with an operator payment
reference; this system never processes a charge.

```bash
# Evaluation order: the amount is set from the public price list, always
curl -X POST localhost:8787/api/orders -d '{"kind": "evaluation", "requester": "vendor-x", "level": "marathon"}'
# Priority verification: the requester sets the fee; it passes through
curl -X POST localhost:8787/api/orders -d '{"kind": "priority_verification", "requester": "vendor-x", "score_id": "<id>", "fee_usd": 150}'
# Lifecycle
curl -X POST localhost:8787/api/orders/<id>/transition -d '{"status": "invoiced"}'
curl -X POST localhost:8787/api/orders/<id>/transition -d '{"status": "paid", "payment_ref": "inv-2026-001"}'
curl -X POST localhost:8787/api/orders/<id>/transition -d '{"status": "fulfilled", "score_id": "<produced score id>"}'
```

Fulfilling a priority-verification order draws priority jobs from the
verifier pool; the fee is payable to the verifier who completes a job and
the org takes no cut. Fulfilling an evaluation links the score row the
evaluation produced. Nothing about an order can create, alter, or
suppress a score, a CI, or a generalization-gap flag: those code paths do
not exist in the orders module, and a regression test
(`test_orders_never_touch_scores`) guards the boundary.
