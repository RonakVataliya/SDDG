"""Per-diagram-type glue between the confirmed review items and the AI service.

For every diagram type except use_case (which keeps its original code path in
routers/integrated.py) this module knows:
  - which approved item categories its AI endpoint needs, in the AI schema shape
  - which AI endpoint to call ({AI_SERVICE_URL}/{endpoint}/generate | /revise)
  - how to turn the returned spec into viewer elements with requirement provenance

Adding a diagram type = one entry in DIAGRAM_PIPELINES at the bottom.
"""
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional

INTERACTION_TYPES = {"actor_to_process", "actor_to_entity", "process_to_entity", "actor_to_actor"}
RELATIONSHIP_TYPES = {"association", "aggregation", "composition", "inheritance", "dependency", "realization"}


# ============================================================================
# Approved model -> AI request fields
# ============================================================================

def build_ai_model(items: List[dict], statements: List[dict]) -> dict:
    """Every approved category in the AI service's element schema shape."""
    by_cat: Dict[str, List[dict]] = {}
    for i in items:
        by_cat.setdefault(i["category"], []).append(i)

    def base(i):
        return {"id": i["id"], "name": i["name"], "description": i["description"],
                "source_refs": i["statement_ids"]}

    def linked(i):
        return bool(i["source_item_id"] and i["target_item_id"])

    return {
        "items_by_id": {i["id"]: i for i in items},
        "actors": [dict(base(i), type="human") for i in by_cat.get("actor", [])],
        "entities": [dict(base(i), type="entity", attributes=[]) for i in by_cat.get("entity", [])],
        "processes": [dict(base(i), inputs=[], outputs=[], triggers=None) for i in by_cat.get("process", [])],
        "data_stores": [base(i) for i in by_cat.get("data_store", [])],
        "data_flows": [
            dict(base(i), source_id=i["source_item_id"], target_id=i["target_item_id"])
            for i in by_cat.get("data_flow", []) if linked(i)
        ],
        "interactions": [
            {
                "id": i["id"], "source_id": i["source_item_id"], "target_id": i["target_item_id"],
                "type": i["relation_type"] if i["relation_type"] in INTERACTION_TYPES else "actor_to_process",
                "description": i["description"] or i["name"], "sequence_hint": None,
                "source_refs": i["statement_ids"],
            }
            for i in by_cat.get("interaction", []) if linked(i)
        ],
        "relationships": [
            {
                "id": i["id"], "source_id": i["source_item_id"], "target_id": i["target_item_id"],
                "type": i["relation_type"] if i["relation_type"] in RELATIONSHIP_TYPES else "association",
                "cardinality": None, "description": i["description"] or i["name"],
                "source_refs": i["statement_ids"],
            }
            for i in by_cat.get("relationship", []) if linked(i)
        ],
        "requirements": [{"id": s["ref"], "text": s["text"]} for s in statements],
    }


# ============================================================================
# Returned spec -> viewer elements (with requirement provenance)
# ============================================================================

def _refs(source_ids: Iterable[str], items_by_id: dict) -> tuple[Optional[str], List[str]]:
    known = [i for i in source_ids if i in items_by_id]
    refs = list(dict.fromkeys(r for i in known for r in items_by_id[i]["statement_ids"]))
    return (known[0] if known else None), refs


def element(element_id, kind, label, source_ids, items_by_id) -> dict:
    model_item_id, refs = _refs(source_ids or [], items_by_id)
    return {
        "element_id": str(element_id),
        "model_item_id": model_item_id,
        "kind": kind,
        "label": label or "",
        "statement_ids": refs,
        "is_assumption": not refs,
    }


def flat_elements(layout):
    """Builder for specs whose elements are flat lists:
    layout = [(spec_list_key, kind, label_key, [source_id_list_keys]), ...]"""
    def build(spec: dict, items_by_id: dict) -> List[dict]:
        out = []
        for list_key, kind, label_key, source_keys in layout:
            for n, el in enumerate(spec.get(list_key) or [], start=1):
                sources = [s for k in source_keys for s in (el.get(k) or [])]
                out.append(element(el.get("id") or f"{kind}-{n}", kind, el.get(label_key), sources, items_by_id))
        return out
    return build


# ============================================================================
# Diagram source -> Kroki engine (for PNG export)
# ============================================================================

_DOT_RX = re.compile(r"^(strict\s+)?(di)?graph\b[^{\n]*\{", re.IGNORECASE)


def kroki_engine_for_source(source: str) -> str:
    """The stored source says which engine drew it, so export keeps working
    for old and new diagrams even after ENGINE_FOR_DIAGRAM is changed."""
    lines = [ln.strip() for ln in (source or "").splitlines()]
    first = next((ln for ln in lines if ln and not ln.startswith(("//", "#", "%%"))), "")
    if first.startswith("@start"):
        return "plantuml"
    if _DOT_RX.match(first):
        return "graphviz"
    if first.split(" ")[0] in {"flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram",
                               "stateDiagram-v2", "erDiagram", "---"}:
        return "mermaid"
    return "plantuml"  # every diagram stored before multi-engine support was PlantUML


# ============================================================================
# Registry
# ============================================================================

@dataclass(frozen=True)
class DiagramPipeline:
    label: str                       # matches the frontend's typeLabel
    endpoint: str                    # AI service router prefix
    fields: tuple                    # approved-model keys sent to /generate
    elements: Callable[[dict, dict], List[dict]]
    progress_label: str = ""
    extra: dict = field(default_factory=dict)

    def payload(self, project: dict, model: dict) -> dict:
        body = {"project_name": project["name"], "system_name": project["name"]}
        body.update({k: model[k] for k in self.fields})
        return body


DIAGRAM_PIPELINES: Dict[str, DiagramPipeline] = {
    "dfd": DiagramPipeline(
        label="Data Flow (DFD)",
        endpoint="dfd",
        fields=("actors", "processes", "data_stores", "data_flows", "requirements"),
        elements=flat_elements([
            ("external_entities", "external_entity", "name", ["source_actor_ids"]),
            ("processes", "process", "name", ["source_process_ids"]),
            ("data_stores", "data_store", "name", ["source_data_store_ids"]),
            ("flows", "data_flow", "label", ["source_data_flow_ids"]),
        ]),
    ),
}
