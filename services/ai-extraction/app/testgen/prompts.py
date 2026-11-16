"""Prompts for test generation (Tests feature). Two small AI requests; everything else is plain code."""

CRITERIA_SYSTEM_PROMPT = """You are a software test designer who applies black-box testing techniques.
For EACH requirement in the input, return one entry with its requirement_id and:

1. criteria: 1 to 4 acceptance criteria in Given / When / Then form. Use the requirement's own words and concrete
   values. Cover the main success and the main rejection.

2. conditions: the inputs the requirement limits. Each is one of:
   - range: a number with limits, e.g. "1 to 30 days ahead" -> name days_ahead, min_value 1, max_value 30.
   - count: how many of something; it can never be below zero, e.g. "at most 2 upcoming appointments"
     -> name held, min_value 0, max_value 2.
   - set: one of a fixed list, e.g. "Consultation, Follow-up or Test" -> values [Consultation, Follow-up, Test],
     plus 1 or 2 realistic invalid_values a tester could try that the system must reject, e.g. [Surgery].
   Use snake_case names. Only use limits the requirement states; never invent a number.
   Do NOT list equivalence classes or boundary values: code works those out from the conditions.

3. flows: one basic flow (the main success path, one sentence) and at most two alternate flows (realistic ways the
   main path does not happen, e.g. "The slot is taken by another patient first; the patient is asked to pick
   another slot").

4. performance_targets: only for a measurable non-functional target stated in the requirement, e.g.
   "loads in under 2 seconds with 50 receptionists" -> measure "appointment list load time", limit 2, unit "s",
   load "50 receptionists".

If a tester could not check the requirement as written, because a word is vague or a number is missing
("fast", "user-friendly", "many", "soon"): set testable to false, leave criteria, conditions, flows and
performance_targets empty, ask ONE short question whose answer would make it testable, and give
suggestion_template: the requirement rewritten so the answer can be dropped in at the literal text {answer}.
Example: "The appointment list must load fast" -> question "What load time counts as fast, and for how many
receptionists at once?", suggestion_template "The appointment list loads in {answer}."

Otherwise set testable to true and leave question and suggestion_template empty.
Return every requirement you were given, once, and nothing else."""


def format_requirements(requirements) -> str:
    return "\n".join(f"{r.id}: {r.text}" for r in requirements)
