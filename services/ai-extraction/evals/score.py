"""Scoring for the eval harness: plain functions, no LLM, no I/O.

Names are compared after normalisation (lowercase, punctuation out, simple singular, articles out). A predicted
name matches a gold entry when it equals or closely resembles (difflib ratio >= THRESHOLD) any of the entry's
accepted names, or when one contains the other as whole words ("Library member" ~ "member"). Matching is
one-to-one and greedy by best ratio, so two predictions cannot both claim one gold item.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from itertools import combinations

THRESHOLD = 0.85
ELEMENT_CATEGORIES = ("actors", "entities", "processes", "data_stores")
RELATION_CATEGORIES = ("interactions", "relationships", "data_flows")
DIRECTED = {"data_flows"}  # interactions and relationships are scored without direction
_ARTICLES = {"a", "an", "the"}


def normalise(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower()).split()
    words = [w for w in words if w not in _ARTICLES]
    if words:
        last = words[-1]
        if last.endswith("ies") and len(last) > 4:
            last = last[:-3] + "y"
        elif last.endswith("s") and not last.endswith("ss") and len(last) > 3:
            last = last[:-1]
        words[-1] = last
    return " ".join(words)


def similarity(a: str, b: str) -> float:
    a, b = normalise(a), normalise(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    wa, wb = f" {a} ", f" {b} "
    if wa in wb or wb in wa:  # whole-word containment: "member" vs "library member"
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def entry_similarity(name: str, accepted: list[str]) -> float:
    return max((similarity(name, n) for n in accepted), default=0.0)


def match(pred: list, gold: list, sim) -> list[tuple[int, int]]:
    """Greedy one-to-one matching; returns (pred index, gold index) pairs with sim >= THRESHOLD."""
    scored = sorted(((sim(p, g), i, j) for i, p in enumerate(pred) for j, g in enumerate(gold)), reverse=True)
    used_p, used_g, pairs = set(), set(), []
    for s, i, j in scored:
        if s < THRESHOLD:
            break
        if i not in used_p and j not in used_g:
            used_p.add(i)
            used_g.add(j)
            pairs.append((i, j))
    return pairs


def prf(n_pred: int, n_gold: int, n_match: int) -> dict:
    p = n_match / n_pred if n_pred else (1.0 if not n_gold else 0.0)
    r = n_match / n_gold if n_gold else (1.0 if not n_pred else 0.0)
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "pred": n_pred, "gold": n_gold, "matched": n_match}


def score_elements(pred_names: list[str], gold_entries: list[list[str]]) -> dict:
    return prf(len(pred_names), len(gold_entries), len(match(pred_names, gold_entries, entry_similarity)))


def score_relations(pred: list[tuple[str, str]], gold: list[list[list[str]]], directed: bool) -> dict:
    """pred: (source name, target name); gold: [[accepted source names], [accepted target names]]."""
    def sim(p, g):
        forward = min(entry_similarity(p[0], g[0]), entry_similarity(p[1], g[1]))
        if directed:
            return forward
        return max(forward, min(entry_similarity(p[0], g[1]), entry_similarity(p[1], g[0])))
    return prf(len(pred), len(gold), len(match(pred, gold, sim)))


def expand_relation_gold(gold_relations: list[list[str]], labels: dict) -> list[list[list[str]]]:
    """Gold relations name their ends by the first (canonical) name of an element entry; expand each end to that
    entry's accepted names so a synonym end still matches."""
    synonyms = {}
    for cat in ELEMENT_CATEGORIES:
        for entry in labels.get(cat, []):
            synonyms.setdefault(normalise(entry[0]), entry)
    return [[synonyms.get(normalise(a), [a]), synonyms.get(normalise(b), [b])] for a, b in gold_relations]


def names_by_id(result: dict) -> dict[str, str]:
    return {e["id"]: e["name"] for cat in ELEMENT_CATEGORIES for e in result.get(cat, [])}


def relation_pairs(result: dict, cat: str) -> list[tuple[str, str]]:
    names = names_by_id(result)
    return [(names.get(r.get("source_id"), r.get("source_id") or ""), names.get(r.get("target_id"), r.get("target_id") or ""))
            for r in result.get(cat, [])]


def score_document(result: dict, labels: dict) -> dict:
    """result: an ExtractionResult as a dict (actors, entities, ... with ids and names). Scores only the categories
    the gold labels list (an absent key = not labelled for this document)."""
    out = {}
    for cat in ELEMENT_CATEGORIES:
        if cat in labels:
            out[cat] = score_elements([e["name"] for e in result.get(cat, [])], labels[cat])
    for cat in RELATION_CATEGORIES:
        if cat in labels:
            out[cat] = score_relations(relation_pairs(result, cat), expand_relation_gold(labels[cat], labels), cat in DIRECTED)
    return out


def coverage(result: dict, requirement_ids: list[str]) -> float:
    """Share of requirements referenced by at least one extracted element or relation."""
    if not requirement_ids:
        return 1.0
    used = {r for cat in ELEMENT_CATEGORIES + RELATION_CATEGORIES for e in result.get(cat, []) for r in e.get("source_refs", [])}
    return round(sum(r in used for r in requirement_ids) / len(requirement_ids), 3)


def assumption_rate(result: dict) -> float:
    """Share of extracted elements with no source requirement (they would be shown as assumptions, DR2)."""
    elements = [e for cat in ELEMENT_CATEGORIES for e in result.get(cat, [])]
    return round(sum(not e.get("source_refs") for e in elements) / len(elements), 3) if elements else 0.0


def element_set(result: dict) -> set[str]:
    return {f"{cat}:{normalise(e['name'])}" for cat in ELEMENT_CATEGORIES for e in result.get(cat, [])}


def consistency(sets: list[set[str]]) -> float | None:
    """Mean pairwise Jaccard similarity of the element sets (element_set) of repeated runs on one document;
    1.0 = identical, None with fewer than two runs."""
    pairs = list(combinations(sets, 2))
    if not pairs:
        return None
    return round(sum(len(a & b) / len(a | b) if a | b else 1.0 for a, b in pairs) / len(pairs), 3)


def score_flags(predicted: dict[str, set[str]], labelled: list[dict]) -> dict:
    """predicted: statement id -> flag types raised; labelled: [{id, expected: [types]}] (empty = fine).
    A statement counts as flagged when any type is raised; precision/recall are over flagged statements, and
    type_accuracy is the share of true positives whose types include one expected type."""
    tp = fp = fn = typed = 0
    for item in labelled:
        got, want = predicted.get(item["id"], set()), set(item["expected"])
        if got and want:
            tp += 1
            typed += bool(got & want)
        elif got:
            fp += 1
        elif want:
            fn += 1
    out = prf(tp + fp, tp + fn, tp)
    out["type_accuracy"] = round(typed / tp, 3) if tp else None
    return out


def aggregate(per_doc: list[dict]) -> dict:
    """Micro-averaged P/R/F1 per category over every document that labels it."""
    totals: dict[str, list[int]] = {}
    for doc in per_doc:
        for cat, s in doc.items():
            t = totals.setdefault(cat, [0, 0, 0])
            t[0] += s["pred"]
            t[1] += s["gold"]
            t[2] += s["matched"]
    return {cat: prf(*t) for cat, t in totals.items()}
