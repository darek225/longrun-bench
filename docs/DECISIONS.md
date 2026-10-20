# Design decisions

Every question the spec had to answer, and the answer chosen. Each links to the spec section that implements it.

## Identity and governance

1. **What is it called?** LongRun Bench. The name says what it measures. (§0)
2. **License?** MIT, everything in the repo. Benchmarks need maximum trust and reuse. (§11)
3. **Public or private?** Public from day one. A secret benchmark cannot be trusted. (§7, §11)
4. **Who runs it?** Initially the repo owner. Authority comes from the published spec and open process, not from a person. (§11)

## Tasks

5. **How many tasks?** v1.0: 85 total — 40 Sprint, 30 Marathon, 15 Ultra. Enough for statistical signal, few enough to author well. (§2)
6. **What categories?** Research & synthesis, code repair & building, multi-step planning, data analysis, web navigation & extraction. Covers how people actually use agents. (§3.1)
7. **What does a task look like on disk?** A directory with `task.md` (human brief) and `manifest.json` (prompt template, parameter schema, rubric, deterministic checks, budgets). Machine-readable first. (§3.2)
8. **Who writes tasks?** Maintainers author the seed set; community proposes via PR with two maintainer approvals and a trial grading pass. (§3.3)
9. **How long does a task live?** At most 4 consecutive quarters in the active set, then automatic retirement to the public archive. Rotation is the anti-memorization mechanism. (§3.3, §7.2)

## Levels

10. **Why levels at all?** So small models can compete (Sprint) while frontier agents differentiate (Ultra). One ladder, three rungs. (§2)
11. **What are the step budgets?** Sprint 20, Marathon 100, Ultra 500. A step is one tool call. (§2, §5.3)
12. **What are the time budgets?** Sprint 15 min, Marathon 3 h, Ultra 24 h. Over budget ends the run; partial work is still graded. (§2)
13. **How does Ultra handle multi-day state?** The harness provides a persistent working directory and memory file. Agents that keep useful state score better; the rubric rewards it. (§2, §5.1)

## Rubrics

14. **Why rubrics instead of pass/fail?** Long tasks have no single right answer. Rubrics with partial credit are how school projects are graded, and they are how this works. (§6.1)
15. **What are the default weights?** Correctness 40, completeness 25, efficiency 15, error recovery 10, instruction adherence 10. Correctness dominates; efficiency never compensates for wrong answers. (§6.2)
16. **Who grades the fuzzy criteria?** An LLM judge running a fixed, disclosed model version and prompt. The judge never sees the agent's identity. (§6.1)
17. **What keeps the judge honest?** Human audit on 10% of official transcripts plus 100% of disputes. Human grade overrides. Disagreements published as calibration data. (§6.1)

## Agent profiles

18. **What is actually being scored?** The agent configuration: model + profile + harness version. Never a bare model name. (§4)
19. **What are the profiles?** `bare` (raw API, no tools), `standard` (fixed harness toolset), `native` (vendor product as shipped). (§4)
20. **Can profiles be compared?** No. Separate leaderboard tabs, always. A `bare` 82 and a `native` 82 are different achievements. (§4, §8)
21. **How does a product connect?** Vendor implements the harness protocol (`POST /run`, `GET /run/{id}/transcript`), or the bench org drives the public interface and documents exactly how. Transcripts are re-checked independently; vendors never self-report. (§5.4)

## Harness

22. **What tools does `standard` get?** Shell, file read/write/edit, Python, HTTP fetch (text), text-mode browser. Fixed set, no more, no less. (§5.2)
23. **How is it implemented?** Versioned Docker image, open source, in `harness/`. Rebuilt per run; nothing persists except task-scoped Ultra memory. (§5.1)
24. **What about network access?** Allowlist per task, declared in the manifest. Everything else denied. (§5.1)
25. **Can the agent see the rubric or checks?** It sees the public rubric anchors (they are public by design). It never sees deterministic checks, weights beyond anchors, or held-out tasks. (§7.4)

## Scoring and statistics

26. **How many runs per task?** Minimum n=3 (different seeds) for official scores. Single community runs are flagged provisional. (§6.2)
27. **How are scores aggregated?** Mean with 95% CI; median also reported. A score without CI, task set version, and harness hash is a rumor. (§6.2, §6.3)
28. **How is efficiency scored?** Tokens, steps, and wall-clock relative to budget, worth 15% of the rubric. Cheapest perfect score wins ties. (§6.2)

## Gaming resistance

29. **How do you stop training on the test set?** Tasks are parameterized templates; instances are drawn with a seed at run time. Memorizing task text buys nothing. (§7.1)
30. **How do scores stay comparable over time?** Semver task sets. Comparable within a MAJOR version; MAJOR changes reset the board (old eras archived). (§7.2)
31. **What is the canary?** 20% of tasks are never published. The generalization gap (public mean minus held-out mean) is published per official run. Large gap = gaming signal, published openly after a 14-day vendor response window. (§7.3)
32. **What happens if gaming is proven?** Score removal and a permanent public note. (§7.3)

## Leaderboards

33. **Official vs community — what is the difference?** Official: bench org runs, controlled infra, verified, monthly. Community: self-run, signed, labeled unverified, continuous. Never merged. (§8)
34. **What is the default view?** Marathon / `standard` — the most representative of real agent usage. (§8)
35. **How are disputes handled?** Official: human re-grade, published. Community: not accepted; re-run instead. (§8)

## Business

36. **Who pays for official compute?** Bench org in phases 1-2 to seed trust. Vendors pay per evaluation (public flat pricing) in phase 3. (§9)
37. **Can vendors pay for better scores?** No. Flat pricing per level, no pay-for-score, no suppression of flags, no early held-out access, ever. (§9)
38. **Where does revenue come from?** Paid official evals, enterprise API for score history and comparisons, disclosed sponsored task categories (quarantined one quarter, sponsor never authors the rubric). (§9)
39. **When does the website come?** Phase 2. The repo and spec are phase 1. (§10)

## Harness tools

40. **Does the standard harness include semantic code navigation?** Yes — `code.nav` (find definition/references, list/search symbols) backed by a language server, Python at launch. The standard profile models a well-equipped agent; every real coding agent navigates semantically, not by grep. The `bare` profile exists to isolate the raw model. (Darek's call, 2026-10-19: "whatever lets you work the best.")
