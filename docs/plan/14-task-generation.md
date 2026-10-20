# 14 — Generating the Remaining 70 Tasks (Concrete Build List)

## Decisions

- **No hand-waving.** Every task below names its parameters, its ground-truth source, and what must be built. If it can't be specified this concretely, it's not ready to author.
- **Ground truth is built, not scraped at run time.** Every dataset, buggy repo, and vendor list is constructed during authoring and frozen in the task directory. Nothing depends on the live web at grade time except `url_alive` checks (which are advisory, not load-bearing).
- **Authoring order:** data_analysis and code_repair first (ground truth is cheapest), then research_synthesis, then planning, then web_extraction (most fragile).

## 1. Family S-01: vendor comparison (need 5 more; have 1)

Each new instance = one product with a frozen vendor list (5 vendors, with pricing/features captured at authoring time into `ground_truth.json`).

| Product | Vendors (example set) | Ground truth source |
|---|---|---|
| project_management | asana, monday, clickup, notion, jira | pricing pages, archived at authoring |
| payroll_software | gusto, rippling, adp_run, paychex, quickbooks_payroll | pricing pages |
| business_voip | ringcentral, nextiva, dialpad, ooma, 8x8 | pricing pages |
| email_marketing | mailchimp, convertkit, brevo, constant_contact, klaviyo | pricing pages |
| commercial_insurance | hartford, travelers, next_insurance, hiscox, biBERK | quote estimators (ranges, not exact) |

- Prices go stale: each vendor entry carries `captured_at`. Checks allow ±20% OR accept "price not listed" if the vendor hides pricing (the agent must say so, not invent).
- Anti-invention check: vendor names must come from the frozen list; any other vendor name in the deliverable fails the check.

## 2. Family S-02: buggy repos (need 4 more; have 1)

Each repo: ~200 lines, 1 entry point, a test suite with 8-12 tests, exactly K planted bugs (K parameterized 2-4). The bugs must be independently fixable (fixing one must not require fixing another).

| Repo | Planted bugs (examples) |
|---|---|
| `expense_splitter` | off-by-one in rounding; mutable default arg; wrong CSV delimiter assumption |
| `log_analyzer` | regex catastrophic backtracking on crafted input; timezone-naive comparison; unclosed file handle |
| `inventory_api` (flask) | race condition on stock decrement; missing input validation; N+1 query |
| `backup_tool` | silent failure on permission error; wrong timestamp format in manifest; deletes source before verifying copy |

- The hidden test file is swapped at run time (the agent sees the public tests; grading uses public + hidden). Hidden tests target the planted bugs specifically.
- `git_diff_empty` check on `tests/` ensures the agent didn't "fix" the tests.

## 3. Family S-03: sales CSVs (need 2 more datasets; have 1)

Each dataset: 10k synthetic rows, 3 planted anomalies. Generation script in the task dir (seeded, reproducible).

| Dataset | Planted anomalies |
|---|---|
| `q2_sales` | 47 duplicate rows (same order_id, different timestamps); 12% of rows in EUR labeled USD; 8 orders dated next quarter |
| `q3_sales` | product_id mismatch on 3% of rows (joins to wrong product); negative quantities (returns not flagged); discount column as string "15%" vs float 0.15 mixed |

- Ground truth computed by the generation script and frozen. The agent's numbers must match within tolerance.

## 4. Family M-01: competitive teardowns (need 4 more; have 1)

New (company, market) pairs. Each needs a 1-page author brief confirming the market is researchable (public data exists) and the incumbents are identifiable.

| Company | Market | Why it works |
|---|---|---|
| regional_credit_union | renter_insurance | public filings, clear incumbents |
| landscaping_chain | commercial_pest_control | local + national players, pricing visible |
| boutique_gym_chain | corporate_wellness | B2B motion, public case studies |
| bakery_cafe_chain | ghost_kitchens | recent market, contested narratives (good for the no-go case) |

## 5. Family M-02: feature builds (need 3 more; have 1)

Each: a Flask starter repo (~500 lines), a SPEC_FEATURE.md, 8-12 hidden acceptance tests.

| Feature | Hidden test focus |
|---|---|
| `audit_logging` | every mutation logged with actor + timestamp; log queryable; tamper-evident (append-only check) |
| `search_api` | full-text search with ranking; pagination correct; injection-safe |
| `scheduled_reports` | cron-like scheduling; timezone handling; failure retries with backoff |

- 2 planted misleading comments per repo (e.g., "# TODO: this is handled by the ORM" where it isn't). The rubric's recovery criterion is graded on whether the agent was led astray.

## 6. Family M-03: trip planning (need 3 more cities; have 1 set)

Cities need: a real conference venue, 5+ hotels with public pricing, an airport with multiple airlines.

| City | Venue anchor |
|---|---|
| chicago | McCormick Place |
| san_diego | San Diego Convention Center |
| atlanta | Georgia World Congress Center |

- Author captures 3 reference hotel prices at authoring time (with dates). Checks don't require matching the reference (prices move); they require sourced, verifiable prices and arithmetic that adds up.

## 7. Family M-04: spec extraction (need 2 more devices; have 1 set)

| Device | Spec fields | Ground truth |
|---|---|---|
| cordless_drills | voltage, chuck_size, warranty, weight, price | manufacturer spec PDFs, frozen |
| e_bikes | motor_watts, range_miles, weight, warranty, price | manufacturer spec pages, frozen |

## 8. Ultra families (need 12 more; have 3)

Ultra tasks are the most expensive to author (multi-session design + mid-task changes). Priority order:

1. **U-04 `data_analysis`:** "Q4 close" — reconcile 3 months of messy books across sessions; a mid-task correction arrives (a transaction batch was miscategorized). Tests whether corrections propagate.
2. **U-05 `research_synthesis`:** "Vendor selection" — 3-week simulated procurement: RFP draft, vendor responses (provided as documents at staged times), scoring matrix, recommendation. Staged document drops test session resumption.
3. **U-06 `code_build`:** "Legacy migration" — migrate a Flask app to FastAPI across sessions; hidden tests run at the end; the mid-task change is a new requirement (auth) introduced in session 2.
4-12. Second instances of U-01..U-06 with new parameters (new products, regions, features, cities).

## 9. Authoring pipeline (how the 70 actually get done)

1. **Exemplars first** (done, §02.3). Every new task starts by copying the nearest exemplar's manifest and checklist.
2. **Ground-truth sprints:** 2-week sprints, one category per sprint. A sprint produces all ground-truth artifacts for its families (datasets, repos, vendor lists) before any manifest is written.
3. **Trial grading gate:** no task merges without 2 agents × 1 seed each, scores differing by >5 points, and all checks seen to fail on a broken deliverable.
4. **Tracking:** `tasks/PROGRESS.md` lists every planned task with status (specced → ground-truth → trial → merged). The board doesn't launch until 85 are merged.

## 10. What "done" means for the bank

- 85 tasks merged, each with manifest, checks, rubric anchors, ground truth, and trial transcripts.
- `tasks/PROGRESS.md` all green.
- Discrimination index computed across trial agents: any task with near-zero variance is revised or cut (and replaced, keeping the count at 85).
