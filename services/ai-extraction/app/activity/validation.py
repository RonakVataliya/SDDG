"""Non-fatal checks on an LLM-produced ActivitySpec (see app/usecase/validation.py)."""
from collections import Counter
from typing import List, Optional, Set

from app.schemas.activity import ActivitySpec, ActivityStepKind as K


def validate_spec(
    spec: ActivitySpec,
    known_actor_ids: Optional[Set[str]] = None,
    known_process_ids: Optional[Set[str]] = None,
) -> List[str]:
    errors: List[str] = []
    lane_ids = {lane.id for lane in spec.lanes}
    actions = []
    flow_open = True
    for n, step in enumerate(spec.steps, start=1):
        if not flow_open:
            errors.append(f"Step {n}: unreachable, every branch of an earlier decision ends the flow")
            flow_open = True  # report once per dead stretch
        if step.kind == K.ACTION:
            if step.action is None:
                errors.append(f"Step {n}: kind 'action' without an action (skipped)")
            else:
                actions.append(step.action)
            continue
        if step.kind in (K.DECISION, K.LOOP) and not (step.question or "").strip():
            errors.append(f"Step {n}: {step.kind.value} has no question")
        if step.kind == K.DECISION and len(step.branches) < 2:
            errors.append(f"Step {n}: decision has {len(step.branches)} branch(es); drawn with an implicit 'else'")
        if step.kind == K.PARALLEL and len([b for b in step.branches if b.actions]) < 2:
            errors.append(f"Step {n}: parallel block needs two branches with actions")
        if step.kind == K.LOOP and not any(b.actions for b in step.branches):
            errors.append(f"Step {n}: loop has no actions to repeat (skipped)")
        if step.kind == K.DECISION and step.branches and all(b.ends_flow for b in step.branches):
            flow_open = False
        for b in step.branches:
            actions += b.actions

    if not actions:
        errors.append("An activity diagram needs at least one action")
    ids = [lane.id for lane in spec.lanes] + [a.id for a in actions]
    for element_id, count in Counter(ids).items():
        if count > 1:
            errors.append(f"Duplicate id '{element_id}' (only the first is drawn)")

    used_lanes = set()
    for a in actions:
        if a.lane_id is not None:
            if a.lane_id not in lane_ids:
                errors.append(f"Action {a.id}: unknown lane_id '{a.lane_id}'")
            used_lanes.add(a.lane_id)
        if known_process_ids is not None:
            for ref in a.source_process_ids:
                if ref not in known_process_ids:
                    errors.append(f"Action {a.id}: unknown approved id '{ref}'")
    for lane in spec.lanes:
        if lane.id not in used_lanes:
            errors.append(f"Lane {lane.id} '{lane.name}' has no actions (not drawn)")
        if known_actor_ids is not None:
            for ref in lane.source_actor_ids:
                if ref not in known_actor_ids:
                    errors.append(f"Lane {lane.id}: unknown approved id '{ref}'")
    return errors
