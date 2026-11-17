"""Tests for the shared diagram-stage code in app/rendering/."""
import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.rendering import engines
from app.rendering.engines import DiagramEngineError, check_engine_config, resolve_engine
from app.rendering.escape import AliasMap, dot, dot_html, mmd, puml, puml_title
from app.services.kroki_service import get_kroki_service
from tests.diagram_helpers import HOSTILE, assert_labels_literal


def _gen(spec):
    return "x"


def test_resolve_engine_uses_config(monkeypatch):
    monkeypatch.setitem(engines.ENGINE_FOR_DIAGRAM, "demo", "graphviz")
    engine, generator = resolve_engine("demo", {"graphviz": _gen, "plantuml": _gen})
    assert engine == "graphviz" and generator is _gen


def test_resolve_engine_rejects_unsupported_engine(monkeypatch):
    monkeypatch.setitem(engines.ENGINE_FOR_DIAGRAM, "demo", "mermaid")
    with pytest.raises(DiagramEngineError) as exc:
        resolve_engine("demo", {"graphviz": _gen})
    assert "engines.py" in str(exc.value) and "graphviz" in str(exc.value)


def test_resolve_engine_override_wins(monkeypatch):
    monkeypatch.setitem(engines.ENGINE_FOR_DIAGRAM, "demo", "graphviz")
    assert resolve_engine("demo", {"graphviz": _gen, "plantuml": _gen}, override="PlantUML")[0] == "plantuml"


def test_default_engine_config_is_valid():
    import app.main  # noqa: F401  (imports every router, registering every generator set)

    assert check_engine_config() == []
    assert set(engines.ENGINE_FOR_DIAGRAM) <= set(engines._GENERATORS)


def test_alias_map_is_safe_unique_and_stable():
    alias = AliasMap()
    a, b, c = alias("A-1"), alias("A_1"), alias("end")
    assert a != b and alias("A-1") == a
    assert c.lower() != "end"
    assert alias("123").startswith("n_")
    for value in (a, b, c):
        assert value.replace("_", "").isalnum()


def test_puml_neutralises_directives_and_builtins():
    assert puml("!include /etc/passwd").startswith("&#33;")
    assert "%" not in puml("%date()")
    assert puml_title("'comment")[1].startswith("&#39;")
    assert puml_title("end title")[1].startswith("&#101;")


def test_puml_specials_are_entity_encoded_not_tilde_escaped():
    assert puml("x @enduml") == "x &#64;enduml"
    assert puml("[guard] **b**") == "&#91;guard] &#42;&#42;b&#42;&#42;"
    assert "~" not in puml("~[a]~ -- __u__ //i// #h")


def test_dot_and_mermaid_escapes():
    assert dot('say "hi" & \\N') == 'say \\"hi\\" &amp; \\\\N'
    assert "\\\\" in dot_html("\\G")
    assert '"' not in mmd('"x" %% #;')


def test_long_text_is_capped():
    assert len(puml("x" * 500)) <= 120


@pytest.mark.parametrize("engine", ["plantuml", "graphviz"])
def test_hostile_labels_render_literally(live_kroki, engine):
    if engine == "plantuml":
        lines = ["@startuml", *puml_title(HOSTILE[0])]
        for n, text in enumerate(HOSTILE):
            lines.append(f'rectangle "{puml(text)}" as R{n}')
        lines += [f"R0 --> R1 : {puml(t)}" for t in HOSTILE[:5]] + ["@enduml"]
    else:
        lines = ["digraph G {"]
        for n, text in enumerate(HOSTILE):
            lines.append(f'  n{n} [label="{dot(text)}"];')
            lines.append(f'  h{n} [shape=plain, label=<<TABLE><TR><TD>{dot_html(text)}</TD></TR></TABLE>>];')
        lines.append("}")
    svg, _ = get_kroki_service().render_svg("\n".join(lines), engine=engine)
    assert_labels_literal(svg, HOSTILE, engine)


def _shape_count(svg: str) -> int:
    import re

    return len(re.findall(r"<(?:path|polygon|rect|ellipse|image|line|polyline)\b", svg))


@pytest.mark.parametrize("first_char", list("[*/-_#~<@%"))
def test_leading_special_char_in_arrow_label_draws_no_extra_glyph(live_kroki, first_char):
    """PlantUML draws a stray glyph before an arrow label starting with a "~" escape."""
    template = '@startuml\nstate "A" as A\nstate "B" as B\nA --> B : {label}\n@enduml'
    kroki = get_kroki_service()
    baseline, _ = kroki.render_svg(template.format(label=puml("guard")), engine="plantuml")
    svg, _ = kroki.render_svg(template.format(label=puml(f"{first_char}guard")), engine="plantuml")
    assert _shape_count(svg) == _shape_count(baseline)
    assert_labels_literal(svg, [f"{first_char}guard"], "plantuml")
