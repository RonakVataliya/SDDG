"""
Engine-independent preparation shared by the three DFD generators:
de-duplicates ids, numbers processes (1.0, 2.0, ...) and stores (D1, D2, ...)
by list order, and drops flows whose endpoints do not exist, so every
generator draws exactly the same diagram.
"""
from dataclasses import dataclass
from typing import Dict, List

from app.rendering.engines import EmptyDiagramError
from app.rendering.escape import unique_by_id
from app.schemas.dfd import DfdDataStore, DfdExternalEntity, DfdFlow, DfdProcess, DfdSpec


@dataclass
class PreparedDfd:
    system: str
    entities: List[DfdExternalEntity]
    processes: List[DfdProcess]
    stores: List[DfdDataStore]
    flows: List[DfdFlow]
    process_number: Dict[str, str]
    store_number: Dict[str, str]


def prepare(spec: DfdSpec) -> PreparedDfd:
    processes = unique_by_id(spec.processes)
    if not processes:
        raise EmptyDiagramError("The DFD has no processes to draw. Approve at least one process and try again.")

    seen: set[str] = {p.id for p in processes}
    entities = [e for e in unique_by_id(spec.external_entities) if e.id not in seen]
    seen |= {e.id for e in entities}
    stores = [d for d in unique_by_id(spec.data_stores) if d.id not in seen]
    seen |= {d.id for d in stores}

    flows = [
        f for f in unique_by_id(spec.flows)
        if f.source_id in seen and f.target_id in seen and f.source_id != f.target_id
    ]
    return PreparedDfd(
        system=spec.system,
        entities=entities,
        processes=processes,
        stores=stores,
        flows=flows,
        process_number={p.id: f"{i}.0" for i, p in enumerate(processes, start=1)},
        store_number={d.id: f"D{i}" for i, d in enumerate(stores, start=1)},
    )
