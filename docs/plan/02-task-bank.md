# 02 — Task Bank: Authoring Guide and Exemplars

## Decisions

- **Task count v1.0:** 85 active (40 Sprint / 30 Marathon / 15 Ultra) + 17 held-out canary tasks (private mirror, never in this repo).
- **Authoring:** maintainers write the seed set; community PRs need 2 maintainer approvals + a trial grading pass (run the task with 2 different agents, confirm the rubric discriminates).
- **Parameterization rule:** every task MUST have at least 2 parameters with at least 3 values each, so no two official instances are identical. A task that cannot be parameterized is not a LongRun task; rewrite or reject it.
- **Deterministic checks:** every task MUST have at least 3 deterministic checks. Checks are the floor for correctness; the rubric is the ceiling.
- **Time to author:** budget 2-4 hours per task including trial runs. 85 tasks is roughly 250 hours of authoring. This is the real cost of the benchmark.

## 1. Authoring checklist

For each task, the author produces:
1. `task.md` — the brief the agent sees (after parameter rendering).
2. `manifest.json` — per SPEC §3.2.
3. `checks.py` — the deterministic checks, runnable against a deliverable.
4. `rubric.md` — criterion anchors with concrete examples of 0 / half / full.
5. Trial runs: at least 2 agents, 1 seed each. If both score within 5 points, the rubric does not discriminate; revise.
6. Parameter sweep: render 5 instances, confirm all are solvable and distinct.

## 2. Rubric anchor template

Every rubric criterion uses this shape:

```markdown
### Correctness (40)
- 40: Every deterministic check passes. No fabricated facts found on audit.
  Numbers, names, and dates all verify against sources.
- 25: Checks pass with minor exceptions (1-2). No material fabrications.
- 10: Multiple check failures or one material fabrication. Core answer present.
- 0: Checks mostly fail, or deliverable is fabricated/plausible-sounding but wrong.
```

Anchors must reference observable evidence, never vibes. "Thorough" is banned; "cites at least 3 independent sources with URLs" is required.

## 3. Exemplar tasks

Fifteen fully specified. Each shows the prompt template, parameters, checks, and rubric notes. These are the pattern the remaining 70 follow.

### Sprint (level 1)

**S-01 `research_synthesis` — Vendor comparison brief**
- Template: "Compare {{n}} {{product}} vendors for a {{business_type}}. Deliver a markdown table with pricing, key features, and contract terms, plus a 150-word recommendation."
- Parameters: n ∈ {3,4,5}, product ∈ {crm, voip, accounting_software, email_marketing}, business_type ∈ {dental_practice, food_truck, law_firm, auto_shop}
- Checks: all n vendors named; pricing figures present with $ amounts; recommendation ≤ 200 words; no vendor invented (names cross-checked against allowlisted vendor list per product).
- Rubric notes: correctness = prices within 20% of listed prices on vendor sites; completeness = all three table columns filled for every vendor.

**S-02 `code_repair` — Failing test suite**
- Template: "This Python repo has {{k}} failing tests. Fix the source (not the tests) so the suite passes. Repo: {{repo_seed}}."
- Parameters: k ∈ {2,3,4}, repo_seed ∈ {inventory_tracker, csv_deduper, url_shortener} (each a small buggy repo with a hidden test file swapped in at run time)
- Checks: `pytest` exit 0; no test files modified (git diff on tests/ empty); fix is minimal (diff under 100 lines).
- Rubric notes: efficiency rewards fewest steps to green; recovery rewards diagnosing root cause vs shotgun edits.

**S-03 `data_analysis` — Sales CSV**
- Template: "Analyze {{dataset}} (10k rows). Report: top 3 products by revenue, month-over-month growth, and any data quality issues. Numbers must be reproducible."
- Parameters: dataset ∈ {q1_sales, q2_sales, q3_sales} (synthetic CSVs with planted anomalies: duplicate rows, currency mixing, future dates)
- Checks: top-3 list matches ground truth; growth % within 0.5pp; at least 2 of 3 planted anomalies named.
- Rubric notes: correctness is exact-match on numbers; completeness requires the anomaly section.

### Marathon (level 2)

**M-01 `research_synthesis` — Competitive teardown**
- Template: "{{company}} is considering entering {{market}}. Produce a 1500-word teardown: market size, top 5 incumbents with positioning, regulatory barriers, and a go/no-go recommendation with reasoning."
- Parameters: company ∈ {regional_bank, hvac_chain, meal_kit_startup}, market ∈ {pet_insurance, commercial_solar, telehealth_dermatology}
- Checks: 5 incumbents named with one positioning sentence each; market size figure with source URL; word count 1200-1800; recommendation explicitly go or no-go.
- Rubric notes: correctness = figures sourced, no invented statistics (audit 3 random claims); completeness = all four sections present.

**M-02 `code_repair` — Broken feature build**
- Template: "Implement {{feature}} in this Flask app per the spec in SPEC_FEATURE.md. The existing test suite must keep passing; {{h}} hidden tests will judge the feature."
- Parameters: feature ∈ {rate_limiting, csv_export, webhook_retries}, h ∈ {8,10,12}
- Checks: existing suite green; hidden tests pass rate ≥ 80%; no new dependencies without justification in NOTES.md.
- Rubric notes: recovery = handling the 2 planted misleading comments in the codebase without being led astray.

**M-03 `planning` — Conference trip**
- Template: "Plan a 4-day trip to {{city}} for a team of {{n}} attending {{event}}. Budget ${{budget}}. Book nothing; produce an itinerary with flights, hotel, ground transport, and per-person cost breakdown. All prices must be verifiable today."
- Parameters: city ∈ {austin, denver, nashville}, n ∈ {3,4,5}, event ∈ {saas_conference, trade_show}, budget ∈ {8000, 12000}
- Checks: per-person total ≤ budget/n; every price has a source URL; itinerary covers all 4 days; no invented venues (cross-check names against search).
- Rubric notes: instruction adherence = stayed in budget, booked nothing; efficiency = steps per verified price.

**M-04 `web_extraction` — Spec sheet hunt**
- Template: "Find the official spec sheets for {{n}} {{device}} models released in {{year}}. Extract {{fields}} into a CSV. Every cell needs a source URL column."
- Parameters: n ∈ {4,5}, device ∈ {cordless_drills, robot_vacuums}, year ∈ {2025, 2026}, fields = {battery, weight, warranty, price}
- Checks: CSV parses; every row has a source URL returning 200; extracted values match ground truth within tolerance.
- Rubric notes: recovery = handling JS-heavy manufacturer pages, CAPTCHAs, or 404s gracefully.

### Ultra (level 3)

**U-01 `research_synthesis` — Market entry dossier**
- Template: "Over multiple sessions, build a market-entry dossier for {{product}} in {{region}}: regulatory landscape, competitor matrix (10+), pricing analysis, partnership targets, risk register. Deliverable is a structured document; you may use the memory file across sessions."
- Parameters: product ∈ {home_battery, commercial_ev_charging}, region ∈ {texas, florida}
- Checks: 10+ competitors with sources; regulatory section cites actual statutes/agencies; risk register has ≥ 8 risks with mitigations; document internally consistent (no contradictory figures).
- Rubric notes: the memory criterion — dossier must not contradict itself across sections written in different sessions. This is what Ultra tests.

**U-02 `code_build` — Full-stack feature**
- Template: "Build {{feature}} end-to-end in this repo: database migration, API endpoints, frontend page, and tests. The hidden acceptance suite ({{h}} tests) runs at the end."
- Parameters: feature ∈ {team_invitations, usage_billing_dashboard}, h ∈ {15, 20}
- Checks: migration applies cleanly on fresh DB; acceptance pass rate ≥ 75%; no secrets hardcoded; README documents the feature.
- Rubric notes: recovery across sessions — the agent must resume correctly after the harness pauses it (simulated by splitting the run into 3 sessions with memory only).

**U-03 `planning` — Office relocation**
- Template: "Plan a 25-person office move from {{from_city}} to {{to_city}}: movers (3 quotes), lease comparison (3 options), IT cutover plan, timeline with dependencies, total budget under ${{budget}}. Multi-session; constraints will change mid-task (you will be notified)."
- Parameters: from_city/to_city ∈ {(charlotte, raleigh), (austin, dallas)}, budget ∈ {50000, 75000}
- Checks: 3 mover quotes with sources; lease options real; timeline has no dependency cycles; budget holds AFTER the mid-task constraint change; change log documents what adapted.
- Rubric notes: the mid-task change is the test — agents that planned rigidly fail; agents that kept options open adapt. This is the Ultra differentiator.

### Cross-category Sprint exemplars (S-04 to S-06 abbreviated)

**S-04 `planning`** — "Three vendor quotes for {{service}} in {{zip}}; deliver comparison with response-time notes." Checks: 3 real businesses, phone/URL verified.
**S-05 `web_extraction`** — "Extract {{spec}} from the top {{n}} results for {{query}}; flag contradictions." Checks: contradictions actually contradict (not paraphrase).
**S-06 `code_repair`** — "This script crashes on {{input_type}} input; fix and add a regression test." Checks: crash fixed, new test fails on old code.

## 4. Generating the remaining 70

Do not hand-write 70 more tasks the same way. Instead:

1. **Task family expansion:** each exemplar defines a family. New tasks = new parameter values + new ground-truth datasets for existing families (e.g., 6 more vendor products for S-01, 4 more buggy repos for S-02). Target: 4-6 instances per family.
2. **New families:** 2 per category, following the authoring checklist (§1). Priority: categories with the fewest exemplars.
3. **Trial grading is mandatory** for every new task, no exceptions. A task that cannot discriminate between a good and mediocre agent is worse than no task.
4. **Quarterly rotation planning:** maintain a spreadsheet (in `tasks/`) mapping each task to its active quarters, guaranteeing category and level balance every quarter.
