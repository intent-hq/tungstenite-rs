#!/usr/bin/env python3
"""Summarize an Autobahn TestSuite report and gate on case results.

Usage: autobahn-summary.py <index.json> <label>

Prints a per-behavior summary (and a section 13 breakdown) to stdout and,
when running on GitHub Actions, appends it to the job summary. Exits
non-zero if any case reports a behavior other than OK / NON-STRICT /
INFORMATIONAL. UNIMPLEMENTED is additionally tolerated for section 13
cases, where it means a permessage-deflate parameter set was cleanly
declined rather than mishandled.
"""

import json
import os
import sys
from collections import Counter

ALLOWED = {"OK", "NON-STRICT", "INFORMATIONAL"}
ALLOWED_13 = ALLOWED | {"UNIMPLEMENTED"}


def case_key(case_id):
    return tuple(int(part) for part in case_id.split("."))


def main():
    index_path, label = sys.argv[1], sys.argv[2]
    if not os.path.exists(index_path):
        print(f"::warning::{label}: no report found at {index_path}, skipping summary")
        return 0

    with open(index_path) as f:
        report = json.load(f)

    (agent, cases), = report.items()

    behaviors = Counter(case["behavior"] for case in cases.values())
    close_behaviors = Counter(case["behaviorClose"] for case in cases.values())

    failures = []
    for case_id in sorted(cases, key=case_key):
        case = cases[case_id]
        allowed = ALLOWED_13 if case_id.startswith("13.") else ALLOWED
        if case["behavior"] not in allowed or case["behaviorClose"] not in allowed:
            failures.append(
                f"{case_id}: behavior={case['behavior']} "
                f"behaviorClose={case['behaviorClose']}"
            )

    section13 = {k: v for k, v in cases.items() if k.startswith("13.")}
    sub13 = Counter(
        (".".join(k.split(".")[:2]), v["behavior"]) for k, v in section13.items()
    )

    lines = [f"### {label} — agent `{agent}`, {len(cases)} cases", ""]
    lines.append("| Behavior | Cases | Close behavior | Cases |")
    lines.append("|---|---|---|---|")
    rows = max(len(behaviors), len(close_behaviors))
    b_items = behaviors.most_common() + [("", "")] * rows
    c_items = close_behaviors.most_common() + [("", "")] * rows
    for i in range(rows):
        lines.append(
            f"| {b_items[i][0]} | {b_items[i][1]} | {c_items[i][0]} | {c_items[i][1]} |"
        )
    lines.append("")
    if section13:
        lines.append(
            f"Section 13 (permessage-deflate): {len(section13)} cases — "
            + ", ".join(
                f"{sub} {behavior}×{count}"
                for (sub, behavior), count in sorted(
                    sub13.items(), key=lambda item: case_key(item[0][0])
                )
            )
        )
    else:
        lines.append("Section 13 (permessage-deflate): no cases in report")
    lines.append("")
    if failures:
        lines.append(f"**{len(failures)} case(s) with unacceptable results:**")
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("All case results acceptable (OK / NON-STRICT / INFORMATIONAL; "
                     "UNIMPLEMENTED tolerated for section 13).")

    output = "\n".join(lines)
    print(output)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(output + "\n\n")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
