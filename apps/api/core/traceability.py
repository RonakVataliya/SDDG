"""Traceability checks over stored diagrams (FR17d drift warning, FR17e naming consistency). Plain code over rows,
no AI and no database, so it is tested without either (tests_traceability_logic.py).

Nothing here is stored: a warning exists exactly while its condition holds, so it clears by itself when the edit
is reverted, the diagram is generated again or the requirement is changed to match.
"""
import html
import re

STOP = {"a", "an", "the", "of", "to", "for", "and", "or", "in", "on", "by", "with", "from", "is", "are", "be"}


def _stem(word):
    for suffix in ("ing", "es", "ed", "s", "e"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _stems(text):
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", (text or "").lower())}


def mentions(text, label):
    """Does the requirement text talk about this element? Every meaningful word of the label must appear in the
    text (ignoring case and simple endings, so "Issue book" matches "issues a book")."""
    need = {_stem(w) for w in re.findall(r"[a-z0-9]+", (label or "").lower()) if w not in STOP}
    return bool(need) and need <= _stems(text)


def norm(label):
    return " ".join((label or "").split())


# ---------------------------------------------------------------------------------------------------------------
# FR17d: a manual edit that drifted away from the requirements
# ---------------------------------------------------------------------------------------------------------------

def shape(diagram, lines):
    """What drift compares: {"nodes": {element id: element}, "relations": {line id: (kind, source, target)}}.
    lines: the diagram's (id, kind, source, target, label) tuples (routers/layout.lines)."""
    nodes = {e["element_id"]: e for e in diagram.get("elements") or []
             if e.get("element_id") and e["kind"] not in {"include", "extend", "relationship", "data_flow", "message",
                                                          "dependency", "transition", "flow", "association"}}
    return {"nodes": nodes, "relations": {i: (k, s, t) for i, k, s, t, _ in lines}}


def _relation_key(sh, kind, source, target):
    a, b = sh["nodes"].get(source), sh["nodes"].get(target)
    return (kind, norm(a["label"]).lower() if a else source, norm(b["label"]).lower() if b else target)


def drift_warnings(root, current, statements):
    """root: shape() of the generated version, current: shape() of the saved one, statements: {id: {"ref", "text"}}.

    - element_removed: the generated diagram had an element a requirement mandates (the requirement is linked to
      it and still talks about it) and the saved one does not.
    - relationship_added: the saved diagram has a relationship the generated one lacked and no linked requirement
      mentions both of its ends."""
    out = []
    # An AI edit may give an element a new id, so an element also counts as still there when one of the same kind
    # and name exists; the same goes for relationships (matched by kind and the names of their ends).
    names = {(n["kind"], norm(n["label"]).lower()) for n in current["nodes"].values()}
    before = {_relation_key(root, *r) for r in root["relations"].values()}
    for eid, e in root["nodes"].items():
        if eid in current["nodes"] or (e["kind"], norm(e["label"]).lower()) in names or e.get("is_assumption"):
            continue
        for sid in e.get("statement_ids") or []:
            st = statements.get(sid)
            if st and mentions(st["text"], e["label"]):
                out.append({
                    "id": f"element_removed:{eid}:{sid}", "kind": "element_removed", "element_id": eid,
                    "label": e["label"], "statement_id": sid, "ref": st["ref"],
                    "message": f'{st["ref"]} calls for "{e["label"]}", but this version no longer has it.',
                })
    linked = {sid for n in current["nodes"].values() for sid in n.get("statement_ids") or []}
    for lid, (kind, source, target) in current["relations"].items():
        if _relation_key(current, kind, source, target) in before:
            continue
        a, b = current["nodes"].get(source), current["nodes"].get(target)
        if not a or not b:
            continue
        ids = linked | set(a.get("statement_ids") or []) | set(b.get("statement_ids") or [])
        if any(mentions(statements[s]["text"], a["label"]) and mentions(statements[s]["text"], b["label"])
               for s in ids if s in statements):
            continue
        out.append({
            "id": f"relationship_added:{lid}", "kind": "relationship_added", "element_id": lid, "label": kind,
            "statement_id": None, "ref": None,
            "message": f'"{a["label"]}" and "{b["label"]}" are now connected, but no requirement mentions both.',
        })
    return out


# ---------------------------------------------------------------------------------------------------------------
# FR17e: the same model item named differently on different diagrams
# ---------------------------------------------------------------------------------------------------------------

def naming_issues(diagrams):
    """diagrams: the latest version of each diagram, [{"id", "title", "version", "elements"}]. The same model item
    (matched by model_item_id, never by name) with more than one label is one issue; two different items that happen
    to share a name are not. Returns [{"model_item_id", "names": [{"label", "diagrams": [...]}]}]."""
    by_item = {}
    for d in diagrams:
        for e in d.get("elements") or []:
            item = e.get("model_item_id")
            if not item or not norm(e.get("label")):
                continue
            seen = by_item.setdefault(item, {}).setdefault(norm(e["label"]), [])
            if not any(x["diagram_id"] == d["id"] for x in seen):
                seen.append({"diagram_id": d["id"], "title": d["title"], "version": d.get("version")})
    return [
        {"model_item_id": item, "names": [{"label": label, "diagrams": where} for label, where in labels.items()]}
        for item, labels in sorted(by_item.items()) if len(labels) > 1
    ]


def _replace_values(obj, old, new):
    if isinstance(obj, str):
        return new if norm(obj) == old else obj
    if isinstance(obj, list):
        return [_replace_values(v, old, new) for v in obj]
    if isinstance(obj, dict):
        return {k: _replace_values(v, old, new) for k, v in obj.items()}
    return obj


def _replace_source(source, old, new):
    """Diagram code (PlantUML, DOT or Mermaid): the label where it stands alone between quotes, brackets, colons or
    line ends, never inside a longer label ("Book" in "Book room")."""
    pattern = r'(?<=["(\[:>{|])' + re.escape(old) + r'(?=["\)\]:<}|]|$)'
    return re.sub(pattern, lambda _: new, source, flags=re.MULTILINE)


def _replace_svg(svg, old, new):
    pattern = r"(>\s*)" + re.escape(html.escape(old, quote=False)) + r"(\s*<)"
    return re.sub(pattern, lambda m: m.group(1) + html.escape(new, quote=False) + m.group(2), svg)


def rename_in_diagram(diagram, model_item_id, new_name):
    """The diagram's fields with every element of this model item shown as new_name: the elements, the spec the
    layout and lines are read from, the diagram code Kroki draws exports from and the stored picture.
    None when the diagram already uses that name everywhere."""
    new = norm(new_name)
    old_labels = {norm(e["label"]) for e in diagram["elements"] if e.get("model_item_id") == model_item_id} - {new}
    if not old_labels:
        return None
    elements = [{**e, "label": new} if e.get("model_item_id") == model_item_id else e for e in diagram["elements"]]
    spec, source, svg = diagram.get("spec"), diagram.get("plantuml_source"), diagram.get("svg") or ""
    for old in old_labels:
        spec = _replace_values(spec, old, new) if spec is not None else None
        source = _replace_source(source, old, new) if source else source
        svg = _replace_svg(svg, old, new)
    return {"elements": elements, "spec": spec, "plantuml_source": source, "svg": svg, "was": sorted(old_labels)}
