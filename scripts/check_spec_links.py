#!/usr/bin/env python3
"""Spec-link check (docs/plan/15 §9.4): every § reference in the docs
resolves to a real section.

Rules checked:
1. Every `docs/plan/<file>.md` path referenced in any doc exists.
2. A `§N` or `§N.M` reference resolves when the file it points at has a
   numbered heading `## N.` / `### N.M`. The target file is the one named in
   backticks immediately before the reference (e.g. `01-harness.md` §5), the
   plan doc whose number is the reference's zero-padded two-digit prefix
   (§09.1 means doc 09, section 1), or the file containing the reference.

Exits 1 and prints every unresolved reference.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLAN_DIR = REPO / "docs" / "plan"

SECTION_REF = re.compile(r"§(\d+)(?:\.(\d+))?")
FILE_THEN_SECTION = re.compile(r"`(\d{2}-[a-z0-9-]+\.md)`\s*§(\d+)(?:\.(\d+))?")
PATH_REF = re.compile(r"docs/plan/([0-9a-z-]+\.md)")


def heading_numbers(path: Path) -> set[str]:
    numbers: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"#{2,4}\s+(\d+(?:\.\d+)?)\b", line)
        if match:
            numbers.add(match.group(1))
            numbers.add(match.group(1).split(".")[0])
        if re.match(r"#{2,4}\s+Decisions\b", line):
            numbers.add("0")  # the Decisions preamble is §0 by convention
    return numbers


def main() -> int:
    docs = sorted((REPO / "docs").rglob("*.md")) + [REPO / "SPEC.md", REPO / "README.md"]
    plan_files = {path.name: path for path in PLAN_DIR.glob("*.md")}
    headings = {name: heading_numbers(path) for name, path in plan_files.items()}
    headings["SPEC.md"] = heading_numbers(REPO / "SPEC.md")
    problems: list[str] = []

    for doc in docs:
        if not doc.exists():
            continue
        text = doc.read_text(encoding="utf-8")
        rel = doc.relative_to(REPO)
        for match in PATH_REF.finditer(text):
            if match.group(1) not in plan_files:
                problems.append(f"{rel}: references missing file docs/plan/{match.group(1)}")
        # File-qualified references first, and remember their spans so the
        # bare-reference pass does not double-report them.
        qualified_spans = []
        for match in FILE_THEN_SECTION.finditer(text):
            qualified_spans.append(match.span())
            target = match.group(1)
            number = match.group(2) + (f".{match.group(3)}" if match.group(3) else "")
            if target in plan_files and number not in headings[target] and match.group(2) not in headings[target]:
                problems.append(f"{rel}: `{target}` §{number} has no matching heading in docs/plan/{target}")
        for match in SECTION_REF.finditer(text):
            if any(start <= match.start() < end for start, end in qualified_spans):
                continue
            top, sub = match.group(1), match.group(2)
            number = top + (f".{sub}" if sub else "")
            # §09.1 style: two-digit doc number + section. A bare two-digit
            # §12 names plan doc 12 as a whole and resolves if the doc exists.
            if len(top) == 2:
                target = next((name for name in plan_files if name.startswith(top + "-")), None)
                if target:
                    if sub and sub not in headings[target] and number not in headings[target]:
                        problems.append(f"{rel}: §{number} has no matching heading in docs/plan/{target}")
                    continue
            own = headings.get(doc.name)
            if own is not None and number not in own and top not in own:
                problems.append(f"{rel}: §{number} has no matching heading in {doc.name}")

    for problem in problems:
        print("UNRESOLVED:", problem)
    print(f"checked {len(docs)} docs, {len(problems)} unresolved references")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
