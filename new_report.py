#!/usr/bin/env python3
"""
Budget Watch — new report wizard.
Run with: python3 new_report.py
"""

import os
import re
import subprocess
from datetime import datetime

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "content", "reports")

# ── helpers ───────────────────────────────────────────────────────────────────

def ask(prompt, required=True, default=None):
    hint = f" [{default}]" if default else ""
    while True:
        val = input(f"  {prompt}{hint}: ").strip()
        if not val and default is not None:
            return default
        if val or not required:
            return val
        print("    ↳ Required — please enter a value.")

def ask_yn(prompt, default="y"):
    hint = "Y/n" if default == "y" else "y/N"
    val = input(f"  {prompt} [{hint}]: ").strip().lower()
    if not val:
        return default == "y"
    return val.startswith("y")

def ask_choice(prompt, choices):
    print(f"  {prompt}")
    for i, c in enumerate(choices, 1):
        print(f"    {i}. {c}")
    while True:
        val = input("  Choice: ").strip()
        if val.isdigit() and 1 <= int(val) <= len(choices):
            return choices[int(val) - 1]
        print(f"    ↳ Enter a number between 1 and {len(choices)}.")

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text

def severity_from_findings(findings):
    if any(f["severity"] == "high" for f in findings):
        return "high"
    if any(f["severity"] == "medium" for f in findings):
        return "medium"
    return "low"

# ── finding collector ─────────────────────────────────────────────────────────

def collect_findings():
    findings = []
    print()
    print("  Now add your findings. Each finding needs:")
    print("  • a fact (what the numbers say)")
    print("  • a neutral question for the public")
    print("  • the page in the budget where the figure appears")
    print()

    while True:
        print(f"  ── Finding #{len(findings) + 1} ──────────────────────────")
        severity = ask_choice("Severity?", ["high", "medium", "low"])
        check    = ask("Check name (e.g. Year-over-year spike)")
        fact     = ask("Fact — what do the numbers say?")
        question = ask("Neutral question for the public?")
        source   = ask("Source citation (e.g. FY2024 Budget, p. 34)")

        findings.append(dict(severity=severity, check=check,
                             fact=fact, question=question, source=source))

        print()
        if not ask_yn("Add another finding?", default="y"):
            break
        print()

    return findings

# ── file builder ──────────────────────────────────────────────────────────────

def build_finding_block(f):
    return f"""
<div class="finding {f['severity']}">
  <div class="finding-label">{f['severity'].title()} · {f['check']}</div>
  <div class="finding-fact">{f['fact']}</div>
  <div class="finding-question">{f['question']}</div>
  <div class="finding-source">Source: {f['source']}</div>
</div>
"""

def build_report(meta, summary, findings):
    blocks = "\n".join(build_finding_block(f) for f in findings)
    news_desert_str = "true" if meta["news_desert"] else "false"
    draft_str = "true" if meta["draft"] else "false"

    return f"""---
title: "{meta['title']}"
town: "{meta['town']}"
state: "{meta['state']}"
fiscal_year: "{meta['fiscal_year']}"
population: {meta['population']}
severity: "{meta['severity']}"
news_desert: {news_desert_str}
lat: {meta['lat']}
lng: {meta['lng']}
source_url: "{meta['source_url']}"
draft: {draft_str}
---

## Summary

{summary}

## Findings

{blocks}
"""

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Budget Watch — New Report Wizard")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()

    # ── metadata ──────────────────────────────────────────────────────────────
    print("TOWN INFO")
    town       = ask("Town / City name")
    state      = ask("State (two-letter code, e.g. IL)")
    fy         = ask("Fiscal year (e.g. 2024)", default=str(datetime.now().year))
    population = ask("Approximate population")
    news_desert = ask_yn("Is this a news-desert town (no local newspaper)?")
    source_url  = ask("URL of the official budget document", required=False, default="")

    print()
    print("COORDINATES  (needed for the map)")
    print("  Tip: Google '[town name] coordinates' and copy the lat/lng.")
    lat = ask("Latitude  (e.g. 41.8827)")
    lng = ask("Longitude (e.g. -87.6233)")

    title = f"{town}, {state.upper()} — FY{fy} Budget Analysis"

    print()
    print("REPORT CONTENT")
    summary = ask("One or two sentence summary (why this town, what you found)")

    # ── findings ──────────────────────────────────────────────────────────────
    findings = collect_findings()
    severity = severity_from_findings(findings)

    # ── draft? ────────────────────────────────────────────────────────────────
    print()
    draft = not ask_yn("Publish now? (choose No to save as draft)", default="y")

    # ── write file ────────────────────────────────────────────────────────────
    meta = dict(title=title, town=town, state=state.upper(), fiscal_year=fy,
                population=population, severity=severity, news_desert=news_desert,
                lat=lat, lng=lng, source_url=source_url, draft=draft)

    slug     = f"{slugify(town)}-{state.lower()}-{fy}"
    filepath = os.path.join(REPORTS_DIR, f"{slug}.md")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(filepath, "w") as fh:
        fh.write(build_report(meta, summary, findings))

    print()
    print(f"  ✓ Report saved → content/reports/{slug}.md")

    # ── git + push? ───────────────────────────────────────────────────────────
    print()
    if ask_yn("Commit and push to GitHub now?", default="y"):
        status = "draft" if draft else "published"
        msg    = f"Add {status} report: {town}, {state.upper()} FY{fy}"
        cmds = [
            ["git", "add", filepath],
            ["git", "commit", "-m", msg],
            ["git", "push"],
        ]
        for cmd in cmds:
            result = subprocess.run(cmd, cwd=os.path.dirname(__file__),
                                    capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  ✗ Error running {' '.join(cmd)}:")
                print(f"    {result.stderr.strip()}")
                return
        print()
        print("  ✓ Pushed. Your report will be live in ~2 minutes.")
        print(f"  → https://sid-code-git.github.io/budgetwatch/reports/{slug}/")
    else:
        print()
        print("  To publish later, run:")
        print(f"    git add content/reports/{slug}.md")
        print(f"    git commit -m 'Add report: {town} FY{fy}'")
        print(f"    git push")

    print()

if __name__ == "__main__":
    main()
