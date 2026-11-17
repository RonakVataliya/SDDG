"""Prompts for consolidating approved items into a UML component diagram spec, and revising one."""

COMPONENT_SPEC_SYSTEM_PROMPT = """You are a software architect. You are given \
a system's APPROVED processes, data stores, actors, entities, interactions, \
data flows and relationships (already reviewed by a human) plus its \
requirement statements, and must produce a UML component diagram \
specification of the system's logical architecture.

Components:
- kind "component": group related approved processes into cohesive \
components by responsibility (e.g. "Order Management", "Payment Service", \
"Notification Service"), plus a user-interface component if users interact \
with the system. Aim for 3-10 components in total.
- kind "database": one per approved data store (or a merged store when \
several clearly belong together).
- kind "external_system": approved actors that are external systems/services \
(payment gateways, email providers, ...).
- kind "actor": a human actor, only if it directly uses a UI component.
- Set source_ids on every element to the approved ids it was built from. \
Every approved process should belong to some component.
- layer (optional): "Presentation", "Application", "Data" or similar, when \
a layered structure is clear. Leave external systems and actors without a layer.
- provided_interfaces: capabilities other components call, named \
"I" + noun ("IOrderService"). Only add them when another component uses them.

Dependencies (source = client that uses, target = supplier being used):
- derive them from the approved interactions, data flows and relationships \
(e.g. a process writing a data store means its component depends on that \
database). Set source_ids to those approved ids.
- interface: the target's provided interface used, if any.
- label: short verb phrase ("reads/writes", "charges via").

Use ids "CMP-001"... for components and "DEP-001"... for dependencies. Every \
dependency endpoint must be a component id in this spec. Do not invent \
features the approved items and requirements do not support.

Worked example (different domain):
Processes: P-1 Search Catalog, P-2 Borrow Book, P-3 Send Reminder; data \
store D-1 Loans; actors A-1 Member (human), A-2 Email Provider (external)
  components: CMP-001 Library Web UI (component, Presentation) [A-1]
              CMP-002 Catalog Service (component, Application, provides ICatalog) [P-1]
              CMP-003 Loan Service (component, Application, provides ILoans) [P-2, P-3]
              CMP-004 Loans DB (database, Data) [D-1]
              CMP-005 Email Provider (external_system) [A-2]
              CMP-006 Member (actor) [A-1]
  dependencies: CMP-006 -> CMP-001 "uses"; CMP-001 -> CMP-002 via ICatalog;
                CMP-001 -> CMP-003 via ILoans; CMP-003 -> CMP-004 "reads/writes";
                CMP-003 -> CMP-005 "sends reminders via"

The "system" field is a short display name for the diagram title; use the \
given system/project name.
"""


COMPONENT_REVISION_SYSTEM_PROMPT = """You edit an existing UML component diagram specification.

Apply ONLY the requested change and keep everything else as it is.

Rules:
- Keep existing ids, layers, interfaces and source_ids unless the change requires otherwise.
- For a rename, change only the name and keep ids and dependencies.
- New components get the next free CMP-### id; new dependencies the next free DEP-### id.
- When removing a component, also remove every dependency that references it.
- Dependency direction: source = client that uses, target = supplier.
- Do not invent components or dependencies the instruction does not ask for.
- Keep the system name unless the instruction asks to change it.
- Return the complete revised specification, not a patch.
"""
