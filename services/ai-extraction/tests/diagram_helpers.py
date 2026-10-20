"""Fakes and assertions shared by the per-diagram test modules."""
import html
import re

from app.rendering.escape import clean

# Names an LLM could plausibly emit that break naive generators: quotes,
# braces, creole/HTML markup, PlantUML preprocessor directives and builtins,
# DOT escapes, Mermaid directives/entities, unicode, and very long text.
HOSTILE = [
    'He said "hi"', "back\\slash", "a\\nb", "semi;colon", "pipe|bar", "braces {x}", "close }",
    "<b>bold</b>", "<color:red>red", "[[http://x.y]]", "**bold**", "//it//", "--strike--",
    "~~wave~~", "List~int~", "#hash", "&amp; amp", "@enduml", "end", ":colon:", "(paren)",
    "a)b", "[brk]", "'quote'", "100%", "%date()", "!include /etc/passwd", "!$x = 1",
    "=== heading", "Café ñ 日本", "a -> b", "<<stereo>>", "\\N \\G", "%%{init: {}}%%",
    "x" * 150,
]


class FakeAIService:
    """Returns a fixed spec for any structured_extract call and records the calls."""

    def __init__(self, spec):
        self.spec = spec
        self.calls = []

    def structured_extract(self, *, node_name, system_prompt, user_content, schema):
        self.calls.append({"node": node_name, "schema": schema, "user_content": user_content})
        assert isinstance(self.spec, schema)
        meta = {"node": node_name, "duration_seconds": 0.02, "attempts": 1, "status": "ok"}
        return self.spec.model_copy(deep=True), meta


class FakeKrokiService:
    def __init__(self):
        self.calls = []

    def render_svg(self, source, engine=None):
        self.calls.append({"source": source, "engine": engine})
        return "<svg>fake</svg>", 0.05


def svg_text(svg: str) -> str:
    """All <text> content, unescaped, whitespace removed (labels may be wrapped)."""
    return re.sub(r"\s+", "", html.unescape("".join(re.findall(r"<text[^>]*>([^<]*)</text>", svg))))


def assert_labels_literal(svg: str, labels, engine: str) -> None:
    text = svg_text(svg)
    assert "Welcome to PlantUML" not in svg and "Syntax Error" not in svg
    for label in labels:
        expected = clean(label)
        if engine == "plantuml":
            expected = expected.replace('"', "'")
        expected = re.sub(r"\s+", "", expected)
        assert expected in text, f"{engine}: label {label!r} not rendered literally"
    # A label can match as a substring while an escape character leaks next to
    # it ("~@enduml" contains "@enduml"), so also reject escape residue that no
    # label actually contains.
    # Checked per rendered <text> element with whitespace intact, so adjacent
    # elements or a "~ name" visibility prefix cannot fake a match.
    cleaned = [clean(label) for label in labels]
    elements = [html.unescape(t) for t in re.findall(r"<text[^>]*>([^<]*)</text>", svg)]
    for residue in ("~@", "~*", "~/", "~-", "~_", "~[", "~#", "&#"):
        if any(residue in element for element in elements):
            assert any(residue in label for label in cleaned), f"{engine}: escape residue {residue!r} rendered"
