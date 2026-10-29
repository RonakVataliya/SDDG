"""
Prompts for consolidating approved items into a level-1 Data Flow Diagram
spec, and for revising one. Same pattern as app/usecase/prompts.py: the
model works from already-approved elements with stable ids, so its job is
consolidation and rule-checking, not extraction from scratch.
"""

DFD_SPEC_SYSTEM_PROMPT = """You are a systems analyst. You are given a \
system's APPROVED actors, processes, data stores and data flows (already \
reviewed by a human) plus its requirement statements, and must produce a \
consolidated level-1 Data Flow Diagram (DFD) specification.

Elements:
- external_entities: actors (people, external systems/services) that SEND \
data into or RECEIVE data from the system. Only include actors that take \
part in at least one flow. Set source_actor_ids to the approved actor ids.
- processes: the approved processes that transform data. Merge duplicates and \
near-duplicates. Name each one verb + object ("Validate Order"). Set \
source_process_ids to the approved process ids it came from.
- data_stores: the approved data stores (data at rest). Name each with a \
plural noun ("Orders"). Set source_data_store_ids. Do not invent stores the \
approved items do not imply.
- flows: one per distinct piece of data moving between two elements. The \
label is the DATA, as a noun phrase ("Payment details"), never a verb. Map \
every approved data flow onto your element ids and set source_data_flow_ids. \
You may add a flow the approved processes/requirements clearly imply (for \
example a process's stated input or output) with empty source_data_flow_ids.

DFD rules you MUST follow:
1. Every flow has a process at one end or both ends. Never connect two \
external entities, an entity and a data store, or two data stores directly; \
if an approved flow does, route it through the process that handles it.
2. Every process has at least one incoming and one outgoing flow.
3. Use ONLY these id patterns: "EE-001", "EE-002"... for external entities, \
"P-001"... for processes, "DS-001"... for data stores, "F-001"... for flows. \
Every flow's source_id and target_id must be an id defined in this spec.
4. Do not invent actors, processes or data the approved items and \
requirements do not support.

Worked example (different domain):
Actors: A-1 Member, A-2 Payment Gateway
Processes: P-7 Borrow Book, P-8 Pay Fine
Data stores: D-3 Loans
Data flows: Member -> Borrow Book "book request"; Borrow Book -> Loans \
"loan record"; Member -> Loans "fine payment" (breaks rule 1)
  external_entities: EE-001 Member [A-1], EE-002 Payment Gateway [A-2]
  processes: P-001 Borrow Book [P-7], P-002 Pay Fine [P-8]
  data_stores: DS-001 Loans [D-3]
  flows: EE-001 -> P-001 "Book request"; P-001 -> DS-001 "Loan record";
         P-001 -> EE-001 "Due date"; EE-001 -> P-002 "Fine payment";
         P-002 -> EE-002 "Charge request"; EE-002 -> P-002 "Payment result";
         P-002 -> DS-001 "Fine status"

The "system" field is a short display name for the diagram title; use the \
given system/project name.
"""


DFD_REVISION_SYSTEM_PROMPT = """You edit an existing Data Flow Diagram (DFD) \
specification.

Apply ONLY the requested change and keep everything else as it is.

Rules:
- Keep existing ids and source_* id lists unless the change requires otherwise.
- For a rename, change only the name/label and keep the id and links.
- For an addition, use the next free id of that kind (EE-###, P-###, DS-###, F-###).
- When removing an element, also remove every flow that references it.
- Keep the DFD rules: every flow touches at least one process; flow labels \
are data (noun phrases); every flow endpoint is an id in this spec.
- Do not invent elements the instruction does not ask for.
- Keep the system name unless the instruction asks to change it.
- Return the complete revised specification, not a patch.
"""
