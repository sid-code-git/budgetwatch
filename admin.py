#!/usr/bin/env python3
"""
Budget Watch local admin. Run with: python3 admin.py
Then open: http://localhost:8787
"""

import http.server, os, re, subprocess, urllib.parse, urllib.request, json
from datetime import datetime

BASE = os.path.dirname(__file__)
REPORTS = os.path.join(BASE, "content", "reports")
BRIEFS  = os.path.join(BASE, "content", "briefs")
CONFIG_FILE = os.path.join(BASE, ".admin_config.json")
SITE_CONFIG_FILE = os.path.join(BASE, "data", "site_config.yaml")
PORT = 8787

# ── config (stores Netlify token) ──────────────────────────────────────────────

def load_site_config():
    try:
        with open(SITE_CONFIG_FILE) as f:
            cfg = {}
            for line in f:
                if ":" in line:
                    k, _, v = line.partition(":")
                    cfg[k.strip()] = v.strip().strip('"')
            return cfg
    except Exception:
        return {}

def save_site_config(cfg):
    os.makedirs(os.path.dirname(SITE_CONFIG_FILE), exist_ok=True)
    with open(SITE_CONFIG_FILE, "w") as f:
        for k, v in cfg.items():
            f.write(f'{k}: "{v}"\n')

TEAM_FILE = os.path.join(BASE, "data", "team.json")
TEAM_PHOTO_DIR = os.path.join(BASE, "static", "images", "team")

def load_team():
    try:
        with open(TEAM_FILE) as f:
            team = json.load(f)
            return sorted(team, key=lambda m: m.get("order", 0))
    except Exception:
        return []

def save_team(team):
    for i, m in enumerate(team):
        m["order"] = i + 1
    os.makedirs(os.path.dirname(TEAM_FILE), exist_ok=True)
    with open(TEAM_FILE, "w") as f:
        json.dump(team, f, indent=2)

def git_push_all(message):
    cmds = [
        ["git", "add", "-A"],
        ["git", "commit", "-m", message],
        ["git", "push"],
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr.strip()
    return True, ""

def parse_multipart(body, boundary):
    """Minimal multipart/form-data parser.

    Returns (fields, files): fields is a MultiDict (supports repeated names),
    files maps name -> list of (filename, bytes) for non-empty uploads."""
    fields, files = {}, {}
    delim = b"--" + boundary
    for part in body.split(delim):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if b"\r\n\r\n" not in part:
            continue
        head, _, content = part.partition(b"\r\n\r\n")
        head_text = head.decode("utf-8", "replace")
        name_m = re.search(r'name="([^"]*)"', head_text)
        if not name_m:
            continue
        name = name_m.group(1)
        file_m = re.search(r'filename="([^"]*)"', head_text)
        if file_m is not None:
            if file_m.group(1) and content:
                files.setdefault(name, []).append((os.path.basename(file_m.group(1)), content))
        else:
            fields.setdefault(name, []).append(content.decode("utf-8", "replace"))
    return MultiDict(fields), files

UPLOAD_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".pdf"}

def save_uploads(files, field, slug):
    """Save uploaded graphics under static/images/uploads/<slug>/.
    Returns list of (original name, site-relative url, ext)."""
    saved = []
    for filename, content in files.get(field, []):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in UPLOAD_EXTS or not content:
            continue
        updir = os.path.join(BASE, "static", "images", "uploads", slug)
        os.makedirs(updir, exist_ok=True)
        base = slugify(os.path.splitext(filename)[0]) or "file"
        name, n = f"{base}{ext}", 2
        while os.path.exists(os.path.join(updir, name)):
            name = f"{base}-{n}{ext}"
            n += 1
        with open(os.path.join(updir, name), "wb") as f:
            f.write(content)
        saved.append((filename, f"/images/uploads/{slug}/{name}", ext))
    return saved

def graphics_md(saved):
    """Markdown section embedding uploaded graphics (images inline, PDFs as links)."""
    if not saved:
        return ""
    out = "\n\n## Charts & Graphics\n\n"
    for original, url, ext in saved:
        label = os.path.splitext(original)[0]
        if ext == ".pdf":
            out += f"📄 [{label} (PDF)]({url})\n\n"
        else:
            out += f"![{label}]({url})\n\n"
    return out

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f)

# ── netlify ────────────────────────────────────────────────────────────────────

def netlify_api(path, token):
    req = urllib.request.Request(
        f"https://api.netlify.com/api/v1{path}",
        headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def fetch_form(token, site_id, form_name):
    forms = netlify_api(f"/sites/{site_id}/forms", token)
    if isinstance(forms, dict) and "error" in forms:
        return None, forms["error"]
    target = next((f for f in forms if f.get("name") == form_name), None)
    if not target:
        return [], None
    subs = netlify_api(f"/forms/{target['id']}/submissions", token)
    if isinstance(subs, dict) and "error" in subs:
        return None, subs["error"]
    return subs, None

def fetch_submissions(token, site_id):
    return fetch_form(token, site_id, "town-report")

def fetch_applications(token, site_id):
    return fetch_form(token, site_id, "analyst-application")

def fetch_sites(token):
    return netlify_api("/sites", token)

# ── helpers ────────────────────────────────────────────────────────────────────

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text

def list_briefs():
    if not os.path.exists(BRIEFS):
        return []
    files = [f for f in os.listdir(BRIEFS) if f.endswith(".md") and f != "_index.md"]
    out = []
    for f in sorted(files, reverse=True):
        path = os.path.join(BRIEFS, f)
        meta = parse_frontmatter(path)
        meta["slug"] = f.replace(".md", "")
        out.append(meta)
    return out

def read_brief(slug):
    path = os.path.join(BRIEFS, slug + ".md")
    try:
        with open(path) as fh:
            return fh.read()
    except Exception:
        return ""

def write_brief(slug, content):
    os.makedirs(BRIEFS, exist_ok=True)
    path = os.path.join(BRIEFS, slug + ".md")
    with open(path, "w") as fh:
        fh.write(content)
    return path

def build_brief_md(d):
    draft = "false" if d.get("publish") == "true" else "true"
    # key_facts as YAML list
    facts = [f.strip() for f in d.get("key_facts", "").split("\n") if f.strip()]
    facts_yaml = "".join(f'\n  - "{esc(f)}"' for f in facts) if facts else ""

    return f"""---
title: "{d.get('title', '')}"
subtitle: "{d.get('subtitle', '')}"
topic: "{d.get('topic', '')}"
date: {d.get('date', datetime.now().strftime('%Y-%m-%d'))}
author: "{d.get('author', '')}"
summary: "{d.get('summary', '').replace(chr(34), chr(39))}"
key_facts:{facts_yaml if facts_yaml else ' []'}
source_url: "{d.get('source_url', '')}"
draft: {draft}
---

{d.get('body', '')}
"""

def list_reports():
    if not os.path.exists(REPORTS):
        return []
    files = [f for f in os.listdir(REPORTS) if f.endswith(".md") and f != "_index.md"]
    out = []
    for f in sorted(files, reverse=True):
        path = os.path.join(REPORTS, f)
        meta = parse_frontmatter(path)
        meta["slug"] = f.replace(".md", "")
        out.append(meta)
    return out

def parse_frontmatter(path):
    meta = {}
    try:
        with open(path) as fh:
            content = fh.read()
        if content.startswith("---"):
            fm = content.split("---", 2)[1]
            for line in fm.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip().strip('"')
    except Exception:
        pass
    return meta

def read_report(slug):
    path = os.path.join(REPORTS, slug + ".md")
    try:
        with open(path) as fh:
            return fh.read()
    except Exception:
        return ""

def write_report(slug, content):
    os.makedirs(REPORTS, exist_ok=True)
    path = os.path.join(REPORTS, slug + ".md")
    with open(path, "w") as fh:
        fh.write(content)
    return path

def git_push(path, message):
    cmds = [
        ["git", "add", path],
        ["git", "commit", "-m", message],
        ["git", "push"],
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr.strip()
    return True, ""

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ── markdown builder ───────────────────────────────────────────────────────────

def build_report_md(d):
    draft      = "false" if d.get("publish") == "true" else "true"
    news_desert = "true" if d.get("news_desert") == "on" else "false"

    # Red flags (dynamic rows)
    flags_md = ""
    flag_facts  = d.getlist("flag_fact")
    flag_qs     = d.getlist("flag_question")
    flag_srcs   = d.getlist("flag_source")
    flag_sevs   = d.getlist("flag_severity")
    flag_names  = d.getlist("flag_name")
    for i in range(len(flag_facts)):
        if not flag_facts[i].strip():
            continue
        sev  = flag_sevs[i]  if i < len(flag_sevs)  else "medium"
        name = flag_names[i] if i < len(flag_names) else ""
        q    = flag_qs[i]    if i < len(flag_qs)    else ""
        src  = flag_srcs[i]  if i < len(flag_srcs)  else ""
        flags_md += f"""
<div class="finding {sev}">
  <div class="finding-label">{sev.title()} · {name}</div>
  <div class="finding-fact">{flag_facts[i]}</div>
  <div class="finding-question">{q}</div>
  <div class="finding-source">Source: {src}</div>
</div>
"""

    # Peer comparison table rows
    peers_md = ""
    peer_towns = d.getlist("peer_town")
    peer_pops  = d.getlist("peer_pop")
    peer_budgets = d.getlist("peer_budget")
    peer_percap  = d.getlist("peer_percap")
    peer_notes   = d.getlist("peer_note")
    if any(t.strip() for t in peer_towns):
        peers_md = "| Town | Population | Total Budget | Per-Capita | Notes |\n"
        peers_md += "|------|-----------|-------------|-----------|-------|\n"
        for i in range(len(peer_towns)):
            if not peer_towns[i].strip():
                continue
            peers_md += f"| {peer_towns[i]} | {peer_pops[i] if i<len(peer_pops) else ''} | {peer_budgets[i] if i<len(peer_budgets) else ''} | {peer_percap[i] if i<len(peer_percap) else ''} | {peer_notes[i] if i<len(peer_notes) else ''} |\n"

    # 5-year revenue trend table
    trend_md = ""
    trend_years    = d.getlist("trend_year")
    trend_revenues = d.getlist("trend_revenue")
    trend_expenses = d.getlist("trend_expense")
    trend_balances = d.getlist("trend_balance")
    if any(y.strip() for y in trend_years):
        trend_md = "| Year | Total Revenue | Total Expenditure | Fund Balance |\n"
        trend_md += "|------|-------------|-----------------|-------------|\n"
        for i in range(len(trend_years)):
            if not trend_years[i].strip():
                continue
            trend_md += f"| {trend_years[i]} | {trend_revenues[i] if i<len(trend_revenues) else ''} | {trend_expenses[i] if i<len(trend_expenses) else ''} | {trend_balances[i] if i<len(trend_balances) else ''} |\n"

    return f"""---
title: "{d.get('title', '')}"
town: "{d.get('town', '')}"
state: "{d.get('state', '').upper()}"
fiscal_year: "{d.get('fiscal_year', '')}"
population: {d.get('population', '0') or '0'}
severity: "{d.get('severity', 'medium')}"
news_desert: {news_desert}
lat: {d.get('lat', '0') or '0'}
lng: {d.get('lng', '0') or '0'}
source_url: "{d.get('source_url', '')}"
draft: {draft}
---

## I. Executive Summary

{d.get('exec_summary', '')}

**Total Budget:** {d.get('total_budget', '')} &nbsp;|&nbsp; **Per Capita:** {d.get('per_capita', '')} &nbsp;|&nbsp; **Fund Balance:** {d.get('fund_balance', '')} &nbsp;|&nbsp; **Debt Load:** {d.get('debt_load', '')}

## II. Socioeconomic Context & Peer Comparison

{d.get('socio_context', '')}

### Population & Economic Trends

{d.get('pop_trends', '')}

### Peer Comparison

{peers_md if peers_md else '_No peer data entered._'}

## III. Revenue & Expenditure Ledger

### Where the Money Comes From

{d.get('revenue_sources', '')}

### Where the Money Goes

{d.get('expenditure_breakdown', '')}

### 5-Year Trend

{trend_md if trend_md else '_No trend data entered._'}

## IV. Debt, Pensions & Long-Term Obligations

**Bonded Debt:** {d.get('bonded_debt', '')}

**Unfunded Pension Liability:** {d.get('pension_liability', '')}

**OPEB Liability:** {d.get('opeb_liability', '')}

**Debt Service as % of General Fund:** {d.get('debt_service_pct', '')}

{d.get('debt_narrative', '')}

## V. Community Impact Analysis

### A. Education & Youth Programs

{d.get('impact_education', '')}

### B. Facilities, Infrastructure & Parks

{d.get('impact_infrastructure', '')}

### C. Public Safety Staffing & Allocation

{d.get('impact_safety', '')}

### D. Social Services & Senior Programs

{d.get('impact_social', '')}

## VI. Major Financial Red Flags & Ghost Indicators

{flags_md.strip() if flags_md.strip() else '_No red flags entered._'}

## VII. Governance & Transparency Audit

{d.get('governance', '')}

**Budget document publicly available:** {d.get('budget_public', '')} &nbsp;|&nbsp; **Last audit published:** {d.get('last_audit', '')} &nbsp;|&nbsp; **Public hearings held:** {d.get('public_hearings', '')}

## VIII. Policy Options & Strategic Recommendations

{d.get('recommendations', '')}

## IX. Citizen Action Guide

{d.get('citizen_action', '')}

**Next budget hearing:** {d.get('next_hearing', '')}

**FOIA contact:** {d.get('foia_contact', '')}

## X. Conclusion & Long-Term Outlook

{d.get('conclusion', '')}
"""

# ── styles ─────────────────────────────────────────────────────────────────────

STYLE = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Inter',system-ui,sans-serif;background:#f5f5fa;color:#0a0a0f;min-height:100vh}
  .topbar{background:#0a0a0f;color:white;padding:1rem 2rem;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
  .topbar h1{font-size:1rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase}
  .topbar a{color:rgba(255,255,255,.6);font-size:.82rem;text-decoration:none}
  .topbar a:hover{color:white}
  .wrap{max-width:960px;margin:0 auto;padding:2.5rem 2rem}
  h2{font-size:1.5rem;font-weight:800;letter-spacing:-.03em;margin-bottom:1.5rem}
  .btn{display:inline-block;font-family:inherit;font-size:.88rem;font-weight:700;padding:.6rem 1.25rem;border-radius:20px;border:none;cursor:pointer;text-decoration:none;transition:background .12s}
  .btn-primary{background:#0a0a0f;color:white}
  .btn-primary:hover{background:#333}
  .btn-green{background:#16a34a;color:white}
  .btn-green:hover{background:#15803d}
  .btn-outline{background:white;color:#0a0a0f;border:1.5px solid #ddd}
  .btn-outline:hover{border-color:#aaa}
  .btn-sm{font-size:.78rem;padding:.4rem .9rem}
  .btn-purple{background:#5b5bd6;color:white}
  .btn-purple:hover{background:#4a4ac4}
  .card{background:white;border:1px solid #e5e5f0;border-radius:14px;padding:1.75rem;margin-bottom:1.25rem}
  .card-header{display:flex;align-items:baseline;gap:.75rem;margin-bottom:1.25rem}
  .card-num{font-size:.72rem;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:white;background:#5b5bd6;border-radius:20px;padding:.2rem .6rem;flex-shrink:0}
  .card-title{font-size:1rem;font-weight:700;color:#0a0a0f}
  .card-subtitle{font-size:.78rem;color:#6b6b80;margin-top:.15rem}
  .report-row{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}
  .report-title{font-weight:700;font-size:.97rem}
  .report-meta{font-size:.78rem;color:#6b6b80;margin-top:.2rem;font-family:monospace}
  .badge{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;padding:.18rem .55rem;border-radius:20px}
  .badge-high{background:#fef2f2;color:#dc2626;border:1px solid #fecaca}
  .badge-medium{background:#fff7ed;color:#ea580c;border:1px solid #fed7aa}
  .badge-low{background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0}
  .badge-draft{background:#f5f5fa;color:#6b6b80;border:1px solid #ddd}
  .row-actions{display:flex;gap:.5rem;flex-shrink:0}
  .form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1.1rem}
  .form-grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1.1rem}
  .form-grid-4{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:.9rem}
  .form-group{display:flex;flex-direction:column;gap:.3rem}
  .form-group.full{grid-column:1/-1}
  label{font-size:.8rem;font-weight:600;color:#3a3a4a}
  input,select,textarea{font-family:inherit;font-size:.9rem;padding:.55rem .8rem;border:1.5px solid #e5e5f0;border-radius:8px;background:white;color:#0a0a0f;outline:none;transition:border-color .12s}
  input:focus,select:focus,textarea:focus{border-color:#5b5bd6;box-shadow:0 0 0 3px rgba(91,91,214,.1)}
  textarea{resize:vertical;min-height:75px}
  .sub-label{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#9090a0;margin:1.25rem 0 .6rem;padding-bottom:.35rem;border-bottom:1px solid #f0f0f8}
  .flag-block{border:1.5px solid #fde8e8;border-radius:10px;padding:1.1rem;margin-bottom:.85rem;position:relative;background:#fff8f8}
  .flag-block h4{font-size:.82rem;font-weight:700;margin-bottom:.8rem;color:#dc2626}
  .flag-grid{display:grid;grid-template-columns:1fr 1fr;gap:.8rem}
  .flag-grid .full{grid-column:1/-1}
  .peer-block,.trend-block{border:1.5px solid #e5e5f0;border-radius:10px;padding:1rem;margin-bottom:.75rem;position:relative;background:#fafafa}
  .peer-block h4,.trend-block h4{font-size:.8rem;font-weight:700;margin-bottom:.75rem;color:#5b5bd6}
  .remove-btn{position:absolute;top:.6rem;right:.6rem;background:none;border:none;cursor:pointer;color:#ccc;font-size:1rem;line-height:1}
  .remove-btn:hover{color:#dc2626}
  .alert{padding:.85rem 1.1rem;border-radius:8px;font-size:.88rem;font-weight:500;margin-bottom:1.25rem}
  .alert-green{background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0}
  .alert-red{background:#fef2f2;color:#dc2626;border:1px solid #fecaca}
  .actions-bar{display:flex;gap:.75rem;align-items:center;margin-top:2rem;padding-top:1.5rem;border-top:1px solid #e5e5f0;position:sticky;bottom:0;background:#f5f5fa;padding-bottom:1.5rem}
  .empty{color:#6b6b80;font-style:italic;text-align:center;padding:3rem 0}
  .hint{font-size:.72rem;color:#9090a0;margin-top:.15rem}
  .add-row-btn{font-size:.78rem;font-weight:600;color:#5b5bd6;background:none;border:none;cursor:pointer;padding:.3rem 0;text-decoration:underline;text-underline-offset:2px}
  .add-row-btn:hover{color:#4a4ac4}
  .toc{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:1.75rem}
  .toc a{font-size:.75rem;font-weight:600;color:#5b5bd6;background:#eeeeff;padding:.3rem .7rem;border-radius:20px;text-decoration:none}
  .toc a:hover{background:#ddddf8}
</style>
"""

# ── page shell ─────────────────────────────────────────────────────────────────

def page(title, body, active="reports"):
    nav_items = [("reports", "/", "Reports"), ("new", "/new", "+ New Report"), ("briefs", "/briefs", "Policy Briefs"), ("new-brief", "/briefs/new", "+ New Brief"), ("team", "/team", "Team"), ("settings", "/settings", "Settings")]
    nav = "".join(
        f'<a href="{href}" style="color:{"white" if active==k else "rgba(255,255,255,.5)"};margin-left:1.5rem;text-decoration:none;font-size:.85rem;font-weight:{"700" if active==k else "400"}">{label}</a>'
        for k, href, label in nav_items
    )
    return f"""<!doctype html><html lang=en><head>
<meta charset=UTF-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{title} · Budget Watch Admin</title>{STYLE}</head><body>
<div class=topbar>
  <h1>Budget Watch Admin</h1>
  <div>{nav}<a href="https://sid-code-git.github.io/budgetwatch" target=_blank style="color:rgba(255,255,255,.35);margin-left:1.5rem;font-size:.8rem">View site ↗</a></div>
</div>
<div class=wrap>{body}</div>
</body></html>"""

# ── dynamic block templates ────────────────────────────────────────────────────

FLAG_TPL = """<div class="flag-block" id="flag-{n}">
  <button type=button class=remove-btn onclick="removeEl('flag-{n}')" title=Remove>✕</button>
  <h4>Red Flag #{n}</h4>
  <div class=flag-grid>
    <div class=form-group>
      <label>Severity</label>
      <select name=flag_severity>
        <option value=high>🔴 High</option>
        <option value=medium selected>🟠 Medium</option>
        <option value=low>🟢 Low</option>
      </select>
    </div>
    <div class=form-group>
      <label>Flag name</label>
      <input type=text name=flag_name placeholder="e.g. Vacancy trick, structural deficit">
    </div>
    <div class="form-group full">
      <label>Fact — what do the numbers say?</label>
      <textarea name=flag_fact rows=2 placeholder="Police Dept budget rose 43% YoY, from $1.2M to $1.72M."></textarea>
    </div>
    <div class="form-group full">
      <label>Neutral public question</label>
      <textarea name=flag_question rows=2 placeholder="What drove the 43% increase? Was this planned?"></textarea>
    </div>
    <div class="form-group full">
      <label>Source citation</label>
      <input type=text name=flag_source placeholder="FY2024 Annual Budget, p. 34">
    </div>
  </div>
</div>"""

PEER_TPL = """<div class="peer-block" id="peer-{n}">
  <button type=button class=remove-btn onclick="removeEl('peer-{n}')" title=Remove>✕</button>
  <h4>Peer Town #{n}</h4>
  <div class=form-grid-4>
    <div class=form-group><label>Town, State</label><input type=text name=peer_town placeholder="Millbrook, NY"></div>
    <div class=form-group><label>Population</label><input type=text name=peer_pop placeholder="4,200"></div>
    <div class=form-group><label>Total Budget</label><input type=text name=peer_budget placeholder="$3.1M"></div>
    <div class=form-group><label>Per Capita</label><input type=text name=peer_percap placeholder="$738"></div>
    <div class="form-group full"><label>Notes</label><input type=text name=peer_note placeholder="Similar size, lower admin cost"></div>
  </div>
</div>"""

TREND_TPL = """<div class="trend-block" id="trend-{n}">
  <button type=button class=remove-btn onclick="removeEl('trend-{n}')" title=Remove>✕</button>
  <div class=form-grid-4>
    <div class=form-group><label>Year</label><input type=text name=trend_year placeholder="2024"></div>
    <div class=form-group><label>Total Revenue</label><input type=text name=trend_revenue placeholder="$4.2M"></div>
    <div class=form-group><label>Total Expenditure</label><input type=text name=trend_expense placeholder="$4.5M"></div>
    <div class=form-group><label>Fund Balance</label><input type=text name=trend_balance placeholder="$620K"></div>
  </div>
</div>"""

# ── new brief form ─────────────────────────────────────────────────────────────

TOPICS = ["Property Tax Policy","Municipal Fiscal Stress","Pension & OPEB Reform","Shared Services","State Aid & Formulas","Economic Development","Infrastructure Finance","Public Safety Policy","Education Finance","Housing & Zoning","Other"]

def render_brief_form(alert=""):
    year = datetime.now().year
    topic_opts = "".join(f'<option value="{t}">{t}</option>' for t in TOPICS)
    return f"""
<h2>New Policy Brief</h2>
{alert}
<form method=POST action=/briefs/save enctype="multipart/form-data">

  <div class=card>
    <div class=card-header><span class=card-num>Meta</span><div><div class=card-title>Brief Info</div></div></div>
    <div class=form-grid>
      <div class="form-group full"><label>Title <span style="color:#dc2626">*</span></label><input type=text name=title required placeholder="Property Tax Caps Are Starving Small Towns"></div>
      <div class="form-group full"><label>Subtitle</label><input type=text name=subtitle placeholder="How state-imposed levy limits are accelerating fiscal stress"></div>
      <div class=form-group>
        <label>Topic</label>
        <select name=topic>{topic_opts}</select>
      </div>
      <div class=form-group>
        <label>Date</label>
        <input type=date name=date value="{datetime.now().strftime('%Y-%m-%d')}">
      </div>
      <div class=form-group>
        <label>Author</label>
        <input type=text name=author placeholder="Budget Watch Research" value="Budget Watch Research">
      </div>
      <div class=form-group>
        <label>Primary source URL</label>
        <input type=url name=source_url placeholder="https://...">
      </div>
    </div>
  </div>

  <div class=card>
    <div class=card-header><span class=card-num>Abstract</span><div><div class=card-title>Summary & Key Facts</div><div class=card-subtitle>Shown in the sidebar and on the briefs list page</div></div></div>
    <div class=form-group>
      <label>Abstract / Summary <span style="color:#dc2626">*</span></label>
      <textarea name=summary rows=4 required placeholder="2–3 sentence summary of the brief's argument and findings."></textarea>
    </div>
    <div class=form-group style="margin-top:.75rem">
      <label>Key facts</label>
      <textarea name=key_facts rows=5 placeholder="One fact per line. e.g.&#10;38 states have property tax levy limits&#10;Average cap is 2–3% annual growth&#10;Towns near levy limits have fund balances 40% lower"></textarea>
      <p class=hint>One per line — these appear as bullet points in the sidebar.</p>
    </div>
  </div>

  <div class=card>
    <div class=card-header><span class=card-num>Body</span><div><div class=card-title>Brief Content</div><div class=card-subtitle>Markdown supported. Use ## for section headings.</div></div></div>
    <div class=form-group>
      <textarea name=body rows=30 style="font-family:monospace;font-size:.82rem" placeholder="## The Problem&#10;&#10;Start writing here...&#10;&#10;## What the Data Shows&#10;&#10;## Policy Recommendations&#10;&#10;## Conclusion"></textarea>
    </div>
  </div>

  <div class=card>
    <div class=card-header><span class=card-num>📎</span><div><div class=card-title>Graphics & Attachments</div><div class=card-subtitle>Charts, tables, scans — images appear in a "Charts & Graphics" section; PDFs become download links</div></div></div>
    <div class=form-group>
      <label>Upload files</label>
      <input type=file name=graphics multiple accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml,application/pdf">
      <p class=hint>You can select multiple files. JPG, PNG, WebP, GIF, SVG, or PDF.</p>
    </div>
  </div>

  <div class=card>
    <div class=form-group><label style="display:flex;align-items:center;gap:.5rem;cursor:pointer"><input type=checkbox name=publish value=true> Publish immediately (uncheck to save as draft)</label></div>
    <div style="margin-top:.75rem"><label style="display:flex;align-items:center;gap:.5rem;cursor:pointer"><input type=checkbox name=push value=true checked> Push to GitHub now</label></div>
  </div>

  <div class=actions-bar>
    <button type=submit class="btn btn-green">Save Brief</button>
    <a href=/briefs class="btn btn-outline">Cancel</a>
  </div>
</form>"""

# ── new report form ────────────────────────────────────────────────────────────

def render_new_form(alert=""):
    year = datetime.now().year
    first_flag  = FLAG_TPL.replace("{n}", "1")
    first_peer  = PEER_TPL.replace("{n}", "1")
    first_trend = TREND_TPL.replace("{n}", "1")

    toc_sections = [
        ("s-meta","Town Info"), ("s-exec","I. Executive Summary"),
        ("s-socio","II. Socioeconomic"), ("s-ledger","III. Revenue & Expenditure"),
        ("s-debt","IV. Debt & Pensions"), ("s-impact","V. Community Impact"),
        ("s-flags","VI. Red Flags"), ("s-gov","VII. Governance"),
        ("s-recs","VIII. Recommendations"), ("s-citizen","IX. Citizen Action"),
        ("s-conclusion","X. Conclusion"),
    ]
    toc = '<div class=toc>' + "".join(f'<a href="#{i}">{l}</a>' for i,l in toc_sections) + '</div>'

    return f"""
<h2>New Report</h2>
{alert}
{toc}
<form method=POST action=/save enctype="multipart/form-data">

<!-- ── META ── -->
<div class=card id=s-meta>
  <div class=card-header><span class=card-num>Meta</span><div><div class=card-title>Town Info & Metadata</div><div class=card-subtitle>Used for the map, badges, and slug</div></div></div>
  <div class=form-grid>
    <div class="form-group full"><label>Report title</label><input type=text name=title placeholder="Springfield, IL — FY{year} Budget Analysis" required></div>
    <div class=form-group><label>Town / City</label><input type=text name=town placeholder="Springfield" required></div>
    <div class=form-group><label>State (2 letters)</label><input type=text name=state placeholder="IL" maxlength=2 required></div>
    <div class=form-group><label>Fiscal year</label><input type=text name=fiscal_year placeholder="{year}" value="{year}" required></div>
    <div class=form-group><label>Population</label><input type=number name=population placeholder="4800"></div>
    <div class=form-group><label>Overall severity</label>
      <select name=severity>
        <option value=high>🔴 High</option>
        <option value=medium selected>🟠 Medium</option>
        <option value=low>🟢 Low</option>
      </select>
    </div>
    <div class=form-group><label style="display:flex;align-items:center;gap:.5rem;cursor:pointer;margin-top:1.4rem"><input type=checkbox name=news_desert> News desert (no local paper)</label></div>
  </div>
  <div class=sub-label>Location (for the map)</div>
  <div class=form-grid>
    <div class=form-group><label>Latitude</label><input type=text name=lat placeholder="39.7817"><p class=hint>Google the town name + "coordinates"</p></div>
    <div class=form-group><label>Longitude</label><input type=text name=lng placeholder="-89.6501"></div>
  </div>
  <div class=sub-label>Source</div>
  <div class=form-grid>
    <div class="form-group full"><label>Budget document URL</label><input type=url name=source_url placeholder="https://town.gov/budget2024.pdf"></div>
  </div>
</div>

<!-- ── I. EXEC SUMMARY ── -->
<div class=card id=s-exec>
  <div class=card-header><span class=card-num>I</span><div><div class=card-title>Executive Summary</div><div class=card-subtitle>High-level financial snapshot — 2–3 sentences a taxpayer can read in 30 seconds</div></div></div>
  <div class=form-group><label>Summary</label><textarea name=exec_summary rows=4 placeholder="This report examines Springfield's FY{year} budget of $4.2M — a 12% increase from the prior year despite a declining population. We found three significant red flags..."></textarea></div>
  <div class=sub-label>Key numbers (shown as a stats bar)</div>
  <div class=form-grid-4>
    <div class=form-group><label>Total Budget</label><input type=text name=total_budget placeholder="$4.2M"></div>
    <div class=form-group><label>Per Capita Spending</label><input type=text name=per_capita placeholder="$875"></div>
    <div class=form-group><label>Fund Balance</label><input type=text name=fund_balance placeholder="$320K (7.6%)"></div>
    <div class=form-group><label>Total Debt Load</label><input type=text name=debt_load placeholder="$1.1M"></div>
  </div>
</div>

<!-- ── II. SOCIOECONOMIC ── -->
<div class=card id=s-socio>
  <div class=card-header><span class=card-num>II</span><div><div class=card-title>Socioeconomic Context & Peer Comparison</div><div class=card-subtitle>Population trends, inflation, economic drivers, and how this town compares</div></div></div>
  <div class=form-group><label>Context narrative</label><textarea name=socio_context rows=4 placeholder="Springfield has lost 8% of its population since 2015, shrinking the tax base while fixed costs remain..."></textarea></div>
  <div class=form-group style="margin-top:.75rem"><label>Population & economic trends (key data points)</label><textarea name=pop_trends rows=3 placeholder="Population 2015: 5,200 → 2024: 4,800 (-7.7%). Median household income: $41,200. Unemployment: 6.1% vs. state avg 4.3%."></textarea></div>
  <div class=sub-label>Peer Comparison</div>
  <div id=peers-container>{first_peer}</div>
  <button type=button class=add-row-btn onclick="addBlock('peers-container', peerTpl, 'peer')">+ Add peer town</button>
</div>

<!-- ── III. LEDGER ── -->
<div class=card id=s-ledger>
  <div class=card-header><span class=card-num>III</span><div><div class=card-title>Revenue & Expenditure Ledger</div><div class=card-subtitle>Where money comes from and goes — include percentages</div></div></div>
  <div class=form-grid>
    <div class=form-group><label>Revenue sources</label><textarea name=revenue_sources rows=5 placeholder="Property tax: $2.1M (50%)\nState aid: $1.0M (24%)\nSales tax: $620K (15%)\nFees & permits: $480K (11%)"></textarea></div>
    <div class=form-group><label>Expenditure breakdown</label><textarea name=expenditure_breakdown rows=5 placeholder="Public safety: $1.72M (41%)\nGeneral govt: $840K (20%)\nPublic works: $630K (15%)\nDebt service: $420K (10%)\nParks & rec: $180K (4%)"></textarea></div>
  </div>
  <div class=sub-label>5-Year Trend</div>
  <div id=trend-container>{first_trend}</div>
  <button type=button class=add-row-btn onclick="addBlock('trend-container', trendTpl, 'trend')">+ Add year</button>
</div>

<!-- ── IV. DEBT ── -->
<div class=card id=s-debt>
  <div class=card-header><span class=card-num>IV</span><div><div class=card-title>Debt, Pensions & Long-Term Obligations</div><div class=card-subtitle>The numbers that don't show up in the headline budget</div></div></div>
  <div class=form-grid-4>
    <div class=form-group><label>Bonded Debt</label><input type=text name=bonded_debt placeholder="$680K"></div>
    <div class=form-group><label>Unfunded Pension Liability</label><input type=text name=pension_liability placeholder="$1.2M"></div>
    <div class=form-group><label>OPEB Liability</label><input type=text name=opeb_liability placeholder="$340K"></div>
    <div class=form-group><label>Debt Service % of General Fund</label><input type=text name=debt_service_pct placeholder="10%"></div>
  </div>
  <div class=form-group style="margin-top:.85rem"><label>Narrative</label><textarea name=debt_narrative rows=3 placeholder="The town's pension fund is 61% funded, well below the recommended 80% floor. At current contribution rates..."></textarea></div>
</div>

<!-- ── V. COMMUNITY IMPACT ── -->
<div class=card id=s-impact>
  <div class=card-header><span class=card-num>V</span><div><div class=card-title>Community Impact Analysis</div><div class=card-subtitle>What the budget means for residents on the ground</div></div></div>
  <div class=sub-label>A. Education & Youth Programs</div>
  <div class=form-group><textarea name=impact_education rows=3 placeholder="Youth programs funding cut 22% vs. prior year. After-school program serving 180 kids eliminated..."></textarea></div>
  <div class=sub-label>B. Facilities, Infrastructure & Parks</div>
  <div class=form-group><textarea name=impact_infrastructure rows=3 placeholder="Road resurfacing budget: $85K — enough to pave 0.4 lane miles. Backlog estimated at 12 lane miles..."></textarea></div>
  <div class=sub-label>C. Public Safety Staffing & Allocation</div>
  <div class=form-group><textarea name=impact_safety rows=3 placeholder="1.8 officers per 1,000 residents vs. state average of 2.4. Police budget rose 43% while fire remained flat..."></textarea></div>
  <div class=sub-label>D. Social Services & Senior Programs</div>
  <div class=form-group><textarea name=impact_social rows=3 placeholder="Senior center operating hours reduced. Meals on Wheels contract not renewed for FY{year}..."></textarea></div>
</div>

<!-- ── VI. RED FLAGS ── -->
<div class=card id=s-flags>
  <div class=card-header><span class=card-num>VI</span><div><div class=card-title>Major Financial Red Flags & Ghost Indicators</div><div class=card-subtitle>Structural deficits, the vacancy trick, OPEB liabilities, fund balance erosion</div></div></div>
  <div id=flags-container>{first_flag}</div>
  <button type=button class=add-row-btn onclick="addBlock('flags-container', flagTpl, 'flag')">+ Add red flag</button>
</div>

<!-- ── VII. GOVERNANCE ── -->
<div class=card id=s-gov>
  <div class=card-header><span class=card-num>VII</span><div><div class=card-title>Governance & Transparency Audit</div><div class=card-subtitle>How accessible is this data to a regular citizen?</div></div></div>
  <div class=form-group><label>Narrative</label><textarea name=governance rows=4 placeholder="The FY{year} budget was posted to the town website 3 days before the vote, giving residents almost no time to review. The document spans 214 pages with no summary..."></textarea></div>
  <div class=form-grid-3 style="margin-top:.85rem">
    <div class=form-group><label>Budget publicly available?</label><input type=text name=budget_public placeholder="Yes, PDF only"></div>
    <div class=form-group><label>Last audit published</label><input type=text name=last_audit placeholder="FY2022 (2 years behind)"></div>
    <div class=form-group><label>Public hearings held</label><input type=text name=public_hearings placeholder="1 hearing, 4 days' notice"></div>
  </div>
</div>

<!-- ── VIII. RECOMMENDATIONS ── -->
<div class=card id=s-recs>
  <div class=card-header><span class=card-num>VIII</span><div><div class=card-title>Policy Options & Strategic Recommendations</div><div class=card-subtitle>Shared services, capital prioritization, revenue optimization</div></div></div>
  <div class=form-group><textarea name=recommendations rows=6 placeholder="1. Shared services agreement with neighboring Millbrook for DPW could save ~$180K/yr.\n2. Vacancy tax on downtown properties could generate $60–90K in new revenue.\n3. Five-year capital plan needed — current infrastructure backlog is growing faster than repair budget."></textarea></div>
</div>

<!-- ── IX. CITIZEN ACTION ── -->
<div class=card id=s-citizen>
  <div class=card-header><span class=card-num>IX</span><div><div class=card-title>Citizen Action Guide</div><div class=card-subtitle>What a resident can do right now</div></div></div>
  <div class=form-group><label>Action steps</label><textarea name=citizen_action rows=4 placeholder="1. Attend the next Town Council meeting and ask the Mayor about the police budget increase.\n2. File a FOIA request for the full audited financials using the link below.\n3. Sign up for the budget alert mailing list at springfield.gov/alerts."></textarea></div>
  <div class=form-grid style="margin-top:.85rem">
    <div class=form-group><label>Next budget hearing date</label><input type=text name=next_hearing placeholder="March 15, 2025 · 7pm · Town Hall"></div>
    <div class=form-group><label>FOIA / records contact</label><input type=text name=foia_contact placeholder="clerk@springfield.gov · (555) 000-0000"></div>
  </div>
</div>

<!-- ── X. CONCLUSION ── -->
<div class=card id=s-conclusion>
  <div class=card-header><span class=card-num>X</span><div><div class=card-title>Conclusion & Long-Term Outlook</div><div class=card-subtitle>Where is this town headed if nothing changes?</div></div></div>
  <div class=form-group><textarea name=conclusion rows=5 placeholder="Springfield is caught in a fiscal squeeze familiar to many small post-industrial towns: a shrinking tax base, rising legacy costs, and deferred infrastructure. Without structural changes, the town is likely to face a service-level crisis within 5–7 years..."></textarea></div>
</div>

<!-- ── GRAPHICS ── -->
<div class=card>
  <div class=card-header><span class=card-num>📎</span><div><div class=card-title>Graphics & Attachments</div><div class=card-subtitle>Charts, tables, scans — images appear in a \"Charts & Graphics\" section; PDFs become download links</div></div></div>
  <div class=form-group>
    <label>Upload files</label>
    <input type=file name=graphics multiple accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml,application/pdf">
    <p class=hint>You can select multiple files. JPG, PNG, WebP, GIF, SVG, or PDF.</p>
  </div>
</div>

<!-- ── PUBLISH ── -->
<div class=card>
  <div class=form-group><label style="display:flex;align-items:center;gap:.5rem;cursor:pointer"><input type=checkbox name=publish value=true> Publish immediately (uncheck to save as draft)</label></div>
  <div style="margin-top:.75rem"><label style="display:flex;align-items:center;gap:.5rem;cursor:pointer"><input type=checkbox name=push value=true checked> Push to GitHub now (live in ~2 min)</label></div>
</div>

<div class=actions-bar>
  <button type=submit class="btn btn-green">Save Report</button>
  <a href=/ class="btn btn-outline">Cancel</a>
</div>
</form>

<script>
// counters for each block type
const counts = {{flag: 1, peer: 1, trend: 1}};

const flagTpl = `{FLAG_TPL}`;
const peerTpl = `{PEER_TPL}`;
const trendTpl = `{TREND_TPL}`;

function addBlock(containerId, tpl, type) {{
  counts[type]++;
  const n = counts[type];
  const html = tpl.replace(/\\{{n\\}}/g, n);
  document.getElementById(containerId).insertAdjacentHTML('beforeend', html);
}}

function removeEl(id) {{
  const el = document.getElementById(id);
  if (el) el.remove();
}}
</script>
"""

# ── handler ────────────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def send_html(self, html, code=200):
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, url):
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self.handle_list()
        elif path == "/new":
            self.send_html(page("New Report", render_new_form(), "new"))
        elif path.startswith("/edit/"):
            self.handle_edit(path[6:])
        elif path.startswith("/delete/"):
            self.handle_delete(path[8:])
        elif path == "/briefs":
            self.handle_briefs_list()
        elif path == "/briefs/new":
            self.send_html(page("New Brief", render_brief_form(), "new-brief"))
        elif path.startswith("/briefs/edit/"):
            self.handle_brief_edit(path[13:])
        elif path.startswith("/briefs/delete/"):
            self.handle_brief_delete(path[15:])
        elif path == "/applications":
            self.handle_applications()
        elif path.startswith("/photo/"):
            self.handle_photo(urllib.parse.unquote(path[7:]))
        elif path == "/team":
            self.handle_team_list()
        elif path == "/team/new":
            self.handle_team_form()
        elif path.startswith("/team/edit/"):
            self.handle_team_form(path[11:])
        elif path.startswith("/team/delete/"):
            self.handle_team_delete(path[13:])
        elif path.startswith("/team/move/"):
            rest = path[11:]
            member_id, _, direction = rest.rpartition("/")
            self.handle_team_move(member_id, direction)
        elif path == "/settings":
            self.handle_settings()
        elif path == "/submissions":
            self.handle_submissions()
        elif path == "/submissions/setup":
            self.handle_submissions_setup()
        elif path.startswith("/submissions/import/"):
            self.handle_import(path[20:])
        else:
            self.send_html("<h1>Not found</h1>", 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        path = self.path.split("?")[0]

        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" in ctype and path in ("/team/save", "/save", "/briefs/save"):
            boundary_m = re.search(r'boundary=("?)([^";]+)\1', ctype)
            if not boundary_m:
                self.send_html("<h1>Bad request</h1>", 400)
                return
            raw_bytes = self.rfile.read(length)
            fields, files = parse_multipart(raw_bytes, boundary_m.group(2).encode())
            if path == "/team/save":
                self.handle_team_save(fields, files)
            elif path == "/save":
                self.handle_save(fields, files)
            else:
                self.handle_brief_save(fields, files)
            return

        raw = self.rfile.read(length).decode()
        data = MultiDict(urllib.parse.parse_qs(raw, keep_blank_values=True))
        if path == "/save":
            self.handle_save(data)
        elif path.startswith("/update/"):
            self.handle_update(path[8:], data)
        elif path == "/briefs/save":
            self.handle_brief_save(data)
        elif path.startswith("/briefs/update/"):
            self.handle_brief_update(path[15:], data)
        elif path == "/submissions/setup":
            self.handle_submissions_setup_save(data)
        elif path == "/settings":
            self.handle_settings_save(data)
        else:
            self.send_html("<h1>Not found</h1>", 404)

    def handle_briefs_list(self):
        briefs = list_briefs()
        if not briefs:
            rows = '<p class=empty>No briefs yet. <a href="/briefs/new">Write your first policy brief →</a></p>'
        else:
            rows = ""
            for b in briefs:
                draft = b.get("draft", "true") == "true"
                rows += f"""
<div class=card>
  <div class=report-row>
    <div>
      <div class=report-title>{esc(b.get('title', b['slug']))}</div>
      <div class=report-meta>{esc(b.get('topic',''))} · {esc(b.get('date',''))} · by {esc(b.get('author',''))}</div>
    </div>
    <div style="display:flex;gap:.5rem;align-items:center;flex-shrink:0">
      {"<span class='badge badge-draft'>draft</span>" if draft else "<span class='badge badge-low'>published</span>"}
      <a href="/briefs/edit/{b['slug']}" class="btn btn-outline btn-sm">Edit</a>
      <a href="/briefs/delete/{b['slug']}" class="btn btn-sm" style="background:#fef2f2;color:#dc2626;border:1px solid #fecaca" onclick="return confirm('Delete this brief?')">Delete</a>
    </div>
  </div>
</div>"""
        body = f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem">
  <h2 style="margin:0">Policy Briefs</h2>
  <a href="/briefs/new" class="btn btn-primary">+ New Brief</a>
</div>
{rows}"""
        self.send_html(page("Policy Briefs", body, "briefs"))

    def handle_brief_edit(self, slug):
        content = read_brief(slug)
        safe = esc(content)
        body = f"""
<h2>Edit Brief</h2>
<p style="color:#6b6b80;font-size:.88rem;margin-bottom:1.5rem">Editing <code>{esc(slug)}.md</code> — raw markdown.</p>
<form method=POST action="/briefs/update/{esc(slug)}">
  <div class=card>
    <div class=form-group>
      <label>Brief content (Markdown)</label>
      <textarea name=content rows=35 style="font-family:monospace;font-size:.8rem">{safe}</textarea>
    </div>
  </div>
  <div class=form-group style="margin-bottom:1rem">
    <label style="display:flex;align-items:center;gap:.5rem;cursor:pointer">
      <input type=checkbox name=push value=true checked> Push to GitHub after saving
    </label>
  </div>
  <div class=actions-bar>
    <button type=submit class="btn btn-green">Save Changes</button>
    <a href="/briefs" class="btn btn-outline">Cancel</a>
  </div>
</form>"""
        self.send_html(page("Edit Brief", body, "briefs"))

    def handle_brief_delete(self, slug):
        path = os.path.join(BRIEFS, slug + ".md")
        if os.path.exists(path):
            os.remove(path)
            subprocess.run(["git", "add", "-A"], cwd=BASE)
            subprocess.run(["git", "commit", "-m", f"Delete brief: {slug}"], cwd=BASE)
            subprocess.run(["git", "push"], cwd=BASE)
        self.redirect("/briefs")

    def handle_brief_save(self, data, files=None):
        title = data.get("title", "untitled")
        slug = slugify(title)
        content = build_brief_md(data)
        uploads = save_uploads(files or {}, "graphics", slug)
        content += graphics_md(uploads)
        path = write_brief(slug, content)
        alert = ""
        if data.get("push") == "true":
            ok, err = (git_push_all(f"Add brief: {title}") if uploads else git_push(path, f"Add brief: {title}"))
            alert = '<div class="alert alert-green">✓ Brief saved and pushed. Live in ~2 min.</div>' if ok else f'<div class="alert alert-red">Saved locally but push failed: {esc(err)}</div>'
        else:
            alert = '<div class="alert alert-green">✓ Brief saved locally.</div>'
        self.send_html(page("New Brief", render_brief_form(alert=alert), "new-brief"))

    def handle_brief_update(self, slug, data):
        content = data.get("content", "")
        path = write_brief(slug, content)
        if data.get("push") == "true":
            git_push(path, f"Update brief: {slug}")
        self.redirect("/briefs")

    def handle_settings(self, alert=""):
        cfg = load_site_config()
        apply_url = esc(cfg.get("apply_url", ""))
        alert_html = f'<div class="alert alert-green">{alert}</div>' if alert else ""
        body = f"""
        <h2 style="margin-bottom:1.5rem">Site Settings</h2>
        {alert_html}
        <form method=POST action="/settings" style="max-width:600px">
          <div class=form-group>
            <label>Apply Page — "Join Us" button link</label>
            <input type=url name=apply_url value="{apply_url}" placeholder="https://forms.google.com/..." style="width:100%">
            <p style="font-size:.8rem;color:#888;margin-top:.3rem">Paste the URL where applicants should apply (Google Form, Typeform, Airtable, etc.). Leave blank to show a "coming soon" placeholder.</p>
          </div>
          <button type=submit class=btn>Save Settings</button>
        </form>
        """
        self.send_html(page("Settings", body, "settings"))

    def handle_settings_save(self, data):
        cfg = load_site_config()
        cfg["apply_url"] = data.get("apply_url", "").strip()
        save_site_config(cfg)
        git_push(SITE_CONFIG_FILE, "Update site settings: apply URL")
        self.handle_settings(alert="Settings saved and pushed to GitHub ✓")

    # ── team ────────────────────────────────────────────────────────────────────

    def handle_photo(self, rel):
        safe = os.path.normpath(rel).replace("\\", "/")
        if safe.startswith("..") or os.path.isabs(safe):
            self.send_html("<h1>Not found</h1>", 404)
            return
        full = os.path.join(BASE, "static", safe)
        if not os.path.isfile(full):
            self.send_html("<h1>Not found</h1>", 404)
            return
        ctypes = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        ctype = ctypes.get(os.path.splitext(full)[1].lower(), "application/octet-stream")
        with open(full, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(content))
        self.end_headers()
        self.wfile.write(content)

    def handle_team_list(self, alert=""):
        team = load_team()
        alert_html = alert or ""
        if not team:
            rows = '<p class=empty>No team members yet. <a href="/team/new">Add your first team member →</a></p>'
        else:
            rows = ""
            last = len(team) - 1
            for i, m in enumerate(team):
                photo = m.get("photo", "")
                if photo:
                    avatar = f'<img src="/photo/{esc(photo)}" style="width:52px;height:52px;border-radius:50%;object-fit:cover;border:2px solid #d1fae5" alt="">'
                else:
                    initials = "".join(w[0] for w in m.get("name", "?").split()[:2]).upper()
                    avatar = f'<div style="width:52px;height:52px;border-radius:50%;background:linear-gradient(135deg,#047857,#059669);color:white;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.1rem">{esc(initials)}</div>'
                up_btn = f'<a href="/team/move/{m["id"]}/up" class="btn btn-outline btn-sm" title="Move up">↑</a>' if i > 0 else '<span class="btn btn-outline btn-sm" style="opacity:.25;pointer-events:none">↑</span>'
                down_btn = f'<a href="/team/move/{m["id"]}/down" class="btn btn-outline btn-sm" title="Move down">↓</a>' if i < last else '<span class="btn btn-outline btn-sm" style="opacity:.25;pointer-events:none">↓</span>'
                linkedin = f' · <a href="{esc(m["linkedin"])}" target=_blank style="color:#0a66c2">LinkedIn ↗</a>' if m.get("linkedin") else ""
                rows += f"""
<div class=card>
  <div class=report-row style="align-items:center">
    <div style="display:flex;gap:1rem;align-items:center">
      <div style="display:flex;flex-direction:column;gap:.25rem">{up_btn}{down_btn}</div>
      {avatar}
      <div>
        <div class=report-title>{i+1}. {esc(m.get('name',''))}</div>
        <div class=report-meta>{esc(m.get('title',''))}{linkedin}</div>
      </div>
    </div>
    <div style="display:flex;gap:.5rem;align-items:center;flex-shrink:0">
      <a href="/team/edit/{m['id']}" class="btn btn-outline btn-sm">Edit</a>
      <a href="/team/delete/{m['id']}" class="btn btn-sm" style="background:#fef2f2;color:#dc2626;border:1px solid #fecaca" onclick="return confirm('Remove {esc(m.get('name',''))} from the team?')">Remove</a>
    </div>
  </div>
</div>"""
        body = f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem">
  <h2 style="margin:0">Team Members</h2>
  <a href="/team/new" class="btn btn-primary">+ Add Member</a>
</div>
{alert_html}
<p style="font-size:.85rem;color:#6b6b80;margin-bottom:1.25rem">Members appear on the public Team page in this order. Use ↑↓ to reorder — changes push to the live site automatically.</p>
{rows}"""
        self.send_html(page("Team", body, "team"))

    def handle_team_form(self, member_id=None, alert=""):
        m = {}
        if member_id:
            m = next((x for x in load_team() if x.get("id") == member_id), {})
            if not m:
                self.redirect("/team")
                return
        heading = "Edit Team Member" if member_id else "Add Team Member"
        photo_note = ""
        if m.get("photo"):
            photo_note = f'<p class=hint style="margin-top:.4rem">Current photo: <img src="/photo/{esc(m["photo"])}" style="width:36px;height:36px;border-radius:50%;object-fit:cover;vertical-align:middle;margin-left:.3rem" alt=""> — upload a new file to replace it.</p>'
        body = f"""
<h2>{heading}</h2>
{alert}
<form method=POST action=/team/save enctype="multipart/form-data" style="max-width:640px">
  <input type=hidden name=member_id value="{esc(m.get('id',''))}">
  <div class=card>
    <div class=form-grid>
      <div class=form-group>
        <label>Full name <span style="color:#dc2626">*</span></label>
        <input type=text name=name required value="{esc(m.get('name',''))}" placeholder="Jane Rivera">
      </div>
      <div class=form-group>
        <label>Title / role <span style="color:#dc2626">*</span></label>
        <input type=text name=title required value="{esc(m.get('title',''))}" placeholder="Lead Budget Analyst">
      </div>
      <div class="form-group full">
        <label>Bio</label>
        <textarea name=bio rows=4 placeholder="Two or three sentences about who they are and what they cover.">{esc(m.get('bio',''))}</textarea>
      </div>
      <div class="form-group full">
        <label>LinkedIn URL</label>
        <input type=url name=linkedin value="{esc(m.get('linkedin',''))}" placeholder="https://www.linkedin.com/in/janerivera">
      </div>
      <div class="form-group full">
        <label>Photo</label>
        <input type=file name=photo accept="image/png,image/jpeg,image/webp">
        <p class=hint>Square photos look best. JPG, PNG, or WebP.</p>
        {photo_note}
      </div>
    </div>
  </div>
  <div class=actions-bar>
    <button type=submit class="btn btn-green">{"Save Changes" if member_id else "Add to Team"}</button>
    <a href=/team class="btn btn-outline">Cancel</a>
  </div>
</form>"""
        self.send_html(page(heading, body, "team"))

    def handle_team_save(self, fields, files):
        team = load_team()
        member_id = fields.get("member_id", "").strip()
        name = fields.get("name", "").strip()
        if not name:
            self.redirect("/team")
            return

        if member_id:
            member = next((x for x in team if x.get("id") == member_id), None)
            if member is None:
                self.redirect("/team")
                return
        else:
            member_id = slugify(name) or "member"
            existing = {x.get("id") for x in team}
            base_id, n = member_id, 2
            while member_id in existing:
                member_id = f"{base_id}-{n}"
                n += 1
            member = {"id": member_id, "order": len(team) + 1}
            team.append(member)

        member["name"] = name
        member["title"] = fields.get("title", "").strip()
        member["bio"] = fields.get("bio", "").strip()
        member["linkedin"] = fields.get("linkedin", "").strip()

        if files.get("photo"):
            filename, content = files["photo"][0]
            ext = os.path.splitext(filename)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp") and content:
                os.makedirs(TEAM_PHOTO_DIR, exist_ok=True)
                old = member.get("photo")
                if old:
                    old_path = os.path.join(BASE, "static", old.replace("/", os.sep))
                    if os.path.exists(old_path):
                        os.remove(old_path)
                photo_name = f"{member_id}{ext}"
                with open(os.path.join(TEAM_PHOTO_DIR, photo_name), "wb") as f:
                    f.write(content)
                member["photo"] = f"images/team/{photo_name}"

        save_team(team)
        ok, err = git_push_all(f"Team: save member {name}")
        alert = '<div class="alert alert-green">✓ Team member saved and pushed. Live in ~2 min.</div>' if ok else f'<div class="alert alert-red">Saved locally but push failed: {esc(err)}</div>'
        self.handle_team_list(alert=alert)

    def handle_team_delete(self, member_id):
        team = load_team()
        member = next((x for x in team if x.get("id") == member_id), None)
        if member:
            if member.get("photo"):
                photo_path = os.path.join(BASE, "static", member["photo"].replace("/", os.sep))
                if os.path.exists(photo_path):
                    os.remove(photo_path)
            team.remove(member)
            save_team(team)
            git_push_all(f"Team: remove member {member.get('name', member_id)}")
        self.redirect("/team")

    def handle_team_move(self, member_id, direction):
        team = load_team()
        idx = next((i for i, x in enumerate(team) if x.get("id") == member_id), None)
        if idx is not None:
            new_idx = idx - 1 if direction == "up" else idx + 1
            if 0 <= new_idx < len(team):
                team[idx], team[new_idx] = team[new_idx], team[idx]
                save_team(team)
                git_push_all(f"Team: reorder members")
        self.redirect("/team")

    def handle_applications(self):
        cfg = load_config()
        token = cfg.get("netlify_token", "")
        site_id = cfg.get("netlify_site_id", "")

        if not token or not site_id:
            self.redirect("/submissions/setup")
            return

        apps, err = fetch_applications(token, site_id)

        if err:
            body = f'<h2>Applications</h2><div class="alert alert-red">Could not connect to Netlify: {esc(err)}</div>'
            self.send_html(page("Applications", body, "applications"))
            return

        if not apps:
            body = '<h2>Applications</h2><p class=empty>No applications yet.</p>'
            self.send_html(page("Applications", body, "applications"))
            return

        EXP_LABELS = {
            "yes-extensively": "✅ Yes, extensively",
            "yes-some": "✅ Yes, a few times",
            "no-but-comfortable": "🟡 No, but comfortable with financial docs",
            "no-new": "🔴 New to this",
        }

        rows = ""
        for a in apps:
            d = a.get("data", {})
            created = a.get("created_at", "")[:10]
            name = d.get("name", "Unknown")
            email = d.get("email", "")
            location = d.get("location", "")
            occupation = d.get("occupation", "")
            experience = EXP_LABELS.get(d.get("experience", ""), d.get("experience", ""))
            motivation = d.get("motivation", "")
            town_interest = d.get("town_interest", "")
            other = d.get("other", "")

            rows += f"""
<div class=card>
  <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;flex-wrap:wrap">
    <div>
      <div class=report-title>{esc(name)}</div>
      <div class=report-meta>{esc(email)} · {esc(location)} · {esc(occupation)} · Applied {esc(created)}</div>
    </div>
    <span class="badge badge-draft" style="flex-shrink:0">{esc(experience)}</span>
  </div>
  {"" if not motivation else f'<div style="margin-top:1rem"><div style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#6b6b80;margin-bottom:.3rem">Why they want to do this</div><div style="font-size:.88rem;color:#3a3a4a;line-height:1.6">{esc(motivation)}</div></div>'}
  {"" if not town_interest else f'<div style="margin-top:.85rem"><div style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#6b6b80;margin-bottom:.3rem">Town they\'d cover first</div><div style="font-size:.88rem;color:#3a3a4a;line-height:1.6">{esc(town_interest)}</div></div>'}
  {"" if not other else f'<div style="margin-top:.85rem"><div style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#6b6b80;margin-bottom:.3rem">Additional notes</div><div style="font-size:.88rem;color:#3a3a4a;line-height:1.6">{esc(other)}</div></div>'}
  {"" if not d.get("resume") else f'<div style="margin-top:.85rem"><div style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#6b6b80;margin-bottom:.3rem">Resume / CV</div><pre style="font-size:.78rem;color:#3a3a4a;line-height:1.6;white-space:pre-wrap;background:#f7f7fb;border:1px solid #e5e5f0;border-radius:8px;padding:.85rem;overflow-x:auto">{esc(d.get("resume",""))}</pre></div>'}
  {f'<div style="margin-top:.85rem"><a href="mailto:{esc(email)}" class="btn btn-outline btn-sm">Reply by email</a></div>' if email else ""}
</div>"""

        body = f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem">
  <h2 style="margin:0">Analyst Applications <span style="font-size:.85rem;font-weight:400;color:#6b6b80">({len(apps)} received)</span></h2>
</div>
{rows}"""
        self.send_html(page("Applications", body, "applications"))

    def handle_submissions(self):
        cfg = load_config()
        token = cfg.get("netlify_token", "")
        site_id = cfg.get("netlify_site_id", "")

        if not token or not site_id:
            self.redirect("/submissions/setup")
            return

        subs, err = fetch_submissions(token, site_id)

        if err:
            body = f"""
<h2>Submissions</h2>
<div class="alert alert-red">Could not connect to Netlify: {esc(err)}<br>
<a href="/submissions/setup" style="color:inherit;font-weight:700">Re-enter your credentials →</a></div>"""
            self.send_html(page("Submissions", body, "submissions"))
            return

        if not subs:
            body = """
<h2>Submissions</h2>
<p class=empty>No submissions yet. When someone fills out the Submit a Town form on your site, they'll appear here.</p>"""
            self.send_html(page("Submissions", body, "submissions"))
            return

        rows = ""
        for s in subs:
            d = s.get("data", {})
            sid = s.get("id", "")
            town = d.get("town", "Unknown town")
            state = d.get("state", "")
            fy = d.get("fiscal_year", "")
            sev = d.get("overall_severity", "medium")
            created = s.get("created_at", "")[:10]
            summary = d.get("exec_summary", "")[:200]
            flags = d.get("red_flags", "")[:200]
            rows += f"""
<div class=card>
  <div class=report-row>
    <div style="flex:1;min-width:0">
      <div class=report-title>{esc(town)}, {esc(state)} — FY{esc(fy)}</div>
      <div class=report-meta>Submitted {esc(created)}</div>
      {f'<div style="margin-top:.6rem;font-size:.83rem;color:#444;line-height:1.5">{esc(summary)}{"…" if len(d.get("exec_summary",""))>200 else ""}</div>' if summary else ''}
      {f'<div style="margin-top:.4rem;font-size:.78rem;color:#dc2626;line-height:1.5"><strong>Flags:</strong> {esc(flags)}{"…" if len(d.get("red_flags",""))>200 else ""}</div>' if flags else ''}
    </div>
    <div style="display:flex;gap:.5rem;align-items:center;flex-shrink:0;flex-wrap:wrap;margin-left:1rem">
      <span class="badge badge-{sev}">{sev}</span>
      <a href="/submissions/import/{sid}" class="btn btn-green btn-sm">Import as Draft</a>
    </div>
  </div>
</div>"""

        body = f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem">
  <h2 style="margin:0">Submissions <span style="font-size:.85rem;font-weight:400;color:#6b6b80">({len(subs)} pending)</span></h2>
  <a href="/submissions/setup" class="btn btn-outline btn-sm">Settings</a>
</div>
{rows}"""
        self.send_html(page("Submissions", body, "submissions"))

    def handle_submissions_setup(self, error=""):
        cfg = load_config()
        token = cfg.get("netlify_token", "")
        site_id = cfg.get("netlify_site_id", "")

        # If we have a token, load available sites to help them find site_id
        sites_html = ""
        if token and not site_id:
            sites = fetch_sites(token)
            if isinstance(sites, list):
                opts = "".join(f'<option value="{s["id"]}">{esc(s.get("name",""))}.netlify.app</option>' for s in sites)
                sites_html = f"""
<div class=form-group style="margin-top:.75rem">
  <label>Or pick your site from the list</label>
  <select onchange="document.getElementById('site_id_input').value=this.value">
    <option value="">— select —</option>
    {opts}
  </select>
</div>"""

        alert = f'<div class="alert alert-red">{esc(error)}</div>' if error else ""

        body = f"""
<h2>Netlify Submissions Setup</h2>
{alert}
<div class=card>
  <p style="font-size:.9rem;color:#444;line-height:1.6;margin-bottom:1.25rem">
    Submissions from your public site are stored by Netlify. To read them here you need a
    <strong>Netlify personal access token</strong> (free) and your site ID.
  </p>
  <ol style="font-size:.88rem;color:#444;line-height:2;padding-left:1.25rem;margin-bottom:1.5rem">
    <li>Go to <strong>app.netlify.com → avatar (top right) → User settings → Applications</strong></li>
    <li>Click <strong>New access token</strong>, name it "Budget Watch Admin", copy it</li>
    <li>Your site ID is in <strong>Site configuration → General → Site ID</strong></li>
  </ol>
  <form method=POST action="/submissions/setup">
    <div class=form-group>
      <label>Netlify personal access token</label>
      <input type=password name=netlify_token value="{esc(token)}" placeholder="nfp_..." required>
    </div>
    <div class=form-group>
      <label>Site ID</label>
      <input type=text id=site_id_input name=netlify_site_id value="{esc(site_id)}" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx">
    </div>
    {sites_html}
    <div class=actions-bar style="position:static;padding:0;border:none;margin-top:1.25rem">
      <button type=submit class="btn btn-green">Save & Connect</button>
      <a href="/submissions" class="btn btn-outline">Cancel</a>
    </div>
  </form>
</div>"""
        self.send_html(page("Submissions Setup", body, "submissions"))

    def handle_submissions_setup_save(self, data):
        cfg = load_config()
        token = data.get("netlify_token", "").strip()
        site_id = data.get("netlify_site_id", "").strip()

        if not site_id and token:
            # Try to auto-detect if there's only one site
            sites = fetch_sites(token)
            if isinstance(sites, list) and len(sites) == 1:
                site_id = sites[0]["id"]

        if not site_id:
            self.handle_submissions_setup(error="Could not detect site ID — please enter it manually.")
            return

        cfg["netlify_token"] = token
        cfg["netlify_site_id"] = site_id
        save_config(cfg)
        self.redirect("/submissions")

    def handle_import(self, sub_id):
        cfg = load_config()
        token = cfg.get("netlify_token", "")
        site_id = cfg.get("netlify_site_id", "")

        subs, err = fetch_submissions(token, site_id)
        if err or not subs:
            self.redirect("/submissions")
            return

        sub = next((s for s in subs if s.get("id") == sub_id), None)
        if not sub:
            self.redirect("/submissions")
            return

        d = sub.get("data", {})

        # Build a MultiDict-like object from the submission data
        class FakeMultiDict:
            def __init__(self, d):
                self._d = d
            def get(self, key, default=""):
                return str(self._d.get(key, default))
            def getlist(self, key):
                return []

        fake = FakeMultiDict({
            "title": f"{d.get('town','')}, {d.get('state','').upper()} — FY{d.get('fiscal_year','')} Budget Analysis",
            "town": d.get("town", ""),
            "state": d.get("state", ""),
            "fiscal_year": d.get("fiscal_year", str(datetime.now().year)),
            "population": d.get("population", "0"),
            "severity": d.get("overall_severity", "medium"),
            "news_desert": "on" if d.get("news_desert") == "no" else "",
            "source_url": d.get("source_url", ""),
            "exec_summary": d.get("exec_summary", ""),
            "total_budget": d.get("total_budget", ""),
            "per_capita": d.get("per_capita", ""),
            "fund_balance": d.get("fund_balance", ""),
            "debt_load": "",
            "socio_context": d.get("socio_context", ""),
            "revenue_sources": d.get("revenue_sources", ""),
            "expenditure_breakdown": d.get("expenditure_breakdown", ""),
            "impact_education": d.get("impact_education", ""),
            "impact_infrastructure": d.get("impact_infrastructure", ""),
            "impact_safety": d.get("impact_safety", ""),
            "impact_social": d.get("impact_social", ""),
            "governance": d.get("governance", ""),
            "last_audit": d.get("last_audit", ""),
            "public_hearings": d.get("public_hearings", ""),
            "additional_notes": d.get("additional_notes", ""),
            "push": "false",
            "publish": "",
        })

        # Red flags: stored as freeform text, put in body section
        flags_text = d.get("red_flags", "")

        town = d.get("town", "town")
        state = d.get("state", "xx").lower()
        fy = d.get("fiscal_year", str(datetime.now().year))
        slug = f"{slugify(town)}-{slugify(state)}-{fy}-submitted"

        # Build the markdown manually to preserve the freeform flags field
        content = f"""---
title: "{fake.get('title')}"
town: "{fake.get('town')}"
state: "{fake.get('state').upper()}"
fiscal_year: "{fake.get('fiscal_year')}"
population: {fake.get('population') or '0'}
severity: "{fake.get('severity')}"
news_desert: {'true' if fake.get('news_desert') == 'on' else 'false'}
lat: 0
lng: 0
source_url: "{fake.get('source_url')}"
draft: true
submitter: "{esc(d.get('credit_name', 'Anonymous'))}"
submitter_email: "{esc(d.get('submitter_email', ''))}"
---

> **Submitted report** — review all figures against the source document before publishing.

## I. Executive Summary

{fake.get('exec_summary')}

**Total Budget:** {fake.get('total_budget')} | **Per Capita:** {fake.get('per_capita')} | **Fund Balance:** {fake.get('fund_balance')}

## III. Revenue & Expenditure Ledger

### Revenue Sources

{fake.get('revenue_sources')}

### Expenditure Breakdown

{fake.get('expenditure_breakdown')}

## V. Community Impact

### A. Education & Youth Programs

{fake.get('impact_education')}

### B. Facilities, Infrastructure & Parks

{fake.get('impact_infrastructure')}

### C. Public Safety

{fake.get('impact_safety')}

### D. Social Services & Senior Programs

{fake.get('impact_social')}

## VI. Red Flags

{flags_text}

## VII. Governance & Transparency

{fake.get('governance')}

**Last audit:** {fake.get('last_audit')} | **Public hearings:** {fake.get('public_hearings')}

## II. Socioeconomic Context

{fake.get('socio_context')}

## Additional Notes

{fake.get('additional_notes')}
"""

        write_report(slug, content)
        self.redirect("/?imported=1")

    def handle_list(self):
        reports = list_reports()
        if not reports:
            rows = '<p class=empty>No reports yet. <a href="/new">Add your first report →</a></p>'
        else:
            rows = ""
            for r in reports:
                sev   = r.get("severity", "medium")
                draft = r.get("draft", "true") == "true"
                rows += f"""
<div class=card>
  <div class=report-row>
    <div>
      <div class=report-title>{esc(r.get('title', r['slug']))}</div>
      <div class=report-meta>{esc(r.get('town',''))}, {esc(r.get('state',''))} · FY{esc(r.get('fiscal_year',''))} · pop. {esc(r.get('population',''))}</div>
    </div>
    <div style="display:flex;gap:.5rem;align-items:center;flex-shrink:0;flex-wrap:wrap">
      <span class="badge badge-{sev}">{sev}</span>
      {"<span class='badge badge-draft'>draft</span>" if draft else ""}
      <div class=row-actions>
        <a href="/edit/{r['slug']}" class="btn btn-outline btn-sm">Edit</a>
        <a href="/delete/{r['slug']}" class="btn btn-sm" style="background:#fef2f2;color:#dc2626;border:1px solid #fecaca" onclick="return confirm('Delete this report?')">Delete</a>
      </div>
    </div>
  </div>
</div>"""
        body = f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem">
  <h2 style="margin:0">Reports</h2>
  <a href="/new" class="btn btn-primary">+ New Report</a>
</div>
{rows}"""
        self.send_html(page("Reports", body, "reports"))

    def handle_edit(self, slug):
        content = read_report(slug)
        safe = esc(content)
        body = f"""
<h2>Edit Report</h2>
<p style="color:#6b6b80;font-size:.88rem;margin-bottom:1.5rem">Editing <code>{esc(slug)}.md</code> — raw markdown.</p>
<form method=POST action="/update/{esc(slug)}">
  <div class=card>
    <div class=form-group>
      <label>Report content (Markdown)</label>
      <textarea name=content rows=35 style="font-family:monospace;font-size:.8rem">{safe}</textarea>
    </div>
  </div>
  <div class=form-group style="margin-bottom:1rem">
    <label style="display:flex;align-items:center;gap:.5rem;cursor:pointer">
      <input type=checkbox name=push value=true checked> Push to GitHub after saving
    </label>
  </div>
  <div class=actions-bar>
    <button type=submit class="btn btn-green">Save Changes</button>
    <a href=/ class="btn btn-outline">Cancel</a>
  </div>
</form>"""
        self.send_html(page("Edit Report", body))

    def handle_delete(self, slug):
        path = os.path.join(REPORTS, slug + ".md")
        if os.path.exists(path):
            os.remove(path)
            subprocess.run(["git", "add", "-A"], cwd=BASE)
            subprocess.run(["git", "commit", "-m", f"Delete report: {slug}"], cwd=BASE)
            subprocess.run(["git", "push"], cwd=BASE)
        self.redirect("/")

    def handle_save(self, data, files=None):
        town  = data.get("town", "town")
        state = data.get("state", "xx").lower()
        fy    = data.get("fiscal_year", str(datetime.now().year))
        slug  = f"{slugify(town)}-{slugify(state)}-{fy}"
        content = build_report_md(data)
        uploads = save_uploads(files or {}, "graphics", slug)
        content += graphics_md(uploads)
        path = write_report(slug, content)

        msg = f"Add report: {town}, {state.upper()} FY{fy}"
        if data.get("publish") == "true":
            msg = "Publish " + msg

        alert = ""
        if data.get("push") == "true":
            ok, err = (git_push_all(msg) if uploads else git_push(path, msg))
            if ok:
                alert = '<div class="alert alert-green">✓ Report saved and pushed to GitHub. Live in ~2 min.</div>'
            else:
                alert = f'<div class="alert alert-red">Saved locally but push failed: {esc(err)}</div>'
        else:
            alert = '<div class="alert alert-green">✓ Report saved locally (not pushed).</div>'

        self.send_html(page("New Report", render_new_form(alert=alert), "new"))

    def handle_update(self, slug, data):
        content = data.get("content", "")
        path = write_report(slug, content)
        if data.get("push") == "true":
            git_push(path, f"Update report: {slug}")
        self.redirect("/")


class MultiDict:
    def __init__(self, d):
        self._d = d
    def get(self, key, default=""):
        return self._d.get(key, [default])[0]
    def getlist(self, key):
        return self._d.get(key, [])


if __name__ == "__main__":
    import webbrowser
    print(f"\n  Budget Watch Admin")
    print(f"  → http://localhost:{PORT}")
    print(f"  Press Ctrl+C to stop.\n")
    webbrowser.open(f"http://localhost:{PORT}")
    with http.server.HTTPServer(("", PORT), Handler) as srv:
        srv.serve_forever()
