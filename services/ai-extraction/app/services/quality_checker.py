"""Requirement Quality Checker: ambiguity, incompleteness, and conflict detection."""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.schemas.quality import QualityCheckResponse, QualityFlag, QualityIssueType, RequirementInput

_compile_regex = lambda pattern: re.compile(pattern, re.IGNORECASE)

_VAGUE_PERFORMANCE_PATTERN = _compile_regex(r"\b(respond(s)?\s+quickly|quickly|fast|promptly|rapidly|as quickly as possible|as fast as possible|real-time|low latency|instant(ly)?)\b")
_MEASURABLE_METRIC_PATTERN = _compile_regex(r"\b(within|under|less than|at most|no more than)\s+\d+\s*(ms|milliseconds?|seconds?|secs?|minutes?|mins?|hours?)\b")
_VAGUE_USABILITY_PATTERN = _compile_regex(r"\b(user-friendly|intuitive|easy to use|effortless|convenient|seamless|clean interface|simple interface)\b")
_VAGUE_SUBJECTIVE_PATTERN = _compile_regex(r"\b(appropriate|appropriately|suitable|suitably|adequate|adequately|sufficient|sufficiently|reasonable|reasonably|efficient|efficiently|effective|effectively|optimal|optimally|robust|flexible|state-of-the-art)\b")
_VAGUE_HEDGES_PATTERN = _compile_regex(r"\b(etc\.?|and so forth|and so on|including but not limited to|as needed|as appropriate)\b")

_MISSING_ACTOR_MODAL_PATTERN = _compile_regex(r"^(must|shall|should|can|could|would|will)\s+")
_PASSIVE_UNNAMED_ACTOR_PATTERN = _compile_regex(r"^(the system|the application|the data)\s+(shall|must|should|will|can)\s+be\s+([a-z]+ed)\b")
_TRIGGER_PATTERN = _compile_regex(r"\b(by|when|upon|if|on|after)\b")
_UNDEFINED_ACTOR_PATTERN = _compile_regex(r"\b(someone|somebody|anybody|an authorized party|some entity)\b")
_MISSING_MEASURABLE_VALUE_PATTERN = _compile_regex(r"\b(for a period of time|for some time|after a period of time|after an idle period|minimum length|maximum length|rate limit|retention period|time limit|certain threshold)\b")
_QUANTIFIED_VALUE_PATTERN = _compile_regex(r"\b(\d+(?:\.\d+)?)\s*(minutes?|mins?|seconds?|secs?|hours?|hrs?|days?|months?|years?|characters?|chars?|attempts?|times?|mb|gb|kb|%|percent)?\b")
_TRAILING_CONDITIONAL_PATTERN = _compile_regex(r"\b(if|when|unless|provided that|in case of)\s*[\.\?!]?$")
_VAGUE_CONDITION_PATTERN = _compile_regex(r"\b(under certain conditions|depending on (the )?(situation|case|circumstances)|as required)\b")

_VALUE_EXTRACTOR_PATTERN = _compile_regex(r"(\d+(?:\.\d+)?)\s*(minutes?|mins?|seconds?|secs?|hours?|hrs?|days?|months?|years?|characters?|chars?|attempts?|times?|mb|gb|kb|%|percent)\b")
_NEGATIVE_POLARITY_PATTERN = _compile_regex(r"\b(must not allow|shall not allow|does not allow|cannot allow|should not allow|will not allow|must not permit|shall not permit|does not permit|cannot permit|prohibits?|disallows?|forbidden|must not|shall not|cannot|should not|will not|is not allowed|are not allowed|disables?|disable)\b")
_POSITIVE_POLARITY_PATTERN = _compile_regex(r"\b(must allow|shall allow|allows|permits|can allow|must permit|shall permit|is allowed|are allowed|enables?|enable|must|shall|can|will|should)\b")
_SCOPE_PATTERN = _compile_regex(r"\b(for mobile users|for desktop users|for web users|for guest users|for admin(s)?|for standard users|when online|when offline|in development|in production)\b")
_ROLE_PATTERN = _compile_regex(r"\b(admin(istrator)?s?|standard users?|guests?|customers?|anonymous users?)\b")

# Suggested fixes: a full rewritten requirement, only where the rewrite is safe without guessing intent.
_ADVERB_SPEED_PATTERN = _compile_regex(r"\b(quickly|promptly|rapidly|instantly|as quickly as possible|as fast as possible)\b")
_DEFAULT_RESPONSE_TIME = "within 2 seconds"


def _tidy(text: str) -> str:
    """Collapses spaces and stray commas left behind by a removal."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,\s*([.?!])", r"\1", text)
    text = re.sub(r"\s+([.,;?!])", r"\1", text)
    return text.strip()


_BE_FAST_PATTERN = _compile_regex(r"\b(be|is|are)\s+(fast|quick)\b")


def _fix_vague_speed(text: str, match: re.Match) -> Optional[str]:
    """'The system responds quickly.' -> 'The system responds within 2 seconds.';
    'Search must be fast.' -> 'Search must respond within 2 seconds.' Other wordings ('real-time', 'low latency')
    are left to the user."""
    if _ADVERB_SPEED_PATTERN.search(text):
        return _ADVERB_SPEED_PATTERN.sub(_DEFAULT_RESPONSE_TIME, text, count=1)
    if _BE_FAST_PATTERN.search(text):
        return _BE_FAST_PATTERN.sub(f"respond {_DEFAULT_RESPONSE_TIME}", text, count=1)
    return None


def _fix_hedge(text: str, match: re.Match) -> Optional[str]:
    """Closes an open-ended list: drops 'etc.', 'and so on', 'as needed'...; 'including but not limited to' -> 'including'."""
    word = match.group(0)
    if word.lower() == "including but not limited to":
        return text[:match.start()] + "including" + text[match.end():]
    fixed = _tidy(text[:match.start()] + text[match.end():])
    return fixed if fixed and fixed[-1] in ".?!" else fixed + "."


def _fix_undefined_actor(text: str, match: re.Match) -> Optional[str]:
    """'Someone can approve refunds.' -> 'An authorized user can approve refunds.'"""
    actor = "An authorized user" if match.start() == 0 else "an authorized user"
    return text[:match.start()] + actor + text[match.end():]


def _fix_missing_actor(text: str, match: re.Match) -> Optional[str]:
    """'Must send a reminder.' -> 'The system must send a reminder.' Only for obligations; 'Can view reports' is
    usually a user, so no fix is guessed for can/could/would."""
    if match.group(1).lower() not in {"must", "shall", "should", "will"}:
        return None
    return "The system " + text[0].lower() + text[1:]


_AMBIGUITY_RULES: List[Tuple] = [  # (pattern, message, guard, fixer)
    (_VAGUE_PERFORMANCE_PATTERN, "Vague performance wording: '{match}'. Specify measurable criteria (e.g. 'within 500 ms').", lambda text: not _MEASURABLE_METRIC_PATTERN.search(text), _fix_vague_speed),
    (_VAGUE_USABILITY_PATTERN, "Vague usability wording: '{match}'. Subjective interface qualities cannot be tested without concrete criteria.", None),
    (_VAGUE_SUBJECTIVE_PATTERN, "Subjective wording: '{match}'. Define precise, objective requirements instead of open-ended qualities.", None),
    (_VAGUE_HEDGES_PATTERN, "Ambiguous open-ended wording: '{match}'. List all required items explicitly.", None, _fix_hedge),
]

_INCOMPLETENESS_RULES: List[Tuple] = [  # (pattern, message, guard, fixer)
    (_MISSING_ACTOR_MODAL_PATTERN, "Missing actor: requirement begins with a modal verb without specifying who performs the action.", None, _fix_missing_actor),
    (_PASSIVE_UNNAMED_ACTOR_PATTERN, "Missing actor or trigger: passive sentence does not specify who initiates this event.", lambda text: not _TRIGGER_PATTERN.search(text)),
    (_UNDEFINED_ACTOR_PATTERN, "Undefined actor: '{match}' is ambiguous. Specify a defined system role or component.", None, _fix_undefined_actor),
    (_MISSING_MEASURABLE_VALUE_PATTERN, "Missing measurable value: '{match}' requires a concrete numeric value or unit.", lambda text: not _QUANTIFIED_VALUE_PATTERN.search(text)),
    (_TRAILING_CONDITIONAL_PATTERN, "Incomplete condition: sentence ends with a conditional keyword without completing the condition.", None),
    (_VAGUE_CONDITION_PATTERN, "Missing condition details: '{match}' is vague. Explicitly specify the necessary conditions.", None),
]
def _normalize_text(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _compatible_context(text1: str, text2: str, check_role: bool = False) -> bool:
    if check_role:
        role1, role2 = _ROLE_PATTERN.search(text1), _ROLE_PATTERN.search(text2)
        if role1 and role2 and role1.group(0).lower() != role2.group(0).lower():
            return False
    scope1, scope2 = _SCOPE_PATTERN.search(text1), _SCOPE_PATTERN.search(text2)
    return not (scope1 and scope2 and scope1.group(0).lower() != scope2.group(0).lower())


def _word_similarity(text1: str, text2: str) -> float:
    words1, words2 = set(text1.split()), set(text2.split())
    return len(words1 & words2) / max(len(words1), len(words2)) if words1 and words2 else 0.0


def _to_req_tuples(requirements: List[Any]) -> List[Tuple[str, str]]:
    return [(str(req.get("id", "") if isinstance(req, dict) else getattr(req, "id", "")),
             str(req.get("text", "") if isinstance(req, dict) else getattr(req, "text", ""))) for req in requirements]


def _candidate_pairs(requirements: List[Any]) -> List[Tuple[str, str, str, str]]:
    req_tuples = _to_req_tuples(requirements)
    return [(req_tuples[i][0], req_tuples[i][1], req_tuples[j][0], req_tuples[j][1])
            for i in range(len(req_tuples)) for j in range(i + 1, len(req_tuples))]


def _make_pair_flags(req_id1: str, req_id2: str, message1: str, message2: str,
                     trigger1: Optional[str] = None, trigger2: Optional[str] = None,
                     fix1: Optional[str] = None, fix2: Optional[str] = None) -> List[QualityFlag]:
    return [
        QualityFlag(requirement_id=req_id1, type=QualityIssueType.CONFLICT, message=message1, related_requirement_ids=[req_id2],
                    trigger_text=trigger1, suggested_fix=fix1),
        QualityFlag(requirement_id=req_id2, type=QualityIssueType.CONFLICT, message=message2, related_requirement_ids=[req_id1],
                    trigger_text=trigger2, suggested_fix=fix2),
    ]


def _check_rules(req_id: str, text: str, issue_type: QualityIssueType, rules: list) -> List[QualityFlag]:
    trimmed_text = text.strip()
    if not trimmed_text:
        return []
    flags = []
    for pattern, message_template, guard_condition, *fixer in rules:
        match = pattern.search(trimmed_text)
        if match and (guard_condition is None or guard_condition(trimmed_text)):
            fix = fixer[0](trimmed_text, match) if fixer else None
            flags.append(QualityFlag(requirement_id=req_id, type=issue_type, message=message_template.format(match=match.group(0)),
                                     related_requirement_ids=[], trigger_text=match.group(0).strip() or None, suggested_fix=fix))
    return flags


def detect_ambiguity(req_id: str, text: str) -> List[QualityFlag]:
    """Flags vague or subjective wording that lacks measurable criteria."""
    return _check_rules(req_id, text, QualityIssueType.AMBIGUOUS, _AMBIGUITY_RULES)


def detect_incompleteness(req_id: str, text: str) -> List[QualityFlag]:
    """Flags requirements missing essential information (actor, measurable value, condition)."""
    return _check_rules(req_id, text, QualityIssueType.INCOMPLETE, _INCOMPLETENESS_RULES)


def detect_inconsistency_pairs(requirements: List[RequirementInput] | List[Dict[str, Any]]) -> List[QualityFlag]:
    """Identifies related requirements specifying conflicting values under the same conditions."""
    flags: List[QualityFlag] = []
    seen_pairs: Set[Tuple[str, str]] = set()
    for req_id1, text1, req_id2, text2 in _candidate_pairs(requirements):
        pair = (min(req_id1, req_id2), max(req_id1, req_id2))
        if pair in seen_pairs or not _compatible_context(text1, text2):
            continue
        val1_match, val2_match = _VALUE_EXTRACTOR_PATTERN.search(text1), _VALUE_EXTRACTOR_PATTERN.search(text2)
        if not (val1_match and val2_match):
            continue
        val1, val2 = val1_match.group(0).lower().strip(), val2_match.group(0).lower().strip()
        if val1 == val2:
            continue
        template1 = _normalize_text(_VALUE_EXTRACTOR_PATTERN.sub("<VALUE>", _SCOPE_PATTERN.sub("", text1)))
        template2 = _normalize_text(_VALUE_EXTRACTOR_PATTERN.sub("<VALUE>", _SCOPE_PATTERN.sub("", text2)))
        if _word_similarity(template1, template2) >= 0.6:
            seen_pairs.add(pair)
            flags.extend(_make_pair_flags(
                req_id1, req_id2,
                f"Conflicts with {req_id2}: specifies conflicting values for the same attribute ('{val1}' vs '{val2}').",
                f"Conflicts with {req_id1}: specifies conflicting values for the same attribute ('{val2}' vs '{val1}').",
                val1_match.group(0).strip(), val2_match.group(0).strip(),
                # each side's fix adopts the other side's value; the user picks which flag to apply
                text1[:val1_match.start()] + val2_match.group(0) + text1[val1_match.end():],
                text2[:val2_match.start()] + val1_match.group(0) + text2[val2_match.end():],
            ))
    return flags


def detect_contradiction_pairs(requirements: List[RequirementInput] | List[Dict[str, Any]]) -> List[QualityFlag]:
    """Identifies opposing behavior for the same entity under the same conditions."""
    flags: List[QualityFlag] = []
    seen_pairs: Set[Tuple[str, str]] = set()
    for req_id1, text1, req_id2, text2 in _candidate_pairs(requirements):
        pair = (min(req_id1, req_id2), max(req_id1, req_id2))
        if pair in seen_pairs or not _compatible_context(text1, text2, check_role=True):
            continue
        neg1, pos1 = bool(_NEGATIVE_POLARITY_PATTERN.search(text1)), bool(_POSITIVE_POLARITY_PATTERN.search(text1))
        neg2, pos2 = bool(_NEGATIVE_POLARITY_PATTERN.search(text2)), bool(_POSITIVE_POLARITY_PATTERN.search(text2))
        if not ((neg1 and not neg2 and pos2) or (neg2 and not neg1 and pos1)):
            continue
        core1 = _normalize_text(_NEGATIVE_POLARITY_PATTERN.sub("", _POSITIVE_POLARITY_PATTERN.sub("", text1)))
        core2 = _normalize_text(_NEGATIVE_POLARITY_PATTERN.sub("", _POSITIVE_POLARITY_PATTERN.sub("", text2)))
        if _word_similarity(core1, core2) >= 0.5:
            seen_pairs.add(pair)
            match1 = _NEGATIVE_POLARITY_PATTERN.search(text1) if neg1 else _POSITIVE_POLARITY_PATTERN.search(text1)
            match2 = _NEGATIVE_POLARITY_PATTERN.search(text2) if neg2 else _POSITIVE_POLARITY_PATTERN.search(text2)
            action1 = match1.group(0).strip() if match1 else "action"
            action2 = match2.group(0).strip() if match2 else "opposing action"
            flags.extend(_make_pair_flags(
                req_id1, req_id2,
                f"Contradicts {req_id2}: opposing behavior under the same conditions ('{action1}' vs '{action2}').",
                f"Contradicts {req_id1}: opposing behavior under the same conditions ('{action2}' vs '{action1}').",
                action1, action2,
            ))
    return flags


def detect_conflict_pairs(requirements: List[RequirementInput] | List[Dict[str, Any]]) -> List[QualityFlag]:
    """Unified detector for value inconsistencies and behavioral contradictions."""
    return detect_inconsistency_pairs(requirements) + detect_contradiction_pairs(requirements)


def analyze_requirements(requirements: List[RequirementInput] | List[Dict[str, Any]]) -> QualityCheckResponse:
    """Main entry point for requirement quality analysis."""
    flags: List[QualityFlag] = []
    for req_id, text in _to_req_tuples(requirements):
        if text.strip():
            flags.extend(detect_ambiguity(req_id, text) + detect_incompleteness(req_id, text))

    flags.extend(detect_conflict_pairs(requirements))

    unique_flags, seen = [], set()
    for flag in flags:
        key = (flag.requirement_id, str(flag.type), flag.message, tuple(sorted(flag.related_requirement_ids)))
        if key not in seen:
            seen.add(key)
            unique_flags.append(flag)

    summary = {category: 0 for category in ("ambiguous", "incomplete", "conflict")}
    overview, seen_conflict_pairs = [], set()
    for flag in unique_flags:
        category_name = getattr(flag.type, "value", str(flag.type))
        if flag.related_requirement_ids:
            pair_key = (flag.type, tuple(sorted([flag.requirement_id, *flag.related_requirement_ids])))
            if pair_key in seen_conflict_pairs:
                continue
            seen_conflict_pairs.add(pair_key)
        if category_name in summary:
            summary[category_name] += 1
        overview.append(f"{', '.join([flag.requirement_id, *flag.related_requirement_ids])}: {category_name}")

    return QualityCheckResponse(overview=overview, total_flags=len(unique_flags), summary=summary, flags=unique_flags)
