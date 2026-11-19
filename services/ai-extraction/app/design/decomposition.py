"""System Design 4.2, subsystem decomposition, in plain code (no LLM): the layers, cohesion and coupling over the
extracted model, the lecture 24 heuristics as warnings, and the package diagram as PlantUML."""
from app.rendering.escape import AliasMap, puml

MAX_SUBSYSTEMS = 9  # 7 plus or minus 2
MAX_LAYERS = 6  # 4 plus or minus 2


def _score(internal, crossing):
    return round(internal / (internal + crossing), 2) if internal + crossing else None


def _name(text):
    # PlantUML strips a package name wrapped in ":...:" or "(...)" (its shape syntax), as in component/plantuml_gen.py.
    name = puml(text, 80)
    return f"&#{ord(name[0])};{name[1:]}" if name[:1] in ":(" else name


def package_diagram(subsystems, edges, layer):
    """One package per subsystem inside a package per layer, top layer first; a dependency arrow per depends_on edge,
    an upward one in red and written reversed so the layer it points at stays on top."""
    alias = AliasMap("s")
    layers = sorted(set(layer.values()))
    lines = ["@startuml", "skinparam shadowing false", "hide empty members"]
    layer_alias = {n: alias(f"\0layer {n}") for n in layers}  # taken first: "layer_<n>", never a subsystem's alias
    for n in layers:
        lines.append(f'package "Layer {n}" as {layer_alias[n]} {{')
        for s in subsystems:
            if s["layer"] == n:
                lines += [f'  package "{_name(s.get("name") or s["id"])}" as {alias(s["id"])} {{', "  }"]
        lines.append("}")
    firsts = [next(s["id"] for s in subsystems if s["layer"] == n) for n in layers]
    lines += [f"{alias(a)} -[hidden]-> {alias(b)}" for a, b in zip(firsts, firsts[1:])]
    for a, b in edges:
        lines.append(f"{alias(b)} <.. {alias(a)} #red;text:red : upward" if layer[b] < layer[a] else
                     f"{alias(a)} ..> {alias(b)}")
    lines.append("@enduml")
    return "\n".join(lines)


def derive_decomposition(content, model=None):
    """{architecture, subsystems} and the extracted model {classes: [name], relations: [{source, target}]} ->
    {layers, subsystems: [{id, cohesion, coupling}], cohesion, warnings, package_diagram}. Warnings never block."""
    subsystems = content.get("subsystems", [])
    model = model or {}
    by_id = {s["id"]: s for s in subsystems}
    layer = {s["id"]: s["layer"] for s in subsystems}
    owner = {}
    for s in subsystems:
        for c in s.get("classes", []):
            owner.setdefault(c, s["id"])
    edges = list(dict.fromkeys((s["id"], t) for s in subsystems for t in s.get("depends_on", [])
                               if t in by_id and t != s["id"]))

    internal, crossing = dict.fromkeys(by_id, 0), dict.fromkeys(by_id, 0)
    linked = {i: set() for i in by_id}
    for a, b in edges:
        linked[a].add(b)
        linked[b].add(a)
    for r in model.get("relations", []):
        a, b = owner.get(r["source"]), owner.get(r["target"])
        if not a or not b:
            continue  # a relation of a class no subsystem owns says nothing about the decomposition
        if a == b:
            internal[a] += 1
        else:
            crossing[a] += 1
            crossing[b] += 1
            linked[a].add(b)
            linked[b].add(a)

    name = lambda i: by_id[i].get("name") or i  # noqa: E731
    warnings = []
    if len(subsystems) > MAX_SUBSYSTEMS:
        warnings.append({"code": "too_many_subsystems", "subsystem_ids": [],
                         "message": f"{len(subsystems)} subsystems: keep to about 7 plus or minus 2."})
    if len(set(layer.values())) > MAX_LAYERS:
        warnings.append({"code": "too_many_layers", "subsystem_ids": [],
                         "message": f"{len(set(layer.values()))} layers: keep to about 4 plus or minus 2 (3 is a good "
                                    "default)."})
    for a, b in edges:
        if layer[b] < layer[a]:
            warnings.append({"code": "upward_dependency", "subsystem_ids": [a, b],
                             "message": f"{name(a)} (layer {layer[a]}) depends on {name(b)} in the higher layer "
                                        f"{layer[b]}; a layer should know nothing of the layers above it."})
    for a, b in edges:
        if content.get("architecture") == "closed" and layer[b] > layer[a] + 1:
            warnings.append({"code": "skipped_layer", "subsystem_ids": [a, b],
                             "message": f"{name(a)} (layer {layer[a]}) calls {name(b)} in layer {layer[b]}; in a "
                                        "closed architecture a layer calls only the layer directly below."})
    warnings += [{"code": "unassigned_class", "subsystem_ids": [], "message": f"The class {c} belongs to no subsystem."}
                 for c in dict.fromkeys(model.get("classes", [])) if c not in owner]
    warnings += [{"code": "empty_subsystem", "subsystem_ids": [s["id"]],
                  "message": f"{name(s['id'])} has no classes and no services."}
                 for s in subsystems if not s.get("classes") and not s.get("services")]

    return {
        "layers": [{"layer": n, "subsystem_ids": [s["id"] for s in subsystems if s["layer"] == n]}
                   for n in sorted(set(layer.values()))],
        "subsystems": [{"id": i, "cohesion": _score(internal[i], crossing[i]), "coupling": len(linked[i])}
                       for i in by_id],
        "cohesion": _score(sum(internal.values()), sum(crossing.values()) // 2),
        "warnings": warnings,
        "package_diagram": package_diagram(subsystems, edges, layer),
    }
