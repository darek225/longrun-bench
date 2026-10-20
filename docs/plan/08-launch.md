# 08 — Launch: Positioning, Cold Start, Growth

## Decisions

- **Positioning:** "the benchmark that measures the actual job." Every existing benchmark (SWE-bench, GAIA, Terminal-Bench, Artificial Analysis) measures slices; none measures sustained multi-step agent work with rubrics, profiles, and anti-gaming as one system. That sentence is the pitch.
- **Launch in public from day one.** Build the task bank in the open, livestream calibration, publish the judge's mistakes. The benchmark's credibility is its marketing.
- **First audience is builders, not buyers.** Agent framework authors (LangChain, AutoGen, CrewAI, open-source agent devs) want to know if their scaffolding helps. They are also the people who will run the harness for free.
- **No paid marketing.** The launch budget is $0.

## 1. Competitive landscape

| Benchmark | Measures | Gap LongRun fills |
|---|---|---|
| SWE-bench | Code repair, pass/fail | Single-domain, no rubrics, no agent profiles |
| GAIA | General assistant tasks | Short tasks, no levels, no gaming resistance |
| Terminal-Bench | Terminal tasks | Single-domain, pass/fail |
| Artificial Analysis | Model intelligence index | Models, not agents; no long-horizon tasks |
| METR RE-Bench | AI R&D tasks | Not public, not community-run |

LongRun's defensible differences, in order: (1) agent profiles — nobody separates bare/standard/native; (2) rubrics with partial credit on long tasks; (3) the time-based canary; (4) community-run at near-zero cost.

## 2. Cold start plan

A benchmark with no scores is an empty room. Sequence:

**Week 1-4 (during task authoring):**
- Publish the spec and plan docs. Post to Hacker News, r/LocalLLaMA, agent framework Discords.
- The ask: "we're building the task bank in public; contribute a task family." Contributors get founding-author credit.

**Week 5-8:**
- Release the harness. The ask shifts: "run your agent on the 15 exemplar tasks, submit checks-only scores." Zero cost to participate.
- Target: 20 community submissions across at least 5 different agent configurations. That is the minimum viable board.

**Week 9-12:**
- First verification lottery runs. Publish the first `verified` badges.
- Approach 3 agent vendors for `native` submissions. The pitch: "your competitors will be on this board; the cost to you is one engineer-day."

**Launch week:**
- Board goes live with whatever scores exist. Methodology page published.
- Launch post: the positioning sentence, the first verified scores, the generalization gaps (even if small — transparency about small gaps builds trust).

## 3. Growth loops

1. **Vendor FOMO:** once 2 vendors are on the board, the third cannot afford to be absent. Prioritize getting the first 2.
2. **Author prestige:** the task author leaderboard makes contributing status-positive. Good tasks get cited when agents fail them ("failed LongRun M-07" becomes shorthand).
3. **Research citations:** publish a quarterly "State of Agents" report from the board data. Researchers cite it; citations drive traffic; traffic drives submissions.
4. **Enterprise pull:** the enterprise API (phase 3) gives buyers the comparison data. Buyer inquiries get forwarded to vendors as leads — vendors then want to be listed.

## 4. What can kill it

- **Empty board at launch.** Mitigation: do not launch the site until 20+ submissions exist. The site launch is not the project launch.
- **One vendor dominates and stops participating.** Mitigation: community board doesn't need vendors; open models and frameworks are the base.
- **Task quality is low.** Mitigation: trial grading is mandatory; the authoring checklist (§02.1) is enforced by maintainers, not suggested.
- **The judge is embarrassing.** Mitigation: calibration data is public from day one; the judge's accuracy is itself a published metric.
