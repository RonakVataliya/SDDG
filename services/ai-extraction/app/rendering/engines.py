"""
=====================================================================================
 RENDERER ROUTING  --  which engine draws which diagram type
 >>>  To switch a diagram's renderer, edit ENGINE_FOR_DIAGRAM below.  <<<
=====================================================================================

Defaults follow the renderer comparison prototype (diagram_renderer_comparison_v2.py,
section 5, RECOMMENDED ROUTING): PlantUML for the UML-family diagrams it supports
natively, Graphviz where we want direct control over node shapes (DFD).

Engine names are Kroki endpoint names, so a value here is used verbatim in
POST {KROKI_BASE_URL}/{engine}/svg.

Only engines that have a generator for that diagram type are accepted; the
allowed values are listed next to each entry. An unsupported value fails
loudly (startup log + HTTP 500 naming this file), never silently.

Notes
- "mermaid" needs the kroki-mermaid companion container. infra/kroki-compose.yml
  already starts it, but check your deployed Kroki has it before switching.
- Changing a value affects diagrams generated or revised AFTER the service
  restarts. Existing diagrams keep their stored source, and PNG export picks
  the engine from that stored source, so old and new diagrams both export.
- Use-case diagrams are not listed: that pipeline (app/usecase/) is PlantUML
  only and is not switchable from here.
"""
from typing import Callable, Dict, Mapping, Tuple

from app.logging_config import get_logger

logger = get_logger("diagram_engines")

GRAPHVIZ = "graphviz"
PLANTUML = "plantuml"
MERMAID = "mermaid"

# ------------------------------------------------------------------------------------
#  TWEAK HERE
# ------------------------------------------------------------------------------------
ENGINE_FOR_DIAGRAM: Dict[str, str] = {
    "dfd": GRAPHVIZ,         # allowed: graphviz | plantuml | mermaid
    "class": PLANTUML,       # allowed: plantuml | mermaid | graphviz
    "sequence": PLANTUML,    # allowed: plantuml | mermaid   (graphviz has no lifelines)
}
# ------------------------------------------------------------------------------------


class DiagramEngineError(RuntimeError):
    """The configured engine has no generator for that diagram type."""


class EmptyDiagramError(ValueError):
    """The spec has nothing drawable (PlantUML would render its Welcome page)."""


# Filled in by each diagram service module at import time:
#   register_generators("dfd", {"graphviz": to_dot, "plantuml": to_plantuml, ...})
_GENERATORS: Dict[str, Mapping[str, Callable]] = {}


def register_generators(diagram_type: str, generators: Mapping[str, Callable]) -> None:
    _GENERATORS[diagram_type] = generators


def supported_engines(diagram_type: str) -> list[str]:
    return sorted(_GENERATORS.get(diagram_type, {}))


def resolve_engine(
    diagram_type: str,
    generators: Mapping[str, Callable],
    override: str | None = None,
) -> Tuple[str, Callable]:
    """
    Returns (engine, generator) for a diagram type. `override` lets the
    /render endpoints re-render hand-edited source in a specific engine.
    """
    engine = (override or ENGINE_FOR_DIAGRAM.get(diagram_type) or "").strip().lower()
    if engine not in generators:
        raise DiagramEngineError(
            f"Engine '{engine or '(not set)'}' is not available for '{diagram_type}' diagrams. "
            f"Supported: {', '.join(sorted(generators))}. "
            "Fix ENGINE_FOR_DIAGRAM in services/ai-extraction/app/rendering/engines.py."
        )
    return engine, generators[engine]


def check_engine_config() -> list[str]:
    """Called at startup: returns (and logs) every misconfigured entry."""
    problems: list[str] = []
    for diagram_type, generators in _GENERATORS.items():
        try:
            resolve_engine(diagram_type, generators)
        except DiagramEngineError as exc:
            problems.append(str(exc))
    for problem in problems:
        logger.error("engine_config_error %s", problem)
    return problems
