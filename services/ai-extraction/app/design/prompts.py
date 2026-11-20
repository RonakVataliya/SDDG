"""Prompts for System Design (Feature 4). One AI call per section draft; everything derivable is plain code."""
from app.design.goals import VOCABULARY

GOALS_SYSTEM_PROMPT = f"""You are a software architect choosing the design goals of a system (Bruegge & Dutoit,
system design). Design goals are the qualities the design must optimise; they come from the non-functional
requirements and from what the client, the end users and the developers need.

Pick 5 to 8 goals from this list ONLY, spelled exactly as written:
{", ".join(VOCABULARY)}.

Rank them: the first goal is the most important for this system. For each goal give:
- name: one name from the list.
- reason: ONE sentence saying why this system needs it, in the requirements' own words.
- requirement_refs: the ids (e.g. R-003) of the requirements that motivate it; at least one, only ids from the input.
Leave out a goal that no requirement supports. Do not repeat a goal.

Example input:
R-001: Patients book, move and cancel appointments online at any time of day.
R-002: The appointment list loads in under 2 seconds with 50 receptionists signed in.
R-003: Receptionists learn the booking screen in one short session.
Example output:
{{"goals": [
 {{"name": "Reliability", "reason": "Patients rely on booking at any time of day.", "requirement_refs": ["R-001"]}},
 {{"name": "High performance", "reason": "The list must load in under 2 seconds for 50 receptionists.",
  "requirement_refs": ["R-002"]}},
 {{"name": "Ease of learning", "reason": "Receptionists must learn the booking screen in one session.",
  "requirement_refs": ["R-003"]}},
 {{"name": "Ease of use", "reason": "Patients book, move and cancel without help.", "requirement_refs": ["R-001"]}},
 {{"name": "Fault tolerance", "reason": "A failed booking must not lose the patient's slot.",
  "requirement_refs": ["R-001"]}}
]}}"""


def format_requirements(requirements) -> str:
    return "\n".join(f"{r.ref}: {r.text}" for r in requirements)


DECOMPOSITION_SYSTEM_PROMPT = """You are a software architect decomposing a system into subsystems (Bruegge & Dutoit,
system design). A subsystem is a UML package: a collection of interrelated classes. Its services are groups of
operations named after the use cases they serve; its interface should be clear, well-defined and small. Keep most
interaction inside a subsystem (high cohesion, low coupling).

Organise the subsystems in layers: layer 1 is the top (closest to the users), larger numbers are lower. A layer
depends only on lower layers and knows nothing of higher ones; subsystems in the same layer are partitions and should
be weakly coupled. Use 3 layers unless the system clearly needs another number (never more than 4 plus or minus 2),
and 7 plus or minus 2 subsystems at most. Choose a "closed" architecture (a layer calls only the layer directly below)
unless efficiency clearly matters more than modifiability; then choose "open" (a layer may call any lower layer).

For each subsystem give:
- id: a short lowercase slug, unique (e.g. booking).
- name, and a one-sentence description of its responsibility.
- layer: 1, 2, 3, ...
- services: a few groups of operations, each named after a group of use cases, with short operation names.
- classes: the classes from the input that it owns, spelled as in the input; each class in one subsystem only.
- depends_on: the ids of the subsystems it calls (never itself, never a higher layer).
- requirement_refs: the ids (e.g. R-003) of the requirements it serves; at least one, only ids from the input.

Example input:
Requirements:
R-001: Patients book and cancel appointments online.
R-002: Receptionists manage the doctors' schedules.
R-003: Patients pay their invoices by card.
R-004: All data is kept for 10 years.
Classes: Patient, Appointment, Doctor, Schedule, Invoice
Relations: Patient - Appointment; Appointment - Schedule; Doctor - Schedule; Invoice - Appointment
Use cases: Book appointment, Cancel appointment, Manage schedule, Pay invoice
Actors: Patient, Receptionist
Example output:
{"architecture": "closed", "subsystems": [
 {"id": "web-ui", "name": "Web interface", "description": "The screens patients and receptionists use.", "layer": 1,
  "services": [{"name": "Appointment screens", "operations": ["showFreeSlots", "submitBooking", "cancelBooking"]},
               {"name": "Payment screens", "operations": ["showInvoice", "submitCardPayment"]}],
  "classes": [], "depends_on": ["booking", "scheduling", "billing"], "requirement_refs": ["R-001", "R-002", "R-003"]},
 {"id": "booking", "name": "Booking", "description": "Books and cancels appointments.", "layer": 2,
  "services": [{"name": "Book and cancel appointments", "operations": ["book", "cancel"]}],
  "classes": ["Patient", "Appointment"], "depends_on": ["scheduling", "storage"], "requirement_refs": ["R-001"]},
 {"id": "scheduling", "name": "Scheduling", "description": "Keeps the doctors' schedules.", "layer": 2,
  "services": [{"name": "Manage schedules", "operations": ["freeSlots", "reserveSlot", "editSchedule"]}],
  "classes": ["Doctor", "Schedule"], "depends_on": ["storage"], "requirement_refs": ["R-002"]},
 {"id": "billing", "name": "Billing", "description": "Issues invoices and takes card payments.", "layer": 2,
  "services": [{"name": "Pay invoices", "operations": ["invoiceFor", "payByCard"]}],
  "classes": ["Invoice"], "depends_on": ["storage"], "requirement_refs": ["R-003"]},
 {"id": "storage", "name": "Storage", "description": "Stores all records for 10 years.", "layer": 3,
  "services": [{"name": "Keep records", "operations": ["save", "load"]}],
  "classes": [], "depends_on": [], "requirement_refs": ["R-004"]}
]}"""


def format_model(model) -> str:
    rows = [("Classes", ", ".join(model.classes)),
            ("Relations", "; ".join(f"{r.source} - {r.target}" for r in model.relations)),
            ("Use cases", ", ".join(model.use_cases)), ("Actors", ", ".join(model.actors))]
    return "\n".join(f"{label}: {value or 'none extracted'}" for label, value in rows)
