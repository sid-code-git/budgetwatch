#!/usr/bin/env python3
"""
Budget Watch — AI Report Researcher
Usage: python3 research_town.py
       python3 research_town.py "Springfield, IL" 2024

Searches for a town's public budget, analyzes it using Claude,
and submits a draft report to the local admin at http://localhost:8787.

SETUP (one time):
  1. Get a free API key at https://console.anthropic.com
  2. Either set it as an env variable:
       export ANTHROPIC_API_KEY="sk-ant-..."
     Or paste it below where it says YOUR_KEY_HERE
  3. Install the Anthropic SDK:
       pip3 install anthropic
"""

import os, sys, json, urllib.request, urllib.parse, subprocess, time

# ── API key ────────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_KEY_HERE")
ADMIN_URL = "http://localhost:8787"

# ── check dependencies ─────────────────────────────────────────────────────────

def check_setup():
    if API_KEY == "YOUR_KEY_HERE" or not API_KEY:
        print("""
  ✗  No API key found.

  1. Go to https://console.anthropic.com and sign up (free)
  2. Create an API key
  3. Run:  export ANTHROPIC_API_KEY="sk-ant-..."
     Then re-run this script.
""")
        sys.exit(1)

    try:
        import anthropic
    except ImportError:
        print("\n  Installing anthropic SDK...")
        subprocess.run([sys.executable, "-m", "pip", "install", "anthropic", "-q"])
        print("  Done.\n")

# ── ensure admin is running ────────────────────────────────────────────────────

def ensure_admin_running():
    try:
        urllib.request.urlopen(ADMIN_URL, timeout=2)
        return True
    except Exception:
        pass
    print("  Starting admin server...")
    base = os.path.dirname(__file__)
    subprocess.Popen(
        [sys.executable, os.path.join(base, "admin.py")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(2)
    try:
        urllib.request.urlopen(ADMIN_URL, timeout=3)
        print("  Admin running at http://localhost:8787\n")
        return True
    except Exception:
        print("  Could not start admin. Open Budget Watch Admin.command manually first.")
        return False

# ── call Claude API ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a municipal budget analyst for Budget Watch, a public accountability journalism project.
Your job is to research a town's public budget and extract structured data for a report.

When given a town and fiscal year, you will:
1. Search for the official budget document (PDF or web page) from the town/city government website
2. Search for socioeconomic data (population trends, income, unemployment)
3. Search for any news coverage about the town's finances
4. Extract all the structured data needed for a Budget Watch report

Be factual and neutral. Cite page numbers and sources. If you cannot find a specific number, write "Not found in available sources."
Flag anything that looks unusual — large year-over-year changes, very low fund balances, high debt loads, etc.
"""

RESEARCH_PROMPT = """Research the public budget for {town}, {state} for fiscal year {fy}.

Find:
1. The official budget document URL
2. Total budget amount
3. Major revenue sources with amounts and percentages
4. Major expenditure categories with amounts and percentages
5. Fund balance / reserves
6. Any debt, pension liabilities, or OPEB obligations
7. Population and key socioeconomic data
8. Any notable financial issues or red flags
9. When was the last audit published? Is the budget easy to find online?
10. 3-5 years of historical budget totals if available

Then output a JSON object with exactly these fields (use empty string "" if unknown):

{{
  "title": "full report title e.g. Springfield, IL — FY2024 Budget Analysis",
  "town": "town name",
  "state": "2-letter state code",
  "fiscal_year": "year as string",
  "population": "number only",
  "severity": "high, medium, or low — your overall assessment",
  "news_desert": "true or false — is there no local newspaper?",
  "lat": "latitude as decimal",
  "lng": "longitude as decimal",
  "source_url": "direct URL to the budget document",
  "exec_summary": "2-3 sentence executive summary a taxpayer can read in 30 seconds",
  "total_budget": "e.g. $4.2M",
  "per_capita": "e.g. $875",
  "fund_balance": "e.g. $320K (7.6% of general fund)",
  "debt_load": "total debt e.g. $1.1M",
  "socio_context": "paragraph on economic context",
  "pop_trends": "key population and income data points",
  "revenue_sources": "line-by-line list with amounts and percentages",
  "expenditure_breakdown": "line-by-line list with amounts and percentages",
  "trend_years": ["2020","2021","2022","2023","2024"],
  "trend_revenues": ["$3.8M","$3.9M","$4.0M","$4.1M","$4.2M"],
  "trend_expenses": ["$3.7M","$3.9M","$4.1M","$4.3M","$4.5M"],
  "trend_balances": ["$500K","$490K","$400K","$320K","$280K"],
  "bonded_debt": "e.g. $680K",
  "pension_liability": "e.g. $1.2M unfunded",
  "opeb_liability": "e.g. $340K",
  "debt_service_pct": "e.g. 10% of general fund",
  "debt_narrative": "paragraph on long-term obligations",
  "impact_education": "paragraph on education/youth program cuts or investments",
  "impact_infrastructure": "paragraph on roads, parks, facilities",
  "impact_safety": "paragraph on police/fire staffing and budget",
  "impact_social": "paragraph on senior services, social programs",
  "flags": [
    {{
      "severity": "high/medium/low",
      "name": "flag name e.g. Fund balance erosion",
      "fact": "specific factual observation with numbers",
      "question": "neutral public question this raises",
      "source": "page number or document reference"
    }}
  ],
  "governance": "paragraph on how accessible/transparent the budget process is",
  "budget_public": "Yes/No and how",
  "last_audit": "e.g. FY2022 (2 years behind)",
  "public_hearings": "e.g. 1 hearing, 4 days notice",
  "recommendations": "3-5 numbered policy recommendations",
  "citizen_action": "3-4 numbered action steps for a resident",
  "next_hearing": "date and location if known",
  "foia_contact": "clerk email or records contact if found",
  "conclusion": "2-3 sentence long-term outlook paragraph"
}}

Output ONLY the JSON object. No markdown, no explanation."""

def research_town(town, state, fy):
    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY)

    prompt = RESEARCH_PROMPT.format(town=town, state=state, fy=fy)

    print(f"  Researching {town}, {state} FY{fy}...")
    print("  (This takes 30–60 seconds — Claude is searching the web)\n")

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    # Extract text from response (may be after tool use blocks)
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    # If we got tool use but no final text, do a follow-up
    if not text.strip() and response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Search complete"
                })

        response2 = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": tool_results}
            ]
        )
        for block in response2.content:
            if hasattr(block, "text"):
                text += block.text

    return text.strip()

# ── parse JSON from Claude ─────────────────────────────────────────────────────

def parse_json(raw):
    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"\n  Warning: Could not parse JSON ({e}). Saving raw text for review.")
        return None

# ── submit to admin ────────────────────────────────────────────────────────────

def submit_to_admin(data):
    """POST the structured data to the admin server's /save endpoint."""
    params = {}

    simple_fields = [
        "title","town","state","fiscal_year","population","severity",
        "source_url","exec_summary","total_budget","per_capita","fund_balance",
        "debt_load","socio_context","pop_trends","revenue_sources",
        "expenditure_breakdown","bonded_debt","pension_liability","opeb_liability",
        "debt_service_pct","debt_narrative","impact_education","impact_infrastructure",
        "impact_safety","impact_social","governance","budget_public","last_audit",
        "public_hearings","recommendations","citizen_action","next_hearing",
        "foia_contact","conclusion","lat","lng"
    ]
    for f in simple_fields:
        val = data.get(f, "")
        if val:
            params[f] = [str(val)]

    if data.get("news_desert") == "true":
        params["news_desert"] = ["on"]

    # Save as draft by default (user can review and publish from admin)
    # params["publish"] = ["true"]  # uncomment to publish immediately
    params["push"] = ["false"]  # don't push yet — let user review first

    # 5-year trend (parallel lists)
    for key in ("trend_year","trend_revenue","trend_expense","trend_balance"):
        src = {"trend_year":"trend_years","trend_revenue":"trend_revenues",
               "trend_expense":"trend_expenses","trend_balance":"trend_balances"}[key]
        vals = data.get(src, [])
        if vals:
            params[key] = [str(v) for v in vals]

    # Red flags
    flags = data.get("flags", [])
    if flags:
        params["flag_severity"] = [f.get("severity","medium") for f in flags]
        params["flag_name"]     = [f.get("name","") for f in flags]
        params["flag_fact"]     = [f.get("fact","") for f in flags]
        params["flag_question"] = [f.get("question","") for f in flags]
        params["flag_source"]   = [f.get("source","") for f in flags]

    body = urllib.parse.urlencode(params, doseq=True).encode()
    req  = urllib.request.Request(f"{ADMIN_URL}/save", data=body,
                                  headers={"Content-Type":"application/x-www-form-urlencoded"})
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"  Admin submit error: {e}")
        return False

# ── save raw fallback ──────────────────────────────────────────────────────────

def save_raw(town, state, fy, raw):
    slug = f"{town.lower().replace(' ','-')}-{state.lower()}-{fy}-raw.txt"
    path = os.path.join(os.path.dirname(__file__), "content", "reports", slug)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(raw)
    print(f"  Raw output saved to: {path}")

# ── main ───────────────────────────────────────────────────────────────────────

def main():
    check_setup()

    # Get town from args or prompt
    if len(sys.argv) >= 3:
        town_input = sys.argv[1]
        fy = sys.argv[2]
    elif len(sys.argv) == 2:
        town_input = sys.argv[1]
        fy = str(__import__("datetime").date.today().year)
    else:
        print("\n  Budget Watch — AI Report Researcher\n")
        town_input = input("  Town name and state (e.g. Springfield, IL): ").strip()
        fy = input(f"  Fiscal year [{__import__('datetime').date.today().year}]: ").strip()
        if not fy:
            fy = str(__import__("datetime").date.today().year)

    # Split town and state
    if "," in town_input:
        parts = town_input.rsplit(",", 1)
        town  = parts[0].strip()
        state = parts[1].strip().upper()
    else:
        town  = town_input.strip()
        state = input("  State abbreviation (e.g. IL): ").strip().upper()

    print()
    ensure_admin_running()

    raw = research_town(town, state, fy)

    print("  Parsing results...")
    data = parse_json(raw)

    if data:
        print("  Submitting to admin...")
        ok = submit_to_admin(data)
        if ok:
            print(f"""
  ✓ Draft report created!

  → Open http://localhost:8787 to review and edit it
  → Check all numbers against the source budget document
  → When ready, open the report and push to GitHub

  Report saved as draft — nothing is published yet.
""")
        else:
            save_raw(town, state, fy, raw)
    else:
        save_raw(town, state, fy, raw)


if __name__ == "__main__":
    main()
