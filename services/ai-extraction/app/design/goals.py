"""System Design 4.1, design goals, in plain code (no LLM): the lecture 24 vocabulary, who each goal matters to, and
the typical trade-offs between them. No imports, so the backend's tests can load this file as it is."""

# Lecture 24 "List of Design Goals", plus Functionality from "Relationship between Design Goals". Canonical spelling.
VOCABULARY = (
    "Reliability", "Modifiability", "Maintainability", "Understandability", "Adaptability", "Reusability",
    "Efficiency", "Portability", "Traceability of requirements", "Fault tolerance", "Backward compatibility",
    "Cost-effectiveness", "Robustness", "High performance", "Good documentation", "Well-defined interfaces",
    "User-friendliness", "Reuse of components", "Rapid development", "Minimum number of errors", "Readability",
    "Ease of learning", "Ease of remembering", "Ease of use", "Increased productivity", "Low cost", "Flexibility",
    "Functionality",
)

# The stakeholder groups of the lecture slide; a goal can matter to several, and one in none goes to "other".
GROUPS = {
    "client": ("Low cost", "Increased productivity", "Backward compatibility", "Rapid development", "Flexibility",
               "Efficiency", "Portability", "Good documentation", "Reliability"),
    "end_user": ("Functionality", "User-friendliness", "Ease of use", "Ease of learning", "Fault tolerance",
                 "Robustness", "Efficiency", "Reliability"),
    "developer": ("Minimum number of errors", "Modifiability", "Readability", "Reusability", "Adaptability",
                  "Well-defined interfaces", "Traceability of requirements", "Portability", "Good documentation",
                  "Reliability"),
}

# Lecture 24 "Typical design Trade-Offs": (label, left side, right side).
TRADE_OFFS = (
    ("Functionality vs. Usability", ("Functionality",),
     ("User-friendliness", "Ease of use", "Ease of learning", "Ease of remembering")),
    ("Cost vs. Robustness", ("Low cost", "Cost-effectiveness"), ("Robustness",)),
    ("Efficiency vs. Portability (or Modifiability)", ("Efficiency", "High performance"),
     ("Portability", "Modifiability")),
    ("Rapid development vs. Functionality", ("Rapid development",), ("Functionality",)),
    ("Cost vs. Reusability", ("Low cost", "Cost-effectiveness"), ("Reusability", "Reuse of components")),
    ("Backward compatibility vs. Readability", ("Backward compatibility",), ("Readability",)),
)


def derive_goals(content):
    """{goals: [{name, ...}]} in ranking order -> {groups, conflicts}. Conflicts are information, never a refusal."""
    names = list(dict.fromkeys(g["name"] for g in content.get("goals", [])))
    chosen = set(names)
    groups = {group: [n for n in names if n in members] for group, members in GROUPS.items()}
    grouped = {n for members in GROUPS.values() for n in members}
    groups["other"] = [n for n in names if n not in grouped]
    conflicts = [{"a": a, "b": b, "pair": label}
                 for label, left, right in TRADE_OFFS for a in left if a in chosen for b in right if b in chosen]
    return {"groups": groups, "conflicts": conflicts}
