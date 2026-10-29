"""
Schemas for the Class diagram stage (same shape as app/schemas/usecase.py).

Relation direction is fixed by type so generators never have to guess:
  inheritance   source = subclass,            target = superclass
  realization   source = implementing class,  target = interface
  aggregation   source = whole,               target = part (part can exist alone)
  composition   source = whole,               target = part (part dies with whole)
  dependency    source = class that uses,     target = class used
  association   source / target = the two related classes
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.diagram_common import DiagramMetadata, RequirementRef
from app.schemas.elements import Actor, Entity, Process, Relationship, RelationshipType


class ClassApprovalRequest(BaseModel):
    project_name: Optional[str] = None
    system_name: Optional[str] = None
    entities: List[Entity] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    processes: List[Process] = Field(
        default_factory=list, description="Used to infer operations; not drawn as classes."
    )
    actors: List[Actor] = Field(
        default_factory=list, description="Become classes only if the system stores data about them."
    )
    requirements: List[RequirementRef] = Field(default_factory=list)


class Visibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    PACKAGE = "package"


class ClassKind(str, Enum):
    CLASS = "class"
    ABSTRACT = "abstract"
    INTERFACE = "interface"
    ENUM = "enum"


class ClassAttributeSpec(BaseModel):
    name: str
    type: Optional[str] = Field(default=None, description="e.g. string, int, datetime, List<Item>")
    visibility: Visibility = Visibility.PRIVATE


class ClassParameter(BaseModel):
    name: str
    type: Optional[str] = None


class ClassOperation(BaseModel):
    name: str = Field(..., description="Method name without parentheses, e.g. 'placeOrder'.")
    parameters: List[ClassParameter] = Field(default_factory=list)
    return_type: Optional[str] = None
    visibility: Visibility = Visibility.PUBLIC


class ClassElement(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'C-001'.")
    name: str = Field(..., description="Singular PascalCase noun, e.g. 'MenuItem'.")
    kind: ClassKind = ClassKind.CLASS
    attributes: List[ClassAttributeSpec] = Field(default_factory=list)
    operations: List[ClassOperation] = Field(default_factory=list)
    enum_values: List[str] = Field(default_factory=list, description="Only for kind=enum.")
    source_entity_ids: List[str] = Field(
        default_factory=list, description="Approved entity (or actor) ids this class came from."
    )


class ClassRelation(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'CR-001'.")
    source_id: str = Field(..., description="Class id; see the direction rules for each type.")
    target_id: str = Field(..., description="Class id; see the direction rules for each type.")
    type: RelationshipType = RelationshipType.ASSOCIATION
    label: Optional[str] = Field(default=None, description="Short verb phrase, e.g. 'places'.")
    source_multiplicity: Optional[str] = Field(default=None, description="e.g. '1', '0..1', '*', '1..*'.")
    target_multiplicity: Optional[str] = None
    source_relationship_ids: List[str] = Field(default_factory=list)


class ClassSpec(BaseModel):
    system: str
    classes: List[ClassElement] = Field(default_factory=list)
    relations: List[ClassRelation] = Field(default_factory=list)


class ClassRevisionRequest(BaseModel):
    spec: ClassSpec
    instruction: str = Field(..., min_length=1, max_length=500)
    system_name: Optional[str] = None


class ClassDiagramResult(BaseModel):
    spec: ClassSpec
    source: str = Field(..., description="Diagram source in the language of `engine`.")
    engine: str = Field(..., description="Kroki engine that rendered it: plantuml | mermaid | graphviz.")
    svg: str
    errors: List[str] = Field(default_factory=list)
    metadata: DiagramMetadata
