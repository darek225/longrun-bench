#!/usr/bin/env python3
"""Generate the LongRun Bench task bank (docs/plan/02-task-bank.md, 14-task-generation.md).

Every task is emitted with frozen ground truth in its directory: fixtures the
solver computes from, a manifest whose deterministic checks bind to derived
per-instance ground truth, and a smoke-script.json scripted solver that
genuinely performs the task on a pinned instance. The validation sweep
(tasks/validate_bank.py) runs every solver and a broken-deliverable control.

Run: python3 tasks/generate_bank.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LEVEL_DIRS = {1: "sprint", 2: "marathon", 3: "ultra"}
BUDGETS = {
    1: {"steps": 20, "wall_clock_minutes": 15},
    2: {"steps": 100, "wall_clock_minutes": 180},
    3: {"steps": 500, "wall_clock_minutes": 1440},
}
INDEX: list[dict[str, Any]] = []
BUSINESS_TYPES = ["dental_practice", "food_truck", "law_firm", "auto_shop"]


def rubric(c40: str, c25: str, r10: str, a10: str) -> list[dict[str, Any]]:
    return [
        {"criterion": "correctness", "weight": 40, "anchors": {"40": c40, "20": "Core answer present with material errors or several failed checks.", "0": "Deliverable missing, fabricated, or unrelated to the task."}},
        {"criterion": "completeness", "weight": 25, "anchors": {"25": c25, "15": "Most required elements present; one section thin or missing.", "0": "Most required elements missing."}},
        {"criterion": "efficiency", "weight": 15, "anchors": {"15": "Finished quickly relative to budget.", "8": "Finished with substantial budget use.", "0": "Budget exhausted with little progress."}},
        {"criterion": "error_recovery", "weight": 10, "anchors": {"10": r10, "5": "Recovers from some problems; others silently absorbed.", "0": "First problem ends useful work or is silently absorbed."}},
        {"criterion": "instruction_adherence", "weight": 10, "anchors": {"10": a10, "5": "Minor deviations that do not change the result.", "0": "Ignores explicit instructions."}},
    ]


def rubric_md(title: str, c40: str, c25: str, r10: str, a10: str) -> str:
    return (
        f"# Rubric — {title}\n\n"
        f"### Correctness (40)\n- 40: {c40}\n- 20: Core answer present with material errors.\n- 0: Missing, fabricated, or unrelated.\n\n"
        f"### Completeness (25)\n- 25: {c25}\n- 15: One required element thin or missing.\n- 0: Most elements missing.\n\n"
        "### Efficiency (15)\n- Computed by the harness formula (steps, tokens, wall clock vs budget), capped by correctness.\n\n"
        f"### Error recovery (10)\n- 10: {r10}\n- 5: Handles some problems.\n- 0: Problems silently absorbed.\n\n"
        f"### Instruction adherence (10)\n- 10: {a10}\n- 5: Minor deviations.\n- 0: Instructions ignored.\n"
    )


def write_task(
    task_id: str,
    level: int,
    category: str,
    prompt_template: str,
    parameters: dict[str, Any],
    checks: list[dict[str, Any]],
    *,
    rubric_list: list[dict[str, Any]],
    task_md: str,
    rubric_text: str,
    derived_params: list[dict[str, Any]] | None = None,
    fixtures: dict[str, str] | None = None,
    smoke: list[dict[str, Any]] | None = None,
    pinned_params: dict[str, Any] | None = None,
    allowlist: list[str] | None = None,
) -> None:
    task_dir = ROOT / LEVEL_DIRS[level] / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "id": task_id,
        "level": level,
        "category": category,
        "version": "0.1.0",
        "task_set_version": "0.1.0",
        "quarters_active": ["2026-Q4"],
        "prompt_template": prompt_template,
        "parameters": parameters,
        "budgets": BUDGETS[level],
        "network_allowlist": allowlist or [],
        "rubric": rubric_list,
        "deterministic_checks": checks,
    }
    if derived_params:
        manifest["derived_params"] = derived_params
    (task_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (task_dir / "task.md").write_text(task_md, encoding="utf-8")
    (task_dir / "rubric.md").write_text(rubric_text, encoding="utf-8")
    for rel, content in (fixtures or {}).items():
        path = task_dir / "fixtures" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if smoke is not None:
        (task_dir / "smoke-script.json").write_text(json.dumps(smoke, indent=2), encoding="utf-8")
    INDEX.append({"task_id": task_id, "level": level, "category": category, "dir": f"{LEVEL_DIRS[level]}/{task_id}", "pinned_params": pinned_params or {}})


def resp(calls: list[dict[str, Any]], tin: int = 300, tout: int = 120) -> dict[str, Any]:
    return {"tool_calls": calls, "usage": {"input_tokens": tin, "output_tokens": tout}}


def call(name: str, **args: Any) -> dict[str, Any]:
    return {"name": name, "args": args}


def py(code: str) -> dict[str, Any]:
    return resp([call("python.exec", code=code)], 500, 200)


def read(path: str) -> dict[str, Any]:
    return resp([call("file.read", path=path)], 120, 40)


def write(path: str, content: str) -> dict[str, Any]:
    return resp([call("file.write", path=path, content=content)], 300, 150)


def edit(path: str, old: str, new: str) -> dict[str, Any]:
    return resp([call("file.edit", path=path, old_text=old, new_text=new)], 250, 100)


def shell(cmd: str) -> dict[str, Any]:
    return resp([call("shell.exec", command=cmd)], 150, 60)


def deliver(artifact: str, summary: str) -> dict[str, Any]:
    return resp([call("deliver", summary=summary, artifact_uri=artifact)], 80, 30)


# -- Family S-01: vendor comparison (docs/plan/14 section 1) -------------------

VENDOR_TASKS: list[dict[str, Any]] = [
    {
        "id": "sprint-vendor-002", "product": "project_management", "label": "project management tools", "suffix": "/user/month",
        "vendors": [
            ("ClickUp", 7, "tasks, docs, goals, time tracking", "lowest cost full feature set"),
            ("Notion", 10, "docs, wikis, lightweight project tracking", "doc-centric teams"),
            ("Asana", 11, "task management, timelines, workload views", "structured project tracking"),
            ("Jira", 8, "issue tracking, sprints, dev workflows", "software teams"),
            ("Monday", 14, "visual boards, automations, dashboards", "visual planning"),
        ],
        "foreign": ["HubSpot", "Gusto", "Mailchimp"],
    },
    {
        "id": "sprint-vendor-003", "product": "payroll_software", "label": "payroll software", "suffix": "/user/month",
        "vendors": [
            ("ADP Run", 29, "payroll runs, tax filing, HR basics", "established provider"),
            ("Rippling", 35, "payroll plus IT and HR automation", "automation depth"),
            ("Paychex", 39, "payroll, tax services, HR support", "supported service"),
            ("QuickBooks Payroll", 45, "payroll integrated with QuickBooks accounting", "QuickBooks users"),
            ("Gusto", 49, "payroll, benefits, onboarding", "easiest onboarding"),
        ],
        "foreign": ["Asana", "RingCentral", "Brevo"],
    },
    {
        "id": "sprint-vendor-004", "product": "business_voip", "label": "business VoIP systems", "suffix": "/user/month",
        "vendors": [
            ("Ooma", 20, "virtual receptionist, unlimited calling", "lowest cost"),
            ("Dialpad", 25, "AI transcription, unlimited calling", "AI call features"),
            ("Nextiva", 26, "unified communications, call analytics", "analytics"),
            ("8x8", 28, "global calling, contact center options", "international calling"),
            ("RingCentral", 30, "unlimited calling, video meetings, integrations", "most integrations"),
        ],
        "foreign": ["Gusto", "Notion", "Xero"],
    },
    {
        "id": "sprint-vendor-005", "product": "email_marketing", "label": "email marketing platforms", "suffix": "/user/month",
        "vendors": [
            ("Brevo", 9, "email campaigns, transactional email, CRM basics", "lowest cost"),
            ("Constant Contact", 12, "email editor, event tools, support", "guided support"),
            ("Mailchimp", 13, "campaigns, automations, audience tools", "brand familiarity"),
            ("Klaviyo", 20, "ecommerce flows, segmentation, SMS", "ecommerce depth"),
            ("ConvertKit", 29, "creator automations, landing pages, tagging", "creator workflows"),
        ],
        "foreign": ["Salesforce", "Dialpad", "Gusto"],
    },
    {
        "id": "sprint-vendor-006", "product": "commercial_insurance", "label": "commercial insurance providers", "suffix": "/mo",
        "vendors": [
            ("Next Insurance", 19, "online quotes, general liability, fast binding", "fastest online quote"),
            ("Hiscox", 22, "general liability, professional liability, online purchase", "online purchase"),
            ("biBERK", 25, "workers comp, general liability, small business focus", "small business focus"),
            ("Hartford", 40, "broad commercial lines, agent network", "agent support"),
            ("Travelers", 55, "broad commercial lines, risk control services", "risk control depth"),
        ],
        "foreign": ["Mailchimp", "Asana", "Zoho CRM"],
    },
]


def build_vendor_family() -> None:
    for spec in VENDOR_TASKS:
        vendors = spec["vendors"]
        names = [v[0] for v in vendors]
        term_base = "/user" if spec["suffix"] == "/user/month" else "/mo"
        price_terms = [str(v[1]) + term_base for v in vendors]
        cheapest = min(vendors, key=lambda v: v[1])[0]
        priciest = max(vendors, key=lambda v: v[1])[0]
        easiest = vendors[-1][0]
        derived = [
            {
                "name": "expected",
                "key": "{{focus}}",
                "map": {
                    "lowest_cost": {"recommended": cheapest},
                    "easiest_onboarding": {"recommended": easiest},
                    "most_capable": {"recommended": priciest},
                },
            }
        ]
        fixtures = {
            "vendors.json": json.dumps(
                {spec["product"]: [{"name": n, "price": p, "features": f, "best_for": b} for n, p, f, b in vendors]},
                indent=2,
            )
        }
        checks = [
            {"id": "vendors_named", "check": "regex_all", "params": {"patterns": names}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "prices_present", "check": "regex_all", "params": {"patterns": price_terms}, "caps": {"correctness": 20}},
            {"id": "recommendation_matches_focus", "check": "regex_all", "params": {"patterns": ["{{expected.recommended}}"]}, "caps": {"completeness": 15}},
            {"id": "no_invented_vendors", "check": "banned_phrases", "params": {"phrases": spec["foreign"]}, "caps": {"correctness": 15}},
            {"id": "brief_length", "check": "word_count", "params": {"min": 80, "max": 400}, "caps": {"instruction_adherence": 5}},
        ]
        solver_code = "\n".join(
            [
                "import json",
                "data = json.load(open('vendors.json'))['" + spec["product"] + "']",
                "lines = ['Vendor comparison for a dental practice (" + spec["label"] + "):', '']",
                "for v in data:",
                "    lines.append('- {}: ${}" + spec["suffix"] + ", key features: {}, best for: {}'.format(v['name'], v['price'], v['features'], v['best_for']))",
                "cheapest = min(data, key=lambda v: v['price'])",
                "lines.append('')",
                "lines.append('Recommendation: For a small dental practice, ' + cheapest['name'] + ' is the recommendation on lowest cost at $' + str(cheapest['price']) + ' per unit per month, and its feature set (' + cheapest['features'] + ') covers what a small team needs daily. The pricier options add depth a small practice rarely uses in year one. Start on a monthly plan, keep the contract short, and re-evaluate after a quarter of real usage against the shortlist above before committing to an annual deal.')",
                "open('brief.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('wrote brief.md')",
            ]
        )
        write_task(
            spec["id"],
            1,
            "research_synthesis",
            "Using vendors.json in the workspace, compare the " + spec["label"] + " vendors for a {{business_type}}. Write brief.md with one line per vendor giving its name, monthly price, and key features, plus a recommendation paragraph of at least 60 words. The recommendation must fit the drawn focus: {{focus}}.",
            {
                "business_type": {"type": "enum", "values": BUSINESS_TYPES},
                "focus": {"type": "enum", "values": ["lowest_cost", "easiest_onboarding", "most_capable"]},
            },
            checks,
            rubric_list=rubric(
                "Every deterministic check passes; vendor names and prices match vendors.json exactly; no vendor invented.",
                "All vendors with price and features, plus a recommendation matching the drawn focus.",
                "Notices data quirks in the source file and still delivers a consistent brief.",
                "One line per vendor; recommendation paragraph present; brief.md delivered.",
            ),
            task_md="# Vendor comparison — " + spec["label"] + "\n\nUsing `vendors.json`, compare the vendors for the drawn business type and focus. One line per vendor (name, monthly price, key features) plus a recommendation paragraph of at least 60 words that fits the drawn focus. Do not invent vendors or prices.\n",
            rubric_text=rubric_md(spec["id"], "Names and prices match vendors.json exactly; no invented vendors.", "All vendors plus a focus-matching recommendation.", "Handles source quirks without inventing data.", "Format followed; brief.md delivered."),
            derived_params=derived,
            fixtures=fixtures,
            smoke=[read("vendors.json"), py(solver_code), deliver("brief.md", "Compared the " + spec["label"] + " vendors from vendors.json and wrote brief.md.")],
            pinned_params={"business_type": "dental_practice", "focus": "lowest_cost"},
        )


# -- Family S-02: buggy repos (docs/plan/14 section 2) --------------------------

BUGGY_REPOS: list[dict[str, Any]] = [
    {
        "id": "sprint-code-002", "module": "expense_splitter.py",
        "src": (
            '"""Split shared expenses."""\n\n\n'
            "def split_evenly(total_cents, people):\n"
            "    share = total_cents // people\n"
            "    return [share] * people\n\n\n"
            "def parse_amount(text):\n"
            '    return float(text.replace("$", "").strip())\n\n\n'
            "def split_weighted(total_cents, weights):\n"
            "    weights.append(1)\n"
            "    total_weight = sum(weights)\n"
            "    return [total_cents * w // total_weight for w in weights]\n"
        ),
        "tests": (
            "from expense_splitter import parse_amount, split_evenly, split_weighted\n\n\n"
            "def test_split_evenly_exact():\n"
            "    assert split_evenly(100, 4) == [25, 25, 25, 25]\n\n\n"
            "def test_split_evenly_remainder_is_distributed():\n"
            "    parts = split_evenly(100, 3)\n"
            "    assert sum(parts) == 100\n"
            "    assert max(parts) - min(parts) <= 1\n\n\n"
            "def test_parse_amount_with_commas():\n"
            '    assert parse_amount("$1,200.50") == 1200.50\n\n\n'
            "def test_parse_amount_plain():\n"
            '    assert parse_amount("42") == 42.0\n\n\n'
            "def test_split_weighted_does_not_mutate_weights():\n"
            "    weights = [1, 1]\n"
            "    split_weighted(100, weights)\n"
            "    assert weights == [1, 1]\n\n\n"
            "def test_split_weighted_values():\n"
            "    assert split_weighted(100, [3, 1]) == [75, 25]\n"
        ),
        "fixes": [
            (
                "    share = total_cents // people\n    return [share] * people",
                "    base = total_cents // people\n    remainder = total_cents - base * people\n    return [base + 1] * remainder + [base] * (people - remainder)",
            ),
            (
                '    return float(text.replace("$", "").strip())',
                '    return float(text.replace("$", "").replace(",", "").strip())',
            ),
            (
                "    weights.append(1)\n    total_weight = sum(weights)",
                "    total_weight = sum(weights)",
            ),
        ],
        "summary": "Bugs: split_evenly dropped the remainder so shares summed below the total; parse_amount crashed on thousands separators; split_weighted mutated the caller's weights list by appending to it. Fixes: distribute the remainder one cent at a time to the first shares, strip commas before parsing, and never mutate the input weights. All six tests pass and no test files were modified in any way.",
    },
    {
        "id": "sprint-code-003", "module": "log_analyzer.py",
        "src": (
            '"""Analyze plain-text log files."""\n\n\n'
            "def count_level(lines, level):\n"
            "    return sum(1 for line in lines if level in line)\n\n\n"
            "def first_error(lines):\n"
            "    for line in reversed(lines):\n"
            '        if "ERROR" in line:\n'
            "            return line\n"
            "    return None\n\n\n"
            "def summarize(path):\n"
            "    count = 0\n"
            "    with open(path) as handle:\n"
            "        for line in handle:\n"
            "            count += 1\n"
            "    return count\n"
        ),
        "tests": (
            "from log_analyzer import count_level, first_error, summarize\n\n\n"
            "def test_count_level_matches_whole_word():\n"
            '    lines = ["ERROR disk full", "NOERROR here", "ERRORS galore", "INFO ok"]\n'
            '    assert count_level(lines, "ERROR") == 1\n\n\n'
            "def test_first_error_returns_first():\n"
            '    lines = ["INFO start", "ERROR first", "ERROR second"]\n'
            '    assert first_error(lines) == "ERROR first"\n\n\n'
            "def test_summarize_skips_blank_lines(tmp_path):\n"
            '    path = tmp_path / "app.log"\n'
            '    path.write_text("one\\n\\n\\ntwo\\n")\n'
            "    assert summarize(str(path)) == 2\n"
        ),
        "fixes": [
            (
                "    return sum(1 for line in lines if level in line)",
                "    import re\n    return sum(1 for line in lines if re.search(r'\\b' + re.escape(level) + r'\\b', line))",
            ),
            (
                "    for line in reversed(lines):",
                "    for line in lines:",
            ),
            (
                "        for line in handle:\n            count += 1",
                "        for line in handle:\n            if line.strip():\n                count += 1",
            ),
        ],
        "summary": "Bugs: count_level used substring matching so NOERROR and ERRORS counted as errors; first_error scanned the log backwards and returned the last error instead of the first; summarize counted blank lines as entries. Fixes: match the level as a whole word with a regex, scan forwards, and skip blank lines when counting entries. All tests pass and the test files were not modified at all.",
    },
    {
        "id": "sprint-code-004", "module": "backup_tool.py",
        "src": (
            '"""Plan file backups."""\n\n\n'
            "def manifest_name(ts):\n"
            '    return "backup-" + ts.strftime("%Y-%m-%d %H:%M:%S") + ".json"\n\n\n'
            "def plan_backup(files, excludes):\n"
            "    planned = []\n"
            "    for name in files:\n"
            "        if name in excludes:\n"
            "            planned.append(name)\n"
            "    return planned\n\n\n"
            "def verify_copy(src_hash, dst_hash):\n"
            "    return True\n"
        ),
        "tests": (
            "from datetime import datetime\n\n"
            "from backup_tool import manifest_name, plan_backup, verify_copy\n\n\n"
            "def test_manifest_name_is_a_valid_filename():\n"
            "    name = manifest_name(datetime(2026, 1, 2, 3, 4, 5))\n"
            '    assert " " not in name and ":" not in name\n'
            '    assert name.endswith(".json")\n\n\n'
            "def test_plan_backup_skips_excluded():\n"
            '    assert plan_backup(["a.txt", "b.tmp", "c.log"], ["b.tmp"]) == ["a.txt", "c.log"]\n\n\n'
            "def test_verify_copy_detects_mismatch():\n"
            '    assert verify_copy("abc", "xyz") is False\n'
            '    assert verify_copy("abc", "abc") is True\n'
        ),
        "fixes": [
            (
                '    return "backup-" + ts.strftime("%Y-%m-%d %H:%M:%S") + ".json"',
                '    return "backup-" + ts.strftime("%Y%m%d-%H%M%S") + ".json"',
            ),
            (
                "        if name in excludes:",
                "        if name not in excludes:",
            ),
            (
                "def verify_copy(src_hash, dst_hash):\n    return True",
                "def verify_copy(src_hash, dst_hash):\n    return src_hash == dst_hash",
            ),
        ],
        "summary": "Bugs: manifest_name embedded spaces and colons, which are invalid in filenames on common filesystems; plan_backup had an inverted condition and planned only the excluded files; verify_copy always returned True without comparing hashes, so corrupt copies passed verification. Fixes: use a compact timestamp format, include files that are not excluded, and actually compare the source and destination hashes. All tests pass now.",
    },
    {
        "id": "sprint-code-005", "module": "inventory_api.py",
        "src": (
            '"""A tiny in-memory inventory."""\n\n\n'
            "class Inventory:\n"
            "    def __init__(self):\n"
            "        self.stock = {}\n\n"
            "    def add(self, sku, qty):\n"
            "        self.stock[sku] = qty\n\n"
            "    def decrement(self, sku, qty):\n"
            "        self.stock[sku] = self.stock.get(sku, 0) - qty\n"
            "        return True\n\n"
            "    def low_stock(self, threshold):\n"
            "        return [sku for sku, qty in self.stock.items() if qty < threshold]\n"
        ),
        "tests": (
            "from inventory_api import Inventory\n\n\n"
            "def test_add_accumulates():\n"
            "    inv = Inventory()\n"
            '    inv.add("A", 5)\n'
            '    inv.add("A", 3)\n'
            '    assert inv.stock["A"] == 8\n\n\n'
            "def test_decrement_refuses_insufficient_stock():\n"
            "    inv = Inventory()\n"
            '    inv.add("A", 2)\n'
            '    assert inv.decrement("A", 5) is False\n'
            '    assert inv.stock["A"] == 2\n\n\n'
            "def test_decrement_ok():\n"
            "    inv = Inventory()\n"
            '    inv.add("A", 5)\n'
            '    assert inv.decrement("A", 2) is True\n'
            '    assert inv.stock["A"] == 3\n\n\n'
            "def test_low_stock_includes_at_threshold():\n"
            "    inv = Inventory()\n"
            '    inv.add("A", 5)\n'
            '    inv.add("B", 9)\n'
            '    assert inv.low_stock(5) == ["A"]\n'
        ),
        "fixes": [
            (
                "        self.stock[sku] = qty",
                "        self.stock[sku] = self.stock.get(sku, 0) + qty",
            ),
            (
                "    def decrement(self, sku, qty):\n        self.stock[sku] = self.stock.get(sku, 0) - qty\n        return True",
                "    def decrement(self, sku, qty):\n        if self.stock.get(sku, 0) < qty:\n            return False\n        self.stock[sku] -= qty\n        return True",
            ),
            (
                "if qty < threshold",
                "if qty <= threshold",
            ),
        ],
        "summary": "Bugs: add overwrote the existing quantity instead of accumulating; decrement happily drove stock negative and always reported success; low_stock used a strict less-than so items exactly at the threshold were never flagged. Fixes: accumulate on add, refuse and report False when stock is insufficient, and flag items at or below the threshold. The full suite passes and no tests were changed.",
    },
]


def build_buggy_repos() -> None:
    for spec in BUGGY_REPOS:
        module = spec["module"]
        test_name = "test_" + module
        fixtures = {
            module: spec["src"],
            "tests/" + test_name: spec["tests"],
            "conftest.py": "# Ensures the workspace root is on sys.path for test imports.\n",
        }
        checks = [
            {"id": "tests_pass", "check": "pytest_pass", "params": {"test_path": "tests"}, "caps": {"correctness": 10, "completeness": 10}},
            {"id": "module_intact", "check": "file_contains", "params": {"path": module, "patterns": ["def "]}, "caps": {"correctness": 20}},
            {"id": "summary_length", "check": "word_count", "params": {"min": 30, "max": 300}, "caps": {"completeness": 20}},
        ]
        smoke = [read(module)]
        for old, new in spec["fixes"]:
            smoke.append(edit(module, old, new))
        smoke.append(shell("python3 -m pytest -q tests"))
        smoke.append(write("summary.md", spec["summary"] + "\n"))
        smoke.append(deliver("summary.md", "Fixed all planted bugs in " + module + "; suite is green; summary.md explains each bug and fix."))
        write_task(
            spec["id"],
            1,
            "code_repair",
            "The workspace contains " + module + " with a failing test suite in tests/. There are {{bug_count}} planted bugs; the {{theme}} cases expose them. Fix " + module + " only; do not modify the tests. When the suite passes, write summary.md describing each bug and its fix, then deliver summary.md.",
            {
                "bug_count": {"type": "enum", "values": ["three", "3", "several"]},
                "theme": {"type": "enum", "values": ["edge-case", "boundary", "regression"]},
            },
            checks,
            rubric_list=rubric(
                "Full suite passes; every planted bug fixed at its root cause.",
                "Suite green and summary explains every bug and fix.",
                "Reads the failures and diagnoses root causes instead of shotgun edits.",
                "Only the module changed; tests untouched; summary.md delivered.",
            ),
            task_md="# Failing test suite — " + module + "\n\nThe workspace contains `" + module + "` with a failing test suite in `tests/`. Fix the module only; do not modify the tests. When the suite passes, write `summary.md` describing each bug and its fix, then deliver `summary.md`.\n",
            rubric_text=rubric_md(spec["id"], "Full suite passes; bugs fixed at the root cause.", "Suite green; summary covers every bug.", "Diagnoses from test failures.", "Only the module changed; summary.md delivered."),
            fixtures=fixtures,
            smoke=smoke,
            pinned_params={"bug_count": "three", "theme": "edge-case"},
        )


# -- Family S-06: crashing scripts (docs/plan/02 S-06) --------------------------

CRASH_TASKS: list[dict[str, Any]] = [
    {
        "id": "sprint-code-006", "module": "parse_csv_line.py", "input_type": "quoted fields containing commas",
        "src": (
            '"""Parse one CSV line into fields."""\n\n\n'
            "def parse_line(line):\n"
            '    return [part.strip().strip(chr(34)) for part in line.split(",")]\n'
        ),
        "tests": (
            "from parse_csv_line import parse_line\n\n\n"
            "def test_simple():\n"
            '    assert parse_line("a,b,c") == ["a", "b", "c"]\n\n\n'
            "def test_quoted_comma():\n"
            '    assert parse_line(\'a,"b,c",d\') == ["a", "b,c", "d"]\n'
        ),
        "fixed": (
            '"""Parse one CSV line into fields."""\n\n'
            "import csv\n"
            "import io\n\n\n"
            "def parse_line(line):\n"
            "    rows = list(csv.reader(io.StringIO(line)))\n"
            "    return rows[0] if rows else []\n"
        ),
        "regression": (
            "from parse_csv_line import parse_line\n\n\n"
            "def test_regression_quoted_comma_and_spaces():\n"
            '    assert parse_line(\'x,"y, z",w\') == ["x", "y, z", "w"]\n'
        ),
        "summary": "Crash report: parse_line split on every comma, so a quoted field containing a comma was torn into pieces and the field count came out wrong. Fix: delegate parsing to the csv module, which understands quoting. Added a regression test covering a quoted field with a comma and a space. The original suite plus the new regression test pass.",
    },
    {
        "id": "sprint-code-007", "module": "summarize_log.py", "input_type": "blank lines in the log",
        "src": (
            '"""Summarize log lines as (level, message) pairs."""\n\n\n'
            "def summarize(lines):\n"
            "    out = []\n"
            "    for line in lines:\n"
            "        parts = line.split(' ', 1)\n"
            "        out.append((parts[0], parts[1]))\n"
            "    return out\n"
        ),
        "tests": (
            "from summarize_log import summarize\n\n\n"
            "def test_pairs():\n"
            '    assert summarize(["INFO start", "ERROR disk"]) == [("INFO", "start"), ("ERROR", "disk")]\n\n\n'
            "def test_blank_lines_are_skipped():\n"
            '    assert summarize(["INFO start", "", "ERROR disk"]) == [("INFO", "start"), ("ERROR", "disk")]\n'
        ),
        "fixed": (
            '"""Summarize log lines as (level, message) pairs."""\n\n\n'
            "def summarize(lines):\n"
            "    out = []\n"
            "    for line in lines:\n"
            "        if not line.strip():\n"
            "            continue\n"
            "        parts = line.split(' ', 1)\n"
            "        out.append((parts[0], parts[1] if len(parts) > 1 else ''))\n"
            "    return out\n"
        ),
        "regression": (
            "from summarize_log import summarize\n\n\n"
            "def test_regression_only_blank_lines():\n"
            '    assert summarize(["", "   "]) == []\n'
        ),
        "summary": "Crash report: summarize indexed parts[1] on every line, so a blank line (which splits into a single empty piece) raised IndexError and killed the run. Fix: skip blank lines and tolerate a missing message part. Added a regression test with only blank lines. The original suite and the regression test pass.",
    },
    {
        "id": "sprint-code-008", "module": "load_config.py", "input_type": "configs missing optional keys",
        "src": (
            '"""Load service configuration."""\n\n\n'
            "def load_config(raw):\n"
            "    return {\n"
            '        "host": raw["host"],\n'
            '        "port": raw["port"],\n'
            '        "timeout": raw["timeout"],\n'
            '        "retries": raw["retries"],\n'
            "    }\n"
        ),
        "tests": (
            "from load_config import load_config\n\n\n"
            "def test_full_config():\n"
            '    cfg = load_config({"host": "h", "port": 80, "timeout": 5, "retries": 2})\n'
            '    assert cfg == {"host": "h", "port": 80, "timeout": 5, "retries": 2}\n\n\n'
            "def test_missing_optional_keys_use_defaults():\n"
            '    cfg = load_config({"host": "h", "port": 80})\n'
            '    assert cfg["timeout"] == 30\n'
            '    assert cfg["retries"] == 3\n'
        ),
        "fixed": (
            '"""Load service configuration."""\n\n\n'
            "DEFAULTS = {'timeout': 30, 'retries': 3}\n\n\n"
            "def load_config(raw):\n"
            "    return {\n"
            '        "host": raw["host"],\n'
            '        "port": raw["port"],\n'
            '        "timeout": raw.get("timeout", DEFAULTS["timeout"]),\n'
            '        "retries": raw.get("retries", DEFAULTS["retries"]),\n'
            "    }\n"
        ),
        "regression": (
            "from load_config import load_config\n\n\n"
            "def test_regression_explicit_values_win_over_defaults():\n"
            '    cfg = load_config({"host": "h", "port": 1, "timeout": 1, "retries": 0})\n'
            '    assert cfg["timeout"] == 1 and cfg["retries"] == 0\n'
        ),
        "summary": "Crash report: load_config indexed optional keys directly, so any config omitting timeout or retries raised KeyError. Fix: read optional keys with documented defaults (timeout 30, retries 3) while required keys still fail loudly when absent. Added a regression test proving explicit values, including zero, win over the defaults. All tests pass.",
    },
    {
        "id": "sprint-code-009", "module": "text_stats.py", "input_type": "empty text",
        "src": (
            '"""Compute simple text statistics."""\n\n\n'
            "def stats(text):\n"
            "    words = text.split()\n"
            "    longest = max(words, key=len)\n"
            "    return {'words': len(words), 'longest': longest, 'avg_len': sum(len(w) for w in words) / len(words)}\n"
        ),
        "tests": (
            "from text_stats import stats\n\n\n"
            "def test_basic():\n"
            '    out = stats("a bb ccc")\n'
            '    assert out["words"] == 3 and out["longest"] == "ccc"\n\n\n'
            "def test_empty_text():\n"
            '    out = stats("")\n'
            '    assert out == {"words": 0, "longest": "", "avg_len": 0.0}\n'
        ),
        "fixed": (
            '"""Compute simple text statistics."""\n\n\n'
            "def stats(text):\n"
            "    words = text.split()\n"
            "    if not words:\n"
            "        return {'words': 0, 'longest': '', 'avg_len': 0.0}\n"
            "    longest = max(words, key=len)\n"
            "    return {'words': len(words), 'longest': longest, 'avg_len': sum(len(w) for w in words) / len(words)}\n"
        ),
        "regression": (
            "from text_stats import stats\n\n\n"
            "def test_regression_whitespace_only():\n"
            '    assert stats("   ") == {"words": 0, "longest": "", "avg_len": 0.0}\n'
        ),
        "summary": "Crash report: stats called max() on an empty word list and divided by the word count, so empty input raised ValueError and ZeroDivisionError. Fix: return the documented zero result for empty or whitespace-only text before computing anything. Added a regression test for whitespace-only input. The original suite and the regression test pass.",
    },
]


def build_crash_family() -> None:
    for spec in CRASH_TASKS:
        module = spec["module"]
        fixtures = {
            module: spec["src"],
            "tests/test_" + module: spec["tests"],
            "conftest.py": "# Ensures the workspace root is on sys.path for test imports.\n",
        }
        checks = [
            {"id": "tests_pass", "check": "pytest_pass", "params": {"test_path": "tests"}, "caps": {"correctness": 10, "completeness": 10}},
            {"id": "regression_test_added", "check": "file_exists", "params": {"path": "tests/test_regression.py"}, "caps": {"completeness": 15}},
            {"id": "summary_length", "check": "word_count", "params": {"min": 30, "max": 300}, "caps": {"completeness": 20}},
        ]
        smoke = [
            read(module),
            write(module, spec["fixed"]),
            write("tests/test_regression.py", spec["regression"]),
            shell("python3 -m pytest -q tests"),
            write("summary.md", spec["summary"] + "\n"),
            deliver("summary.md", "Fixed the crash in " + module + ", added a regression test, suite green, summary.md delivered."),
        ]
        write_task(
            spec["id"],
            1,
            "code_repair",
            "The workspace contains " + module + ", which crashes on " + spec["input_type"] + ". The failing tests in tests/ show the crash. Fix " + module + ", add a regression test at tests/test_regression.py that would have caught the crash, write summary.md describing the crash and the fix, then deliver summary.md. Input flavor: {{input_flavor}}; codebase: {{codebase}}.",
            {
                "input_flavor": {"type": "enum", "values": ["production-like", "adversarial", "minimal"]},
                "codebase": {"type": "enum", "values": ["internal tools", "client utilities", "open source mirror"]},
            },
            checks,
            rubric_list=rubric(
                "Crash fixed at the root cause; full suite including the new regression test passes.",
                "Fix, regression test, and summary all present.",
                "Reproduces the crash from the failing test before fixing it.",
                "Regression test added at the required path; summary.md delivered.",
            ),
            task_md="# Crashing script — " + module + "\n\n`" + module + "` crashes on " + spec["input_type"] + ". Fix it, add a regression test at `tests/test_regression.py`, write `summary.md`, and deliver `summary.md`.\n",
            rubric_text=rubric_md(spec["id"], "Crash fixed; suite plus regression test green.", "Fix, regression test, and summary present.", "Reproduces before fixing.", "Required paths respected; summary.md delivered."),
            fixtures=fixtures,
            smoke=smoke,
            pinned_params={"input_flavor": "production-like", "codebase": "internal tools"},
        )


# -- Family S-03 + extra data tasks (docs/plan/14 section 3) ---------------------

def _sales_checks(anomaly_terms: list[str]) -> list[dict[str, Any]]:
    return [
        {"id": "top_products_named", "check": "regex_all", "params": {"patterns": "{{expected.top_products}}"}, "caps": {"correctness": 25, "completeness": 15}},
        {"id": "total_revenue_correct", "check": "numeric_within", "params": {"label": "total revenue", "value": "{{expected.total_revenue}}", "tolerance": 1.5}, "caps": {"correctness": 20}},
        {"id": "anomalies_named", "check": "regex_all", "params": {"patterns": anomaly_terms}, "caps": {"completeness": 15}},
        {"id": "report_length", "check": "word_count", "params": {"min": 60, "max": 500}, "caps": {"instruction_adherence": 5}},
    ]


def _sales_task(
    task_id: str,
    csv_name: str,
    csv_text: str,
    truth: dict[str, dict[str, Any]],
    anomaly_terms: list[str],
    prompt: str,
    solver_code: str,
    title: str,
) -> None:
    derived = [{"name": "expected", "key": "{{region}}|{{top_n}}", "map": truth}]
    write_task(
        task_id,
        1,
        "data_analysis",
        prompt,
        {
            "region": {"type": "enum", "values": ["north", "south", "west"]},
            "top_n": {"type": "integer", "min": 2, "max": 3},
        },
        _sales_checks(anomaly_terms),
        rubric_list=rubric(
            "Revenue and top products match ground truth for the drawn instance under the stated rules.",
            "Revenue, full top-N list, and every planted anomaly class named.",
            "Notices and correctly handles every planted data problem instead of absorbing it.",
            "Follows the stated computation rules exactly; report.md delivered.",
        ),
        task_md="# " + title + "\n\n" + prompt.replace("{{region}}", "the drawn region").replace("{{top_n}}", "the drawn N") + "\n",
        rubric_text=rubric_md(task_id, "Numbers match ground truth under the stated rules.", "Revenue, top-N, and all anomaly classes named.", "Planted problems handled and disclosed.", "Rules followed; report.md delivered."),
        derived_params=derived,
        fixtures={csv_name: csv_text},
        smoke=[read(csv_name), py(solver_code), deliver("report.md", "Computed the report from " + csv_name + " under the stated rules.")],
        pinned_params={"region": "north", "top_n": 3},
    )


Q2_CSV = (
    "order_id,date,region,product,quantity,unit_price,currency\n"
    "2001,2026-04-05,north,Alpha,10,100,USD\n"
    "2002,2026-04-06,north,Beta,8,50,USD\n"
    "2003,2026-04-07,north,Gamma,3,200,USD\n"
    "2003,2026-04-08,north,Gamma,3,200,USD\n"
    "2004,2026-04-09,north,Alpha,2,100,EUR\n"
    "2005,2026-04-10,north,Delta,4,25,USD\n"
    "2006,2026-05-01,north,Beta,2,50,EUR\n"
    "2007,2026-04-05,south,Alpha,5,100,USD\n"
    "2008,2026-04-06,south,Gamma,1,200,EUR\n"
    "2009,2026-04-07,south,Beta,11,50,USD\n"
    "2010,2026-07-15,south,Alpha,10,100,USD\n"
    "2011,2026-04-08,south,Delta,2,25,USD\n"
    "2012,2026-04-05,west,Gamma,5,200,USD\n"
    "2013,2026-04-06,west,Alpha,3,100,USD\n"
    "2014,2026-04-07,west,Beta,5,50,USD\n"
    "2015,2026-04-08,west,Delta,1,25,EUR\n"
    "2016,2026-04-09,west,Beta,2,,USD\n"
)

Q2_TRUTH = {
    "north|2": {"top_products": ["Alpha", "Gamma"], "total_revenue": 2424.0},
    "north|3": {"top_products": ["Alpha", "Gamma", "Beta"], "total_revenue": 2424.0},
    "south|2": {"top_products": ["Beta", "Alpha"], "total_revenue": 1316.0},
    "south|3": {"top_products": ["Beta", "Alpha", "Gamma"], "total_revenue": 1316.0},
    "west|2": {"top_products": ["Gamma", "Alpha"], "total_revenue": 1577.0},
    "west|3": {"top_products": ["Gamma", "Alpha", "Beta"], "total_revenue": 1577.0},
}

Q2_SOLVER = "\n".join(
    [
        "import csv",
        "from collections import defaultdict",
        "rows = list(csv.DictReader(open('sales_q2.csv')))",
        "seen = set()",
        "kept = []",
        "for r in rows:",
        "    if r['order_id'] in seen:",
        "        continue",
        "    seen.add(r['order_id'])",
        "    kept.append(r)",
        "rev = defaultdict(float)",
        "for r in kept:",
        "    if r['region'] != 'north' or not r['unit_price'] or r['date'] > '2026-06-30':",
        "        continue",
        "    price = float(r['unit_price']) * (1.08 if r['currency'] == 'EUR' else 1.0)",
        "    rev[r['product']] += int(r['quantity']) * price",
        "top = sorted(rev.items(), key=lambda kv: -kv[1])[:3]",
        "total = sum(rev.values())",
        "lines = ['Total revenue: ${:,.2f} for the north region.'.format(total), '', 'Top products by revenue:']",
        "for name, val in top:",
        "    lines.append('- {}: ${:,.2f}'.format(name, val))",
        "lines.append('')",
        "lines.append('Data quality issues: duplicate order_id rows (keep the first occurrence), EUR-denominated rows converted at 1.08, future-dated rows after 2026-06-30 excluded from revenue, and one row with a missing unit price excluded. Each rule was applied before totals were computed and the affected rows are flagged here for the data owner to review.')",
        "open('report.md', 'w').write(chr(10).join(lines) + chr(10))",
        "print('wrote report.md')",
    ]
)

Q3_CSV = (
    "order_id,date,region,product_id,product,quantity,unit_price,discount\n"
    "3001,2026-07-05,north,P1,Alpha,10,100,0\n"
    "3002,2026-07-06,north,P2,Beta,8,50,10%\n"
    "3003,2026-07-07,north,P3,Gamma,3,200,0.15\n"
    "3004,2026-07-08,north,P1,Alpha,-2,100,0\n"
    "3005,2026-07-09,north,P9,Beta,5,50,0\n"
    "3006,2026-07-10,north,P4,Delta,4,25,0\n"
    "3007,2026-07-05,south,P2,Beta,12,50,0\n"
    "3008,2026-07-06,south,P1,Alpha,4,100,20%\n"
    "3009,2026-07-07,south,P3,Gamma,2,200,0\n"
    "3010,2026-07-08,south,P4,Delta,-1,25,0\n"
    "3011,2026-07-05,west,P3,Gamma,4,200,10%\n"
    "3012,2026-07-06,west,P1,Alpha,2,100,0\n"
    "3013,2026-07-07,west,P2,Beta,3,50,0.2\n"
    "3014,2026-07-08,west,P4,Delta,6,25,0\n"
)

Q3_TRUTH = {
    "north|2": {"top_products": ["Alpha", "Gamma"], "total_revenue": 1770.0},
    "north|3": {"top_products": ["Alpha", "Gamma", "Beta"], "total_revenue": 1770.0},
    "south|2": {"top_products": ["Beta", "Gamma"], "total_revenue": 1295.0},
    "south|3": {"top_products": ["Beta", "Gamma", "Alpha"], "total_revenue": 1295.0},
    "west|2": {"top_products": ["Gamma", "Alpha"], "total_revenue": 1190.0},
    "west|3": {"top_products": ["Gamma", "Alpha", "Delta"], "total_revenue": 1190.0},
}

Q3_SOLVER = "\n".join(
    [
        "import csv",
        "from collections import defaultdict",
        "CANON = {'P1': 'Alpha', 'P2': 'Beta', 'P3': 'Gamma', 'P4': 'Delta'}",
        "rows = list(csv.DictReader(open('sales_q3.csv')))",
        "rev = defaultdict(float)",
        "for r in rows:",
        "    if r['region'] != 'north':",
        "        continue",
        "    if CANON.get(r['product_id']) != r['product']:",
        "        continue",
        "    d = r['discount']",
        "    disc = float(d.strip('%')) / 100.0 if d.endswith('%') else float(d)",
        "    rev[r['product']] += int(r['quantity']) * float(r['unit_price']) * (1.0 - disc)",
        "top = sorted(rev.items(), key=lambda kv: -kv[1])[:3]",
        "total = sum(rev.values())",
        "lines = ['Total revenue: ${:,.2f} for the north region.'.format(total), '', 'Top products by revenue:']",
        "for name, val in top:",
        "    lines.append('- {}: ${:,.2f}'.format(name, val))",
        "lines.append('')",
        "lines.append('Data quality issues: negative-quantity return rows were counted as negative revenue, the discount column mixes percent strings and decimal fractions and was normalized before applying discounts, and one product_id mismatch row was excluded from revenue and flagged here for correction in the source system by its owner.')",
        "open('report.md', 'w').write(chr(10).join(lines) + chr(10))",
        "print('wrote report.md')",
    ]
)


def build_sales_family() -> None:
    _sales_task(
        "sprint-data-002",
        "sales_q2.csv",
        Q2_CSV,
        Q2_TRUTH,
        ["duplicate", "eur", "future", "missing"],
        "Analyze sales_q2.csv in the workspace. Rules: deduplicate by order_id keeping the first occurrence; EUR rows convert at 1.08 USD; rows dated after 2026-06-30 are excluded from revenue; rows with a missing unit price are excluded. For the {{region}} region, write report.md with the total revenue, the top {{top_n}} products by revenue, and the data quality issues (duplicate, EUR, future-dated, and missing-price rows).",
        Q2_SOLVER,
        "Q2 sales analysis",
    )
    _sales_task(
        "sprint-data-003",
        "sales_q3.csv",
        Q3_CSV,
        Q3_TRUTH,
        ["return", "discount", "mismatch"],
        "Analyze sales_q3.csv in the workspace. Rules: negative quantities are returns and count as negative revenue; the discount column mixes percent strings like 10% and decimals like 0.15, normalize before applying; rows whose product_id does not match the canonical map (P1 Alpha, P2 Beta, P3 Gamma, P4 Delta) are excluded. For the {{region}} region, write report.md with the total revenue, the top {{top_n}} products by revenue, and the data quality issues (return rows, discount formats, product mismatch).",
        Q3_SOLVER,
        "Q3 sales analysis",
    )


# -- Extra data tasks: invoices, inventory, traffic, tickets ---------------------

def _metric_task(
    task_id: str,
    csv_name: str,
    csv_text: str,
    param_name: str,
    param_values: list[str],
    truth: dict[str, dict[str, Any]],
    top_key: str,
    total_label: str,
    total_key: str,
    anomaly_terms: list[str],
    prompt: str,
    solver_code: str,
    title: str,
    extra_numeric: tuple[str, str, float] | None = None,
) -> None:
    checks: list[dict[str, Any]] = [
        {"id": "top_named", "check": "regex_all", "params": {"patterns": "{{expected." + top_key + "}}"}, "caps": {"correctness": 25, "completeness": 15}},
        {"id": "total_correct", "check": "numeric_within", "params": {"label": total_label, "value": "{{expected." + total_key + "}}", "tolerance": 1.5}, "caps": {"correctness": 20}},
        {"id": "anomalies_named", "check": "regex_all", "params": {"patterns": anomaly_terms}, "caps": {"completeness": 15}},
        {"id": "report_length", "check": "word_count", "params": {"min": 60, "max": 500}, "caps": {"instruction_adherence": 5}},
    ]
    if extra_numeric is not None:
        label, key, tol = extra_numeric
        checks.insert(2, {"id": "extra_numeric", "check": "numeric_within", "params": {"label": label, "value": "{{expected." + key + "}}", "tolerance": tol}, "caps": {"correctness": 15}})
    derived = [{"name": "expected", "key": "{{" + param_name + "}}|{{top_n}}", "map": truth}]
    write_task(
        task_id,
        1,
        "data_analysis",
        prompt,
        {
            param_name: {"type": "enum", "values": param_values},
            "top_n": {"type": "integer", "min": 2, "max": 3},
        },
        checks,
        rubric_list=rubric(
            "Figures match ground truth for the drawn instance under the stated rules.",
            "Totals, full top-N list, and every planted anomaly class named.",
            "Notices and correctly handles every planted data problem instead of absorbing it.",
            "Follows the stated computation rules exactly; report.md delivered.",
        ),
        task_md="# " + title + "\n\n" + prompt + "\n",
        rubric_text=rubric_md(task_id, "Figures match ground truth under the stated rules.", "Totals, top-N, and all anomaly classes named.", "Planted problems handled and disclosed.", "Rules followed; report.md delivered."),
        derived_params=derived,
        fixtures={csv_name: csv_text},
        smoke=[read(csv_name), py(solver_code), deliver("report.md", "Computed the report from " + csv_name + " under the stated rules.")],
        pinned_params={param_name: param_values[0], "top_n": 3},
    )


INVOICE_CSV = (
    "invoice_id,client,segment,amount,tax_rate,paid,due\n"
    "I1,Acme,retail,1000,0.07,yes,2026-09-01\n"
    "I2,Acme,retail,500,0.07,yes,2026-09-02\n"
    "I3,Baker,retail,800,0.07,no,2026-09-03\n"
    "I3,Baker,retail,800,0.07,no,2026-09-03\n"
    "I4,Baker,retail,-200,0.07,yes,2026-09-04\n"
    "I5,Corfu,retail,300,,no,2026-09-05\n"
    "I6,Delta,wholesale,2000,0.05,yes,2026-09-01\n"
    "I7,Delta,wholesale,1000,0.05,no,2026-09-02\n"
    "I8,Ember,wholesale,1200,0.05,yes,2026-09-03\n"
    "I9,Ember,wholesale,-300,0.05,yes,2026-09-04\n"
    "I10,Fox,wholesale,400,,no,2026-09-05\n"
    "I11,Golf,services,700,0,yes,2026-09-01\n"
    "I12,Golf,services,300,0,yes,2026-09-02\n"
    "I13,Hotel,services,950,0,no,2026-09-03\n"
    "I14,Hotel,services,100,,no,2026-09-04\n"
    "I15,India,services,200,0,yes,2026-09-05\n"
)

INVOICE_TRUTH = {
    "retail|2": {"top_clients": ["Acme", "Baker"], "total_revenue": 2400.0, "total_tax": 147.0},
    "retail|3": {"top_clients": ["Acme", "Baker", "Corfu"], "total_revenue": 2400.0, "total_tax": 147.0},
    "wholesale|2": {"top_clients": ["Delta", "Ember"], "total_revenue": 4300.0, "total_tax": 195.0},
    "wholesale|3": {"top_clients": ["Delta", "Ember", "Fox"], "total_revenue": 4300.0, "total_tax": 195.0},
    "services|2": {"top_clients": ["Hotel", "Golf"], "total_revenue": 2250.0, "total_tax": 0.0},
    "services|3": {"top_clients": ["Hotel", "Golf", "India"], "total_revenue": 2250.0, "total_tax": 0.0},
}

INVOICE_SOLVER = "\n".join(
    [
        "import csv",
        "from collections import defaultdict",
        "rows = list(csv.DictReader(open('invoices.csv')))",
        "seen = set()",
        "kept = []",
        "for r in rows:",
        "    if r['invoice_id'] in seen:",
        "        continue",
        "    seen.add(r['invoice_id'])",
        "    kept.append(r)",
        "billed = defaultdict(float)",
        "tax = 0.0",
        "for r in kept:",
        "    if r['segment'] != 'retail':",
        "        continue",
        "    amount = float(r['amount'])",
        "    billed[r['client']] += amount",
        "    if r['tax_rate'] != '':",
        "        tax += amount * float(r['tax_rate'])",
        "top = sorted(billed.items(), key=lambda kv: -kv[1])[:3]",
        "total = sum(billed.values())",
        "lines = ['Total revenue: ${:,.2f} billed for the retail segment.'.format(total), 'Total tax: ${:,.2f}.'.format(tax), '', 'Top clients by billed amount:']",
        "for name, val in top:",
        "    lines.append('- {}: ${:,.2f}'.format(name, val))",
        "lines.append('')",
        "lines.append('Data quality issues: one duplicate invoice row was removed before totals, one negative credit note was included as negative billed revenue, and rows with a missing tax rate were excluded from the tax total and flagged here for the billing owner to correct in the source system records.')",
        "open('report.md', 'w').write(chr(10).join(lines) + chr(10))",
        "print('wrote report.md')",
    ]
)

INVENTORY_CSV = (
    "sku,warehouse,expected,counted,unit_cost\n"
    "A1,A,100,90,10\n"
    "A2,A,50,50,20\n"
    "A3,A,200,150,4\n"
    "A4,A,80,95,10\n"
    "A5,A,60,,5\n"
    "A6,A,30,25,8\n"
    "B1,B,100,80,5\n"
    "B2,B,40,10,30\n"
    "B3,B,90,90,2\n"
    "B4,B,20,25,3\n"
    "B5,B,70,60,6\n"
    "C1,C,500,400,1\n"
    "C2,C,10,9,100\n"
    "C3,C,50,40,3\n"
)

INVENTORY_TRUTH = {
    "A|2": {"top_skus": ["A3", "A1"], "total_shrinkage_value": 340.0},
    "A|3": {"top_skus": ["A3", "A1", "A6"], "total_shrinkage_value": 340.0},
    "B|2": {"top_skus": ["B2", "B1"], "total_shrinkage_value": 1060.0},
    "B|3": {"top_skus": ["B2", "B1", "B5"], "total_shrinkage_value": 1060.0},
    "C|2": {"top_skus": ["C1", "C2"], "total_shrinkage_value": 230.0},
    "C|3": {"top_skus": ["C1", "C2", "C3"], "total_shrinkage_value": 230.0},
}

INVENTORY_SOLVER = "\n".join(
    [
        "import csv",
        "from collections import defaultdict",
        "rows = list(csv.DictReader(open('counts.csv')))",
        "values = {}",
        "total = 0.0",
        "for r in rows:",
        "    if r['warehouse'] != 'A' or r['counted'] == '':",
        "        continue",
        "    shrink = int(r['expected']) - int(r['counted'])",
        "    if shrink > 0:",
        "        val = shrink * float(r['unit_cost'])",
        "        values[r['sku']] = val",
        "        total += val",
        "top = sorted(values.items(), key=lambda kv: -kv[1])[:3]",
        "lines = ['Total shrinkage value: ${:,.2f} for warehouse A.'.format(total), '', 'Top SKUs by shrinkage value:']",
        "for name, val in top:",
        "    lines.append('- {}: ${:,.2f}'.format(name, val))",
        "lines.append('')",
        "lines.append('Data quality issues: one SKU shows an overage (counted above expected) and was not netted against shrinkage, and one SKU has a missing count and was excluded from the totals entirely. Both rows are flagged here so the warehouse team can recount those SKUs and correct the source records before the next cycle count begins.')",
        "open('report.md', 'w').write(chr(10).join(lines) + chr(10))",
        "print('wrote report.md')",
    ]
)

TRAFFIC_CSV = (
    "date,month,channel,sessions,conversions\n"
    "2026-08-01,aug,organic,1000,40\n"
    "2026-08-01,aug,organic,200,8\n"
    "2026-08-02,aug,paid,800,40\n"
    "2026-08-03,aug,social,500,10\n"
    "2026-08-04,aug,email,300,21\n"
    "2026-08-05,aug,paid,100,150\n"
    "2026-09-01,sep,organic,900,36\n"
    "2026-09-02,sep,paid,700,28\n"
    "2026-09-03,sep,social,600,30\n"
    "2026-09-04,sep,email,200,8\n"
    "2026-09-05,sep,social,100,5\n"
)

TRAFFIC_TRUTH = {
    "aug|2": {"top_channels": ["organic", "paid"], "total_conversions": 119.0, "overall_rate": 4.25},
    "aug|3": {"top_channels": ["organic", "paid", "email"], "total_conversions": 119.0, "overall_rate": 4.25},
    "sep|2": {"top_channels": ["organic", "social"], "total_conversions": 107.0, "overall_rate": 4.28},
    "sep|3": {"top_channels": ["organic", "social", "paid"], "total_conversions": 107.0, "overall_rate": 4.28},
}

TRAFFIC_SOLVER = "\n".join(
    [
        "import csv",
        "from collections import defaultdict",
        "rows = list(csv.DictReader(open('sessions.csv')))",
        "agg = defaultdict(lambda: [0, 0])",
        "invalid = 0",
        "for r in rows:",
        "    if r['month'] != 'aug':",
        "        continue",
        "    if int(r['conversions']) > int(r['sessions']):",
        "        invalid += 1",
        "        continue",
        "    agg[r['channel']][0] += int(r['sessions'])",
        "    agg[r['channel']][1] += int(r['conversions'])",
        "total_sessions = sum(v[0] for v in agg.values())",
        "total_conv = sum(v[1] for v in agg.values())",
        "rate = 100.0 * total_conv / total_sessions",
        "top = sorted(agg.items(), key=lambda kv: -kv[1][1])[:3]",
        "lines = ['Total conversions: {} for aug.'.format(total_conv), 'Overall conversion rate: {:.2f}%.'.format(rate), '', 'Top channels by conversions:']",
        "for name, v in top:",
        "    lines.append('- {}: {} conversions from {} sessions'.format(name, v[1], v[0]))",
        "lines.append('')",
        "lines.append('Data quality issues: duplicate date and channel rows from a tracking double-fire were summed rather than double counted as separate days, {} invalid row with conversions above sessions was excluded entirely, and social shows a gap with no rows in the second week of the month, which the analytics owner should confirm is a tracking outage rather than a real traffic drop.'.format(invalid))",
        "open('report.md', 'w').write(chr(10).join(lines) + chr(10))",
        "print('wrote report.md')",
    ]
)

TICKETS_CSV = (
    "id,queue,category,priority,resolved_h\n"
    "T1,support,login,high,2.0\n"
    "T2,support,login,normal,3.0\n"
    "T3,support,network,high,5.0\n"
    "T4,support,network,normal,-4.0\n"
    "T5,support,billing,low,1.5\n"
    "T6,support,,normal,2.5\n"
    "T7,support,network,normal,4.0\n"
    "T8,billing,refund,normal,2.0\n"
    "T9,billing,refund,high,2.0\n"
    "T10,billing,invoice,normal,6.0\n"
    "T11,billing,invoice,low,1.0\n"
    "T12,billing,chargeback,high,-1.0\n"
    "T13,billing,,normal,3.0\n"
)

TICKETS_TRUTH = {
    "support|2": {"top_categories": ["network", "login"], "total_tickets": 7.0},
    "support|3": {"top_categories": ["network", "login", "unknown"], "total_tickets": 7.0},
    "billing|2": {"top_categories": ["invoice", "refund"], "total_tickets": 6.0},
    "billing|3": {"top_categories": ["invoice", "refund", "unknown"], "total_tickets": 6.0},
}

TICKETS_SOLVER = "\n".join(
    [
        "import csv",
        "from collections import defaultdict",
        "rows = list(csv.DictReader(open('tickets.csv')))",
        "hours = defaultdict(float)",
        "valid = 0",
        "for r in rows:",
        "    if r['queue'] != 'support':",
        "        continue",
        "    valid += 1",
        "    if float(r['resolved_h']) < 0:",
        "        continue",
        "    cat = r['category'] if r['category'] else 'unknown'",
        "    hours[cat] += float(r['resolved_h'])",
        "top = sorted(hours.items(), key=lambda kv: -kv[1])[:3]",
        "lines = ['Total tickets: {} in the support queue (including flagged rows).'.format(valid), '', 'Top categories by total resolution hours:']",
        "for name, val in top:",
        "    lines.append('- {}: {:.1f} hours'.format(name, val))",
        "lines.append('')",
        "lines.append('Data quality issues: one ticket carries a negative resolution time, which is a data error; it was excluded from the hour totals and flagged. One ticket has a missing category and was bucketed as unknown rather than dropped, so queue volume stays honest while the taxonomy gap is visible to the support operations owner for cleanup.')",
        "open('report.md', 'w').write(chr(10).join(lines) + chr(10))",
        "print('wrote report.md')",
    ]
)


def build_extra_data_family() -> None:
    _metric_task(
        "sprint-data-004", "invoices.csv", INVOICE_CSV, "segment", ["retail", "wholesale", "services"],
        INVOICE_TRUTH, "top_clients", "total revenue", "total_revenue", ["duplicate", "credit", "missing"],
        "Analyze invoices.csv in the workspace. Rules: deduplicate by invoice_id keeping the first row; negative amounts are credit notes and count as negative revenue; rows with a missing tax_rate are excluded from the tax total only. For the {{segment}} segment, write report.md with the total revenue billed, the total tax, the top {{top_n}} clients by billed amount, and the data quality issues (duplicate, credit, missing tax).",
        INVOICE_SOLVER, "Invoice summary",
        extra_numeric=("total tax", "total_tax", 1.5),
    )
    _metric_task(
        "sprint-data-005", "counts.csv", INVENTORY_CSV, "warehouse", ["A", "B", "C"],
        INVENTORY_TRUTH, "top_skus", "total shrinkage value", "total_shrinkage_value", ["overage", "missing"],
        "Analyze counts.csv in the workspace. Shrinkage is expected minus counted when positive, valued at unit_cost. Overages (counted above expected) are flagged, never netted. Rows with a missing count are excluded. For warehouse {{warehouse}}, write report.md with the total shrinkage value, the top {{top_n}} SKUs by shrinkage value, and the data quality issues (overage, missing count).",
        INVENTORY_SOLVER, "Inventory shrinkage",
    )
    _metric_task(
        "sprint-data-006", "sessions.csv", TRAFFIC_CSV, "month", ["aug", "sep"],
        TRAFFIC_TRUTH, "top_channels", "total conversions", "total_conversions", ["duplicate", "gap", "invalid"],
        "Analyze sessions.csv in the workspace. Rules: rows sharing a date and channel are a tracking double-fire and must be summed; rows with conversions above sessions are invalid and excluded. For the month {{month}}, write report.md with the total conversions, the overall conversion rate as a percent, the top {{top_n}} channels by conversions, and the data quality issues (duplicate rows, invalid rows, channel gaps).",
        TRAFFIC_SOLVER, "Traffic analysis",
        extra_numeric=("overall conversion rate", "overall_rate", 0.1),
    )
    _metric_task(
        "sprint-data-007", "tickets.csv", TICKETS_CSV, "queue", ["support", "billing"],
        TICKETS_TRUTH, "top_categories", "total tickets", "total_tickets", ["negative", "missing"],
        "Analyze tickets.csv in the workspace. Rules: tickets with a negative resolved_h are data errors and are excluded from hour totals but still counted in total tickets; a missing category is bucketed as unknown. For the {{queue}} queue, write report.md with the total tickets, the top {{top_n}} categories by total resolution hours, and the data quality issues (negative times, missing categories).",
        TICKETS_SOLVER, "Support ticket analysis",
    )


# -- Family S-04: planning from quotes (docs/plan/02 S-04) -----------------------

QUOTE_TASKS: list[dict[str, Any]] = [
    {"id": "sprint-planning-001", "service": "lawn care", "foreign": ["SparkleCo", "CoolAir", "FlowRight"],
     "biz": [("GreenEdge", {"north_side": 45, "downtown": 55, "suburbs": 40}, 4, 4.8), ("TurfPro", {"north_side": 50, "downtown": 50, "suburbs": 50}, 2, 4.6), ("YardWorks", {"north_side": 60, "downtown": 65, "suburbs": 55}, 24, 4.9), ("SoloMow", {"north_side": 35, "downtown": 45, "suburbs": 30}, 48, 4.2)],
     "truth": {"north_side": ("GreenEdge", 45, "TurfPro"), "downtown": ("TurfPro", 50, "TurfPro"), "suburbs": ("GreenEdge", 40, "TurfPro")}},
    {"id": "sprint-planning-002", "service": "house cleaning", "foreign": ["GreenEdge", "FrostLine", "PipePro"],
     "biz": [("SparkleCo", {"north_side": 120, "downtown": 140, "suburbs": 110}, 6, 4.7), ("MaidDay", {"north_side": 100, "downtown": 130, "suburbs": 95}, 12, 4.4), ("PureHome", {"north_side": 150, "downtown": 150, "suburbs": 140}, 3, 4.9), ("BrightNest", {"north_side": 110, "downtown": 125, "suburbs": 105}, 24, 4.6)],
     "truth": {"north_side": ("BrightNest", 110, "PureHome"), "downtown": ("BrightNest", 125, "PureHome"), "suburbs": ("BrightNest", 105, "PureHome")}},
    {"id": "sprint-planning-003", "service": "HVAC repair", "foreign": ["MaidDay", "DrainKing", "SwiftMove"],
     "biz": [("CoolAir", {"north_side": 89, "downtown": 99, "suburbs": 79}, 2, 4.8), ("FrostLine", {"north_side": 95, "downtown": 95, "suburbs": 95}, 5, 4.5), ("AirMedic", {"north_side": 120, "downtown": 110, "suburbs": 105}, 1, 4.3), ("ClimatePro", {"north_side": 105, "downtown": 115, "suburbs": 100}, 8, 4.9)],
     "truth": {"north_side": ("CoolAir", 89, "AirMedic"), "downtown": ("FrostLine", 95, "AirMedic"), "suburbs": ("CoolAir", 79, "AirMedic")}},
    {"id": "sprint-planning-004", "service": "plumbing repair", "foreign": ["YardWorks", "PureHome", "CityMove"],
     "biz": [("FlowRight", {"north_side": 75, "downtown": 85, "suburbs": 70}, 3, 4.7), ("PipePro", {"north_side": 80, "downtown": 80, "suburbs": 80}, 6, 4.6), ("DrainKing", {"north_side": 65, "downtown": 75, "suburbs": 60}, 24, 4.1), ("AquaFix", {"north_side": 90, "downtown": 95, "suburbs": 85}, 2, 4.8)],
     "truth": {"north_side": ("FlowRight", 75, "AquaFix"), "downtown": ("PipePro", 80, "AquaFix"), "suburbs": ("FlowRight", 70, "AquaFix")}},
    {"id": "sprint-planning-005", "service": "moving services", "foreign": ["TurfPro", "SparkleCo", "AirMedic"],
     "biz": [("SwiftMove", {"north_side": 600, "downtown": 700, "suburbs": 550}, 12, 4.7), ("BoxAndGo", {"north_side": 550, "downtown": 650, "suburbs": 500}, 24, 4.3), ("HeavyLifters", {"north_side": 800, "downtown": 850, "suburbs": 750}, 6, 4.9), ("CityMove", {"north_side": 650, "downtown": 600, "suburbs": 580}, 10, 4.6)],
     "truth": {"north_side": ("SwiftMove", 600, "HeavyLifters"), "downtown": ("CityMove", 600, "HeavyLifters"), "suburbs": ("SwiftMove", 550, "HeavyLifters")}},
]


def build_quote_family() -> None:
    for spec in QUOTE_TASKS:
        names = [b[0] for b in spec["biz"]]
        fixture = {
            "quotes.json": json.dumps(
                {"businesses": [{"name": n, "prices": p, "response_hours": r, "rating": rt} for n, p, r, rt in spec["biz"]]},
                indent=2,
            )
        }
        derived = [
            {
                "name": "expected",
                "key": "{{zone}}",
                "map": {zone: {"cheapest": t[0], "cheapest_price": t[1], "fastest": t[2]} for zone, t in spec["truth"].items()},
            }
        ]
        checks = [
            {"id": "businesses_named", "check": "regex_all", "params": {"patterns": names}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "recommendation_correct", "check": "regex_all", "params": {"patterns": ["{{expected.cheapest}}", "{{expected.fastest}}"]}, "caps": {"correctness": 20}},
            {"id": "price_correct", "check": "numeric_within", "params": {"label": "recommended price", "value": "{{expected.cheapest_price}}", "tolerance": 0.5}, "caps": {"correctness": 15}},
            {"id": "no_invented_businesses", "check": "banned_phrases", "params": {"phrases": spec["foreign"]}, "caps": {"correctness": 15}},
            {"id": "plan_length", "check": "word_count", "params": {"min": 80, "max": 300}, "caps": {"instruction_adherence": 5}},
        ]
        solver_code = "\n".join(
            [
                "import json",
                "data = json.load(open('quotes.json'))['businesses']",
                "zone = 'north_side'",
                "lines = ['Quotes comparison for " + spec["service"] + " (zone: north_side, urgency handled by response time):', '']",
                "for b in data:",
                "    lines.append('- {}: ${} in this zone, responds in {}h, rated {}'.format(b['name'], b['prices'][zone], b['response_hours'], b['rating']))",
                "eligible = [b for b in data if b['rating'] >= 4.5]",
                "best = min(eligible, key=lambda b: b['prices'][zone])",
                "fastest = min(data, key=lambda b: b['response_hours'])",
                "lines.append('')",
                "lines.append('Recommendation: Book {} for this job. Recommended price: ${}. It is the lowest price among businesses rated 4.5 or higher in this zone, which keeps quality risk low without paying the premium tier. If the schedule slips, {} is the fastest responder at {} hours, so keep their number as the backup option and confirm the booking window a day ahead by phone.'.format(best['name'], best['prices'][zone], fastest['name'], fastest['response_hours']))",
                "open('plan.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('wrote plan.md')",
            ]
        )
        write_task(
            spec["id"],
            1,
            "planning",
            "Compare the " + spec["service"] + " quotes in quotes.json for the {{zone}} zone (urgency: {{urgency}}). Write plan.md listing every business with its price for the zone, response time, and rating. Recommend the lowest-priced business rated 4.5 or higher (print 'Recommended price: $X' for it) and also name the fastest responder overall as the backup.",
            {
                "zone": {"type": "enum", "values": ["north_side", "downtown", "suburbs"]},
                "urgency": {"type": "enum", "values": ["standard", "soon", "urgent"]},
            },
            checks,
            rubric_list=rubric(
                "Recommendation matches the rating-filtered lowest price for the drawn zone; fastest responder named correctly.",
                "All businesses with zone price, response time, and rating, plus recommendation and backup.",
                "Applies the rating filter instead of picking the raw cheapest quote.",
                "Follows the stated selection rule; plan.md delivered.",
            ),
            task_md="# Quotes comparison — " + spec["service"] + "\n\nCompare the quotes in `quotes.json` for the drawn zone. Recommend the lowest-priced business rated 4.5 or higher, print its price as 'Recommended price: $X', and name the fastest responder as backup. Write `plan.md` and deliver it.\n",
            rubric_text=rubric_md(spec["id"], "Selection rule applied correctly for the drawn zone.", "All businesses plus recommendation and backup.", "Rating filter applied, not raw cheapest.", "plan.md delivered in the required format."),
            derived_params=derived,
            fixtures=fixture,
            smoke=[read("quotes.json"), py(solver_code), deliver("plan.md", "Compared quotes and wrote plan.md with the rule-based recommendation.")],
            pinned_params={"zone": "north_side", "urgency": "standard"},
        )


# -- Family S-05: spec extraction from frozen HTML (docs/plan/02 S-05) -----------

WEB_TASKS: list[dict[str, Any]] = [
    {"id": "sprint-web-001", "product": "robot vacuums", "spec_label": "Runtime",
     "models": [("RoboVac X1", 299, "120 min"), ("DustBot Pro", 449, "180 min"), ("CleanSweep Mini", 149, "90 min"), ("NaviMop S2", 549, "240 min")],
     "focus": {"RoboVac": ("RoboVac X1", "299", "120 min"), "DustBot": ("DustBot Pro", "449", "180 min"), "NaviMop": ("NaviMop S2", "549", "240 min")}},
    {"id": "sprint-web-002", "product": "air purifiers", "spec_label": "Coverage",
     "models": [("PureAir 200", 199, "350 sq ft"), ("AeroClean Max", 329, "600 sq ft"), ("BreezePod", 99, "150 sq ft"), ("IonShield Pro", 459, "900 sq ft")],
     "focus": {"PureAir": ("PureAir 200", "199", "350 sq ft"), "AeroClean": ("AeroClean Max", "329", "600 sq ft"), "IonShield": ("IonShield Pro", "459", "900 sq ft")}},
    {"id": "sprint-web-003", "product": "espresso machines", "spec_label": "Pump pressure",
     "models": [("BaristaOne", 349, "15 bar"), ("EspressoLab Pro", 799, "19 bar"), ("CremaMini", 129, "12 bar"), ("SteamCraft", 249, "20 bar")],
     "focus": {"BaristaOne": ("BaristaOne", "349", "15 bar"), "EspressoLab": ("EspressoLab Pro", "799", "19 bar"), "SteamCraft": ("SteamCraft", "249", "20 bar")}},
    {"id": "sprint-web-004", "product": "cordless drills", "spec_label": "Max speed",
     "models": [("DrillDriver 18V", 89, "1300 RPM"), ("TorqueMax Pro", 159, "2100 RPM"), ("CompactDrill 12V", 59, "900 RPM"), ("HammerPro X", 199, "2600 RPM")],
     "focus": {"DrillDriver": ("DrillDriver 18V", "89", "1300 RPM"), "TorqueMax": ("TorqueMax Pro", "159", "2100 RPM"), "HammerPro": ("HammerPro X", "199", "2600 RPM")}},
    {"id": "sprint-web-005", "product": "laptops", "spec_label": "Memory",
     "models": [("SlimBook 14", 749, "16 GB"), ("PowerStation 16", 1299, "32 GB"), ("TravelLite 13", 549, "8 GB"), ("CreatorMax 15", 1899, "64 GB")],
     "focus": {"SlimBook": ("SlimBook 14", "749", "16 GB"), "PowerStation": ("PowerStation 16", "1299", "32 GB"), "CreatorMax": ("CreatorMax 15", "1899", "64 GB")}},
]


def build_web_family() -> None:
    for spec in WEB_TASKS:
        rows_html = "\n".join(
            "<tr><td>" + name + "</td><td>$" + str(price) + "</td><td>" + sval + "</td></tr>" for name, price, sval in spec["models"]
        )
        html = (
            "<html><head><title>" + spec["product"] + " specs</title></head><body>\n<h1>" + spec["product"] + "</h1>\n<table>\n"
            "<tr><th>Model</th><th>Price</th><th>" + spec["spec_label"] + "</th></tr>\n" + rows_html + "\n</table>\n</body></html>\n"
        )
        derived = [
            {
                "name": "expected",
                "key": "{{brand_focus}}",
                "map": {brand: {"model": v[0], "price": v[1], "spec": v[2]} for brand, v in spec["focus"].items()},
            }
        ]
        checks = [
            {"id": "csv_shape", "check": "csv_valid", "params": {"columns": ["model", "price", "spec", "source"], "min_rows": 4}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "focus_row_values", "check": "regex_all", "params": {"patterns": ["{{expected.model}}", "{{expected.price}}", "{{expected.spec}}"]}, "caps": {"correctness": 20}},
            {"id": "all_models_present", "check": "regex_all", "params": {"patterns": [m[0] for m in spec["models"]]}, "caps": {"completeness": 15}},
        ]
        solver_code = "\n".join(
            [
                "import re",
                "html = open('specs.html').read()",
                "rows = re.findall(r'<tr><td>(.*?)</td><td>\\$(.*?)</td><td>(.*?)</td></tr>', html)",
                "lines = ['model,price,spec,source']",
                "for name, price, sval in rows:",
                "    lines.append('{},\"${}\",{},specs.html'.format(name, price, sval))",
                "open('specs.csv', 'w').write(chr(10).join(lines) + chr(10))",
                "print('extracted', len(rows), 'models')",
            ]
        )
        write_task(
            spec["id"],
            1,
            "web_research",
            "Extract the " + spec["product"] + " comparison table from specs.html in the workspace into specs.csv with columns model, price, spec, source (source is the fixture filename for every row). Brand focus for this run: {{brand_focus}}. Output format: {{output_format}}.",
            {
                "brand_focus": {"type": "enum", "values": list(spec["focus"].keys())},
                "output_format": {"type": "enum", "values": ["csv", "spreadsheet-ready csv", "plain csv"]},
            },
            checks,
            rubric_list=rubric(
                "Every extracted value matches the source table exactly, including the focus brand row.",
                "All models extracted with price, spec, and source columns.",
                "Parses the table structure instead of copying rendered text blindly.",
                "Exact columns and source attribution; specs.csv delivered.",
            ),
            task_md="# Spec extraction — " + spec["product"] + "\n\nExtract the comparison table from `specs.html` into `specs.csv` with columns model, price, spec, source. Deliver `specs.csv`.\n",
            rubric_text=rubric_md(spec["id"], "Values match the source table exactly.", "All models with all columns.", "Structure parsed correctly.", "Columns and source respected; specs.csv delivered."),
            derived_params=derived,
            fixtures={"specs.html": html},
            smoke=[read("specs.html"), py(solver_code), deliver("specs.csv", "Extracted the full table from specs.html into specs.csv.")],
            pinned_params={"brand_focus": list(spec["focus"].keys())[0], "output_format": "csv"},
        )


# -- Research briefs from frozen sources -----------------------------------------

BRIEF_TASKS: list[dict[str, Any]] = [
    {"id": "sprint-research-001", "topic": "US pet insurance market", "size": "5.2 billion", "growth": "11%",
     "players": [("Trupanion", 28), ("Healthy Paws", 18), ("Nationwide Pet", 15)], "sources": ["NAIC pet insurance report", "AVMA pet ownership statistics"]},
    {"id": "sprint-research-002", "topic": "US home cleaning services market", "size": "18.5 billion", "growth": "6%",
     "players": [("Molly Maid", 9), ("Merry Maids", 8), ("The Cleaning Authority", 5)], "sources": ["IBISWorld cleaning services report", "BLS occupational outlook"]},
    {"id": "sprint-research-003", "topic": "US public EV charging market", "size": "12.4 billion", "growth": "23%",
     "players": [("ChargePoint", 31), ("Tesla Supercharger", 28), ("Blink", 9)], "sources": ["DOE AFDC station counts", "NEVI program filings"]},
    {"id": "sprint-research-004", "topic": "US wedding venues market", "size": "8.7 billion", "growth": "4%",
     "players": [("Zola Venues", 12), ("WeddingWire", 10), ("Independent venues", 58)], "sources": ["The Knot real weddings study", "IBISWorld wedding services report"]},
    {"id": "sprint-research-005", "topic": "US meal kit market", "size": "6.3 billion", "growth": "5%",
     "players": [("HelloFresh", 42), ("Blue Apron", 18), ("Home Chef", 12)], "sources": ["company earnings reports", "USDA food expenditure data"]},
]


def build_brief_family() -> None:
    for spec in BRIEF_TASKS:
        fixture = {
            "sources.json": json.dumps(
                {
                    "topic": spec["topic"],
                    "market_size": spec["size"],
                    "growth": spec["growth"],
                    "players": [{"name": n, "share": s} for n, s in spec["players"]],
                    "sources": spec["sources"],
                },
                indent=2,
            )
        }
        checks = [
            {"id": "key_figures", "check": "regex_all", "params": {"patterns": [spec["size"], spec["growth"]]}, "caps": {"correctness": 25}},
            {"id": "players_named", "check": "regex_all", "params": {"patterns": [p[0] for p in spec["players"]]}, "caps": {"correctness": 20, "completeness": 15}},
            {"id": "sources_cited", "check": "regex_all", "params": {"patterns": spec["sources"]}, "caps": {"completeness": 15}},
            {"id": "no_filler", "check": "banned_phrases", "params": {"phrases": ["lorem", "as an ai"]}, "caps": {"instruction_adherence": 5}},
            {"id": "brief_length", "check": "word_count", "params": {"min": 150, "max": 350}, "caps": {"instruction_adherence": 5}},
        ]
        solver_code = "\n".join(
            [
                "import json",
                "d = json.load(open('sources.json'))",
                "lines = ['# ' + d['topic'] + ' — brief', '']",
                "lines.append('The ' + d['topic'] + ' is sized at $' + d['market_size'] + ' and growing at ' + d['growth'] + ' per year according to the frozen source pack. Growth at that rate doubles the market in well under a decade, which makes share won today compound in value for whoever holds it.')",
                "lines.append('')",
                "lines.append('Competitive landscape:')",
                "for p in d['players']:",
                "    lines.append('- {} holds a {}% share.'.format(p['name'], p['share']))",
                "lines.append('')",
                "lines.append('The leader\\'s position is real but not unassailable: the top player holds under half the market, and the long tail of smaller rivals keeps pricing honest. For an operator, the practical read is that distribution and retention decide outcomes more than product novelty at this stage of the market. For an investor, the question is whether the growth rate survives contact with household budgets; the sources below are the ones to interrogate first.')",
                "lines.append('')",
                "lines.append('Sources: ' + '; '.join(d['sources']) + '.')",
                "open('brief.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('wrote brief.md')",
            ]
        )
        write_task(
            spec["id"],
            1,
            "research_synthesis",
            "Using only sources.json in the workspace, write a brief on the " + spec["topic"] + " for a {{audience}}. Angle: {{angle}}. The brief must state the market size and growth rate, name every player with its share, and cite both sources by name. 150-350 words. Write brief.md and deliver it.",
            {
                "audience": {"type": "enum", "values": ["investor", "operator", "partner"]},
                "angle": {"type": "enum", "values": ["opportunity", "competition", "pricing"]},
            },
            checks,
            rubric_list=rubric(
                "Market size, growth, players, and shares all match sources.json exactly.",
                "Figures, all players, and both sources cited, within the word budget.",
                "Stays inside the frozen sources instead of inventing outside facts.",
                "Word budget and citations respected; brief.md delivered.",
            ),
            task_md="# Market brief — " + spec["topic"] + "\n\nUsing only `sources.json`, write a 150-350 word brief: market size, growth rate, every player with share, both sources cited by name. Deliver `brief.md`.\n",
            rubric_text=rubric_md(spec["id"], "Figures and shares match sources.json.", "All required elements inside the word budget.", "No invented facts beyond the sources.", "Citations and length respected; brief.md delivered."),
            fixtures=fixture,
            smoke=[read("sources.json"), py(solver_code), deliver("brief.md", "Wrote the market brief from sources.json.")],
            pinned_params={"audience": "investor", "angle": "opportunity"},
        )


# -- Trip-lite: one-day offsite packages ------------------------------------------

TRIP_TASKS: list[dict[str, Any]] = [
    {"id": "sprint-planning-006", "city": "Austin",
     "venues": [("Ranch House", 40), ("Downtown Loft", 65), ("Lakeside Pavilion", 90)],
     "activities": [("BBQ class", 25), ("Live music session", 30), ("Kayak tour", 45)],
     "meals": [("Food truck", 18), ("Taco bar", 24), ("Steakhouse", 55)],
     "packages": {"basic": (0, 0, 0), "plus": (1, 1, 1), "premium": (2, 2, 2)}},
    {"id": "sprint-planning-007", "city": "Denver",
     "venues": [("Mountain Lodge", 55), ("City Hub", 70), ("Garden Terrace", 95)],
     "activities": [("Brewery tour", 28), ("Escape room", 32), ("Hiking guide", 35)],
     "meals": [("Deli spread", 16), ("Bistro lunch", 28), ("Farm dinner", 60)],
     "packages": {"basic": (0, 0, 0), "plus": (1, 1, 1), "premium": (2, 2, 2)}},
    {"id": "sprint-planning-008", "city": "Nashville",
     "venues": [("Honky Tonk Hall", 45), ("Riverfront Space", 75), ("Historic Mansion", 110)],
     "activities": [("Distillery tour", 30), ("Songwriting session", 40), ("River cruise", 50)],
     "meals": [("Hot chicken bar", 20), ("Southern buffet", 26), ("Fine dining", 65)],
     "packages": {"basic": (0, 0, 0), "plus": (1, 1, 1), "premium": (2, 2, 2)}},
]


def build_trip_family() -> None:
    for spec in TRIP_TASKS:
        fixture = {
            "options.json": json.dumps(
                {
                    "venues": [{"name": n, "price_pp": p} for n, p in spec["venues"]],
                    "activities": [{"name": n, "price_pp": p} for n, p in spec["activities"]],
                    "meals": [{"name": n, "price_pp": p} for n, p in spec["meals"]],
                },
                indent=2,
            )
        }
        truth: dict[str, dict[str, Any]] = {}
        for pkg, (vi, ai, mi) in spec["packages"].items():
            picks = [spec["venues"][vi][0], spec["activities"][ai][0], spec["meals"][mi][0]]
            pp = spec["venues"][vi][1] + spec["activities"][ai][1] + spec["meals"][mi][1]
            for team in (8, 12, 20):
                truth[pkg + "|" + str(team)] = {"picks": picks, "total": float(pp * team)}
        derived = [{"name": "expected", "key": "{{package}}|{{team_size}}", "map": truth}]
        checks = [
            {"id": "picks_named", "check": "regex_all", "params": {"patterns": "{{expected.picks}}"}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "total_correct", "check": "numeric_within", "params": {"label": "total for the team", "value": "{{expected.total}}", "tolerance": 1.0}, "caps": {"correctness": 20}},
            {"id": "plan_length", "check": "word_count", "params": {"min": 60, "max": 300}, "caps": {"instruction_adherence": 5}},
        ]
        solver_code = "\n".join(
            [
                "import json",
                "d = json.load(open('options.json'))",
                "venue = d['venues'][1]",
                "activity = d['activities'][1]",
                "meal = d['meals'][1]",
                "team = 12",
                "pp = venue['price_pp'] + activity['price_pp'] + meal['price_pp']",
                "total = pp * team",
                "lines = ['One-day team offsite in " + spec["city"] + " (plus package, 12 people):', '']",
                "lines.append('- Venue: {} at ${} per person'.format(venue['name'], venue['price_pp']))",
                "lines.append('- Activity: {} at ${} per person'.format(activity['name'], activity['price_pp']))",
                "lines.append('- Meal: {} at ${} per person'.format(meal['name'], meal['price_pp']))",
                "lines.append('')",
                "lines.append('Per-person subtotal: ${}. Total for the team: ${}. The plus package balances a proper venue with a memorable activity without paying premium-tier prices; book the venue first since it is the only piece with real capacity risk, then lock the activity and meal once headcount is confirmed a week out.'.format(pp, total))",
                "open('plan.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('wrote plan.md')",
            ]
        )
        write_task(
            spec["id"],
            1,
            "planning",
            "Plan a one-day team offsite in " + spec["city"] + " using options.json. The {{package}} package picks, in each category sorted by price, the option at the package tier (basic = cheapest, plus = middle, premium = priciest). For a team of {{team_size}}, write plan.md naming the venue, activity, and meal picks with per-person prices, and print the team total as 'Total for the team: $X'.",
            {
                "package": {"type": "enum", "values": ["basic", "plus", "premium"]},
                "team_size": {"type": "enum", "values": [8, 12, 20]},
            },
            checks,
            rubric_list=rubric(
                "Picks match the package tier rule and the team total is arithmetically exact.",
                "Venue, activity, meal, per-person prices, and total all present.",
                "Applies the tier rule per category instead of mixing tiers.",
                "Total printed in the required format; plan.md delivered.",
            ),
            task_md="# One-day offsite — " + spec["city"] + "\n\nUse `options.json`. Package tiers pick per category by price rank (basic cheapest, plus middle, premium priciest). Print the team total as 'Total for the team: $X'. Deliver `plan.md`.\n",
            rubric_text=rubric_md(spec["id"], "Tier rule and total exact.", "All picks, prices, and total present.", "Tier rule applied per category.", "plan.md delivered."),
            derived_params=derived,
            fixtures=fixture,
            smoke=[read("options.json"), py(solver_code), deliver("plan.md", "Planned the plus-package offsite for 12 and wrote plan.md.")],
            pinned_params={"package": "plus", "team_size": 12},
        )


# -- Marathon family M-01: teardowns (docs/plan/14 section 4) ---------------------

TEARDOWNS: list[dict[str, Any]] = [
    {"id": "marathon-research-001", "company": "regional HVAC chains", "market": "US HVAC services", "size": "210 billion", "growth": "5%",
     "names": ["Apex Heating", "CoolPro Services", "AirFlow Group", "ComfortFirst", "Polar Mechanical"]},
    {"id": "marathon-research-002", "company": "pet insurance challengers", "market": "US pet insurance", "size": "5.2 billion", "growth": "11%",
     "names": ["Trupanion", "Healthy Paws", "Embrace", "Spot Insurance", "Figo"]},
    {"id": "marathon-research-003", "company": "neobanks for contractors", "market": "US small-business banking", "size": "38 billion", "growth": "9%",
     "names": ["Mercury", "Relay", "NorthOne", "Novo", "Lili"]},
    {"id": "marathon-research-004", "company": "express car wash rollups", "market": "US car wash services", "size": "16 billion", "growth": "4%",
     "names": ["Mister Car Wash", "Zips Car Wash", "Quick Quack", "Tommy's Express", "WhiteWater Express"]},
    {"id": "marathon-research-005", "company": "hybrid-work coworking operators", "market": "US flexible office", "size": "11 billion", "growth": "7%",
     "names": ["Industrious", "Convene", "Expansive", "Spaces", "Knotel"]},
]


def build_teardown_family() -> None:
    for spec in TEARDOWNS:
        incumbents = [
            {"name": n, "positioning": "premium full-service positioning", "price_tier": "high", "strength": "brand trust and service network density", "weakness": "slow digital experience"}
            for n in spec["names"]
        ]
        fixture = {
            "market.json": json.dumps(
                {"company_focus": spec["company"], "market": spec["market"], "market_size": spec["size"], "growth": spec["growth"], "incumbents": incumbents, "barriers": ["customer acquisition cost", "licensed labor scarcity", "incumbent brand trust"]},
                indent=2,
            )
        }
        checks = [
            {"id": "incumbents_named", "check": "regex_all", "params": {"patterns": spec["names"]}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "market_figures", "check": "regex_all", "params": {"patterns": [spec["size"], spec["growth"]]}, "caps": {"correctness": 20}},
            {"id": "verdict_present", "check": "regex_all", "params": {"patterns": ["Recommendation:"]}, "caps": {"completeness": 15}},
            {"id": "teardown_length", "check": "word_count", "params": {"min": 1200, "max": 1800}, "caps": {"instruction_adherence": 5}},
        ]
        solver_code = "\n".join(
            [
                "import json",
                "d = json.load(open('market.json'))",
                "lines = ['# Teardown: ' + d['company_focus'] + ' entering the ' + d['market'], '']",
                "lines.append('## Market')",
                "lines.append('The ' + d['market'] + ' is a $' + d['market_size'] + ' market growing at ' + d['growth'] + ' per year. A market of this size with mid-single-digit or better growth supports multiple scaled players, but growth alone does not create an opening: the structure of incumbent advantage decides whether entry is attractive. The sections below examine each incumbent, the barriers that protect them, the risks that cut the other way, and a final recommendation.')",
                "lines.append('')",
                "lines.append('## Incumbents')",
                "for inc in d['incumbents']:",
                "    lines.append('### ' + inc['name'])",
                "    lines.append(inc['name'] + ' competes with ' + inc['positioning'] + ' at a ' + inc['price_tier'] + ' price tier. Its core strength is ' + inc['strength'] + ', which compounds: customers acquired through that strength tend to stay, refer, and lower the marginal cost of the next customer. Its core weakness is a ' + inc['weakness'] + ', and that weakness is structural rather than accidental, because fixing it would require spending against the very asset that makes the company profitable today. For a challenger, the implication is to attack the weakness directly with a focused offer rather than matching the incumbent across the full line, where its scale advantages in procurement, brand, and distribution would neutralize a head-on assault within a few planning cycles.')",
                "    lines.append('Watch how ' + inc['name'] + ' responds in the first two quarters after entry: a price response signals that the wedge is landing on customers the incumbent actually values, while silence usually means the entrant is serving a segment the incumbent has already decided to cede. Either response is information. The mistake would be reading silence as safety and widening the offer before the unit economics of the wedge are proven at small scale with real retention data.')",
                "    lines.append('')",
                "lines.append('## Barriers')",
                "for b in d['barriers']:",
                "    lines.append('- ' + b + ': real but surmountable with a narrow wedge and patience; the barrier binds generalists harder than specialists.')",
                "lines.append('')",
                "lines.append('## Risks')",
                "lines.append('The three risks that matter most are a price response from the largest incumbent, slower-than-modeled customer acquisition in the first two years, and execution drift toward the generalist middle where the incumbents are strongest. Each risk is manageable with a narrow initial wedge, a conservative hiring plan, and pricing that never depends on matching incumbent discounts for longer than a single quarter of runway.')",
                "lines.append('')",
                "lines.append('## Verdict')",
                "lines.append('Recommendation: GO, conditionally. Enter with the narrow wedge, hold the price line, and review against the acquisition milestones after two quarters before widening the offer.')",
                "open('teardown.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('wrote teardown.md')",
            ]
        )
        write_task(
            spec["id"],
            2,
            "research_synthesis",
            "Write a market teardown for " + spec["company"] + " entering the " + spec["market"] + ", using only market.json in the workspace. Length 1200-1800 words. Cover the market (size, growth), every incumbent by name with positioning, the barriers, the risks, and end with a verdict paragraph starting 'Recommendation:'. Audience: {{audience}}; depth: {{depth}}.",
            {
                "audience": {"type": "enum", "values": ["investor", "operator", "board"]},
                "depth": {"type": "enum", "values": ["standard", "deep", "executive"]},
            },
            checks,
            rubric_list=rubric(
                "Incumbents, figures, and barriers all match market.json; verdict argued from the evidence.",
                "Market, all incumbents, barriers, risks, and verdict, inside the word budget.",
                "Reconciles conflicting signals in the source pack instead of cherry-picking.",
                "Structure and verdict format as specified; teardown.md delivered.",
            ),
            task_md="# Teardown — " + spec["company"] + "\n\nUsing only `market.json`, write a 1200-1800 word teardown ending with a verdict paragraph starting 'Recommendation:'. Deliver `teardown.md`.\n",
            rubric_text=rubric_md(spec["id"], "All facts match market.json.", "All sections inside the word budget.", "Conflicts reconciled.", "teardown.md delivered."),
            fixtures=fixture,
            smoke=[read("market.json"), py(solver_code), deliver("teardown.md", "Wrote the full teardown from market.json.")],
            pinned_params={"audience": "investor", "depth": "standard"},
        )


# -- Marathon family M-03: trip planning (docs/plan/14 section 6) ------------------

TRAVEL_TASKS: list[dict[str, Any]] = [
    {"id": "marathon-planning-001", "city": "Austin", "venue": "SXSW",
     "flights": [("SkyAir", 240, "flights.example/sky240"), ("JetWest", 310, "flights.example/jw310"), ("BudgetAir", 190, "flights.example/ba190")],
     "hotels": [("Downtown Suites", 180, "mid", "hotels.example/ds180"), ("Grand Austin", 260, "upscale", "hotels.example/ga260"), ("Airport Inn", 120, "mid", "hotels.example/ai120")]},
    {"id": "marathon-planning-002", "city": "Chicago", "venue": "McCormick Place",
     "flights": [("SkyAir", 210, "flights.example/sky210"), ("United Skies", 265, "flights.example/us265"), ("BudgetAir", 175, "flights.example/ba175")],
     "hotels": [("Lakeside Hotel", 210, "mid", "hotels.example/lh210"), ("The Palmer", 320, "upscale", "hotels.example/tp320"), ("Loop Lodge", 150, "mid", "hotels.example/ll150")]},
    {"id": "marathon-planning-003", "city": "San Diego", "venue": "the convention center",
     "flights": [("CoastAir", 330, "flights.example/ca330"), ("JetWest", 290, "flights.example/jw290"), ("BudgetAir", 260, "flights.example/ba260")],
     "hotels": [("Marina Bay Hotel", 230, "mid", "hotels.example/mb230"), ("Gaslamp Grand", 310, "upscale", "hotels.example/gg310"), ("Mission Inn", 170, "mid", "hotels.example/mi170")]},
    {"id": "marathon-planning-004", "city": "Atlanta", "venue": "the Georgia World Congress Center",
     "flights": [("SkyAir", 180, "flights.example/sky180"), ("PeachAir", 220, "flights.example/pa220"), ("BudgetAir", 150, "flights.example/ba150")],
     "hotels": [("Peachtree Suites", 160, "mid", "hotels.example/ps160"), ("The Georgian", 280, "upscale", "hotels.example/tg280"), ("Midtown Lodge", 130, "mid", "hotels.example/ml130")]},
]


def build_travel_family() -> None:
    for spec in TRAVEL_TASKS:
        cheapest_flight = min(spec["flights"], key=lambda f: f[1])
        truth: dict[str, dict[str, Any]] = {}
        for tier in ("mid", "upscale"):
            tier_hotels = [h for h in spec["hotels"] if h[2] == tier]
            hotel = min(tier_hotels, key=lambda h: h[1])
            per_person = cheapest_flight[1] + 3 * hotel[1]
            truth[tier] = {"flight": cheapest_flight[0], "flight_url": cheapest_flight[2], "hotel": hotel[0], "hotel_url": hotel[2 + 1], "per_person": float(per_person)}
        derived = [{"name": "expected", "key": "{{hotel_tier}}", "map": truth}]
        fixture = {
            "travel.json": json.dumps(
                {
                    "flights": [{"airline": a, "price": p, "url": u} for a, p, u in spec["flights"]],
                    "hotels": [{"name": n, "nightly": p, "tier": t, "url": u} for n, p, t, u in spec["hotels"]],
                },
                indent=2,
            )
        }
        checks = [
            {"id": "picks_and_sources", "check": "regex_all", "params": {"patterns": ["{{expected.flight}}", "{{expected.hotel}}", "{{expected.flight_url}}", "{{expected.hotel_url}}"]}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "per_person_total", "check": "numeric_within", "params": {"label": "per-person total", "value": "{{expected.per_person}}", "tolerance": 1.0}, "caps": {"correctness": 20}},
            {"id": "four_days", "check": "regex_all", "params": {"patterns": ["Day 1", "Day 2", "Day 3", "Day 4"]}, "caps": {"completeness": 15}},
            {"id": "plan_length", "check": "word_count", "params": {"min": 300, "max": 900}, "caps": {"instruction_adherence": 5}},
        ]
        solver_code = "\n".join(
            [
                "import json",
                "d = json.load(open('travel.json'))",
                "flight = min(d['flights'], key=lambda f: f['price'])",
                "hotels = [h for h in d['hotels'] if h['tier'] == 'mid']",
                "hotel = min(hotels, key=lambda h: h['nightly'])",
                "per_person = flight['price'] + 3 * hotel['nightly']",
                "lines = ['# Conference trip to " + spec["city"] + " (" + spec["venue"] + ")', '']",
                "lines.append('Flight: {} at ${} per person, booked via {}. It is the cheapest option in the pack and its schedule leaves a buffer before the first session.'.format(flight['airline'], flight['price'], flight['url']))",
                "lines.append('Hotel: {} at ${} per night for 3 nights, booked via {}. It is the cheapest mid-tier option and close enough to the venue to avoid daily transfers.'.format(hotel['name'], hotel['nightly'], hotel['url']))",
                "lines.append('Per-person total: ${} covering the flight plus three hotel nights. Meals and ground transport are budgeted separately at the team level and are not part of this per-person figure, which keeps the comparison honest across flight and hotel choices.'.format(per_person))",
                "lines.append('')",
                "lines.append('Day 1: Arrive, check in, registration, opening keynote, team dinner near the hotel.')",
                "lines.append('Day 2: Morning sessions, expo floor block, afternoon workshops, free evening.')",
                "lines.append('Day 3: Keynote, deep-dive sessions, partner meetings, group activity in the evening.')",
                "lines.append('Day 4: Closing sessions, checkout, airport transfer, evening flight home.')",
                "lines.append('')",
                "lines.append('Ground transport: the team rideshares from the airport to the hotel on arrival and back on departure; the venue is walkable from the hotel, so no rental cars are booked. Anyone arriving on a different flight should join the group transfer where possible, and the organizer keeps the ride receipts with the trip file for reimbursement alongside the flight and hotel confirmations.')",
                "lines.append('Meals: breakfast is included at the hotel on conference days, and the team dinner on Day 1 is the one planned group meal; other meals are on the per-diem. Flag dietary requirements to the dinner venue when booking, and keep the group dinner inside the mid-tier budget by ordering from the set menu agreed with the restaurant in advance.')",
                "lines.append('')",
                "lines.append('Book the flight first because the cheapest fare is the most perishable piece, then the hotel while the mid-tier rate holds. Reconfirm both bookings a week out and share the day plan with the team once travel is locked.')",
                "open('itinerary.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('wrote itinerary.md')",
            ]
        )
        write_task(
            spec["id"],
            2,
            "planning",
            "Plan a 4-day conference trip to " + spec["city"] + " (" + spec["venue"] + ") for a team of {{team_size}} using travel.json. Pick the cheapest flight and the cheapest {{hotel_tier}}-tier hotel. Write itinerary.md naming both picks with their booking source URLs, the per-person total (flight + 3 nights) printed as 'Per-person total: $X', and a Day 1 to Day 4 outline.",
            {
                "team_size": {"type": "enum", "values": [4, 6, 8]},
                "hotel_tier": {"type": "enum", "values": ["mid", "upscale"]},
            },
            checks,
            rubric_list=rubric(
                "Picks are the true cheapest under the rules and the per-person total is exact.",
                "Picks, sources, total, and all four days present.",
                "Handles tier filtering instead of picking the raw cheapest hotel.",
                "Total format and day outline as specified; itinerary.md delivered.",
            ),
            task_md="# Conference trip — " + spec["city"] + "\n\nUse `travel.json`. Cheapest flight + cheapest hotel in the drawn tier, 3 nights. Print 'Per-person total: $X' and a Day 1-4 outline. Deliver `itinerary.md`.\n",
            rubric_text=rubric_md(spec["id"], "Picks and total exact under the rules.", "All elements present.", "Tier filter applied.", "itinerary.md delivered."),
            derived_params=derived,
            fixtures=fixture,
            smoke=[read("travel.json"), py(solver_code), deliver("itinerary.md", "Planned the trip with the cheapest flight and mid-tier hotel.")],
            pinned_params={"team_size": 6, "hotel_tier": "mid"},
        )


# -- Shared builder: code builds and feature builds --------------------------------

def code_build(
    task_id: str,
    level: int,
    module: str,
    starter: str,
    spec_md: str,
    tests: str,
    impl: str,
    summary: str,
    prompt: str,
    *,
    category: str = "code_build",
    extra_steps: list[dict[str, Any]] | None = None,
    extra_fixtures: dict[str, str] | None = None,
    extra_checks: list[dict[str, Any]] | None = None,
    pinned: dict[str, Any] | None = None,
) -> None:
    fixtures = {
        module: starter,
        "SPEC_FEATURE.md": spec_md,
        "tests/test_" + module: tests,
        "conftest.py": "# Ensures the workspace root is on sys.path for test imports.\n",
    }
    if extra_fixtures:
        fixtures.update(extra_fixtures)
    checks = [
        {"id": "acceptance_tests_pass", "check": "pytest_pass", "params": {"test_path": "tests"}, "caps": {"correctness": 10, "completeness": 10}},
        {"id": "summary_present", "check": "word_count", "params": {"min": 30, "max": 400}, "caps": {"completeness": 20}},
    ]
    if extra_checks:
        checks.extend(extra_checks)
    smoke: list[dict[str, Any]] = [read("SPEC_FEATURE.md"), read(module)]
    if extra_steps:
        smoke.extend(extra_steps)
    smoke.append(write(module, impl))
    smoke.append(shell("python3 -m pytest -q tests"))
    smoke.append(write("summary.md", summary + "\n"))
    smoke.append(deliver("summary.md", "Implemented " + module + " to spec; acceptance suite green; summary.md delivered."))
    write_task(
        task_id,
        level,
        category,
        prompt,
        pinned or {"stack": {"type": "enum", "values": ["python stdlib", "stdlib only", "pure python"]}, "scope": {"type": "enum", "values": ["full spec", "complete implementation", "all acceptance tests"]}},
        checks,
        rubric_list=rubric(
            "The full acceptance suite passes against the implementation.",
            "Implementation plus summary; every spec behavior covered.",
            "Reads failures and iterates instead of guessing APIs.",
            "Spec followed exactly; summary.md delivered; tests unmodified.",
        ),
        task_md="# Build — " + module + "\n\nImplement `" + module + "` to `SPEC_FEATURE.md`. The acceptance suite in `tests/` defines done. Write `summary.md` and deliver it.\n",
        rubric_text=rubric_md(task_id, "Acceptance suite fully green.", "Implementation and summary complete.", "Iterates on test failures.", "Tests unmodified; summary.md delivered."),
        fixtures=fixtures,
        smoke=smoke,
        pinned_params=pinned or {"stack": "python stdlib", "scope": "full spec"},
    )


RATE_LIMITER_IMPL = '''"""Sliding-window rate limiter (docs in SPEC_FEATURE.md)."""

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit, window_seconds):
        self.limit = limit
        self.window = window_seconds
        self.events = defaultdict(deque)

    def _prune(self, key, now):
        q = self.events[key]
        cutoff = now - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    def allow(self, key, now=None):
        now = time.time() if now is None else now
        q = self._prune(key, now)
        if len(q) < self.limit:
            q.append(now)
            return True
        return False

    def remaining(self, key, now=None):
        now = time.time() if now is None else now
        q = self._prune(key, now)
        return max(0, self.limit - len(q))
'''

RATE_LIMITER_TESTS = '''from rate_limiter import SlidingWindowLimiter


def test_allows_up_to_limit():
    lim = SlidingWindowLimiter(3, 60)
    assert [lim.allow("k", now=1000.0 + i) for i in range(3)] == [True, True, True]


def test_blocks_beyond_limit():
    lim = SlidingWindowLimiter(2, 60)
    assert lim.allow("k", now=0.0) is True
    assert lim.allow("k", now=1.0) is True
    assert lim.allow("k", now=2.0) is False


def test_window_expiry_frees_slots():
    lim = SlidingWindowLimiter(1, 60)
    assert lim.allow("k", now=0.0) is True
    assert lim.allow("k", now=30.0) is False
    assert lim.allow("k", now=61.0) is True


def test_keys_are_isolated():
    lim = SlidingWindowLimiter(1, 60)
    assert lim.allow("a", now=0.0) is True
    assert lim.allow("b", now=0.0) is True
    assert lim.allow("a", now=1.0) is False


def test_remaining_counts_down():
    lim = SlidingWindowLimiter(3, 60)
    assert lim.remaining("k", now=0.0) == 3
    lim.allow("k", now=0.0)
    assert lim.remaining("k", now=1.0) == 2
'''

AUDIT_LOG_IMPL = '''"""Append-only audit log with a sha256 hash chain (see SPEC_FEATURE.md)."""

import hashlib
import json
import os


class AuditLog:
    def __init__(self, path):
        self.path = path

    def _entries(self):
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path) as fh:
            for line in fh:
                if line.strip():
                    out.append(json.loads(line))
        return out

    def append(self, actor, action, details=None):
        entries = self._entries()
        prev = entries[-1]["hash"] if entries else "GENESIS"
        payload = {"actor": actor, "action": action, "details": details or {}, "prev": prev}
        payload["hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with open(self.path, "a") as fh:
            fh.write(json.dumps(payload) + "\\n")
        return payload["hash"]

    def verify(self):
        prev = "GENESIS"
        for entry in self._entries():
            if entry["prev"] != prev:
                return False
            check = dict(entry)
            digest = check.pop("hash")
            if hashlib.sha256(json.dumps(check, sort_keys=True).encode()).hexdigest() != digest:
                return False
            prev = digest
        return True

    def query(self, actor=None):
        return [e for e in self._entries() if actor is None or e["actor"] == actor]
'''

AUDIT_LOG_TESTS = '''import json

from audit_log import AuditLog


def test_append_and_verify(tmp_path):
    log = AuditLog(str(tmp_path / "a.log"))
    log.append("alice", "login")
    log.append("bob", "export", {"rows": 5})
    assert log.verify() is True


def test_tamper_breaks_verification(tmp_path):
    path = tmp_path / "a.log"
    log = AuditLog(str(path))
    log.append("alice", "login")
    log.append("bob", "export")
    lines = path.read_text().splitlines()
    entry = json.loads(lines[0])
    entry["actor"] = "mallory"
    lines[0] = json.dumps(entry)
    path.write_text("\\n".join(lines) + "\\n")
    assert log.verify() is False


def test_query_filters_by_actor(tmp_path):
    log = AuditLog(str(tmp_path / "a.log"))
    log.append("alice", "login")
    log.append("bob", "export")
    log.append("alice", "logout")
    assert len(log.query("alice")) == 2
    assert len(log.query()) == 3


def test_chain_links_entries(tmp_path):
    log = AuditLog(str(tmp_path / "a.log"))
    h1 = log.append("alice", "login")
    log.append("alice", "logout")
    entries = log.query()
    assert entries[1]["prev"] == h1
'''

SEARCH_INDEX_IMPL = '''"""Tiny full-text search index (see SPEC_FEATURE.md)."""

import re
from collections import defaultdict


def _terms(text):
    return re.findall(r"[a-z0-9]+", text.lower())


class SearchIndex:
    def __init__(self):
        self.docs = {}
        self.index = defaultdict(set)

    def add(self, doc_id, text):
        self.docs[doc_id] = text
        for term in set(_terms(text)):
            self.index[term].add(doc_id)

    def search(self, query, limit=10, offset=0):
        terms = _terms(query)
        if not terms:
            return []
        candidates = None
        for term in terms:
            ids = self.index.get(term, set())
            candidates = set(ids) if candidates is None else candidates & ids
        scored = []
        for doc_id in candidates or []:
            words = _terms(self.docs[doc_id])
            score = sum(words.count(t) for t in terms)
            scored.append((doc_id, score))
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        return [doc_id for doc_id, _ in scored[offset:offset + limit]]
'''

SEARCH_INDEX_TESTS = '''from search_index import SearchIndex


def _index():
    idx = SearchIndex()
    idx.add("d1", "the quick brown fox jumps")
    idx.add("d2", "the quick blue hare runs quick")
    idx.add("d3", "a slow brown bear sleeps")
    return idx


def test_and_semantics():
    assert _index().search("quick brown") == ["d1"]


def test_ranking_by_frequency():
    assert _index().search("quick") == ["d2", "d1"]


def test_pagination():
    idx = _index()
    assert idx.search("the", limit=1, offset=0) == ["d1"]
    assert idx.search("the", limit=1, offset=1) == ["d2"]


def test_empty_and_unknown():
    idx = _index()
    assert idx.search("") == []
    assert idx.search("zebra") == []
'''

SCHEDULER_IMPL = '''"""Report scheduling helpers (see SPEC_FEATURE.md)."""

from datetime import datetime, timedelta, timezone


def next_run(schedule, after):
    kind = schedule["kind"]
    hour = schedule.get("hour", 9)
    minute = schedule.get("minute", 0)
    offset = timezone(timedelta(hours=schedule.get("utc_offset", 0)))
    local = after.astimezone(offset)
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if kind == "daily":
        if candidate <= local:
            candidate += timedelta(days=1)
        return candidate
    if kind == "weekly":
        days_ahead = (schedule["weekday"] - candidate.weekday()) % 7
        candidate += timedelta(days=days_ahead)
        if candidate <= local:
            candidate += timedelta(days=7)
        return candidate
    raise ValueError("unknown schedule kind: " + str(kind))


def backoff(attempt):
    return min(3600, 60 * (2 ** attempt))
'''

SCHEDULER_TESTS = '''from datetime import datetime, timezone

from scheduler import backoff, next_run


def test_daily_later_today():
    after = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
    nxt = next_run({"kind": "daily", "hour": 9}, after)
    assert nxt == datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)


def test_daily_rolls_to_tomorrow():
    after = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    nxt = next_run({"kind": "daily", "hour": 9}, after)
    assert nxt == datetime(2026, 1, 6, 9, 0, tzinfo=timezone.utc)


def test_weekly_same_week():
    after = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)  # Monday
    nxt = next_run({"kind": "weekly", "weekday": 2, "hour": 9}, after)  # Wednesday
    assert nxt == datetime(2026, 1, 7, 9, 0, tzinfo=timezone.utc)


def test_weekly_rolls_a_week():
    after = datetime(2026, 1, 7, 10, 0, tzinfo=timezone.utc)  # Wednesday, past 9am
    nxt = next_run({"kind": "weekly", "weekday": 2, "hour": 9}, after)
    assert nxt == datetime(2026, 1, 14, 9, 0, tzinfo=timezone.utc)


def test_utc_offset_schedule():
    after = datetime(2026, 1, 5, 13, 0, tzinfo=timezone.utc)  # 08:00 at UTC-5
    nxt = next_run({"kind": "daily", "hour": 9, "utc_offset": -5}, after)
    assert nxt == datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc)


def test_backoff_grows_and_caps():
    assert backoff(0) == 60
    assert backoff(1) == 120
    assert backoff(20) == 3600
'''

CSV2JSON_IMPL = '''"""Convert CSV text to JSON (see SPEC_FEATURE.md)."""

import csv
import io
import json
import sys


def convert(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        return "[]"
    rows = [dict(row) for row in reader]
    return json.dumps(rows, indent=2)


def main(argv):
    with open(argv[1]) as fh:
        print(convert(fh.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
'''

CSV2JSON_TESTS = '''import json

from csv2json import convert


def test_basic_rows():
    out = json.loads(convert("name,age\\nalice,30\\nbob,25\\n"))
    assert out == [{"name": "alice", "age": "30"}, {"name": "bob", "age": "25"}]


def test_quoted_commas():
    out = json.loads(convert('name,note\\nalice,"hi, there"\\n'))
    assert out == [{"name": "alice", "note": "hi, there"}]


def test_empty_input():
    assert json.loads(convert("")) == []
'''

TOC_IMPL = '''"""Generate a table of contents from markdown (see SPEC_FEATURE.md)."""

import re

HEADING = re.compile(r"^(#{1,6})\\s+(.*)$")


def slugify(text):
    slug = text.strip().lower()
    slug = re.sub(r"[^a-z0-9\\s-]", "", slug)
    return re.sub(r"\\s+", "-", slug)


def generate_toc(markdown):
    lines = []
    in_fence = False
    base = None
    for raw in markdown.splitlines():
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING.match(raw)
        if not match:
            continue
        level = len(match.group(1))
        text = match.group(2).strip()
        if base is None:
            base = level
        indent = "  " * (level - base)
        lines.append(indent + "- [" + text + "](#" + slugify(text) + ")")
    return "\\n".join(lines)
'''

TOC_TESTS = '''from markdown_toc import generate_toc


def test_nested_toc():
    md = "# Title\\n\\n## Install\\n\\n## Usage\\n\\n### Advanced Usage\\n"
    toc = generate_toc(md)
    assert "- [Title](#title)" in toc
    assert "  - [Install](#install)" in toc
    assert "    - [Advanced Usage](#advanced-usage)" in toc


def test_headings_in_code_fences_are_ignored():
    md = "# Real\\n\\n```\\n# Not A Heading\\n```\\n"
    toc = generate_toc(md)
    assert "Not A Heading" not in toc
    assert "- [Real](#real)" in toc


def test_slug_punctuation():
    md = "## What's New: v2.0!\\n"
    assert "(#whats-new-v20)" in generate_toc(md)
'''

LOG_SUMMARY_IMPL = '''"""Summarize log lines by level (see SPEC_FEATURE.md)."""

from collections import Counter


def summarize(lines):
    by_level = Counter()
    errors = Counter()
    total = 0
    for line in lines:
        if not line.strip():
            continue
        total += 1
        parts = line.split(" ", 1)
        level = parts[0]
        by_level[level] += 1
        if level == "ERROR" and len(parts) > 1:
            errors[parts[1]] += 1
    return {
        "total": total,
        "by_level": dict(by_level),
        "top_errors": errors.most_common(3),
    }
'''

LOG_SUMMARY_TESTS = '''from log_summary import summarize


def test_counts_by_level():
    out = summarize(["INFO start", "ERROR disk full", "INFO done", "ERROR disk full", ""])
    assert out["total"] == 4
    assert out["by_level"] == {"INFO": 2, "ERROR": 2}


def test_top_errors_ranked():
    lines = ["ERROR a", "ERROR b", "ERROR a", "ERROR c", "ERROR a", "ERROR b"]
    out = summarize(lines)
    assert out["top_errors"][0] == ("a", 3)
    assert out["top_errors"][1] == ("b", 2)


def test_empty_input():
    assert summarize([]) == {"total": 0, "by_level": {}, "top_errors": []}
'''


def _starter(module: str, note: str) -> str:
    return '"""' + note + ' Implementation pending: see SPEC_FEATURE.md."""\n\n# TODO: implement to spec.\n'


def build_feature_and_tool_builders() -> None:
    code_build(
        "marathon-code-001", 2, "rate_limiter.py", _starter("rate_limiter.py", "Sliding-window rate limiter."),
        "# Spec: sliding-window rate limiter\n\nClass `SlidingWindowLimiter(limit, window_seconds)` with `allow(key, now=None)` and `remaining(key, now=None)`. `allow` records the event when allowed. Events older than the window stop counting. Keys are independent. `now` is injectable for tests (epoch seconds); default to the current time.\n",
        RATE_LIMITER_TESTS, RATE_LIMITER_IMPL,
        "Implemented a sliding-window rate limiter: per-key event queues pruned against the window on every call, allow records only when under the limit, remaining reports the free slots. All acceptance tests pass, including window expiry and per-key isolation cases.",
        "Implement rate_limiter.py to SPEC_FEATURE.md in the workspace so the acceptance suite in tests/ passes. Do not modify the tests. Write summary.md and deliver it. Stack: {{stack}}; scope: {{scope}}.",
    )
    code_build(
        "marathon-code-002", 2, "audit_log.py", _starter("audit_log.py", "Append-only audit log."),
        "# Spec: audit log with hash chain\n\nClass `AuditLog(path)`. `append(actor, action, details=None)` appends a JSON line containing actor, action, details, prev (the previous entry's hash, or GENESIS for the first), and hash (sha256 of the entry without the hash field, JSON with sorted keys). Returns the new hash. `verify()` replays the chain and returns False on any mismatch. `query(actor=None)` returns parsed entries, optionally filtered by actor.\n",
        AUDIT_LOG_TESTS, AUDIT_LOG_IMPL,
        "Implemented an append-only audit log: each entry carries the previous entry's sha256 hash forming a chain, verify replays and recomputes every hash so tampering with any historical entry is detected, and query filters by actor. The full acceptance suite passes, including the tamper case.",
        "Implement audit_log.py to SPEC_FEATURE.md in the workspace so the acceptance suite in tests/ passes. Do not modify the tests. Write summary.md and deliver it. Stack: {{stack}}; scope: {{scope}}.",
    )
    code_build(
        "marathon-code-003", 2, "search_index.py", _starter("search_index.py", "Tiny full-text search index."),
        "# Spec: full-text search index\n\nClass `SearchIndex` with `add(doc_id, text)` and `search(query, limit=10, offset=0)`. Tokenize on lowercase alphanumeric runs. Search uses AND semantics across query terms, ranks by total term frequency (ties broken by doc_id ascending), and returns doc_ids sliced by offset/limit. Empty queries and unknown terms return an empty list.\n",
        SEARCH_INDEX_TESTS, SEARCH_INDEX_IMPL,
        "Implemented a small full-text search index: inverted index over lowercase alphanumeric tokens, AND semantics across query terms, ranking by summed term frequency with doc_id tie-breaks, and offset/limit pagination. All acceptance tests pass, including ranking and pagination cases.",
        "Implement search_index.py to SPEC_FEATURE.md in the workspace so the acceptance suite in tests/ passes. Do not modify the tests. Write summary.md and deliver it. Stack: {{stack}}; scope: {{scope}}.",
    )
    code_build(
        "marathon-code-004", 2, "scheduler.py", _starter("scheduler.py", "Report scheduling helpers."),
        "# Spec: report scheduler\n\n`next_run(schedule, after)` where schedule is a dict: kind 'daily' or 'weekly', hour (default 9), minute (default 0), utc_offset in hours (default 0), and weekday (0=Monday) for weekly. Return the next timezone-aware datetime strictly after `after`, in the schedule's offset zone. `backoff(attempt)` returns seconds: 60 * 2**attempt capped at 3600.\n",
        SCHEDULER_TESTS, SCHEDULER_IMPL,
        "Implemented the report scheduler: daily and weekly next-run computation in the schedule's UTC offset with strict after semantics and correct roll-overs, plus exponential backoff capped at one hour. All acceptance tests pass, including the UTC-offset case and both weekly roll cases.",
        "Implement scheduler.py to SPEC_FEATURE.md in the workspace so the acceptance suite in tests/ passes. Do not modify the tests. Write summary.md and deliver it. Stack: {{stack}}; scope: {{scope}}.",
    )
    code_build(
        "marathon-code-005", 2, "csv2json.py", _starter("csv2json.py", "CSV to JSON converter."),
        "# Spec: CSV to JSON tool\n\n`convert(csv_text)` returns a JSON string of an array of row objects keyed by the header row, using the csv module (quoted commas must work). Empty input returns '[]'. A `main(argv)` reads a file path from argv[1] and prints the converted JSON.\n",
        CSV2JSON_TESTS, CSV2JSON_IMPL,
        "Built the CSV to JSON converter on the csv module so quoted fields with commas parse correctly, with the empty-input case returning an empty JSON array and a small CLI entry point that converts a file path argument. The acceptance suite passes on basic rows, quoted commas, and empty input.",
        "Build csv2json.py to SPEC_FEATURE.md in the workspace so the acceptance suite in tests/ passes. Do not modify the tests. Write summary.md and deliver it. Stack: {{stack}}; scope: {{scope}}.",
    )
    code_build(
        "marathon-code-006", 2, "markdown_toc.py", _starter("markdown_toc.py", "Markdown TOC generator."),
        "# Spec: markdown table of contents\n\n`generate_toc(markdown)` returns nested markdown bullets linking to heading anchors. Indentation is relative to the shallowest heading level in the document (two spaces per extra level). Headings inside fenced code blocks are ignored. Slugs: lowercase, strip punctuation other than hyphens, spaces become hyphens (GitHub style, e.g. \"What's New: v2.0!\" becomes whats-new-v20).\n",
        TOC_TESTS, TOC_IMPL,
        "Built the markdown TOC generator: it scans headings outside fenced code blocks, indents relative to the shallowest heading, and slugifies GitHub-style by lowercasing, stripping punctuation, and hyphenating spaces. The acceptance suite passes, including the code-fence exclusion and the punctuation slug case.",
        "Build markdown_toc.py to SPEC_FEATURE.md in the workspace so the acceptance suite in tests/ passes. Do not modify the tests. Write summary.md and deliver it. Stack: {{stack}}; scope: {{scope}}.",
    )
    code_build(
        "marathon-code-007", 2, "log_summary.py", _starter("log_summary.py", "Log summarizer."),
        "# Spec: log summary tool\n\n`summarize(lines)` returns a dict with total (non-blank lines), by_level (counts keyed by the first token of each line), and top_errors: the three most common ERROR messages (the text after the level) as (message, count) pairs from Counter.most_common. Blank lines are skipped entirely.\n",
        LOG_SUMMARY_TESTS, LOG_SUMMARY_IMPL,
        "Built the log summary tool: it counts non-blank lines by their leading level token and ranks the most common error messages with Counter.most_common, skipping blank lines so trailing newlines never distort the counts. The acceptance suite passes on level counts, error ranking, and empty input.",
        "Build log_summary.py to SPEC_FEATURE.md in the workspace so the acceptance suite in tests/ passes. Do not modify the tests. Write summary.md and deliver it. Stack: {{stack}}; scope: {{scope}}.",
    )


# -- Marathon: spec extraction, data dives, dossiers, events, multi-page web ------

MARATHON_WEB: list[dict[str, Any]] = [
    {"id": "marathon-web-001", "product": "pro cordless drills",
     "models": [("DrillDriver Pro", 189, "2200 RPM", "2.1 lb"), ("TorqueMax Ultra", 259, "2800 RPM", "2.6 lb"), ("CompactDrill Max", 129, "1500 RPM", "1.7 lb"), ("HammerPro Elite", 329, "3200 RPM", "3.0 lb"), ("SiteMaster 20V", 219, "2400 RPM", "2.3 lb")],
     "focus": {"TorqueMax": ("TorqueMax Ultra", "259", "2800 RPM"), "HammerPro": ("HammerPro Elite", "329", "3200 RPM"), "SiteMaster": ("SiteMaster 20V", "219", "2400 RPM")}},
    {"id": "marathon-web-002", "product": "e-bikes",
     "models": [("CityGlide", 1299, "60 mi", "44 lb"), ("TrailBlazer X", 2499, "85 mi", "52 lb"), ("MountainGoat Pro", 3499, "100 mi", "58 lb"), ("FoldAway Mini", 899, "40 mi", "38 lb"), ("CargoHaul Max", 2899, "75 mi", "71 lb")],
     "focus": {"TrailBlazer": ("TrailBlazer X", "2499", "85 mi"), "MountainGoat": ("MountainGoat Pro", "3499", "100 mi"), "CargoHaul": ("CargoHaul Max", "2899", "75 mi")}},
    {"id": "marathon-web-003", "product": "pro robot vacuums",
     "models": [("RoboVac Pro", 599, "240 min", "8.1 lb"), ("DustBot Ultra", 749, "300 min", "8.8 lb"), ("CleanSweep Max", 429, "200 min", "7.4 lb"), ("NaviMop Elite", 899, "330 min", "9.2 lb"), ("TurboSuck 3000", 649, "260 min", "8.4 lb")],
     "focus": {"DustBot": ("DustBot Ultra", "749", "300 min"), "NaviMop": ("NaviMop Elite", "899", "330 min"), "TurboSuck": ("TurboSuck 3000", "649", "260 min")}},
]


def build_marathon_web() -> None:
    for spec in MARATHON_WEB:
        rows_html = "\n".join(
            "<tr><td>" + m[0] + "</td><td>$" + str(m[1]) + "</td><td>" + m[2] + "</td><td>" + m[3] + "</td></tr>" for m in spec["models"]
        )
        html = "<html><body>\n<h1>" + spec["product"] + "</h1>\n<table>\n<tr><th>Model</th><th>Price</th><th>Headline spec</th><th>Weight</th></tr>\n" + rows_html + "\n</table>\n</body></html>\n"
        derived = [{"name": "expected", "key": "{{brand_focus}}", "map": {b: {"model": v[0], "price": v[1], "spec": v[2]} for b, v in spec["focus"].items()}}]
        checks = [
            {"id": "csv_shape", "check": "csv_valid", "params": {"columns": ["model", "price", "spec", "weight", "source"], "min_rows": 5}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "focus_row_values", "check": "regex_all", "params": {"patterns": ["{{expected.model}}", "{{expected.price}}", "{{expected.spec}}"]}, "caps": {"correctness": 20}},
            {"id": "all_models_present", "check": "regex_all", "params": {"patterns": [m[0] for m in spec["models"]]}, "caps": {"completeness": 15}},
        ]
        solver_code = "\n".join(
            [
                "import re",
                "html = open('specs.html').read()",
                "rows = re.findall(r'<tr><td>(.*?)</td><td>\\$(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>', html)",
                "lines = ['model,price,spec,weight,source']",
                "for name, price, sval, weight in rows:",
                "    lines.append('{},\"${}\",{},{},specs.html'.format(name, price, sval, weight))",
                "open('specs.csv', 'w').write(chr(10).join(lines) + chr(10))",
                "print('extracted', len(rows), 'models')",
            ]
        )
        write_task(
            spec["id"],
            2,
            "web_research",
            "Extract the full " + spec["product"] + " table from specs.html into specs.csv with columns model, price, spec, weight, source (source = specs.html for every row). Brand focus: {{brand_focus}}; output format: {{output_format}}.",
            {
                "brand_focus": {"type": "enum", "values": list(spec["focus"].keys())},
                "output_format": {"type": "enum", "values": ["csv", "plain csv", "spreadsheet-ready csv"]},
            },
            checks,
            rubric_list=rubric(
                "Every value matches the source table, including the focus row.",
                "All five models with all columns extracted.",
                "Parses structure rather than copying rendered text.",
                "Exact columns and attribution; specs.csv delivered.",
            ),
            task_md="# Spec extraction (pro) — " + spec["product"] + "\n\nExtract the table in `specs.html` into `specs.csv` (model, price, spec, weight, source). Deliver `specs.csv`.\n",
            rubric_text=rubric_md(spec["id"], "Values match source exactly.", "All models and columns.", "Structure parsed.", "specs.csv delivered."),
            derived_params=derived,
            fixtures={"specs.html": html},
            smoke=[read("specs.html"), py(solver_code), deliver("specs.csv", "Extracted all five models into specs.csv.")],
            pinned_params={"brand_focus": list(spec["focus"].keys())[0], "output_format": "csv"},
        )


def build_marathon_data() -> None:
    orders_csv = (
        "order_id,region,product,qty,price\n"
        "N1,north,Alpha,10,100\nN2,north,Beta,8,50\nN3,north,Gamma,3,200\n"
        "S1,south,Beta,11,50\nS2,south,Alpha,5,100\nS3,south,Delta,4,25\n"
        "W1,west,Gamma,5,200\nW2,west,Alpha,3,100\nW3,west,Beta,5,50\n"
    )
    returns_csv = "order_id,qty\nN1,2\nW1,1\nR999,1\n"
    truth1 = {
        "north|2": {"top_products": ["Alpha", "Gamma"], "total_revenue": 1800.0},
        "north|3": {"top_products": ["Alpha", "Gamma", "Beta"], "total_revenue": 1800.0},
        "south|2": {"top_products": ["Beta", "Alpha"], "total_revenue": 1150.0},
        "south|3": {"top_products": ["Beta", "Alpha", "Delta"], "total_revenue": 1150.0},
        "west|2": {"top_products": ["Gamma", "Alpha"], "total_revenue": 1350.0},
        "west|3": {"top_products": ["Gamma", "Alpha", "Beta"], "total_revenue": 1350.0},
    }
    solver1 = "\n".join(
        [
            "import csv",
            "from collections import defaultdict",
            "orders = {r['order_id']: r for r in csv.DictReader(open('orders.csv'))}",
            "returned = defaultdict(int)",
            "for r in csv.DictReader(open('returns.csv')):",
            "    returned[r['order_id']] += int(r['qty'])",
            "rev = defaultdict(float)",
            "for oid, r in orders.items():",
            "    if r['region'] != 'north':",
            "        continue",
            "    net_qty = int(r['qty']) - returned.get(oid, 0)",
            "    rev[r['product']] += net_qty * float(r['price'])",
            "top = sorted(rev.items(), key=lambda kv: -kv[1])[:3]",
            "total = sum(rev.values())",
            "lines = ['Total revenue: ${:,.2f} net of returns for the north region.'.format(total), '', 'Top products by net revenue:']",
            "for name, val in top:",
            "    lines.append('- {}: ${:,.2f}'.format(name, val))",
            "lines.append('')",
            "lines.append('Method and data quality: order revenue was joined with the returns file on order_id, returned quantities were subtracted before valuing lines, and one orphan return row referencing a nonexistent order was excluded and flagged. Gross figures would overstate the quarter; every figure in this report is net of returns so it ties to cash actually kept by the business. The join was checked both ways: every return that matched an order reduced that order line, and every order line was valued exactly once, so there is no double counting in either direction. Where a return only partially offsets an order, the remaining units are valued at the original order price, which matches how the refund ledger settles in practice. Regional managers should read these figures as kept revenue, not demand, when they plan next quarter territory targets.')",
            "open('report.md', 'w').write(chr(10).join(lines) + chr(10))",
            "print('wrote report.md')",
        ]
    )
    derived1 = [{"name": "expected", "key": "{{region}}|{{top_n}}", "map": truth1}]
    write_task(
        "marathon-data-001",
        2,
        "data_analysis",
        "Join orders.csv with returns.csv on order_id. Net revenue subtracts returned quantities. Returns referencing nonexistent orders are orphan rows: exclude and flag them. For the {{region}} region, write report.md with the total revenue (net), the top {{top_n}} products by net revenue, and the method plus data quality notes (orphan returns). Length 150-600 words.",
        {
            "region": {"type": "enum", "values": ["north", "south", "west"]},
            "top_n": {"type": "integer", "min": 2, "max": 3},
        },
        [
            {"id": "top_products_named", "check": "regex_all", "params": {"patterns": "{{expected.top_products}}"}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "total_correct", "check": "numeric_within", "params": {"label": "total revenue", "value": "{{expected.total_revenue}}", "tolerance": 1.5}, "caps": {"correctness": 20}},
            {"id": "anomalies_named", "check": "regex_all", "params": {"patterns": ["orphan", "return"]}, "caps": {"completeness": 15}},
            {"id": "report_length", "check": "word_count", "params": {"min": 150, "max": 600}, "caps": {"instruction_adherence": 5}},
        ],
        rubric_list=rubric(
            "Net revenue and top products match the joined ground truth.",
            "Totals, top-N, method, and anomaly notes complete.",
            "Handles the orphan return explicitly instead of dropping it silently.",
            "Rules followed; report.md delivered.",
        ),
        task_md="# Net revenue deep dive\n\nJoin `orders.csv` with `returns.csv`, subtract returns, exclude and flag orphan returns. Deliver `report.md`.\n",
        rubric_text=rubric_md("marathon-data-001", "Joined figures exact.", "Totals, top-N, method, anomalies.", "Orphan handled explicitly.", "report.md delivered."),
        derived_params=derived1,
        fixtures={"orders.csv": orders_csv, "returns.csv": returns_csv},
        smoke=[read("orders.csv"), py(solver1), deliver("report.md", "Joined orders and returns; wrote the net revenue report.")],
        pinned_params={"region": "north", "top_n": 3},
    )

    stock_csv = "sku,category,stock,unit_cost\nS1,electronics,100,10\nS2,tools,40,30\nS3,electronics,200,4\nS4,tools,10,100\n"
    sales_csv = "sku,sold\nS1,130\nS2,10\nS3,250\nS4,15\n"
    truth2 = {
        "all": {"stockouts": ["S1", "S3", "S4"], "reorder_value": 1000.0},
        "electronics": {"stockouts": ["S1", "S3"], "reorder_value": 500.0},
        "tools": {"stockouts": ["S4"], "reorder_value": 500.0},
    }
    solver2 = "\n".join(
        [
            "import csv",
            "inv = {r['sku']: r for r in csv.DictReader(open('inventory.csv'))}",
            "sold = {r['sku']: int(r['sold']) for r in csv.DictReader(open('sales.csv'))}",
            "short = []",
            "value = 0.0",
            "for sku, r in inv.items():",
            "    unfulfilled = sold.get(sku, 0) - int(r['stock'])",
            "    if unfulfilled > 0:",
            "        short.append(sku)",
            "        value += unfulfilled * float(r['unit_cost'])",
            "lines = ['Stockout analysis across all categories.', '', 'Stockout SKUs: ' + ', '.join(sorted(short)) + '.', 'Reorder value: ${:,.2f} to cover unfulfilled demand.'.format(value), '']",
            "lines.append('Method: sold quantities from sales.csv were compared with on-hand stock in inventory.csv per SKU. A SKU is a stockout when demand exceeded stock; the reorder value prices only the unfulfilled units at unit cost, which is the cash required to make waiting customers whole. Every category was included in this view, and the pattern is clear: demand forecasting, not warehouse space, is the binding constraint this quarter for the affected lines.')",
            "open('report.md', 'w').write(chr(10).join(lines) + chr(10))",
            "print('wrote report.md')",
        ]
    )
    derived2 = [{"name": "expected", "key": "{{category}}", "map": truth2}]
    write_task(
        "marathon-data-002",
        2,
        "data_analysis",
        "Compare sales.csv (units sold) with inventory.csv (stock on hand, unit cost) per SKU. A stockout is demand above stock; the reorder value prices the unfulfilled units at unit cost. For category {{category}}, write report.md naming every stockout SKU and the reorder value printed as 'Reorder value: $X', with a method note. View: {{view}}.",
        {
            "category": {"type": "enum", "values": ["all", "electronics", "tools"]},
            "view": {"type": "enum", "values": ["summary", "detail", "executive"]},
        },
        [
            {"id": "stockouts_named", "check": "regex_all", "params": {"patterns": "{{expected.stockouts}}"}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "reorder_value_correct", "check": "numeric_within", "params": {"label": "reorder value", "value": "{{expected.reorder_value}}", "tolerance": 1.0}, "caps": {"correctness": 20}},
            {"id": "report_length", "check": "word_count", "params": {"min": 80, "max": 500}, "caps": {"instruction_adherence": 5}},
        ],
        rubric_list=rubric(
            "Stockout set and reorder value match the joined ground truth for the category.",
            "All stockouts named with the exact reorder value and a method note.",
            "Reasons about unfulfilled units only, not gross demand.",
            "Format followed; report.md delivered.",
        ),
        task_md="# Stockout analysis\n\nJoin `sales.csv` with `inventory.csv`; name stockout SKUs and price the unfulfilled units. Deliver `report.md`.\n",
        rubric_text=rubric_md("marathon-data-002", "Stockouts and value exact.", "All stockouts plus method.", "Unfulfilled-only reasoning.", "report.md delivered."),
        derived_params=derived2,
        fixtures={"inventory.csv": stock_csv, "sales.csv": sales_csv},
        smoke=[read("inventory.csv"), py(solver2), deliver("report.md", "Computed stockouts and reorder value across categories.")],
        pinned_params={"category": "all", "view": "summary"},
    )

    subs_csv = "customer,plan,mrr\nA,pro,200\nB,pro,200\nC,pro,150\nD,basic,50\nE,basic,50\nF,team,300\nG,team,300\nH,team,100\n"
    churn_csv = "customer\nB\nD\nF\n"
    truth3 = {
        "pro": {"net_mrr": 350.0, "churned": ["B"]},
        "basic": {"net_mrr": 50.0, "churned": ["D"]},
        "team": {"net_mrr": 400.0, "churned": ["F"]},
    }
    solver3 = "\n".join(
        [
            "import csv",
            "churned = {r['customer'] for r in csv.DictReader(open('churn.csv'))}",
            "gross = 0.0",
            "lost = 0.0",
            "lost_names = []",
            "for r in csv.DictReader(open('subscriptions.csv')):",
            "    if r['plan'] != 'pro':",
            "        continue",
            "    gross += float(r['mrr'])",
            "    if r['customer'] in churned:",
            "        lost += float(r['mrr'])",
            "        lost_names.append(r['customer'])",
            "net = gross - lost",
            "lines = ['Net MRR: ${:,.2f} for the pro plan.'.format(net), '']",
            "lines.append('Gross pro MRR was ${:,.2f}; churn removed ${:,.2f} (customers: {}). Net MRR is the only honest planning figure because churned customers stop paying immediately, and the pro plan loses more dollars per churned customer than any other tier. Retention work on this tier pays for itself faster than equivalent acquisition spend, which is the single clearest lever in this dataset. The churned customer named here should be exit-interviewed before the next billing cycle, because one data point is an anecdote but the reason behind it usually generalizes to the rest of the tier.'.format(gross, lost, ', '.join(lost_names)))",
            "open('report.md', 'w').write(chr(10).join(lines) + chr(10))",
            "print('wrote report.md')",
        ]
    )
    derived3 = [{"name": "expected", "key": "{{plan}}", "map": truth3}]
    write_task(
        "marathon-data-003",
        2,
        "data_analysis",
        "Using subscriptions.csv and churn.csv, compute for the {{plan}} plan: gross MRR, churned MRR with the churned customers named, and net MRR printed as 'Net MRR: $X'. Write report.md (100-500 words) with the retention implication. View: {{view}}.",
        {
            "plan": {"type": "enum", "values": ["pro", "basic", "team"]},
            "view": {"type": "enum", "values": ["summary", "detail", "executive"]},
        },
        [
            {"id": "net_mrr_correct", "check": "numeric_within", "params": {"label": "net mrr", "value": "{{expected.net_mrr}}", "tolerance": 1.0}, "caps": {"correctness": 25}},
            {"id": "churned_named", "check": "regex_all", "params": {"patterns": "{{expected.churned}}"}, "caps": {"correctness": 20, "completeness": 15}},
            {"id": "report_length", "check": "word_count", "params": {"min": 100, "max": 500}, "caps": {"instruction_adherence": 5}},
        ],
        rubric_list=rubric(
            "Net MRR exact and churned customers named for the drawn plan.",
            "Gross, churn, net, and implications all present.",
            "Distinguishes gross from net instead of reporting headline MRR.",
            "Format followed; report.md delivered.",
        ),
        task_md="# Net MRR by plan\n\nJoin `subscriptions.csv` with `churn.csv`; print 'Net MRR: $X' for the drawn plan and name the churned customers. Deliver `report.md`.\n",
        rubric_text=rubric_md("marathon-data-003", "Net MRR exact; churn named.", "Gross, churn, net, implications.", "Gross vs net distinguished.", "report.md delivered."),
        derived_params=derived3,
        fixtures={"subscriptions.csv": subs_csv, "churn.csv": churn_csv},
        smoke=[read("subscriptions.csv"), py(solver3), deliver("report.md", "Computed net MRR for the pro plan.")],
        pinned_params={"plan": "pro", "view": "summary"},
    )


DOSSIERS: list[dict[str, Any]] = [
    {"id": "marathon-research-006", "topic": "home services franchising", "src_a": "Fieldnotes Research", "src_b": "MarketPulse", "fig_a": "4.1 billion", "fig_b": "4.6 billion"},
    {"id": "marathon-research-007", "topic": "vertical SaaS pricing benchmarks", "src_a": "SaaSMetrics Lab", "src_b": "BenchmarkCo", "fig_a": "7.9 billion", "fig_b": "8.3 billion"},
    {"id": "marathon-research-008", "topic": "short-term rental regulation", "src_a": "Housing Policy Institute", "src_b": "CityData Review", "fig_a": "2.2 billion", "fig_b": "2.9 billion"},
]


def build_dossier_family() -> None:
    for spec in DOSSIERS:
        doc_a = "# " + spec["src_a"] + " study\n\nThe " + spec["topic"] + " market is sized at $" + spec["fig_a"] + " in our 2025 study, based on operator surveys and franchise disclosures. Growth is steady and driven by consolidation.\n"
        doc_b = "# " + spec["src_b"] + " analysis\n\nOur 2026 analysis sizes the " + spec["topic"] + " market at $" + spec["fig_b"] + ", using tax records and platform data. The higher figure reflects categories the survey-based studies miss.\n"
        fixtures = {"doc_a.md": doc_a, "doc_b.md": doc_b}
        checks = [
            {"id": "sources_named", "check": "regex_all", "params": {"patterns": [spec["src_a"], spec["src_b"]]}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "both_figures_present", "check": "regex_all", "params": {"patterns": [spec["fig_a"], spec["fig_b"]]}, "caps": {"correctness": 20}},
            {"id": "contradiction_flagged", "check": "file_contains", "params": {"path": "dossier.md", "patterns": ["Contradiction"]}, "caps": {"completeness": 15}},
            {"id": "dossier_length", "check": "word_count", "params": {"min": 600, "max": 1500}, "caps": {"instruction_adherence": 5}},
        ]
        solver_code = "\n".join(
            [
                "a = open('doc_a.md').read()",
                "b = open('doc_b.md').read()",
                "lines = ['# Dossier: " + spec["topic"] + "', '']",
                "lines.append('## What the sources say')",
                "lines.append('Two source documents anchor this dossier. " + spec["src_a"] + " sizes the " + spec["topic"] + " market at $" + spec["fig_a"] + " using operator surveys and franchise disclosures, while " + spec["src_b"] + " reaches $" + spec["fig_b"] + " using tax records and platform data. Both agree on the direction of the market and on consolidation as the main driver; they disagree on the level, and that disagreement is itself the most important fact in the pack because every downstream decision, from hiring to territory pricing, inherits whichever figure the reader quietly adopts.')",
                "lines.append('')",
                "lines.append('## Contradiction')",
                "lines.append('Contradiction: the two sources size the same market at $" + spec["fig_a"] + " (" + spec["src_a"] + ") and $" + spec["fig_b"] + " (" + spec["src_b"] + "). The gap is methodological, not arithmetic: survey-based sizing misses categories that tax and platform records capture, particularly the smallest operators. Neither figure is wrong on its own terms, but they are not interchangeable, and any plan that cites one must say which and why. This dossier carries both figures forward rather than averaging them into a number neither source would defend.')",
                "lines.append('')",
                "lines.append('## Implications')",
                "lines.append('For planning, use the lower figure for revenue commitments and the higher figure only for market-share math, and revisit the choice when a third source lands. The consolidation driver both sources agree on matters more than the level dispute: share is moving toward scaled operators either way, so the strategic question is positioning inside the consolidation, not the exact size of the prize. Teams that internalize the range instead of a point estimate will make sturdier decisions under both versions of the truth.')",
                "lines.append('Reading the range honestly also changes how targets should be set. A team aiming at one percent of the conservative figure is committing to a number it can be held to; a team aiming at one percent of the larger figure is quietly committing to roughly a fifth more revenue with the same resources. Boards should therefore ask which denominator any market-share claim uses before debating whether the claim is ambitious or timid, because the same percentage target is two different plans depending on the source behind it.')",
                "lines.append('Finally, the disagreement is a reminder to price primary research before scaling spend. A modest survey or a payment-data pull would narrow this range for less than the cost of one mis-sized territory plan, and the dossier recommends commissioning exactly that before the next planning cycle locks its numbers.')",
                "lines.append('')",
                "lines.append('## Method note')",
                "lines.append('Survey and disclosure-based sizing, the method behind the lower figure, systematically undercounts the smallest operators, who neither answer surveys nor file franchise disclosures, while tax and platform records capture them but risk double-counting multi-category businesses. A careful reader therefore treats the two figures as bounds from different instruments rather than as competing measurements of one instrument, and any serious model of this market should carry the range explicitly instead of hiding it inside a single point estimate that pretends to a precision neither method can support.')",
                "lines.append('')",
                "lines.append('## What would change this picture')",
                "lines.append('A third source built on payment-processor data would arbitrate the level dispute directly, because card and ACH volumes see both the surveyed and the unsurveyed long tail exactly once. Until that exists, the honest position is the range. If a future edition of either current source revises toward the other, the methods note in that edition will say more about the true size than the headline figure itself, and this dossier should be refreshed at that point rather than patched quietly.')",
                "lines.append('')",
                "lines.append('## Bottom line')",
                "lines.append('The " + spec["topic"] + " market is growing and consolidating under either sizing. Cite " + spec["src_a"] + " at $" + spec["fig_a"] + " for conservative planning and " + spec["src_b"] + " at $" + spec["fig_b"] + " for total-addressable-market framing, and never blend the two without naming the methods behind them.')",
                "open('dossier.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('wrote dossier.md', len(' '.join(lines).split()))",
            ]
        )
        write_task(
            spec["id"],
            2,
            "research_synthesis",
            "Write a dossier on " + spec["topic"] + " from doc_a.md and doc_b.md in the workspace (600-1500 words). Name both sources, present both market figures, and include a section titled 'Contradiction' explaining the disagreement and how a planner should handle it. Audience: {{audience}}; angle: {{angle}}.",
            {
                "audience": {"type": "enum", "values": ["investor", "operator", "partner"]},
                "angle": {"type": "enum", "values": ["opportunity", "risk", "pricing"]},
            },
            checks,
            rubric_list=rubric(
                "Both sources, both figures, and the contradiction characterized accurately.",
                "Sources, figures, contradiction section, and implications complete.",
                "Flags the contradiction explicitly instead of silently picking one figure.",
                "Structure and length as specified; dossier.md delivered.",
            ),
            task_md="# Dossier — " + spec["topic"] + "\n\nFrom `doc_a.md` and `doc_b.md`, write a 600-1500 word dossier with a 'Contradiction' section. Deliver `dossier.md`.\n",
            rubric_text=rubric_md(spec["id"], "Sources and figures exact; contradiction characterized.", "All sections complete.", "Contradiction flagged, not hidden.", "dossier.md delivered."),
            fixtures=fixtures,
            smoke=[read("doc_a.md"), read("doc_b.md"), py(solver_code), deliver("dossier.md", "Wrote the dossier with the contradiction flagged.")],
            pinned_params={"audience": "operator", "angle": "risk"},
        )


EVENTS: list[dict[str, Any]] = [
    {"id": "marathon-planning-005", "event": "developer conference",
     "speakers": [("Ada Byron", "Compilers"), ("Grace Hopper", "Debugging"), ("Alan Kay", "Interfaces"), ("Barbara Liskov", "Types"), ("Edsger Dijkstra", "Algorithms"), ("Margaret Hamilton", "Reliability")],
     "rooms": [("Main Hall", 300), ("Workshop A", 450), ("Lab Room", 250)]},
    {"id": "marathon-planning-006", "event": "sales kickoff",
     "speakers": [("Priya Shah", "Pipeline"), ("Tom Becker", "Discovery"), ("Ana Ruiz", "Negotiation"), ("Chris Novak", "Forecasting"), ("Lee Park", "Enablement"), ("Sam Ortiz", "Partnerships")],
     "rooms": [("Ballroom", 300), ("Breakout 1", 450), ("Breakout 2", 250)]},
    {"id": "marathon-planning-007", "event": "community summit",
     "speakers": [("Jo Freeman", "Moderation"), ("Kit Yamada", "Events"), ("Rob Chen", "Sponsorships"), ("Ivy Chen", "Content"), ("Max Weber", "Growth"), ("Nia Brooks", "Accessibility")],
     "rooms": [("Atrium", 300), ("Studio A", 450), ("Studio B", 250)]},
]


def build_event_family() -> None:
    for spec in EVENTS:
        fixture = {
            "event.json": json.dumps(
                {
                    "speakers": [{"name": n, "topic": t} for n, t in spec["speakers"]],
                    "rooms": [{"name": n, "fee": f} for n, f in spec["rooms"]],
                    "catering_pp": 22,
                    "av_flat": 500,
                },
                indent=2,
            )
        }
        derived = [{"name": "expected", "key": "{{attendees}}", "map": {"50": {"total": 2600.0}, "100": {"total": 3700.0}}}]
        checks = [
            {"id": "speakers_scheduled", "check": "regex_all", "params": {"patterns": [s[0] for s in spec["speakers"]]}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "rooms_used", "check": "regex_all", "params": {"patterns": [r[0] for r in spec["rooms"]]}, "caps": {"completeness": 15}},
            {"id": "budget_total", "check": "numeric_within", "params": {"label": "total", "value": "{{expected.total}}", "tolerance": 1.0}, "caps": {"correctness": 20}},
            {"id": "schedule_length", "check": "word_count", "params": {"min": 150, "max": 600}, "caps": {"instruction_adherence": 5}},
        ]
        solver_code = "\n".join(
            [
                "import json",
                "d = json.load(open('event.json'))",
                "attendees = 50",
                "speakers = sorted(d['speakers'], key=lambda s: s['name'])",
                "rooms = d['rooms']",
                "lines = ['# Schedule: " + spec["event"] + "', '']",
                "for i, sp in enumerate(speakers):",
                "    room = rooms[i % len(rooms)]",
                "    slot = 'morning' if i % 2 == 0 else 'afternoon'",
                "    lines.append('- {} speaks on {} in {} ({})'.format(sp['name'], sp['topic'], room['name'], slot))",
                "room_fees = sum(r['fee'] for r in rooms)",
                "total = attendees * d['catering_pp'] + room_fees + d['av_flat']",
                "lines.append('')",
                "lines.append('Budget: catering for {} attendees at ${} per person, room fees of ${}, and a flat AV charge of ${}. Total: ${}. Every speaker is scheduled exactly once, rooms rotate so no room hosts back-to-back sessions in the same slot, and the budget holds the AV line flat because the venue bundles the standard package. Doors open thirty minutes before the first morning session, lunch is served in the largest room between slots, and the afternoon block ends with thirty minutes of open networking before the venue handover.'.format(attendees, d['catering_pp'], room_fees, d['av_flat'], total))",
                "open('schedule.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('wrote schedule.md')",
            ]
        )
        write_task(
            spec["id"],
            2,
            "planning",
            "Build the one-day schedule for a " + spec["event"] + " from event.json: sort speakers alphabetically, assign rooms round-robin in listed order, alternate morning/afternoon slots starting with morning. Budget: catering per person times {{attendees}} attendees, plus all room fees, plus the flat AV charge. Write schedule.md with one line per speaker and the budget printed as 'Total: $X'.",
            {
                "attendees": {"type": "enum", "values": [50, 100]},
                "track": {"type": "enum", "values": ["single", "mixed", "open"]},
            },
            checks,
            rubric_list=rubric(
                "Assignment rule followed exactly and the budget total is arithmetically exact.",
                "Every speaker and room present with the budget breakdown.",
                "Applies the deterministic assignment rule instead of inventing a schedule.",
                "Total format as specified; schedule.md delivered.",
            ),
            task_md="# Event schedule — " + spec["event"] + "\n\nFrom `event.json`, build the schedule with the stated assignment rule and print 'Total: $X'. Deliver `schedule.md`.\n",
            rubric_text=rubric_md(spec["id"], "Rule and total exact.", "All speakers, rooms, budget.", "Rule applied deterministically.", "schedule.md delivered."),
            derived_params=derived,
            fixtures=fixture,
            smoke=[read("event.json"), py(solver_code), deliver("schedule.md", "Built the schedule and budget.")],
            pinned_params={"attendees": 50, "track": "single"},
        )


MULTIPAGE: list[dict[str, Any]] = [
    {"id": "marathon-web-004", "product": "e-bikes",
     "models": [("CityGlide", 1299, 1299, "60 mi"), ("TrailBlazer X", 2299, 2499, "85 mi"), ("MountainGoat Pro", 3499, 3499, "100 mi")],
     "conflict": "TrailBlazer X"},
    {"id": "marathon-web-005", "product": "standing desks",
     "models": [("UpDesk Pro", 749, 799, "34 in lift"), ("ErgoLift", 549, 549, "30 in lift"), ("FlexDesk", 429, 429, "28 in lift")],
     "conflict": "UpDesk Pro"},
]


def build_multipage_family() -> None:
    for spec in MULTIPAGE:
        fixtures: dict[str, str] = {}
        index_rows = "\n".join(
            "<tr><td>" + m[0] + "</td><td>$" + str(m[1]) + "</td></tr>" for m in spec["models"]
        )
        fixtures["site/index.html"] = "<html><body>\n<h1>" + spec["product"] + "</h1>\n<table>\n" + index_rows + "\n</table>\n</body></html>\n"
        for name, _index_price, true_price, extra in spec["models"]:
            slug = name.lower().replace(" ", "_")
            fixtures["site/" + slug + ".html"] = (
                "<html><body>\n<h1>" + name + "</h1>\n<p>Price: $" + str(true_price) + "</p>\n<p>Key spec: " + extra + "</p>\n</body></html>\n"
            )
        conflict_model = next(m for m in spec["models"] if m[0] == spec["conflict"])
        checks = [
            {"id": "models_and_true_prices", "check": "regex_all", "params": {"patterns": [m[0] for m in spec["models"]] + [str(m[2]) for m in spec["models"]]}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "contradiction_named", "check": "regex_all", "params": {"patterns": [spec["conflict"], "contradiction"]}, "caps": {"correctness": 20}},
            {"id": "report_length", "check": "word_count", "params": {"min": 200, "max": 700}, "caps": {"instruction_adherence": 5}},
        ]
        solver_code = "\n".join(
            [
                "import os, re",
                "pages = sorted(f for f in os.listdir('site') if f != 'index.html')",
                "lines = ['# " + spec["product"] + " — extracted from the frozen site', '']",
                "conflicts = []",
                "index = open('site/index.html').read()",
                "for page in pages:",
                "    html = open('site/' + page).read()",
                "    name = re.search(r'<h1>(.*?)</h1>', html).group(1)",
                "    price = re.search(r'Price: \\$(\\d+)', html).group(1)",
                "    extra = re.search(r'Key spec: (.*?)</p>', html).group(1)",
                "    lines.append('- {}: ${} ({}) — source: site/{}'.format(name, price, extra, page))",
                "    m = re.search(re.escape(name) + r'</td><td>\\$(\\d+)', index)",
                "    if m and m.group(1) != price:",
                "        conflicts.append((name, m.group(1), price))",
                "lines.append('')",
                "lines.append('## Price contradiction')",
                "for name, idx_price, true_price in conflicts:",
                "    lines.append('Price contradiction: the index lists {} at ${} but its detail page says ${}. The detail page is treated as the source of truth because it is the page a buyer checks out from, and the index figure is flagged here for the site owner to correct.'.format(name, idx_price, true_price))",
                "lines.append('')",
                "lines.append('All other models agree between the index and their detail pages. Extraction covered every page in the frozen site directory, so nothing outside this list was missed.')",
                "lines.append('')",
                "lines.append('Method: the index page was used only to enumerate the model set. Every figure in the table above comes from the model detail pages, which are the pages buyers actually check out from and therefore the operational source of truth for price. Where the index disagreed, the detail price was kept and the disagreement was recorded rather than silently resolved, because a quiet fix would hide a merchandising error that will keep costing conversions until someone corrects the index at the source. Buyers who saw the lower index price and reach a higher checkout price are the most likely of all visitors to abandon the purchase entirely.')",
                "open('report.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('wrote report.md', conflicts)",
            ]
        )
        write_task(
            spec["id"],
            2,
            "web_research",
            "Extract every " + spec["product"] + " model from the frozen site in site/ (index plus one detail page per model). Detail pages are the source of truth for price. Write report.md listing each model with its true price and key spec, and flag any price contradiction between the index and a detail page in a section that uses the word 'contradiction'. Site snapshot: {{snapshot}}; depth: {{depth}}.",
            {
                "snapshot": {"type": "enum", "values": ["2026-10 capture", "frozen capture", "archived capture"]},
                "depth": {"type": "enum", "values": ["full", "standard", "quick"]},
            },
            checks,
            rubric_list=rubric(
                "True (detail-page) prices extracted; the contradiction model identified exactly.",
                "All models, prices, specs, and the contradiction section present.",
                "Catches the index/detail disagreement instead of copying either blindly.",
                "Detail pages treated as truth; report.md delivered.",
            ),
            task_md="# Site extraction — " + spec["product"] + "\n\nExtract all models from `site/`; detail pages are price truth; flag contradictions. Deliver `report.md`.\n",
            rubric_text=rubric_md(spec["id"], "True prices; contradiction named.", "All models plus contradiction.", "Disagreement caught.", "report.md delivered."),
            fixtures=fixtures,
            smoke=[shell("ls site"), py(solver_code), deliver("report.md", "Extracted the site and flagged the price contradiction.")],
            pinned_params={"snapshot": "2026-10 capture", "depth": "full"},
        )


# -- Ultra family U-01: market-entry dossiers --------------------------------------

DOSSIER_MARKETS: list[dict[str, Any]] = [
    {"id": "ultra-research-001", "market": "home battery storage", "state": "Texas",
     "competitors": ["Tesla Powerwall", "Enphase", "Generac", "FranklinWH", "Sonnen", "LG Chem RESU", "Panasonic EverVolt", "Bluetti", "EcoFlow", "Jackery"],
     "regs": ["SB 1699", "ERCOT", "net metering"]},
    {"id": "ultra-research-002", "market": "public EV charging", "state": "Florida",
     "competitors": ["ChargePoint", "Blink", "EVgo", "Electrify America", "Tesla Supercharger", "ABB E-mobility", "FLO", "Siemens", "Wallbox", "Enel X Way"],
     "regs": ["NEVI", "Florida Statutes 366.94", "FDOT EV Master Plan"]},
    {"id": "ultra-research-003", "market": "residential solar", "state": "Arizona",
     "competitors": ["SunPower", "Tesla Solar", "Sunrun", "Vivint Solar", "Freedom Solar", "Elevation Solar", "Harmon Solar", "Solar Topps", "Semper Solaris", "Palmetto"],
     "regs": ["Arizona Corporation Commission", "net metering grandfathering", "APS interconnection"]},
    {"id": "ultra-research-006", "market": "heat pump installation", "state": "Georgia",
     "competitors": ["Trane", "Carrier", "Lennox", "Rheem", "Goodman", "Mitsubishi Electric", "Daikin", "Bosch", "LG", "Fujitsu"],
     "regs": ["SEER2 standards", "IRA 25C tax credit", "Georgia Power rebates"]},
    {"id": "ultra-research-007", "market": "vertical farming", "state": "Colorado",
     "competitors": ["Plenty", "AeroFarms", "Bowery Farming", "AppHarvest", "Kalera", "Gotham Greens", "BrightFarms", "Local Bounti", "Revol Greens", "80 Acres Farms"],
     "regs": ["prior appropriation doctrine", "Colorado Department of Agriculture", "energy code"]},
]

TIERS = ["premium", "mid-market", "value", "premium", "mid-market", "value", "premium", "mid-market", "value", "premium"]
ANGLES = ["installer network depth", "brand recognition with homeowners", "battery chemistry and warranty terms", "utility partnership programs", "direct-to-consumer pricing", "regional service coverage", "financing offers", "software and monitoring platform", "retail distribution", "commercial segment focus"]


def build_ultra_dossiers() -> None:
    for spec in DOSSIER_MARKETS:
        competitors = [
            {"name": name, "tier": TIERS[i], "angle": ANGLES[i]} for i, name in enumerate(spec["competitors"])
        ]
        fixtures = {
            "competitors.json": json.dumps({"market": spec["market"], "state": spec["state"], "competitors": competitors}, indent=2),
            "regulations.md": "# Regulatory notes — " + spec["state"] + "\n\nKey frameworks for " + spec["market"] + " in " + spec["state"] + ": " + "; ".join(spec["regs"]) + ". Each framework shapes interconnection, incentives, or operating requirements and must be addressed in the entry plan.\n",
        }
        checks = [
            {"id": "competitors_profiled", "check": "regex_all", "params": {"patterns": spec["competitors"]}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "regulations_addressed", "check": "regex_all", "params": {"patterns": spec["regs"]}, "caps": {"correctness": 20}},
            {"id": "risk_register_complete", "check": "regex_all", "params": {"patterns": ["Risk " + str(i) for i in range(1, 9)]}, "caps": {"completeness": 15}},
            {"id": "dossier_length", "check": "word_count", "params": {"min": 2200, "max": 6000}, "caps": {"instruction_adherence": 5}},
        ]
        part1 = "\n".join(
            [
                "import json",
                "d = json.load(open('competitors.json'))",
                "lines = ['# Market entry dossier: ' + d['market'] + ' in ' + d['state'], '']",
                "lines.append('## Executive summary')",
                "lines.append('This dossier assesses entering the ' + d['market'] + ' market in ' + d['state'] + '. It profiles all ten tracked competitors, addresses the regulatory frameworks that gate entry, registers the eight risks that most threaten the plan, and closes with a sequenced recommendation. The work is staged across sessions with memory.md carrying state, per the run protocol for long tasks.')",
                "lines.append('')",
                "lines.append('## Market structure')",
                "lines.append('The market splits into three tiers that behave like separate businesses. The premium tier sells on trust, warranty depth, and installed base, and it tolerates entrants poorly because its customers are the least price-sensitive and the most reference-driven. The mid-market tier is where most volume sits and where an entrant with a credible service story can win share fastest, because buyers there actively compare two or three quotes. The value tier is a financing and channel game: distribution partnerships matter more than product differences, and margins are thin enough that a single bad quarter of acquisition spending can erase a year of progress. Entry sequencing should therefore start mid-market, borrow credibility upward into premium accounts with documented results, and treat the value tier as a later channel decision rather than a launch position.')",
                "lines.append('Demand in this state is also seasonal and policy-sensitive in ways the competitor profiles below only hint at. Weather events, incentive deadlines, and utility program windows all bunch demand into short periods when installer and sales capacity, not lead flow, is the constraint. An entrant that staffs for average demand will fail exactly when the market is most winnable, so the plan should staff for the peak windows the regulatory calendar creates and use the quiet months for training, permitting groundwork, and reference-account cultivation.')",
                "lines.append('')",
                "lines.append('## Competitor profiles')",
                "for c in d['competitors']:",
                "    lines.append('### ' + c['name'])",
                "    lines.append(c['name'] + ' competes at the ' + c['tier'] + ' tier, leading with ' + c['angle'] + '. That position is defensible because it aligns with how buyers in this state actually choose: they shortlist on trust and installed base, then negotiate on price within the tier. A new entrant should not expect to displace this competitor head-on in year one; the realistic play is to win the customers its model serves worst, document those wins, and expand from that beachhead once reference accounts exist in-state. Its likely response to a credible entrant is a targeted price or financing offer in the launch metro rather than a statewide reaction, which means the entrant should model a local price war of two to three quarters, not a permanent margin reset, and should avoid building a cost structure that only works if no response comes.')",
                "    lines.append('')",
                "open('dossier.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('part 1 written')",
            ]
        )
        part2 = "\n".join(
            [
                "regs = " + json.dumps(spec["regs"]),
                "lines = ['', '## Regulatory landscape']",
                "for r in regs:",
                "    lines.append('The framework ' + r + ' directly shapes this entry: it defines either who may sell, how installations connect and get credited, or which incentives offset customer acquisition cost. The entry plan budgets compliance time against ' + r + ' before launch marketing spends anything, because retrofitting compliance after customers are signed is the most common unforced error in this market.')",
                "lines.append('')",
                "lines.append('## Risk register')",
                "risks = ['Incumbent price response in the launch metro', 'Permitting and interconnection delays', 'Installer or technician labor scarcity', 'Incentive program changes mid-year', 'Customer acquisition cost above model', 'Supply chain lead times on core hardware', 'Regulatory interpretation shifts at the state level', 'Early reliability issues damaging reference accounts']",
                "for i, risk in enumerate(risks, 1):",
                "    lines.append('Risk {}: {}. Mitigation: assign an owner, a leading indicator, and a pre-agreed response before launch; review monthly in the first year.'.format(i, risk))",
                "lines.append('')",
                "lines.append('## Recommendation')",
                "lines.append('Enter in one metro first, sell against the weakest-served tier, and hold the second metro until the risk register has two clean quarterly reviews. The competitor set is strong but segmented; the regulatory load is real but knowable in advance; and the state rewards operators who sequence compliance, references, and only then scale. That sequence, followed patiently, is the whole strategy.')",
                "lines.append('')",
                "lines.append('## How to use this dossier')",
                "lines.append('Read the competitor profiles before any pricing decision, the regulatory section before any hiring commitment, and the risk register before any lease signature. Each section was written to be lifted directly into the planning documents for its decision, and the memory file records which sources were used so a future refresh can diff new data against this baseline instead of starting over. Refresh the dossier when any tracked competitor changes tier strategy, when a named regulatory framework is amended, or every two quarters, whichever comes first.')",
                "with open('dossier.md', 'a') as fh:",
                "    fh.write(chr(10).join(lines) + chr(10))",
                "print('part 2 appended')",
            ]
        )
        memory_text = "# Run memory — " + spec["id"] + "\n\nSession 1: read competitors.json and regulations.md; profiled all 10 competitors into dossier.md part 1.\nSession 2: appended regulatory landscape for " + ", ".join(spec["regs"]) + ", the 8-item risk register, and the recommendation.\nState: dossier.md complete; no open questions; ground truth files unchanged.\n"
        write_task(
            spec["id"],
            3,
            "research_synthesis",
            "Produce a market-entry dossier for " + spec["market"] + " in " + spec["state"] + " (2200-6000 words) in dossier.md, working in stages and keeping a memory.md updated between stages. Profile every competitor in competitors.json, address every framework named in regulations.md, include a risk register with items labeled Risk 1 through Risk 8, and close with a sequenced recommendation. Region focus: {{region_focus}}; posture: {{posture}}.",
            {
                "region_focus": {"type": "enum", "values": ["single metro first", "statewide", "two metros"]},
                "posture": {"type": "enum", "values": ["aggressive", "measured", "partnership-led"]},
            },
            checks,
            rubric_list=rubric(
                "All competitors and regulatory frameworks covered accurately from the source pack.",
                "Profiles, regulation, 8-risk register, and recommendation all present at length.",
                "Uses the staged memory protocol and recovers context between stages.",
                "Memory file maintained; dossier.md delivered.",
            ),
            task_md="# Market entry dossier — " + spec["market"] + ", " + spec["state"] + "\n\nProfile all competitors in `competitors.json`, address `regulations.md`, register Risk 1-8, recommend a sequence. Keep `memory.md` updated between stages. Deliver `dossier.md`.\n",
            rubric_text=rubric_md(spec["id"], "Competitors and regulations covered accurately.", "All sections at full length.", "Staged memory protocol used.", "memory.md maintained; dossier.md delivered."),
            fixtures=fixtures,
            smoke=[
                write("memory.md", "# Run memory — " + spec["id"] + "\n\nSession 1 in progress: profiling competitors.\n"),
                py(part1),
                write("memory.md", memory_text),
                py(part2),
                deliver("dossier.md", "Completed the market-entry dossier across two staged sessions with memory.md maintained."),
            ],
            pinned_params={"region_focus": "single metro first", "posture": "measured"},
        )


# -- Ultra: relocation with a mid-task change ---------------------------------------

RELOCATIONS: list[dict[str, Any]] = [
    {"id": "ultra-planning-001", "route": "Austin to Denver",
     "movers": [("SwiftMove", 4200), ("CityMove", 4800), ("HeavyLifters", 5600)],
     "leases": [("Loft B", 2800), ("Loft A", 3200), ("Loft C", 3900)],
     "it_cost": 1000, "cap": 8000, "final": ("SwiftMove", "Loft B", 8000)},
    {"id": "ultra-planning-002", "route": "Charlotte to Nashville",
     "movers": [("SwiftMove", 3900), ("CityMove", 4400), ("HeavyLifters", 5100)],
     "leases": [("Suite 100", 2600), ("Suite 200", 3100), ("Suite 300", 3600)],
     "it_cost": 900, "cap": 7500, "final": ("SwiftMove", "Suite 100", 7400)},
]


def build_relocations() -> None:
    for spec in RELOCATIONS:
        fixtures = {
            "movers.json": json.dumps({"movers": [{"name": n, "price": p} for n, p in spec["movers"]]}, indent=2),
            "leases.json": json.dumps({"leases": [{"name": n, "monthly": p} for n, p in spec["leases"]]}, indent=2),
            "CHANGE.md": "# Budget change (issued mid-task)\n\nFinance has cut the first-month relocation cap to $" + str(spec["cap"]) + " total (moving + first month lease + IT setup). Revise the plan to fit the new cap and document the change in a 'Change log' section.\n",
        }
        derived = [{"name": "expected", "key": "{{scenario}}", "map": {s: {"mover": spec["final"][0], "lease": spec["final"][1], "total": float(spec["final"][2])} for s in ["base", "revised", "audit"]}}]
        checks = [
            {"id": "final_picks", "check": "regex_all", "params": {"patterns": ["{{expected.mover}}", "{{expected.lease}}"]}, "caps": {"correctness": 25, "completeness": 15}},
            {"id": "final_total_within_cap", "check": "numeric_within", "params": {"label": "total", "value": "{{expected.total}}", "tolerance": 1.0}, "caps": {"correctness": 20}},
            {"id": "change_documented", "check": "file_contains", "params": {"path": "plan.md", "patterns": ["Change log"]}, "caps": {"completeness": 15}},
            {"id": "plan_length", "check": "word_count", "params": {"min": 200, "max": 800}, "caps": {"instruction_adherence": 5}},
        ]
        draft_code = "\n".join(
            [
                "import json",
                "movers = json.load(open('movers.json'))['movers']",
                "leases = json.load(open('leases.json'))['leases']",
                "mover = sorted(movers, key=lambda m: m['price'])[1]",
                "lease = sorted(leases, key=lambda l: l['monthly'])[1]",
                "total = mover['price'] + lease['monthly'] + " + str(spec["it_cost"]),
                "lines = ['# Relocation plan: " + spec["route"] + " (draft)', '', 'Mover: {} at ${}. Lease: {} at ${} per month. IT setup: ${}. Total: ${}.'.format(mover['name'], mover['price'], lease['name'], lease['monthly'], " + str(spec["it_cost"]) + ", total)]",
                "open('plan.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('draft total', total)",
            ]
        )
        final_code = "\n".join(
            [
                "import json",
                "movers = json.load(open('movers.json'))['movers']",
                "leases = json.load(open('leases.json'))['leases']",
                "cap = " + str(spec["cap"]),
                "best = None",
                "for m in movers:",
                "    for l in leases:",
                "        total = m['price'] + l['monthly'] + " + str(spec["it_cost"]),
                "        if total <= cap and (best is None or total > best[2]):",
                "            best = (m, l, total)",
                "mover, lease, total = best",
                "lines = ['# Relocation plan: " + spec["route"] + " (final)', '']",
                "lines.append('Mover: {} at ${}. Lease: {} at ${} per month. IT setup: ${}. Total: ${}.'.format(mover['name'], mover['price'], lease['name'], lease['monthly'], " + str(spec["it_cost"]) + ", total))",
                "lines.append('')",
                "lines.append('## Change log')",
                "lines.append('Finance cut the first-month cap to ${} mid-task. The draft plan exceeded the new cap, so the mover and lease picks were revised to the most expensive combination that fits: {} with {}. The IT setup line is fixed and was not negotiable. All other plan elements (dates, headcount, sequence) are unchanged, and the savings versus the draft come entirely from the mover and lease substitutions documented here.'.format(cap, mover['name'], lease['name']))",
                "lines.append('')",
                "lines.append('## Sequence')",
                "lines.append('Week 1: sign the revised lease and book the mover against the new figures in this plan. Week 2: IT walkthrough at the new space, network drop scheduled against the fixed setup budget. Week 3: pack and label by team, freeze non-essential purchases. Week 4: move weekend, Monday standup in the new office, and a week-one snag list reviewed with the mover and landlord before final invoices are approved against this plan.')",
                "lines.append('')",
                "lines.append('Notes: the revised combination deliberately spends up to the cap rather than minimizing cost, because the lease quality difference compounds over the full term while the mover difference is one-time. If finance cuts again, the next lever is the lease start date, not the mover, and that trade should be escalated rather than absorbed silently.')",
                "open('plan.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('final total', total)",
            ]
        )
        write_task(
            spec["id"],
            3,
            "planning",
            "Plan the office relocation " + spec["route"] + " in plan.md: pick a mover from movers.json and a lease from leases.json, add the flat IT setup cost of $" + str(spec["it_cost"]) + ", and print the first-month total as 'Total: $X'. During the task a CHANGE.md will appear with a revised budget cap: revise the plan to the most expensive combination that fits the cap and document it in a 'Change log' section. Scenario: {{scenario}}.",
            {"scenario": {"type": "enum", "values": ["base", "revised", "audit"]}},
            checks,
            rubric_list=rubric(
                "Final picks are the most expensive combination inside the revised cap; total exact.",
                "Draft, change response, and change log all present.",
                "Detects and adapts to the mid-task change instead of delivering the stale draft.",
                "Change documented in the required section; plan.md delivered.",
            ),
            task_md="# Relocation — " + spec["route"] + "\n\nPick a mover and lease, add IT setup, print 'Total: $X'. A `CHANGE.md` budget cut arrives mid-task: revise and document it. Deliver `plan.md`.\n",
            rubric_text=rubric_md(spec["id"], "Final combo fits the cap optimally; total exact.", "Plan plus change log complete.", "Mid-task change absorbed correctly.", "plan.md delivered."),
            derived_params=derived,
            fixtures=fixtures,
            smoke=[read("movers.json"), py(draft_code), read("CHANGE.md"), py(final_code), deliver("plan.md", "Revised the relocation plan under the new cap with a documented change log.")],
            pinned_params={"scenario": "revised"},
        )


# -- Ultra: quarter-close reconciliation ----------------------------------------------

QCLOSES: list[dict[str, Any]] = [
    {"id": "ultra-data-001", "months": [("october", [("O1", 1000), ("O2", 500)]), ("november", [("N1", 2000), ("N2", 250)]), ("december", [("D1", 3000), ("D2", -200)])],
     "corrections": [("O2", 550), ("D1", 2900)], "totals": {"october": 1550.0, "november": 2250.0, "december": 2700.0, "quarter": 6500.0}},
    {"id": "ultra-data-002", "months": [("january", [("J1", 700), ("J2", 500)]), ("february", [("F1", 1000), ("F2", 800)]), ("march", [("M1", 1400), ("M2", 1000)])],
     "corrections": [("J1", 800), ("M1", 1100)], "totals": {"january": 1300.0, "february": 1800.0, "march": 2100.0, "quarter": 5200.0}},
]


def build_qcloses() -> None:
    for spec in QCLOSES:
        fixtures: dict[str, str] = {}
        for month, rows in spec["months"]:
            fixtures[month + ".csv"] = "order_id,amount\n" + "\n".join(oid + "," + str(amt) for oid, amt in rows) + "\n"
        fixtures["corrections.csv"] = "order_id,corrected_amount\n" + "\n".join(oid + "," + str(amt) for oid, amt in spec["corrections"]) + "\n"
        month_names = [m for m, _ in spec["months"]]
        checks: list[dict[str, Any]] = []
        for month in month_names:
            checks.append({"id": month + "_total", "check": "numeric_within", "params": {"label": month + " total", "value": spec["totals"][month], "tolerance": 1.0}, "caps": {"correctness": 20}})
        checks.append({"id": "quarter_total", "check": "numeric_within", "params": {"label": "quarter total", "value": spec["totals"]["quarter"], "tolerance": 1.0}, "caps": {"correctness": 25}})
        checks.append({"id": "corrections_applied", "check": "regex_all", "params": {"patterns": [c[0] for c in spec["corrections"]]}, "caps": {"completeness": 15}})
        solver_code = "\n".join(
            [
                "import csv",
                "corrections = {}",
                "for r in csv.DictReader(open('corrections.csv')):",
                "    corrections[r['order_id']] = float(r['corrected_amount'])",
                "lines = ['# Quarter close ledger', '']",
                "quarter = 0.0",
                "for month in " + json.dumps(month_names) + ":",
                "    total = 0.0",
                "    for r in csv.DictReader(open(month + '.csv')):",
                "        total += corrections.get(r['order_id'], float(r['amount']))",
                "    quarter += total",
                "    lines.append('{} total: ${:,.2f}'.format(month.capitalize(), total))",
                "lines.append('Quarter total: ${:,.2f}'.format(quarter))",
                "lines.append('')",
                "lines.append('Corrections applied from corrections.csv: " + ", ".join(c[0] + " corrected to $" + str(c[1]) for c in spec["corrections"]) + ". Each correction replaces the original booked amount for that order before month totals are struck, so the ledger ties to the corrected source of truth rather than the originally filed figures. No other orders were adjusted.')",
                "open('ledger.md', 'w').write(chr(10).join(lines) + chr(10))",
                "print('wrote ledger.md')",
            ]
        )
        write_task(
            spec["id"],
            3,
            "data_analysis",
            "Close the quarter from the three monthly files (" + ", ".join(m + ".csv" for m in month_names) + ") plus corrections.csv. Each correction replaces the booked amount for its order. Write ledger.md printing each month as '<Month> total: $X' and 'Quarter total: $X', naming every corrected order. Keep a memory.md of the close steps. Quarter: {{quarter}}; book: {{book}}.",
            {
                "quarter": {"type": "enum", "values": ["current", "audit rerun", "final"]},
                "book": {"type": "enum", "values": ["primary", "consolidated", "management"]},
            },
            checks,
            rubric_list=rubric(
                "Every month total and the quarter total match the corrected ground truth.",
                "All months, quarter total, and every correction named.",
                "Applies the correction batch instead of closing on stale figures.",
                "memory.md maintained; ledger.md delivered.",
            ),
            task_md="# Quarter close\n\nApply `corrections.csv` over the three monthly files; print each '<Month> total: $X' and 'Quarter total: $X' in `ledger.md`. Keep `memory.md` updated.\n",
            rubric_text=rubric_md(spec["id"], "Corrected totals exact.", "Months, quarter, corrections named.", "Corrections applied, not ignored.", "ledger.md delivered."),
            fixtures=fixtures,
            smoke=[
                write("memory.md", "# Close memory — " + spec["id"] + "\n\nStep 1: load corrections, then strike month totals.\n"),
                py(solver_code),
                deliver("ledger.md", "Closed the quarter with corrections applied; ledger.md delivered."),
            ],
            pinned_params={"quarter": "final", "book": "primary"},
        )


# -- Ultra: procurement with scored vendor responses ------------------------------------

PROCUREMENTS: list[dict[str, Any]] = [
    {"id": "ultra-research-004", "need": "a CRM platform", "weights": {"price": 40, "features": 35, "support": 25},
     "vendors": [("Vendor A", {"price": 8, "features": 9, "support": 7}), ("Vendor B", {"price": 9, "features": 7, "support": 8}), ("Vendor C", {"price": 7, "features": 8, "support": 9})],
     "winner": "Vendor A", "winning": 8.10, "totals": ["8.10", "8.05", "7.85"]},
    {"id": "ultra-research-005", "need": "cloud hosting", "weights": {"price": 50, "features": 30, "support": 20},
     "vendors": [("Vendor A", {"price": 9, "features": 6, "support": 7}), ("Vendor B", {"price": 7, "features": 9, "support": 8}), ("Vendor C", {"price": 8, "features": 8, "support": 6})],
     "winner": "Vendor B", "winning": 7.80, "totals": ["7.70", "7.80", "7.60"]},
]


def build_procurements() -> None:
    for spec in PROCUREMENTS:
        fixtures = {
            "rfp.md": "# RFP — " + spec["need"] + "\n\nScoring weights: " + ", ".join(k + " " + str(v) + "%" for k, v in spec["weights"].items()) + ". Vendor scores (0-10 per criterion) are in scores.json. The award goes to the highest weighted total.\n",
            "scores.json": json.dumps({"weights": spec["weights"], "vendors": [{"name": v[0], "scores": v[1]} for v in spec["vendors"]]}, indent=2),
        }
        checks = [
            {"id": "matrix_exists", "check": "file_exists", "params": {"path": "matrix.csv"}, "caps": {"completeness": 15}},
            {"id": "matrix_values", "check": "file_contains", "params": {"path": "matrix.csv", "patterns": ["Vendor A", "Vendor B", "Vendor C"] + spec["totals"]}, "caps": {"correctness": 25}},
            {"id": "winner_named", "check": "regex_all", "params": {"patterns": [spec["winner"]]}, "caps": {"correctness": 20}},
            {"id": "winning_score", "check": "numeric_within", "params": {"label": "winning score", "value": spec["winning"], "tolerance": 0.05}, "caps": {"correctness": 20}},
        ]
        solver_code = "\n".join(
            [
                "import csv, io, json",
                "d = json.load(open('scores.json'))",
                "weights = d['weights']",
                "rows = []",
                "for v in d['vendors']:",
                "    total = sum(v['scores'][k] * weights[k] for k in weights) / 100.0",
                "    rows.append((v['name'], round(total, 2)))",
                "rows.sort(key=lambda r: -r[1])",
                "out = io.StringIO()",
                "w = csv.writer(out)",
                "w.writerow(['vendor', 'weighted_total'])",
                "for name, total in rows:",
                "    w.writerow([name, '{:.2f}'.format(total)])",
                "open('matrix.csv', 'w').write(out.getvalue())",
                "winner, score = rows[0]",
                "memo = ['# Award memo — " + spec["need"] + "', '', 'The scoring matrix (matrix.csv) applies the RFP weights to the vendor scores exactly as published. {} wins with a winning score of {:.2f}. The margin over the runner-up is small, so the award is conditional on reference checks confirming the support scores, and the contract should carry a one-year term with an exit clause rather than a multi-year lock-in at this margin.'.format(winner, score)]",
                "open('memo.md', 'w').write(chr(10).join(memo) + chr(10))",
                "print('winner', winner, score)",
            ]
        )
        write_task(
            spec["id"],
            3,
            "research_synthesis",
            "Run the procurement for " + spec["need"] + ": apply the weights in scores.json (published in rfp.md) to each vendor's criterion scores, write the scoring matrix to matrix.csv (columns vendor, weighted_total, one row per vendor), and write memo.md naming the winner with 'Winning score: X.XX'. Round weighted totals to 2 decimals. Round: {{round}}; committee: {{committee}}.",
            {
                "round": {"type": "enum", "values": ["final", "rerun", "audit"]},
                "committee": {"type": "enum", "values": ["standard", "expanded", "executive"]},
            },
            checks,
            rubric_list=rubric(
                "Weighted totals computed exactly per the published weights; winner correct.",
                "Full matrix plus a reasoned award memo.",
                "Follows the published scoring instead of substituting judgment.",
                "matrix.csv and memo.md both delivered; winner named in the memo.",
            ),
            task_md="# Procurement — " + spec["need"] + "\n\nApply the weights in `scores.json` to the vendor scores; write `matrix.csv` and an award `memo.md` naming the winner and its winning score.\n",
            rubric_text=rubric_md(spec["id"], "Weighted math exact; winner correct.", "Matrix plus memo.", "Published scoring followed.", "memo.md delivered; matrix.csv present with exact totals."),
            fixtures=fixtures,
            smoke=[read("rfp.md"), py(solver_code), deliver("memo.md", "Scored the vendors, wrote matrix.csv and the award memo naming the winner.")],
            pinned_params={"round": "final", "committee": "standard"},
        )


# -- Ultra: full-stack builds and legacy migrations (reuse code_build) --------------

TEAM_APP_IMPL = '''"""Team invitations backed by sqlite (see SPEC_FEATURE.md)."""

import secrets
import sqlite3


def init_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS teams (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS members (team_id INTEGER, email TEXT, status TEXT, token TEXT)")
    conn.commit()
    return conn


def create_team(conn, name):
    cur = conn.execute("INSERT INTO teams (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def invite_member(conn, team_id, email):
    token = secrets.token_hex(8)
    conn.execute("INSERT INTO members (team_id, email, status, token) VALUES (?, ?, 'invited', ?)", (team_id, email, token))
    conn.commit()
    return token


def accept_invite(conn, token):
    row = conn.execute("SELECT team_id, email FROM members WHERE token = ? AND status = 'invited'", (token,)).fetchone()
    if row is None:
        return False
    conn.execute("UPDATE members SET status = 'active' WHERE token = ?", (token,))
    conn.commit()
    return True


def list_members(conn, team_id, status=None):
    if status is None:
        rows = conn.execute("SELECT email FROM members WHERE team_id = ? ORDER BY email", (team_id,)).fetchall()
    else:
        rows = conn.execute("SELECT email FROM members WHERE team_id = ? AND status = ? ORDER BY email", (team_id, status)).fetchall()
    return [r[0] for r in rows]
'''

TEAM_APP_TESTS = '''from team_app import accept_invite, create_team, init_db, invite_member, list_members


def _setup(tmp_path):
    conn = init_db(str(tmp_path / "app.db"))
    team = create_team(conn, "Core")
    return conn, team


def test_invite_and_accept(tmp_path):
    conn, team = _setup(tmp_path)
    token = invite_member(conn, team, "a@example.com")
    assert list_members(conn, team, status="active") == []
    assert accept_invite(conn, token) is True
    assert list_members(conn, team, status="active") == ["a@example.com"]


def test_accept_unknown_token_fails(tmp_path):
    conn, team = _setup(tmp_path)
    assert accept_invite(conn, "deadbeef") is False


def test_double_accept_fails(tmp_path):
    conn, team = _setup(tmp_path)
    token = invite_member(conn, team, "a@example.com")
    assert accept_invite(conn, token) is True
    assert accept_invite(conn, token) is False


def test_teams_are_isolated(tmp_path):
    conn, team = _setup(tmp_path)
    other = create_team(conn, "Other")
    invite_member(conn, team, "a@example.com")
    assert list_members(conn, other) == []
'''

BILLING_APP_IMPL = '''"""Usage billing backed by sqlite (see SPEC_FEATURE.md)."""

import sqlite3

FREE_EVENTS = 1000
TIER1_RATE = 0.01
TIER2_THRESHOLD = 10000
TIER2_RATE = 0.008


def init_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS events (customer TEXT, month TEXT, units INTEGER)")
    conn.commit()
    return conn


def record_event(conn, customer, month, units=1):
    conn.execute("INSERT INTO events (customer, month, units) VALUES (?, ?, ?)", (customer, month, units))
    conn.commit()


def monthly_usage(conn, customer, month):
    row = conn.execute("SELECT COALESCE(SUM(units), 0) FROM events WHERE customer = ? AND month = ?", (customer, month)).fetchone()
    return int(row[0])


def invoice_total(conn, customer, month):
    usage = monthly_usage(conn, customer, month)
    billable = max(0, usage - FREE_EVENTS)
    tier1 = min(billable, TIER2_THRESHOLD - FREE_EVENTS)
    tier2 = max(0, billable - tier1)
    return round(tier1 * TIER1_RATE + tier2 * TIER2_RATE, 2)
'''

BILLING_APP_TESTS = '''from billing_app import init_db, invoice_total, monthly_usage, record_event


def _setup(tmp_path):
    return init_db(str(tmp_path / "billing.db"))


def test_usage_sums_units(tmp_path):
    conn = _setup(tmp_path)
    record_event(conn, "acme", "2026-10", 40)
    record_event(conn, "acme", "2026-10", 2)
    record_event(conn, "acme", "2026-11", 5)
    assert monthly_usage(conn, "acme", "2026-10") == 42


def test_free_tier_costs_nothing(tmp_path):
    conn = _setup(tmp_path)
    record_event(conn, "acme", "2026-10", 1000)
    assert invoice_total(conn, "acme", "2026-10") == 0.0


def test_tier1_pricing(tmp_path):
    conn = _setup(tmp_path)
    record_event(conn, "acme", "2026-10", 1500)
    assert invoice_total(conn, "acme", "2026-10") == 5.0


def test_tier2_pricing(tmp_path):
    conn = _setup(tmp_path)
    record_event(conn, "acme", "2026-10", 11000)
    # 9000 events at 0.01 + 1000 events at 0.008 = 90 + 8 = 98
    assert invoice_total(conn, "acme", "2026-10") == 98.0
'''

BLOG_HANDLERS_IMPL = '''"""Blog API, migrated layout with token auth (see SPEC_FEATURE.md and CHANGE.md)."""


class BlogAPI:
    def __init__(self, token):
        self._token = token
        self._posts = {}
        self._next_id = 1

    def _require_auth(self, auth):
        if auth != self._token:
            raise PermissionError("invalid or missing token")

    def create_post(self, auth, title, body):
        self._require_auth(auth)
        post_id = self._next_id
        self._next_id += 1
        self._posts[post_id] = {"id": post_id, "title": title, "body": body}
        return post_id

    def get_post(self, auth, post_id):
        self._require_auth(auth)
        return self._posts.get(post_id)

    def list_posts(self, auth):
        self._require_auth(auth)
        return [self._posts[k] for k in sorted(self._posts)]
'''

BLOG_TESTS = '''import pytest

from handlers import BlogAPI

TOKEN = "s3cret"


def test_create_and_get():
    api = BlogAPI(TOKEN)
    pid = api.create_post(TOKEN, "Hello", "World")
    post = api.get_post(TOKEN, pid)
    assert post["title"] == "Hello" and post["body"] == "World"


def test_auth_required_on_create():
    api = BlogAPI(TOKEN)
    with pytest.raises(PermissionError):
        api.create_post("wrong", "Hello", "World")


def test_auth_required_on_read():
    api = BlogAPI(TOKEN)
    pid = api.create_post(TOKEN, "Hello", "World")
    with pytest.raises(PermissionError):
        api.get_post("wrong", pid)
    with pytest.raises(PermissionError):
        api.list_posts(None)


def test_list_posts_in_order():
    api = BlogAPI(TOKEN)
    api.create_post(TOKEN, "One", "a")
    api.create_post(TOKEN, "Two", "b")
    titles = [p["title"] for p in api.list_posts(TOKEN)]
    assert titles == ["One", "Two"]
'''

ORDER_HANDLERS_IMPL = '''"""Order API, migrated layout with token auth (see SPEC_FEATURE.md and CHANGE.md)."""


class OrderAPI:
    def __init__(self, token):
        self._token = token
        self._orders = {}
        self._next_id = 1

    def _require_auth(self, auth):
        if auth != self._token:
            raise PermissionError("invalid or missing token")

    def create_order(self, auth, sku, qty, unit_price):
        self._require_auth(auth)
        order_id = self._next_id
        self._next_id += 1
        self._orders[order_id] = {"id": order_id, "sku": sku, "qty": qty, "unit_price": unit_price, "total": round(qty * unit_price, 2)}
        return order_id

    def get_order(self, auth, order_id):
        self._require_auth(auth)
        return self._orders.get(order_id)

    def order_total(self, auth, order_id):
        self._require_auth(auth)
        order = self._orders.get(order_id)
        return order["total"] if order else 0.0
'''

ORDER_TESTS = '''import pytest

from handlers import OrderAPI

TOKEN = "s3cret"


def test_create_and_total():
    api = OrderAPI(TOKEN)
    oid = api.create_order(TOKEN, "SKU1", 3, 10.0)
    assert api.order_total(TOKEN, oid) == 30.0
    assert api.get_order(TOKEN, oid)["sku"] == "SKU1"


def test_auth_required():
    api = OrderAPI(TOKEN)
    with pytest.raises(PermissionError):
        api.create_order("nope", "SKU1", 1, 1.0)
    oid = api.create_order(TOKEN, "SKU1", 1, 1.0)
    with pytest.raises(PermissionError):
        api.get_order("nope", oid)


def test_missing_order_total_is_zero():
    api = OrderAPI(TOKEN)
    assert api.order_total(TOKEN, 999) == 0.0
'''


def build_ultra_builds() -> None:
    memory_step = [write("memory.md", "# Build memory\n\nStage 1: read the spec and any CHANGE.md. Stage 2: implement, run acceptance tests, fix. Stage 3: summarize and deliver.\n")]
    code_build(
        "ultra-code-001", 3, "team_app.py", _starter("team_app.py", "Team invitations on sqlite."),
        "# Spec: team invitations (sqlite)\n\nFunctions: `init_db(path)` creates tables teams(id, name) and members(team_id, email, status, token) and returns a connection. `create_team(conn, name)` returns the team id. `invite_member(conn, team_id, email)` inserts an 'invited' member with a random hex token and returns the token. `accept_invite(conn, token)` flips an invited member to 'active' and returns True; unknown or already-accepted tokens return False. `list_members(conn, team_id, status=None)` returns member emails sorted, optionally filtered by status. Work in stages and keep memory.md updated.\n",
        TEAM_APP_TESTS, TEAM_APP_IMPL,
        "Implemented the sqlite-backed team invitations module: schema for teams and members, token-based invites with single-use acceptance semantics, and status-filtered member listing. Worked in stages with memory.md maintained. The full acceptance suite passes, including double-accept and team isolation cases.",
        "Build team_app.py to SPEC_FEATURE.md in the workspace (sqlite stdlib), keeping memory.md updated between stages. The acceptance suite in tests/ defines done. Do not modify the tests. Write summary.md and deliver it.",
        category="code_build", extra_steps=memory_step,
        extra_checks=[{"id": "memory_maintained", "check": "file_exists", "params": {"path": "memory.md"}, "caps": {"completeness": 10}}],
    )
    code_build(
        "ultra-code-002", 3, "billing_app.py", _starter("billing_app.py", "Usage billing on sqlite."),
        "# Spec: usage billing (sqlite)\n\nFunctions: `init_db(path)` creates an events(customer, month, units) table and returns a connection. `record_event(conn, customer, month, units=1)` stores usage units. `monthly_usage(conn, customer, month)` returns summed units (0 when none). `invoice_total(conn, customer, month)`: the first 1000 units are free; units 1001-10000 cost $0.01 each; units above 10000 cost $0.008 each; return the total rounded to 2 decimals. Work in stages and keep memory.md updated.\n",
        BILLING_APP_TESTS, BILLING_APP_IMPL,
        "Implemented the sqlite usage-billing module with the three-tier price curve: the first thousand units free, the next nine thousand at a cent each, and heavier usage at the reduced rate, rounded to cents. Staged the work with memory.md maintained throughout. The acceptance suite passes on usage summation and all three pricing tiers.",
        "Build billing_app.py to SPEC_FEATURE.md in the workspace (sqlite stdlib), keeping memory.md updated between stages. The acceptance suite in tests/ defines done. Do not modify the tests. Write summary.md and deliver it.",
        category="code_build", extra_steps=memory_step,
        extra_checks=[{"id": "memory_maintained", "check": "file_exists", "params": {"path": "memory.md"}, "caps": {"completeness": 10}}],
    )
    legacy_blog = '"""Legacy blog handlers (function style, no auth)."""\n\nPOSTS = {}\n\n\ndef create_post(title, body):\n    pid = len(POSTS) + 1\n    POSTS[pid] = {"id": pid, "title": title, "body": body}\n    return pid\n\n\ndef get_post(post_id):\n    return POSTS.get(post_id)\n'
    code_build(
        "ultra-code-003", 3, "handlers.py", '"""New handlers module: migrate legacy_app.py here per SPEC_FEATURE.md."""\n',
        "# Spec: migrate the blog API\n\nMigrate legacy_app.py (in the workspace) to a class-based layout in handlers.py: class `BlogAPI(token)` with methods create_post(auth, title, body) returning an id, get_post(auth, post_id) returning the post dict or None, and list_posts(auth) returning posts in id order. Behavior must match the legacy semantics. CHANGE.md in the workspace adds a requirement that applies to every method.\n",
        BLOG_TESTS, BLOG_HANDLERS_IMPL,
        "Migrated the legacy function-style blog handlers to a class-based BlogAPI with identical storage semantics, and implemented the mid-task CHANGE.md requirement: every method now requires the instance token and raises PermissionError on a missing or wrong token. Kept memory.md updated across stages. The acceptance suite passes, including all three auth cases.",
        "Migrate legacy_app.py to handlers.py per SPEC_FEATURE.md in the workspace, honoring the additional requirement in CHANGE.md, keeping memory.md updated. The acceptance suite in tests/ defines done. Write summary.md and deliver it.",
        category="code_build",
        extra_fixtures={"legacy_app.py": legacy_blog, "CHANGE.md": "# Mid-task change: authentication required\n\nProduct now requires token authentication on every handler. The API class is constructed with a token; every method takes an auth argument and must raise PermissionError when it does not match.\n"},
        extra_steps=[read("CHANGE.md"), read("legacy_app.py"), write("memory.md", "# Migration memory\n\nStage 1: read legacy_app.py, SPEC_FEATURE.md, CHANGE.md (auth requirement noted). Stage 2: implement handlers.py with token auth on every method. Stage 3: tests green, summary written.\n")],
        extra_checks=[{"id": "memory_maintained", "check": "file_exists", "params": {"path": "memory.md"}, "caps": {"completeness": 10}}],
    )
    legacy_orders = '"""Legacy order handlers (function style, no auth)."""\n\nORDERS = {}\n\n\ndef create_order(sku, qty, unit_price):\n    oid = len(ORDERS) + 1\n    ORDERS[oid] = {"id": oid, "sku": sku, "qty": qty, "unit_price": unit_price, "total": round(qty * unit_price, 2)}\n    return oid\n\n\ndef get_order(order_id):\n    return ORDERS.get(order_id)\n'
    code_build(
        "ultra-code-004", 3, "handlers.py", '"""New handlers module: migrate legacy_app.py here per SPEC_FEATURE.md."""\n',
        "# Spec: migrate the order API\n\nMigrate legacy_app.py (in the workspace) to a class-based layout in handlers.py: class `OrderAPI(token)` with methods create_order(auth, sku, qty, unit_price) returning an id (order total is qty times unit_price, rounded to 2 decimals), get_order(auth, order_id) returning the order dict or None, and order_total(auth, order_id) returning the total or 0.0 for missing orders. CHANGE.md in the workspace adds a requirement that applies to every method.\n",
        ORDER_TESTS, ORDER_HANDLERS_IMPL,
        "Migrated the legacy order handlers to a class-based OrderAPI preserving the legacy total computation, and implemented the mid-task CHANGE.md authentication requirement on every method with PermissionError for bad tokens. Kept memory.md updated across stages. The acceptance suite passes, including the missing-order and auth cases.",
        "Migrate legacy_app.py to handlers.py per SPEC_FEATURE.md in the workspace, honoring the additional requirement in CHANGE.md, keeping memory.md updated. The acceptance suite in tests/ defines done. Write summary.md and deliver it.",
        category="code_build",
        extra_fixtures={"legacy_app.py": legacy_orders, "CHANGE.md": "# Mid-task change: authentication required\n\nProduct now requires token authentication on every handler. The API class is constructed with a token; every method takes an auth argument and must raise PermissionError when it does not match.\n"},
        extra_steps=[read("CHANGE.md"), read("legacy_app.py"), write("memory.md", "# Migration memory\n\nStage 1: read legacy_app.py, SPEC_FEATURE.md, CHANGE.md (auth requirement noted). Stage 2: implement handlers.py with token auth on every method. Stage 3: tests green, summary written.\n")],
        extra_checks=[{"id": "memory_maintained", "check": "file_exists", "params": {"path": "memory.md"}, "caps": {"completeness": 10}}],
    )


def main() -> int:
    builders = [
        build_vendor_family,
        build_buggy_repos,
        build_crash_family,
        build_sales_family,
        build_extra_data_family,
        build_quote_family,
        build_web_family,
        build_brief_family,
        build_trip_family,
        build_teardown_family,
        build_travel_family,
        build_feature_and_tool_builders,
        build_marathon_web,
        build_marathon_data,
        build_dossier_family,
        build_event_family,
        build_multipage_family,
        build_ultra_dossiers,
        build_relocations,
        build_qcloses,
        build_procurements,
        build_ultra_builds,
    ]
    for builder in builders:
        builder()
    seeds = [
        {"task_id": "sprint-data-001", "level": 1, "category": "data_analysis", "dir": "sprint/sprint-data-001", "pinned_params": {"region": "north", "top_n": 3}},
        {"task_id": "sprint-code-001", "level": 1, "category": "code_repair", "dir": "sprint/sprint-code-001", "pinned_params": {}},
        {"task_id": "sprint-vendor-001", "level": 1, "category": "research_synthesis", "dir": "sprint/sprint-vendor-001", "pinned_params": {"product": "crm", "business_type": "dental_practice"}},
    ]
    full_index = seeds + INDEX
    (ROOT / "bank_index.json").write_text(json.dumps(full_index, indent=2), encoding="utf-8")
    by_level = {1: 0, 2: 0, 3: 0}
    for entry in full_index:
        by_level[entry["level"]] += 1
    print("tasks:", len(full_index), "by level:", by_level)
    assert by_level == {1: 40, 2: 30, 3: 15}, by_level
    ids = [e["task_id"] for e in full_index]
    assert len(ids) == len(set(ids)), "duplicate task ids"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
