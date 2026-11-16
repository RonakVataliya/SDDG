"""Black-box test design in plain code (Tests feature, Sprint 3 stream 6). No LLM is involved here.

AI request 1 names a requirement's conditions (its inputs and their limits). From those, this module derives:

  equivalence classes   range: 1 valid + 2 invalid (below, above)
                        count: it cannot go below zero, so 1 valid + 1 invalid above (+ 1 below if min > 0)
                        set:   1 valid class per value + 1 invalid class per invalid value
  boundary values       range: min-1, min, min+1, max-1, max, max+1
                        count: min (and min-1 when min > 0), max, max+1; counts are small, so the inner
                               neighbours (min+1, max-1) repeat values already covered
  draft test cases      single-fault: each case changes ONE input to an invalid or boundary value and keeps every
                        other input at a typical valid value, so one error cannot hide another:
                        - valid classes combined into positive cases, one per value of the largest set
                        - one case per boundary value; an out-of-range boundary also stands for its invalid class
                          (technique BVA+EC), so the invalid class is not tested twice
                        - one case per invalid set value (EC)
                        - one case per flow (Flow) and per performance target (NFR)
                        - only when none of the above exist, one case per acceptance criterion (AC)

Editing a condition reruns these functions, which is why limits can change instantly without an AI call.
The backend (apps/api) calls this through POST /tests/derive and stores the results; the web app's mock
(apps/web/src/mocks/testing-engine.ts) copies these rules, and this file is the reference.
"""
from decimal import Decimal


def fmt(n):
    """30.0 -> '30', 2.5 -> '2.5'."""
    return str(int(n)) if float(n).is_integer() else format(Decimal(str(n)).normalize(), "f")


def _num(n):
    """Whole numbers as int so JSON shows 31, not 31.0."""
    return int(n) if float(n).is_integer() else float(n)


def _decimals(n):
    if n is None or float(n).is_integer():
        return 0
    return max(0, -Decimal(str(n)).normalize().as_tuple().exponent)


def step_of(c):
    """Smallest step between two values: 1 for whole numbers, else 10^-decimals (2.5-9.75 -> 0.01)."""
    d = max(_decimals(c.get("min")), _decimals(c.get("max")))
    return 1 if d == 0 else 10 ** -d


def _limits(c):
    lo, hi = c.get("min"), c.get("max")
    if c["kind"] == "count" and lo is None:
        lo = 0
    return lo, hi


def classes(c):
    """Equivalence classes as [{label, valid}]."""
    if c["kind"] == "set":
        invalid = c.get("invalid_values") or ["any other value"]
        return [{"label": v, "valid": True} for v in c.get("values") or []] + \
               [{"label": v, "valid": False} for v in invalid]
    lo, hi = _limits(c)
    out = []
    if lo is not None and hi is not None:
        out.append({"label": f"{fmt(lo)}–{fmt(hi)}", "valid": True})
    elif lo is not None:
        out.append({"label": f"≥ {fmt(lo)}", "valid": True})
    elif hi is not None:
        out.append({"label": f"≤ {fmt(hi)}", "valid": True})
    if lo is not None and (c["kind"] == "range" or lo > 0):
        out.append({"label": f"< {fmt(lo)}", "valid": False})
    if hi is not None:
        out.append({"label": f"> {fmt(hi)}", "valid": False})
    return out


def boundaries(c):
    """Boundary values as [{value, valid}], sorted, without repeats."""
    if c["kind"] == "set":
        return []
    lo, hi = _limits(c)
    s = step_of(c)
    values = []
    if c["kind"] == "range":
        if lo is not None:
            values += [lo - s, lo, lo + s]
        if hi is not None:
            values += [hi - s, hi, hi + s]
    else:
        if lo is not None:
            values += [lo - 1, lo] if lo > 0 else [lo]
        if hi is not None:
            values += [hi, hi + 1]
    unique = sorted({round(v, 6) for v in values})
    return [{"value": _num(v), "valid": (lo is None or v >= lo) and (hi is None or v <= hi)} for v in unique]


def nominal(c):
    """A typical valid value: the middle of a range or count (rounded down to its step), the first value of a set."""
    if c["kind"] == "set":
        return (c.get("values") or [""])[0]
    lo, hi = _limits(c)
    if lo is not None and hi is not None:
        s = step_of(c)
        return _num(round(lo + ((hi - lo) / 2 // s) * s, 6))
    return _num(lo if lo is not None else hi if hi is not None else 0)


def build_drafts(conditions, flows=(), targets=(), criteria=()):
    """Draft cases as [{title, technique, kind, priority, outcome, test_data, covers}] in the order shown to users."""
    drafts = []
    base = {c["name"]: nominal(c) for c in conditions}
    sets = [c for c in conditions if c["kind"] == "set" and c.get("values")]
    positives = max(len(c["values"]) for c in sets) if sets else (1 if conditions else 0)

    for i in range(positives):
        data = dict(base)
        for c in sets:
            data[c["name"]] = c["values"][i % len(c["values"])]
        picked = [str(data[c["name"]]) for c in sets]
        drafts.append({
            "title": "Valid values" + (", " + ", ".join(picked) if picked else "") + " → accepted",
            "technique": "EC", "kind": "positive", "priority": "high", "outcome": "accepted", "test_data": data,
            "covers": [f"EC:{c['name']}:{data[c['name']] if c['kind'] == 'set' else 'valid'}" for c in conditions],
        })

    for c in conditions:
        if c["kind"] == "set":
            continue
        lo, hi = _limits(c)
        for b in boundaries(c):
            v = b["value"]
            data = {**base, c["name"]: v}
            if b["valid"]:
                drafts.append({
                    "title": f"{c['name']} = {fmt(v)} → accepted", "technique": "BVA", "kind": "edge",
                    "priority": "medium", "outcome": "accepted", "test_data": data,
                    "covers": [f"BVA:{c['name']}:{fmt(v)}"],
                })
            else:
                below = lo is not None and v < lo
                side = f"below {fmt(lo)}" if below else f"above {fmt(hi)}"
                drafts.append({
                    "title": f"{c['name']} = {fmt(v)} ({side}) → rejected", "technique": "BVA+EC", "kind": "negative",
                    "priority": "medium", "outcome": "rejected", "test_data": data,
                    "covers": [f"EC:{c['name']}:{'low' if below else 'high'}", f"BVA:{c['name']}:{fmt(v)}"],
                })

    for c in sets:
        for bad in c.get("invalid_values") or []:
            drafts.append({
                "title": f"{c['name']} = {bad} (not in the set) → rejected", "technique": "EC", "kind": "negative",
                "priority": "medium", "outcome": "rejected", "test_data": {**base, c["name"]: bad},
                "covers": [f"EC:{c['name']}:invalid"],
            })

    for f in flows:
        basic = f["kind"] == "basic"
        drafts.append({
            "title": f"{'Basic flow' if basic else 'Alternate'}: {f['text']}", "technique": "Flow",
            "kind": "positive" if basic else "negative", "priority": "high" if basic else "medium", "outcome": None,
            "test_data": {}, "covers": [f"Flow:{f['kind']}"],
        })

    for t in targets:
        load = f" with {t['load']}" if t.get("load") else ""
        data = {"limit": f"{fmt(t['limit'])} {t['unit']}", **({"load": t["load"]} if t.get("load") else {})}
        drafts.append({
            "title": f"Performance: {t['measure']} < {fmt(t['limit'])} {t['unit']}{load}", "technique": "NFR",
            "kind": "positive", "priority": "medium", "outcome": None, "test_data": data,
            "covers": [f"NFR:{t['measure']}"],
        })

    if not drafts:
        for i, cr in enumerate(criteria, 1):
            drafts.append({
                "title": f"{cr['when']} → {cr['then']}", "technique": "AC", "kind": "positive", "priority": "high",
                "outcome": None, "test_data": {}, "covers": [f"AC:{i}"],
            })
    return drafts


def boundary_count(conditions):
    return sum(len(boundaries(c)) for c in conditions)


def with_classes(c):
    """A condition as the API returns it: its classes and boundaries computed now, never stored."""
    return {**c, "classes": classes(c), "boundaries": boundaries(c)}


def derive(conditions, flows=(), targets=(), criteria=()):
    """Everything the backend stores for one requirement's design: each condition's classes and boundaries, the
    draft cases, and how many boundary values there are."""
    return {
        "conditions": [{"name": c["name"], "classes": classes(c), "boundaries": boundaries(c)} for c in conditions],
        "drafts": build_drafts(conditions, flows, targets, criteria),
        "boundary_count": boundary_count(conditions),
    }
