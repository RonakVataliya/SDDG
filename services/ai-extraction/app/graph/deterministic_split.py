"""Splits well-structured requirement text with code, no LLM (plan 1.6, an experiment behind SPLIT_MODE).

Handles one requirement per item: numbered or lettered lists ("1.", "2)", "FR-3", "NFR1:"), bullets, user stories
("As a ..."), and one-sentence-per-line "shall/must" lists. Continuation lines are joined to their item; a line
that fits no pattern is kept as its own statement labelled unknown, so nothing is lost. Returns None when the text
is not structured enough (prose, mixed paragraphs), so the caller uses the LLM split instead.
"""
from __future__ import annotations

import re

from app.schemas.requirements import RequirementLabel, RequirementStatement, SourceLocation

ITEM = re.compile(r"^\s*(?:(?:\d+[.)]|[A-Za-z][.)]|(?:N?FR|NFR|REQ|UR|SR|R)[-_ ]?\d+[a-z]?\s*[:.)-]?|[-*•–])\s+)(?P<text>\S.*)$")
STORY = re.compile(r"^\s*as (?:an?|the) \w", re.I)
MODAL = re.compile(r"\b(shall|must|should|will|can|may)\b", re.I)
NFR = re.compile(r"^\s*NFR", re.I)
MIN_COVERAGE = 0.8  # share of non-empty lines that must belong to a detected item


def _label(raw: str, text: str) -> RequirementLabel:
    if STORY.match(text):
        return RequirementLabel.USER_STORY
    if NFR.match(raw):
        return RequirementLabel.NON_FUNCTIONAL
    return RequirementLabel.FUNCTIONAL if MODAL.search(text) else RequirementLabel.UNKNOWN


def deterministic_split(text: str) -> list[RequirementStatement] | None:
    lines = text.split("\n")
    items: list[list] = []  # [first line no, last line no, raw first line, text]
    for no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        m = ITEM.match(line)
        if m or STORY.match(line) or (MODAL.search(line) and not line.startswith((" ", "\t"))):
            body = m.group("text") if m else line.strip()
            items.append([no, no, line, body.strip()])
        elif items and items[-1][1] == no - 1 and line.startswith((" ", "\t")):  # indented continuation
            items[-1][1] = no
            items[-1][3] += " " + line.strip()
        else:
            items.append([no, no, line, None])  # a line we cannot place
    placed = [i for i in items if i[3]]
    if not placed or len(placed) / len(items) < MIN_COVERAGE or len(placed) < 2:
        return None
    for item in items:  # nothing is dropped: a line we could not classify becomes a statement labelled unknown
        if not item[3]:
            item[3] = item[2].strip()
    return [
        RequirementStatement(
            id=f"R-{n:03d}", text=body, labels=[_label(raw, body)],
            source_location=SourceLocation(line_start=start, line_end=end, excerpt=body[:200]),
        )
        for n, (start, end, raw, body) in enumerate(items, start=1)
    ]
