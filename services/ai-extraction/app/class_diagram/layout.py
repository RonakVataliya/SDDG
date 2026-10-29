"""
Engine-independent preparation shared by the class-diagram generators:
de-duplicates ids and drops relations that would be invalid to draw
(unknown endpoints, a class inheriting/realising itself).
"""
import re
from dataclasses import dataclass
from typing import List

from app.rendering.engines import EmptyDiagramError
from app.rendering.escape import unique_by_id
from app.schemas.class_diagram import ClassElement, ClassRelation, ClassSpec, Visibility
from app.schemas.elements import RelationshipType as RT

VISIBILITY_MARK = {
    Visibility.PUBLIC: "+",
    Visibility.PRIVATE: "-",
    Visibility.PROTECTED: "#",
    Visibility.PACKAGE: "~",
}
NO_MULTIPLICITY = {RT.INHERITANCE, RT.REALIZATION}


@dataclass
class PreparedClasses:
    system: str
    classes: List[ClassElement]
    relations: List[ClassRelation]


def prepare(spec: ClassSpec) -> PreparedClasses:
    classes = unique_by_id(spec.classes)
    if not classes:
        raise EmptyDiagramError("The class diagram has no classes to draw. Approve at least one entity and try again.")
    ids = {c.id for c in classes}
    relations = [
        r for r in unique_by_id(spec.relations)
        if r.source_id in ids and r.target_id in ids
        and not (r.source_id == r.target_id and r.type in NO_MULTIPLICITY)
    ]
    return PreparedClasses(system=spec.system, classes=classes, relations=relations)


def multiplicity(value) -> str:
    """Keep multiplicities to the characters they are made of (1, 0..1, *, 1..*, n)."""
    return re.sub(r"[^0-9A-Za-z.*]", "", value or "")[:12]
