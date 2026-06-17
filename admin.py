#!/usr/bin/env python3
"""
Budget Watch local admin. Run with: python3 admin.py
Then open: http://localhost:8787
"""

import http.server, json, os, re, subprocess, urllib.parse
from datetime import datetime

BASE = os.path.dirname(__file__)
REPORTS = os.path.join(BASE, "content", "reports")
PORT = 8787

# ── report helpers ─────────────────────────────────────────────────────────────

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text

def list_reports():
    if not os.path.exists(REPORTS):
        return []
    files = [f for f in os.listdir(REPORTS) if f.endswith(".md") and f != "_index.md"]
    out = []
    for f in sorted(files, reverse=True):
        path = os.path.join(REPORTS, f)
        meta = parse_frontmatter(path)
        meta["slug"] = f.replace(".md", "")
        meta["filename"] = f
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

def build_report_md(d):
    findings_md = ""
    facts = d.getlist("fact")
    questions = d.getlist("question")
    sources = d.getlist("source")
    severities = d.getlist("finding_severity")
    checks = d.getlist("check")
    for i in range(len(facts)):
        if not facts[i].strip():
            continue
        sev = severities[i] if i < len(severities) else "medium"
        chk = checks[i] if i < len(checks) else ""
        findings_md += f"""
<div class="finding {sev}">
  <div class="finding-label">{sev.title()} · {chk}</div>
  <div class="finding-fact">{facts[i]}</div>
  <div class="finding-question">{questions[i] if i < len(questions) else ''}</div>
  <div class="finding-source">Source: {sources[i] if i < len(sources) else ''}</div>
</div>
"""
    draft = "false" if d.get("publish") == "true" else "true"
    news_desert = "true" if d.get("news_desert") == "on" else "false"

    return f"""---
title: "{d.get('title', '')}"
town: "{d.get('town', '')}"
state: "{d.get('state', '').upper()}"
fiscal_year: "{d.get('fiscal_year', '')}"
population: {d.get('population', '0')}
severity: "{d.get('severity', 'medium')}"
news_desert: {news_desert}
lat: {d.get('lat', '0')}
lng: {d.get('lng', '0')}
source_url: "{d.get('source_url', '')}"
draft: {draft}
---

## Summary

{d.get('summary', '')}

## Findings

{findings_md.strip()}
"""

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

# ── HTML ───────────────────────────────────────────────────────────────────────

STYLE = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Inter',system-ui,sans-serif;background:#f5f5fa;color:#0a0a0f;min-height:100vh}
  .topbar{background:#0a0a0f;color:white;padding:1rem 2rem;display:flex;align-items:center;justify-content:space-between}
  .topbar h1{font-size:1rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase}
  .topbar a{color:rgba(255,255,255,.6);font-size:.82rem;text-decoration:none}
  .topbar a:hover{color:white}
  .wrap{max-width:900px;margin:0 auto;padding:2.5rem 2rem}
  h2{font-size:1.5rem;font-weight:800;letter-spacing:-.03em;margin-bottom:1.5rem}
  .btn{display:inline-block;font-family:inherit;font-size:.88rem;font-weight:700;padding:.6rem 1.25rem;border-radius:20px;border:none;cursor:pointer;text-decoration:none}
  .btn-primary{background:#0a0a0f;color:white}
  .btn-primary:hover{background:#333}
  .btn-green{background:#16a34a;color:white}
  .btn-green:hover{background:#15803d}
  .btn-outline{background:white;color:#0a0a0f;border:1.5px solid #ddd}
  .btn-outline:hover{border-color:#aaa}
  .btn-sm{font-size:.78rem;padding:.4rem .9rem}
  .card{background:white;border:1px solid #e5e5f0;border-radius:12px;padding:1.5rem;margin-bottom:1rem}
  .report-row{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}
  .report-title{font-weight:700;font-size:.97rem}
  .report-meta{font-size:.78rem;color:#6b6b80;margin-top:.2rem;font-family:monospace}
  .badge{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;padding:.18rem .55rem;border-radius:20px}
  .badge-high{background:#fef2f2;color:#dc2626;border:1px solid #fecaca}
  .badge-medium{background:#fff7ed;color:#ea580c;border:1px solid #fed7aa}
  .badge-low{background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0}
  .badge-draft{background:#f5f5fa;color:#6b6b80;border:1px solid #ddd}
  .row-actions{display:flex;gap:.5rem;flex-shrink:0}
  .form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1.25rem}
  .form-group{display:flex;flex-direction:column;gap:.35rem}
  .form-group.full{grid-column:1/-1}
  label{font-size:.82rem;font-weight:600;color:#3a3a4a}
  input,select,textarea{font-family:inherit;font-size:.92rem;padding:.6rem .85rem;border:1.5px solid #e5e5f0;border-radius:8px;background:white;color:#0a0a0f;outline:none;transition:border-color .12s}
  input:focus,select:focus,textarea:focus{border-color:#5b5bd6;box-shadow:0 0 0 3px rgba(91,91,214,.1)}
  textarea{resize:vertical;min-height:80px}
  .finding-block{border:1.5px solid #e5e5f0;border-radius:10px;padding:1.25rem;margin-bottom:1rem;position:relative;background:#fafafa}
  .finding-block h4{font-size:.88rem;font-weight:700;margin-bottom:.9rem;color:#5b5bd6}
  .finding-grid{display:grid;grid-template-columns:1fr 1fr;gap:.9rem}
  .finding-grid .full{grid-column:1/-1}
  .remove-btn{position:absolute;top:.75rem;right:.75rem;background:none;border:none;cursor:pointer;color:#aaa;font-size:1.1rem;line-height:1}
  .remove-btn:hover{color:#dc2626}
  .add-finding{margin-bottom:1.5rem}
  .section-label{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#6b6b80;margin:1.75rem 0 .75rem;padding-bottom:.4rem;border-bottom:1px solid #e5e5f0}
  .alert{padding:.85rem 1.1rem;border-radius:8px;font-size:.88rem;font-weight:500;margin-bottom:1.25rem}
  .alert-green{background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0}
  .alert-red{background:#fef2f2;color:#dc2626;border:1px solid #fecaca}
  .actions-bar{display:flex;gap:.75rem;align-items:center;margin-top:2rem;padding-top:1.5rem;border-top:1px solid #e5e5f0}
  .empty{color:#6b6b80;font-style:italic;text-align:center;padding:3rem 0}
  .hint{font-size:.75rem;color:#6b6b80;margin-top:.2rem}
</style>
"""

def page(title, body, active="reports"):
    nav_items = [("reports", "/", "Reports"), ("new", "/new", "+ New Report")]
    nav = "".join(
        f'<a href="{href}" style="color:{"white" if active==k else "rgba(255,255,255,.5)"};margin-left:1.5rem;text-decoration:none;font-size:.85rem;font-weight:{"600" if active==k else "400"}">{label}</a>'
        for k, href, label in nav_items
    )
    return f"""<!doctype html><html lang=en><head>
<meta charset=UTF-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{title} · Budget Watch Admin</title>{STYLE}</head><body>
<div class=topbar>
  <h1>Budget Watch Admin</h1>
  <div>{nav}<a href="https://sid-code-git.github.io/budgetwatch" target=_blank style="color:rgba(255,255,255,.4);margin-left:1.5rem;font-size:.82rem">View site ↗</a></div>
</div>
<div class=wrap>{body}</div>
</body></html>"""

FINDING_TEMPLATE = """
<div class="finding-block" id="finding-{n}">
  <button type=button class=remove-btn onclick="removeFinding({n})" title="Remove">✕</button>
  <h4>Finding #{n}</h4>
  <div class=finding-grid>
    <div class="form-group">
      <label>Severity</label>
      <select name=finding_severity>
        <option value=high>🔴 High</option>
        <option value=medium selected>🟠 Medium</option>
        <option value=low>🟢 Low</option>
      </select>
    </div>
    <div class="form-group">
      <label>Check name</label>
      <input type=text name=check placeholder="e.g. Year-over-year spike">
    </div>
    <div class="form-group full">
      <label>Fact — what do the numbers say?</label>
      <textarea name=fact rows=2 placeholder="The Police Dept budget increased 43% from $1.2M to $1.72M."></textarea>
    </div>
    <div class="form-group full">
      <label>Neutral question for the public</label>
      <textarea name=question rows=2 placeholder="What drove the 43% increase? Was this planned or a one-time purchase?"></textarea>
    </div>
    <div class="form-group full">
      <label>Source citation</label>
      <input type=text name=source placeholder="FY2024 Annual Budget, p. 34">
    </div>
  </div>
</div>
"""

NEW_FORM = """
<h2>New Report</h2>
{alert}
<form method=POST action=/save>
  <div class=card>
    <div class=section-label>Town Info</div>
    <div class=form-grid>
      <div class="form-group full">
        <label>Report title</label>
        <input type=text name=title placeholder="Springfield, IL — FY2024 Budget Analysis" required>
      </div>
      <div class=form-group>
        <label>Town / City</label>
        <input type=text name=town placeholder="Springfield" required>
      </div>
      <div class=form-group>
        <label>State (two letters)</label>
        <input type=text name=state placeholder="IL" maxlength=2 required>
      </div>
      <div class=form-group>
        <label>Fiscal year</label>
        <input type=text name=fiscal_year placeholder="2024" value="{year}" required>
      </div>
      <div class=form-group>
        <label>Population</label>
        <input type=number name=population placeholder="4800">
      </div>
      <div class=form-group>
        <label>Severity (worst flag)</label>
        <select name=severity>
          <option value=high>🔴 High</option>
          <option value=medium selected>🟠 Medium</option>
          <option value=low>🟢 Low</option>
        </select>
      </div>
      <div class=form-group>
        <label style="display:flex;align-items:center;gap:.5rem;cursor:pointer">
          <input type=checkbox name=news_desert> News desert (no local paper)
        </label>
      </div>
    </div>

    <div class=section-label>Location (for the map)</div>
    <div class=form-grid>
      <div class=form-group>
        <label>Latitude</label>
        <input type=text name=lat placeholder="39.7817">
        <p class=hint>Google the town name + "coordinates"</p>
      </div>
      <div class=form-group>
        <label>Longitude</label>
        <input type=text name=lng placeholder="-89.6501">
      </div>
    </div>

    <div class=section-label>Source</div>
    <div class=form-grid>
      <div class="form-group full">
        <label>Budget document URL</label>
        <input type=url name=source_url placeholder="https://town.gov/budget2024.pdf">
      </div>
      <div class="form-group full">
        <label>Summary (1-2 sentences)</label>
        <textarea name=summary rows=3 placeholder="Why this town was selected and what you found."></textarea>
      </div>
    </div>
  </div>

  <div id=findings-container>
    {first_finding}
  </div>

  <button type=button class="btn btn-outline add-finding" onclick="addFinding()">+ Add Finding</button>

  <div class=card>
    <div class=section-label>Publish</div>
    <div class=form-group>
      <label style="display:flex;align-items:center;gap:.5rem;cursor:pointer">
        <input type=checkbox name=publish value=true> Publish immediately (uncheck to save as draft)
      </label>
    </div>
    <div style="margin-top:.75rem">
      <label style="display:flex;align-items:center;gap:.5rem;cursor:pointer">
        <input type=checkbox name=push value=true checked> Push to GitHub now
      </label>
    </div>
  </div>

  <div class=actions-bar>
    <button type=submit class="btn btn-green">Save Report</button>
    <a href=/ class="btn btn-outline">Cancel</a>
  </div>
</form>

<script>
let count = 1;
function addFinding() {{
  count++;
  const tpl = `{finding_js}`.replace(/{{n}}/g, count);
  document.getElementById('findings-container').insertAdjacentHTML('beforeend', tpl);
}}
function removeFinding(n) {{
  const el = document.getElementById('finding-' + n);
  if (el) el.remove();
}}
</script>
"""

# ── handler ────────────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # quiet

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
            self.handle_new()
        elif path.startswith("/edit/"):
            self.handle_edit(path[6:])
        elif path.startswith("/delete/"):
            self.handle_delete(path[8:])
        else:
            self.send_html("<h1>Not found</h1>", 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode()
        data = MultiDict(urllib.parse.parse_qs(raw, keep_blank_values=True))
        path = self.path.split("?")[0]
        if path == "/save":
            self.handle_save(data)
        elif path.startswith("/update/"):
            self.handle_update(path[8:], data)
        else:
            self.send_html("<h1>Not found</h1>", 404)

    # ── pages ──────────────────────────────────────────────────────────────────

    def handle_list(self):
        reports = list_reports()
        if not reports:
            rows = '<p class=empty>No reports yet. <a href="/new">Add your first report →</a></p>'
        else:
            rows = ""
            for r in reports:
                sev = r.get("severity", "medium")
                draft = r.get("draft", "true") == "true"
                rows += f"""
<div class=card>
  <div class=report-row>
    <div>
      <div class=report-title>{r.get('title', r['slug'])}</div>
      <div class=report-meta>{r.get('town','')}, {r.get('state','')} · FY{r.get('fiscal_year','')} · pop. {r.get('population','')}</div>
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

    def handle_new(self, alert=""):
        first = FINDING_TEMPLATE.replace("{n}", "1")
        js_tpl = FINDING_TEMPLATE.replace("{n}", "{n}").replace('"', '\\"').replace("\n", "\\n")
        form = NEW_FORM.format(
            alert=alert,
            year=datetime.now().year,
            first_finding=first,
            finding_js=js_tpl
        )
        self.send_html(page("New Report", form, "new"))

    def handle_edit(self, slug):
        content = read_report(slug)
        body = f"""
<h2>Edit Report</h2>
<p style="color:#6b6b80;font-size:.88rem;margin-bottom:1.5rem">Editing <code>{slug}.md</code> directly. Use the raw markdown editor below.</p>
<form method=POST action="/update/{slug}">
  <div class=card>
    <div class=form-group>
      <label>Report content (Markdown)</label>
      <textarea name=content rows=30 style="font-family:monospace;font-size:.82rem">{content}</textarea>
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

    def handle_save(self, data):
        town = data.get("town", "town")
        state = data.get("state", "xx").lower()
        fy = data.get("fiscal_year", str(datetime.now().year))
        slug = f"{slugify(town)}-{slugify(state)}-{fy}"
        content = build_report_md(data)
        path = write_report(slug, content)

        msg = f"Add report: {town}, {state.upper()} FY{fy}"
        if data.get("draft") != "true":
            msg = "Publish " + msg

        alert = ""
        if data.get("push") == "true":
            ok, err = git_push(path, msg)
            if ok:
                alert = '<div class="alert alert-green">✓ Report saved and pushed to GitHub. Live in ~2 min.</div>'
            else:
                alert = f'<div class="alert alert-red">Saved locally but push failed: {err}</div>'
        else:
            alert = '<div class="alert alert-green">✓ Report saved locally.</div>'

        self.handle_new(alert=alert)

    def handle_update(self, slug, data):
        content = data.get("content", "")
        path = write_report(slug, content)
        alert = ""
        if data.get("push") == "true":
            ok, err = git_push(path, f"Update report: {slug}")
            alert = "pushed" if ok else f"push failed: {err}"
        self.redirect("/")


# ── multidict helper ───────────────────────────────────────────────────────────

class MultiDict:
    def __init__(self, d):
        self._d = d
    def get(self, key, default=""):
        return self._d.get(key, [default])[0]
    def getlist(self, key):
        return self._d.get(key, [])


# ── run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import webbrowser
    print(f"\n  Budget Watch Admin")
    print(f"  → http://localhost:{PORT}")
    print(f"  Press Ctrl+C to stop.\n")
    webbrowser.open(f"http://localhost:{PORT}")
    with http.server.HTTPServer(("", PORT), Handler) as srv:
        srv.serve_forever()
