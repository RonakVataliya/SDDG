"""Checks for diagram visual customisation (#38): style validation, apply_style for each engine, and the
style/preview/export endpoints. Needs no database or Kroki: storage and drawing are replaced with fakes.
Run: python tests_styling.py
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused")  # core.db builds its pool lazily
os.environ["DEV_AUTH_BYPASS"] = "true"

from fastapi import HTTPException, Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import core.styling as styling  # noqa: E402
import routers.integrated as integrated  # noqa: E402
import routers.style as style_router  # noqa: E402
from core.styling import DEFAULT_STYLE, StyleError, apply_style, export_style, parse_style  # noqa: E402
from main import app  # noqa: E402

DARK = {**DEFAULT_STYLE, "preset": "dark", "background": "#1E1E24", "fill": "#2B2D36", "text": "#F5F5F5", "line": "#A0A4B0"}

PUML = "@startuml\nleft to right direction\nskinparam shadowing false\nactor \"Student\" as A\nusecase \"Order\" as U\nA -- U\n@enduml"
DOT = (
    "digraph DFD {\n"
    '  graph [rankdir=LR, fontsize=14, label="Canteen"];\n'
    '  node [fontname="Helvetica", fontsize=11];\n'
    '  edge [fontsize=10, color="#444444"];\n'
    '  "S" [shape=circle, style=filled, fillcolor=black, label=""];\n'
    '  "E" [shape=box, style=filled, fillcolor="#eef2f7", label="Student"];\n'
    '  "P" [shape=plain, label=<<TABLE BORDER="1" BGCOLOR="white"><TR><TD>Order</TD></TR></TABLE>>];\n'
    '  "E" -> "P" [label="details"];\n'
    "}"
)
MERMAID = 'flowchart LR\n  E["Student"] --> P("Order")'


def rejects(body, message):
    try:
        parse_style(body)
    except StyleError as exc:
        assert str(exc) == message, str(exc)
    else:
        raise AssertionError(f"accepted {body}")


def test_parse_style():
    assert parse_style({**DARK, "fill": "#2b2d36", "extra": 1}) == DARK  # colours upper-cased, unknown keys dropped
    rejects({**DEFAULT_STYLE, "fill": "yellow"}, "The fill colour must look like #1A2B3C.")
    rejects({**DEFAULT_STYLE, "direction": "RL"}, "Choose a layout direction.")
    for size in (7, 25, 12.5, "12", True):
        rejects({**DEFAULT_STYLE, "font_size": size}, "Font size must be a whole number from 8 to 24 pt.")
    for size in (8, 24):
        assert parse_style({**DEFAULT_STYLE, "font_size": size})["font_size"] == size
    rejects(None, "Send a style.")
    rejects({**DEFAULT_STYLE, "preset": "x" * 5000}, "Choose one of the colour themes.")
    assert parse_style({**DARK, "preset": None})["preset"] is None  # colours edited by hand


def test_plantuml():
    out = apply_style(PUML, "plantuml", DARK, "use_case")
    lines = out.splitlines()
    assert lines[0] == "@startuml" and lines[-1] == "@enduml"
    assert "skinparam backgroundColor #1E1E24" in lines and "skinparam defaultFontColor #F5F5F5" in lines
    assert "skinparam defaultFontSize 14" in lines  # 12 pt keeps PlantUML's normal size
    # Every line of the diagram itself is still there, in order: styling never changes structure.
    body = [ln for ln in PUML.splitlines()]
    assert [ln for ln in lines if ln in body] == body

    tb = apply_style(PUML, "plantuml", {**DEFAULT_STYLE, "direction": "TB", "font_size": 24}, "use_case").splitlines()
    assert "top to bottom direction" in tb and "left to right direction" not in tb
    assert "skinparam defaultFontSize 28" in tb

    seq = apply_style(PUML, "plantuml", {**DEFAULT_STYLE, "direction": "TB"}, "sequence").splitlines()
    assert "top to bottom direction" not in seq and "left to right direction" in seq  # sequence keeps its own
    dfd = "@startuml\nskinparam rectangle {\n  BackgroundColor<<entity>> #EEF2F7\n}\nrectangle \"Student\" <<entity>> as E\n@enduml"
    assert "BackgroundColor<<entity>> #2B2D36" in apply_style(dfd, "plantuml", DARK, "dfd")  # stereotype fill follows the theme
    act = apply_style("@startuml\nstart\n:a;\nstop\n@enduml", "plantuml", {**DEFAULT_STYLE, "direction": "LR"}, "activity")
    assert "direction" not in act.replace("LayoutDirection", "")


def test_graphviz():
    out = apply_style(DOT, "graphviz", {**DARK, "direction": "TB", "font_size": 24}, "dfd")
    assert "rankdir=TB" in out and "rankdir=LR" not in out
    assert "fontsize=28" in out and "fontsize=22" in out and "fontsize=20" in out  # doubled from 14, 11, 10
    assert 'fillcolor="#2B2D36"' in out and "#eef2f7" not in out
    assert 'fillcolor="#F5F5F5"' in out  # the black start dot takes the text colour
    assert 'BGCOLOR="#2B2D36"' in out and '<TABLE COLOR="#A0A4B0" ' in out
    assert 'bgcolor="#1E1E24"' in out and 'color="#A0A4B0"' in out and "#444444" not in out
    assert '"E" -> "P" [label="details"];' in out  # edges untouched
    # A table that already has a COLOR keeps exactly one.
    twice = apply_style('digraph G { "P" [label=<<TABLE COLOR="red" BORDER="1"><TR><TD>x</TD></TR></TABLE>>]; }', "graphviz", DARK, "dfd")
    assert twice.count("COLOR=") - twice.count("BGCOLOR=") == 1 and '<TABLE COLOR="#A0A4B0" BORDER="1">' in twice
    # Labels with no fontsize of their own scale too, through the node/edge/graph defaults.
    plain = apply_style('digraph G { a -> b; }', "graphviz", {**DEFAULT_STYLE, "font_size": 24}, "dfd")
    assert plain.count("fontsize=28") == 3
    same = apply_style(DOT, "graphviz", DEFAULT_STYLE, "dfd")
    assert "rankdir=LR" in same and "fontsize=14" in same and "fontsize=11" in same  # auto + 12 pt keep the layout


def test_mermaid():
    out = apply_style(MERMAID, "mermaid", {**DARK, "direction": "TB"}, "dfd")
    first, rest = out.split("\n", 1)
    assert first.startswith("%%{init: ") and '"background": "#1E1E24"' in first
    assert rest.startswith("flowchart TB") and 'E["Student"] --> P("Order")' in rest
    front = "---\ntitle: Canteen\n---\n" + MERMAID
    lines = apply_style(front, "mermaid", DARK, "dfd").splitlines()
    assert lines[:3] == ["---", "title: Canteen", "---"] and lines[3].startswith("%%{init: ") and lines[4] == "flowchart LR"
    crlf = apply_style(front.replace("\n", "\r\n"), "mermaid", DARK, "dfd")
    assert crlf.startswith("---\r\ntitle: Canteen\r\n---\r\n%%{init: ")  # Windows line endings too

    cls = apply_style("classDiagram\n  class Order", "mermaid", {**DEFAULT_STYLE, "direction": "LR"}, "class").splitlines()
    assert cls[1:3] == ["classDiagram", "  direction LR"]
    state = apply_style("stateDiagram-v2\r\n  [*] --> A", "mermaid", {**DEFAULT_STYLE, "direction": "TB"}, "state")
    assert "stateDiagram-v2\r\n  direction TB\r\n" in state
    assert "direction" not in apply_style("classDiagram\n  class Order", "mermaid", DEFAULT_STYLE, "class").split("\n", 1)[1]

    defs = apply_style(
        "flowchart TD\n  classDef terminal fill:#111,stroke:#111,color:#fff\n  classDef entity fill:#eef2f7,stroke:#334155",
        "mermaid", DARK, "activity",
    ).splitlines()
    assert defs[2] == "  classDef terminal fill:#F5F5F5,stroke:#F5F5F5,color:#1E1E24"  # dots show on dark
    assert defs[3] == "  classDef entity fill:#2B2D36,stroke:#A0A4B0"


def test_export_style():
    saved = styling.style_for
    styling.style_for = lambda _id: DARK  # e.g. inherited from the version before the move
    try:
        assert export_style({"id": "dg_1"}) == DARK
        assert export_style({"id": "dg_2", "layout": {"E": [1, 2]}}) == DEFAULT_STYLE  # moved: standard look, like the screen
    finally:
        styling.style_for = saved


DIAGRAM = {"id": "dg_1", "type": "use_case", "plantuml_source": PUML}


def with_fakes(fn):
    """Runs fn(client, store, drawn) with storage and drawing replaced by in-memory fakes."""
    store, drawn = {}, []
    saved = {name: getattr(style_router, name) for name in ("require_diagram", "style_for", "save_style", "render_styled")}
    saved_export = (integrated.require_diagram, styling.style_for, integrated.render_styled)

    def require(diagram_id, _user):
        if diagram_id != "dg_1":
            raise HTTPException(404, "Not found, or you do not have access to it.")
        return DIAGRAM

    async def render(diagram, style, fmt="png"):
        drawn.append(apply_style(diagram["plantuml_source"], "plantuml", style, diagram["type"]))
        return Response(fmt.encode(), media_type=integrated.EXPORT_MEDIA_TYPES[fmt])

    style_router.require_diagram = integrated.require_diagram = require
    style_router.style_for = styling.style_for = lambda did: store.get(did, dict(DEFAULT_STYLE))
    style_router.save_style = lambda did, s: store.__setitem__(did, s)
    style_router.render_styled = integrated.render_styled = render
    try:
        fn(TestClient(app, headers={"Authorization": "Bearer mock-token:dev@sddg.test"}), store, drawn)
    finally:
        for name, value in saved.items():
            setattr(style_router, name, value)
        integrated.require_diagram, styling.style_for, integrated.render_styled = saved_export


def test_endpoints():
    def check(client, store, drawn):
        assert client.get("/api/v1/diagrams/dg_1/style").json() == DEFAULT_STYLE
        r = client.put("/api/v1/diagrams/dg_1/style", json=DARK)
        assert r.status_code == 200 and r.json() == DARK and store["dg_1"] == DARK
        assert client.get("/api/v1/diagrams/dg_1/style").json() == DARK

        bad = client.put("/api/v1/diagrams/dg_1/style", json={**DARK, "font_size": 30})
        assert bad.status_code == 422 and bad.json()["detail"] == "Font size must be a whole number from 8 to 24 pt."
        assert store["dg_1"] == DARK  # unchanged

        assert client.get("/api/v1/diagrams/dg_missing/style").status_code == 404
        assert client.put("/api/v1/diagrams/dg_missing/style", json=DARK).status_code == 404

        warm = {**DEFAULT_STYLE, "background": "#FFFBF2"}
        r = client.post("/api/v1/diagrams/dg_1/preview", json=warm)
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        assert "skinparam backgroundColor #FFFBF2" in drawn[-1] and store["dg_1"] == DARK  # preview saves nothing

        for fmt in ("png", "svg", "pdf"):
            r = client.get(f"/api/v1/diagrams/dg_1/export?format={fmt}")
            assert r.status_code == 200 and r.content == fmt.encode(), fmt
            assert "skinparam backgroundColor #1E1E24" in drawn[-1]  # every picture export uses the saved style
        r = client.get("/api/v1/diagrams/dg_1/export?format=source")
        assert r.status_code == 200 and r.text == PUML  # the source download is the diagram's own code, unstyled
        assert DIAGRAM["plantuml_source"] == PUML  # the stored source is never rewritten

    with_fakes(check)


if __name__ == "__main__":
    for test in (test_parse_style, test_plantuml, test_graphviz, test_mermaid, test_export_style, test_endpoints):
        test()
        print("ok", test.__name__)
    print("styling tests passed")
