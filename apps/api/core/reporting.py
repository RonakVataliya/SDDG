"""Stream 5 reporting logic, plain code over stored rows (no AI): diagram versions, coverage (FR20) and the
combined report (FR21)."""
import base64
import html
import re

from core import db


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "diagram"


def diagram_versions(rows):
    """{diagram id: (group, version number)}. Rows with the same title (a type's first generation, every "Generate
    again" and every edit) are versions of one diagram, numbered by creation time. The project ZIP's v1, v2 folders,
    coverage and the report all use this one rule."""
    groups = {}
    for r in rows:
        groups.setdefault(slugify(r["title"]), []).append(r)
    return {r["id"]: (group, n) for group, versions in groups.items()
            for n, r in enumerate(sorted(versions, key=lambda r: r["created_at"]), start=1)}


def latest_versions(versions):
    """{group: (diagram id, version number)} of the newest version of each diagram."""
    newest = {}
    for diagram_id, (group, n) in versions.items():
        if group not in newest or n > newest[group][1]:
            newest[group] = (diagram_id, n)
    return newest


def coverage(project_id):
    """Requirements in the latest version of at least one diagram, with open flags, not represented, with tests;
    plus one row per requirement. An older diagram version alone does not represent a requirement."""
    statements = db.get_statements(project_id)
    rows = db.diagram_rows(project_id)
    versions = diagram_versions(rows)
    by_id = {r["id"]: r for r in rows}
    latest = [by_id[i] | {"version": n} for i, n in latest_versions(versions).values()]
    flags = {}
    for f in db.list_flags(project_id, "open"):
        flags.setdefault(f["statement_id"], []).append(f["type"])

    out = []
    for s in statements:
        drawn = [{"id": d["id"], "type": d["type"], "title": d["title"], "version": d["version"]}
                 for d in latest if s["id"] in d["statement_ids"]]
        out.append({"id": s["id"], "ref": s["ref"], "text": s["text"], "label": s["label"], "source": s["source"]["document"],
                    "diagrams": drawn, "open_flags": list(dict.fromkeys(flags.get(s["id"], []))),
                    "tests": None})
    missing = [r["ref"] for r in out if not r["diagrams"]]
    return {
        "total": len(out),
        "with_diagrams": len(out) - len(missing),
        "not_represented": len(missing),
        "not_represented_refs": missing,
        "with_open_flags": sum(bool(r["open_flags"]) for r in out),
        # shortcut: Stream 6 (tests) is not merged; with_tests and each row's tests stay None (the UI shows a dash).
        # When it lands, fill both from its coverage totals (requirements with at least one ready case).
        "with_tests": None,
        "rows": out,
    }


# ---------------------------------------------------------------------------------------------------------------
# The combined report (FR21): one self-contained, print-styled HTML page. The browser saves it as PDF.
# ---------------------------------------------------------------------------------------------------------------

# Stored SVG comes from the renderer; it is shown through <img src="data:...">, where scripts never run, and this
# policy (sent as a header and repeated in a <meta> for copies opened from disk) blocks everything else.
REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"

REPORT_CSS = """
@page { size: A4; margin: 16mm 14mm; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; color: #15171c; margin: 0 auto; max-width: 190mm; padding: 8mm 0; }
h1 { font-size: 24pt; margin: 0 0 2mm; } h2 { font-size: 14pt; margin: 9mm 0 3mm; border-bottom: 1px solid #c9c4b8; padding-bottom: 1.5mm; }
h3 { font-size: 11.5pt; margin: 0 0 1mm; }
.muted { color: #6f737c; } .cover { border-bottom: 2px solid #15171c; padding-bottom: 5mm; }
.cover dl { display: grid; grid-template-columns: 32mm 1fr; gap: 1mm 4mm; margin: 4mm 0 0; } .cover dt { color: #6f737c; } .cover dd { margin: 0; }
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 3mm; }
.tile { border: 1px solid #e0dcd2; border-radius: 2mm; padding: 3mm; } .tile b { display: block; font-size: 18pt; }
table { width: 100%; border-collapse: collapse; font-size: 9.5pt; } th, td { text-align: left; vertical-align: top; padding: 1.5mm 2mm; border-bottom: 1px solid #e0dcd2; }
th { color: #6f737c; font-weight: 600; } tr { break-inside: avoid; }
.ref { font-family: ui-monospace, monospace; white-space: nowrap; }
.flag { color: #a86300; } .warn { color: #c8391a; }
.diagram { break-before: page; } .diagram img { display: block; max-width: 100%; max-height: 225mm; margin: 3mm auto; }
.empty { color: #6f737c; font-style: italic; }
@media print { body { padding: 0; } }
"""


def _when(t):
    return t.strftime("%d %b %Y, %H:%M UTC") if t else ""


def report_html(project, cov, diagrams, open_flags, today):
    """project: the project row; cov: coverage(); diagrams: latest version rows with svg and "version"; open_flags:
    list_flags(open)."""
    e = lambda v: html.escape(str(v if v is not None else ""))  # noqa: E731 -- every stored value is user text
    refs = {r["id"]: r["ref"] for r in cov["rows"]}
    tests = "–" if cov["with_tests"] is None else cov["with_tests"]
    out = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{REPORT_CSP}">
<title>{e(project["name"])} – project report</title><style>{REPORT_CSS}</style></head><body>
<section class="cover"><p class="muted">Project report · SDDG</p><h1>{e(project["name"])}</h1><dl>
<dt>Client</dt><dd>{e(project["client_name"] or "No client set")}{f' · {e(project["contact_email"])}' if project["contact_email"] else ""}</dd>
<dt>Date</dt><dd>{e(today.strftime("%d %B %Y"))}</dd>
{f'<dt>Archived</dt><dd>{e(_when(project["archived_at"]))} by {e(project["archived_by"])}</dd>' if project["archived_at"] else ""}
</dl></section>
<h2>Coverage</h2><div class="tiles">
<div class="tile"><b>{cov["with_diagrams"]} of {cov["total"]}</b>requirements in a diagram</div>
<div class="tile"><b>{cov["with_open_flags"]}</b>with open flags</div>
<div class="tile"><b>{cov["not_represented"]}</b>not represented{f'<br><span class="muted">{e(", ".join(cov["not_represented_refs"]))}</span>' if cov["not_represented_refs"] else ""}</div>
<div class="tile"><b>{tests}</b>with tests</div></div>
<h2>Requirements</h2>"""]
    if cov["rows"]:
        out.append("<table><thead><tr><th>Ref</th><th>Requirement</th><th>Label</th><th>Source</th><th>Open flags</th></tr></thead><tbody>")
        for r in cov["rows"]:
            out.append(f'<tr><td class="ref">{e(r["ref"])}</td><td>{e(r["text"])}</td><td>{e(r["label"])}</td><td>{e(r["source"])}</td>'
                       f'<td class="flag">{e(", ".join(r["open_flags"]))}</td></tr>')
        out.append("</tbody></table>")
    else:
        out.append('<p class="empty">No requirements yet.</p>')

    out.append("<h2>Diagrams</h2>" + ("" if diagrams else '<p class="empty">No diagrams yet.</p>'))
    for d in diagrams:
        linked = ", ".join(refs[i] for i in d["statement_ids"] if i in refs) or "none"
        img = base64.b64encode(d["svg"].encode()).decode()
        out.append(f'<section class="diagram"><h3>{e(d["title"])} · version {d["version"]}</h3>'
                   f'<p class="muted">Requirements: {e(linked)}</p><img alt="{e(d["title"])}" src="data:image/svg+xml;base64,{img}"></section>')

    question = lambda f: f'<br><span class="muted">Question: {e(f["question"])}</span>' if f["question"] else ""  # noqa: E731
    out.append("<h2>Open issues</h2>")
    if open_flags:
        out.append("<table><thead><tr><th>Where</th><th>Issue</th><th>Detail</th></tr></thead><tbody>")
        for f in open_flags:
            out.append(f'<tr><td class="ref">{e(f["statement_ref"])}</td><td class="flag">{e(f["type"].capitalize())} flag</td>'
                       f'<td>{e(f["reason"])}{question(f)}</td></tr>')
        out.append("</tbody></table>")
    else:
        out.append('<p class="empty">No open flags.</p>')

    out.append("<h2>Tests</h2>")
    # shortcut: Stream 6 (tests) is not merged; add its totals and last run pass rate here when it lands.
    out.append('<p class="empty">Test management is not part of this build yet.</p>')

    out.append("</body></html>")
    return "\n".join(out)
