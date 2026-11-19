"""System Design 4.2 subsystem decomposition: the plain-code derive (layers, cohesion, coupling, warnings, package
diagram), the validation of the LLM draft and the HTTP contract of POST /design/decompose and /design/derive, with the
LLM faked."""
import re

import pytest
from fastapi.testclient import TestClient

import app.services.design_service as svc
from app.design.decomposition import derive_decomposition
from app.main import app
from app.schemas.design import DecomposeRequest, DecompositionLLMOutput, SubsystemDraft
from tests.diagram_helpers import svg_text

REQS = [{"id": "st_1", "ref": "R-001", "text": "Patients book appointments online."},
        {"id": "st_2", "ref": "R-002", "text": "Patients pay their invoices online."}]


def sub(sid, layer, classes=(), depends_on=(), services=(("Service", ("op",)),), name=None):
    return {"id": sid, "name": name or sid.title(), "description": "", "layer": layer,
            "services": [{"name": n, "operations": list(ops)} for n, ops in services],
            "classes": list(classes), "depends_on": list(depends_on), "statement_ids": ["st_1"]}


# A clean 3-layer closed design: every dependency goes to the layer directly below (or to a partition).
CLEAN = {"architecture": "closed", "subsystems": [
    sub("ui", 1, depends_on=["booking"]),
    sub("booking", 2, ["Patient", "Appointment"], ["storage"]),
    sub("billing", 2, ["Invoice"], ["storage"]),
    sub("storage", 3, ["Record"]),
]}
MODEL = {"classes": ["Patient", "Appointment", "Invoice", "Record"],
         "relations": [{"source": "Patient", "target": "Appointment"},   # internal to booking
                       {"source": "Appointment", "target": "Invoice"},   # booking - billing
                       {"source": "Invoice", "target": "Record"},        # billing - storage
                       {"source": "Appointment", "target": "Record"}]}   # booking - storage


def codes(derived):
    return [w["code"] for w in derived["warnings"]]


def test_cohesion_and_coupling_hand_computed():
    d = derive_decomposition(CLEAN, MODEL)
    scores = {s["id"]: (s["cohesion"], s["coupling"]) for s in d["subsystems"]}
    # booking: 1 internal, 2 crossing -> 1/3; billing and storage: 0 internal, 2 crossing each -> 0.0;
    # ui owns no class, so it touches no relation -> null.
    # coupling: ui-booking (depends_on); booking-ui, -billing (relation), -storage (depends_on and relation);
    # billing-booking (relation), -storage; storage-booking, -billing.
    assert scores == {"ui": (None, 1), "booking": (0.33, 3), "billing": (0.0, 2), "storage": (0.0, 2)}
    assert d["cohesion"] == 0.25  # 1 internal of 4 relations
    assert d["layers"] == [{"layer": 1, "subsystem_ids": ["ui"]}, {"layer": 2, "subsystem_ids": ["booking", "billing"]},
                           {"layer": 3, "subsystem_ids": ["storage"]}]
    assert d["warnings"] == []


@pytest.mark.parametrize("model", [None, {"classes": MODEL["classes"], "relations": []}])
def test_scores_are_null_without_relations(model):
    d = derive_decomposition(CLEAN, model)
    assert d["cohesion"] is None and all(s["cohesion"] is None for s in d["subsystems"])
    assert {s["id"]: s["coupling"] for s in d["subsystems"]} == {"ui": 1, "booking": 2, "billing": 1, "storage": 2}
    assert d["warnings"] == []


def with_subs(*subs, architecture="closed"):
    return {"architecture": architecture, "subsystems": list(subs)}


def test_too_many_subsystems():
    nine = [sub(f"s{n}", 1) for n in range(9)]
    assert codes(derive_decomposition(with_subs(*nine))) == []
    ten = derive_decomposition(with_subs(*nine, sub("s9", 1)))
    assert codes(ten) == ["too_many_subsystems"] and "10" in ten["warnings"][0]["message"]


def test_too_many_layers():
    def chain(n):
        return [sub(f"l{i}", i, depends_on=[f"l{i + 1}"] if i < n else []) for i in range(1, n + 1)]
    assert codes(derive_decomposition(with_subs(*chain(6)))) == []
    assert codes(derive_decomposition(with_subs(*chain(7)))) == ["too_many_layers"]


def test_upward_dependency_is_flagged_in_either_architecture():
    for arch in ("closed", "open"):
        d = derive_decomposition(with_subs(sub("ui", 1), sub("data", 2, depends_on=["ui"]), architecture=arch))
        assert d["warnings"] == [{"code": "upward_dependency", "subsystem_ids": ["data", "ui"],
                                  "message": d["warnings"][0]["message"]}], arch
        assert "Data" in d["warnings"][0]["message"] and "Ui" in d["warnings"][0]["message"]


def test_skipped_layer_only_in_a_closed_architecture():
    subs = (sub("ui", 1, depends_on=["logic", "data"]), sub("logic", 2, depends_on=["data"]), sub("data", 3))
    closed = derive_decomposition(with_subs(*subs))
    assert codes(closed) == ["skipped_layer"] and closed["warnings"][0]["subsystem_ids"] == ["ui", "data"]
    assert codes(derive_decomposition(with_subs(*subs, architecture="open"))) == []


def test_unassigned_class():
    d = derive_decomposition(CLEAN, {"classes": [*MODEL["classes"], "Doctor"], "relations": []})
    assert codes(d) == ["unassigned_class"] and "Doctor" in d["warnings"][0]["message"]
    assert d["warnings"][0]["subsystem_ids"] == []


def test_empty_subsystem():
    d = derive_decomposition(with_subs(sub("ui", 1, services=()), sub("logic", 1, ["Patient"], services=())))
    assert codes(d) == ["empty_subsystem"] and d["warnings"][0]["subsystem_ids"] == ["ui"]


def package_lines(source):
    return [line.strip() for line in source.splitlines()]


def test_package_diagram_shows_every_subsystem_grouped_by_layer():
    content = with_subs(*CLEAN["subsystems"], sub("audit", 3, ["Log"], ["booking"]))  # audit -> booking is upward
    source = derive_decomposition(content)["package_diagram"]
    lines = package_lines(source)
    assert lines[0] == "@startuml" and lines[-1] == "@enduml"
    assert source.count("{") == source.count("}")
    # Layers top to bottom, each subsystem inside its layer's package.
    layer_at = [lines.index(f'package "Layer {n}" as layer_{n} {{') for n in (1, 2, 3)]
    assert layer_at == sorted(layer_at)
    for s in content["subsystems"]:
        at = next(i for i, line in enumerate(lines) if line.startswith(f'package "{s["name"]}" as '))
        assert layer_at[s["layer"] - 1] < at and (s["layer"] == 3 or at < layer_at[s["layer"]]), s["id"]
    # One arrow per depends_on edge; the upward one (audit -> booking) is drawn in red, pointing at booking above.
    arrows = [line for line in lines if ".." in line]
    assert len(arrows) == 4, arrows
    assert "booking <.. audit #red;text:red : upward" in lines
    assert "ui ..> booking" in lines and "booking ..> storage" in lines and "billing ..> storage" in lines
    assert sum("#red" in line for line in lines) == 1
    # Hidden links keep the layers in order.
    assert "ui -[hidden]-> booking" in lines and "booking -[hidden]-> storage" in lines


def test_package_diagram_names_are_escaped():
    names = ['He said "hi"', "Café ñ 日本", "Order Service", ":colon:", "(paren)", "end", "a -> b }"]
    content = with_subs(*[sub(f"s-{n}", 1, name=name) for n, name in enumerate(names)])
    content["subsystems"][0]["depends_on"] = ["s-1"]
    source = derive_decomposition(content)["package_diagram"]
    assert "He said 'hi'" in source and "Café ñ 日本" in source and "Order Service" in source
    package_rows = [line for line in package_lines(source) if line.startswith("package")]
    assert all(line.count('"') == 2 for line in package_rows), package_rows  # a name never closes its quotes
    assert '"&#58;colon:"' in source and '"&#40;paren)"' in source  # PlantUML's shape syntax stays literal
    assert "a &#45;&#62; b }" in source and source.count("}") == source.count("{") + 1  # "}" in a quoted name only
    aliases = re.findall(r" as (\w+) \{", source)
    assert len(aliases) == len(set(aliases)) == len(names) + 1  # one layer + every subsystem, all distinct


def test_live_render(live_kroki):
    from app.services.kroki_service import get_kroki_service
    names = ['He said "hi"', "Café ñ 日本", "Order Service", "(paren)", "end"]
    content = with_subs(sub("a", 1, name=names[0], depends_on=["b"]), sub("b", 2, name=names[1], depends_on=["a"]),
                        *[sub(f"x{n}", 3, name=name) for n, name in enumerate(names[2:])])
    svg, _ = get_kroki_service().render_svg(derive_decomposition(content)["package_diagram"], engine="plantuml")
    assert "Syntax Error" not in svg and "Welcome to PlantUML" not in svg and "Caféñ日本" in svg_text(svg)


# ---------------------------------------------------------------------------------------------------------------------
# The LLM draft, validated after the call
# ---------------------------------------------------------------------------------------------------------------------

class FakeAI:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def structured_extract(self, *, node_name, system_prompt, user_content, schema):
        assert schema is DecompositionLLMOutput and node_name == "design_decomposition"
        self.calls.append(user_content)
        return self.output, {"duration_seconds": 0.5, "attempts": 1}


def draft(**kw):
    base = {"id": "x", "name": "X", "description": "", "layer": 1, "services": [], "classes": [], "depends_on": [],
            "requirement_refs": ["R-001"]}
    return SubsystemDraft(**{**base, **kw})


DRAFT = DecompositionLLMOutput(architecture="Closed", subsystems=[
    draft(id="Patient UI", name="Patient interface", layer=2, depends_on=["Booking", "nope", "Patient UI"],
          services=[{"name": "Booking screens", "operations": ["showSlots"]}]),
    draft(id="booking", name="Booking", layer=5, classes=["patient", "APPOINTMENT", "Ghost"], depends_on=["store"],
          requirement_refs=["R-001", "R-999"]),
    draft(id="booking", name="Billing", layer=5, classes=["Appointment", "Invoice"], depends_on=["store"],
          requirement_refs=["R-002"]),
    draft(id="store", name="Storage", layer=9, requirement_refs=["R-404"]),  # cites nothing known: dropped
])
REQUEST = {"requirements": REQS, "model": {"classes": ["Patient", "Appointment", "Invoice"],
                                           "relations": [{"source": "Patient", "target": "Appointment"}],
                                           "use_cases": ["Book appointment"], "actors": ["Patient"]}}


def test_draft_is_validated(monkeypatch):
    fake = FakeAI(DRAFT)
    monkeypatch.setattr(svc, "get_ai_service", lambda: fake)
    result = svc.run_decomposition(DecomposeRequest(**REQUEST))
    assert len(fake.calls) == 1
    sent = fake.calls[0]
    assert "R-001: Patients book" in sent and "Patient, Appointment, Invoice" in sent and "Book appointment" in sent
    assert result.architecture == "closed"
    assert [s.model_dump() for s in result.subsystems] == [
        {"id": "patient-ui", "name": "Patient interface", "description": "", "layer": 1,
         "services": [{"name": "Booking screens", "operations": ["showSlots"]}], "classes": [],
         "depends_on": ["booking"], "statement_ids": ["st_1"]},
        {"id": "booking", "name": "Booking", "description": "", "layer": 2, "services": [],
         "classes": ["Patient", "Appointment"], "depends_on": [], "statement_ids": ["st_1"]},
        {"id": "booking-2", "name": "Billing", "description": "", "layer": 2, "services": [],
         "classes": ["Invoice"], "depends_on": [], "statement_ids": ["st_2"]},
    ]
    for word in ("Storage", "Ghost", "R-999", "nope"):
        assert any(word in e for e in result.errors), word


def test_endpoints(monkeypatch):
    monkeypatch.setattr(svc, "get_ai_service", lambda: FakeAI(DRAFT))
    client = TestClient(app)
    ok = client.post("/api/v1/design/decompose", json=REQUEST)
    assert ok.status_code == 200, ok.text
    assert [s["id"] for s in ok.json()["subsystems"]] == ["patient-ui", "booking", "booking-2"]

    derived = client.post("/api/v1/design/derive", json={"kind": "decomposition", "content": CLEAN, "model": MODEL})
    assert derived.status_code == 200, derived.text
    assert derived.json()["cohesion"] == 0.25 and derived.json()["package_diagram"].startswith("@startuml")
    no_model = client.post("/api/v1/design/derive", json={"kind": "decomposition", "content": CLEAN})
    assert no_model.status_code == 200 and no_model.json()["cohesion"] is None
