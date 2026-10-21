"""Checks for diagram visual customisation (#38): style validation, apply_style for each engine, and the
style/preview/export endpoints. Needs no database or Kroki: storage and drawing are replaced with fakes.
Run: python tests_styling.py
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused")  # core.db builds its pool lazily
os.environ["DEV_AUTH_BYPASS"] = "true"

from fastapi import HTTPException, Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import routers.integrated as integrated  # noqa: E402
import routers.style as style_router  # noqa: E402
from core.styling import DEFAULT_STYLE, StyleError, apply_style, parse_style  # noqa: E402
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
    same = apply_style(DOT, "graphviz", DEFAULT_STYLE, "dfd")
    assert "rankdir=LR" in same and "fontsize=14" in same and "fontsize=11" in same  # auto + 12 pt keep the layout


def test_mermaid():
    out = apply_style(MERMAID, "mermaid", {**DARK, "direction": "TB"}, "dfd")
    first, rest = out.split("\n", 1)
    assert first.startswith("%%{init: ") and '"background": "#1E1E24"' in first
    assert rest.startswith("flowchart TB") and 'E["Student"] --> P("Order")' in rest


DIAGRAM = {"id": "dg_1", "type": "use_case", "plantuml_source": PUML}


def with_fakes(fn):
    """Runs fn(client, store, drawn) with storage and drawing replaced by in-memory fakes."""
    store, drawn = {}, []
    saved = {name: getattr(style_router, name) for name in ("require_diagram", "style_for", "save_style", "render_png")}
    saved_export = (integrated.require_diagram, integrated.style_for, integrated.render_png)

    def require(diagram_id, _user):
        if diagram_id != "dg_1":
            raise HTTPException(404, "Not found, or you do not have access to it.")
        return DIAGRAM

    async def render(diagram, style):
        drawn.append(apply_style(diagram["plantuml_source"], "plantuml", style, diagram["type"]))
        return Response(b"png", media_type="image/png")

    style_router.require_diagram = integrated.require_diagram = require
    style_router.style_for = integrated.style_for = lambda did: store.get(did, dict(DEFAULT_STYLE))
    style_router.save_style = lambda did, s: store.__setitem__(did, s)
    style_router.render_png = integrated.render_png = render
    try:
        fn(TestClient(app, headers={"Authorization": "Bearer mock-token:dev@sddg.test"}), store, drawn)
    finally:
        for name, value in saved.items():
            setattr(style_router, name, value)
        integrated.require_diagram, integrated.style_for, integrated.render_png = saved_export


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

        r = client.get("/api/v1/diagrams/dg_1/export?format=png")
        assert r.status_code == 200 and "skinparam backgroundColor #1E1E24" in drawn[-1]  # export uses the saved style
        assert DIAGRAM["plantuml_source"] == PUML  # the stored source is never rewritten

    with_fakes(check)


if __name__ == "__main__":
    for test in (test_parse_style, test_plantuml, test_graphviz, test_mermaid, test_endpoints):
        test()
        print("ok", test.__name__)
    print("styling tests passed")
