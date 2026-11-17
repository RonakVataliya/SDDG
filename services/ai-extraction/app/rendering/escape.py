"""
Text escaping and identifier helpers shared by every diagram generator.

Generators paste LLM-produced names into diagram source, so whatever the
model emits must (a) never break the syntax and (b) render literally rather
than as markup. Each rule below was measured against the renderer versions
the Kroki image pins (PlantUML 1.2026.8, Graphviz 14.1.3, Mermaid 12.1.0):

PlantUML  every character PlantUML could interpret (creole ** // -- __ [[
          #, tags < >, %builtins(), @startuml, ~) becomes a numeric entity;
          PlantUML's "~" escape is avoided because it leaks glyphs or text in
          several contexts. A backslash is doubled so "\\n" stays literal; a
          leading "!" (preprocessor directive such as !include) or "="
          (heading) is entity-encoded. Titles use the block form (`title -->`
          fails).
Graphviz  quoted labels decode HTML entities, so "&" becomes "&amp;"; HTML
          labels still expand \\N \\G escapes, so backslashes are doubled there.
Mermaid   "%%" directives are stripped even inside quotes, "#...;" is an entity
          and ";" ends a statement, so all of them are entity-encoded.
"""
import html
import re
import textwrap
from typing import Dict, Iterable, List

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_WS = re.compile(r"\s+")


def clean(text: object, max_len: int = 120) -> str:
    """Single-line, whitespace-collapsed, length-capped text."""
    value = _CONTROL.sub(" ", "" if text is None else str(text))
    value = _WS.sub(" ", value).strip()
    if max_len and len(value) > max_len:
        value = value[: max_len - 1].rstrip() + "\u2026"
    return value


def wrap(text: str, width: int) -> List[str]:
    return textwrap.wrap(text, width=width, break_long_words=True, break_on_hyphens=False) or [""]


# ----------------------------------------------------------------------------
# PlantUML
# ----------------------------------------------------------------------------
# Characters PlantUML would interpret are all written as numeric entities.
# PlantUML's own "~" escape is not used: "~X" at the start of an arrow label
# draws a stray glyph, "~~" collides with the ~~wave~~ marker, "~<" fails in
# arrow labels and "~@enduml" leaves a visible tilde. Entities render
# literally everywhere. "%" must go because builtins like %date() are
# evaluated in any label.
_PUML_ENTITY = {c: f"&#{ord(c)};" for c in "~<>%&@[*/-_#"}


def _puml_char(c: str) -> str:
    return _PUML_ENTITY.get(c, c)


def _puml_line(line: str) -> str:
    line = line.replace('"', "'").replace("\\", "\\\\")
    line = "".join(_puml_char(c) for c in line)
    if line.startswith("="):
        line = "&#61;" + line[1:]  # leading "=" is a creole heading
    elif line.startswith("!"):
        line = "&#33;" + line[1:]  # leading "!" is a preprocessor directive (!include ...)
    return line


def puml(text: object, max_len: int = 120) -> str:
    """Safe inside "quoted names", after ':' in arrows/messages, in :action;"""
    return _puml_line(clean(text, max_len))


def puml_wrapped(text: object, width: int = 24, max_len: int = 120) -> str:
    """Like puml() but with literal \\n line breaks PlantUML renders."""
    return "\\n".join(_puml_line(line) for line in wrap(clean(text, max_len), width))


def puml_title(text: object) -> List[str]:
    """
    Block-form title lines (`title` ... `end title`). The one-line form rejects
    text like "-->" or "<". Inside the block the text is a raw source line, so
    backslashes are not escapes there (entity-encoded instead), and a line
    starting with ' (comment), ! (directive), = (heading) or reading
    "end title" must not start with its literal first character.
    """
    raw = clean(text).replace('"', "'") or "Diagram"
    line = "".join("&#92;" if c == "\\" else _puml_char(c) for c in raw)
    if line[0] in "'!=" or line.lower().startswith("end"):
        line = f"&#{ord(line[0])};{line[1:]}"
    return ["title", line, "end title"]


# ----------------------------------------------------------------------------
# Graphviz (DOT)
# ----------------------------------------------------------------------------
def _dot_line(line: str) -> str:
    return line.replace("&", "&amp;").replace("\\", "\\\\").replace('"', '\\"')


def dot(text: object, max_len: int = 120) -> str:
    """Safe inside a double-quoted DOT string."""
    return _dot_line(clean(text, max_len))


def dot_wrapped(text: object, width: int = 22, max_len: int = 120) -> str:
    return "\\n".join(_dot_line(line) for line in wrap(clean(text, max_len), width))


def _dot_html_line(line: str) -> str:
    return html.escape(line, quote=True).replace("\\", "\\\\")


def dot_html(text: object, max_len: int = 120) -> str:
    """Safe inside a <TD> of a DOT HTML-like label."""
    return _dot_html_line(clean(text, max_len))


def dot_html_wrapped(text: object, width: int = 22, max_len: int = 120) -> str:
    return "<BR/>".join(_dot_html_line(line) for line in wrap(clean(text, max_len), width))


# ----------------------------------------------------------------------------
# Mermaid
# ----------------------------------------------------------------------------
def _mmd_line(line: str) -> str:
    line = (
        line.replace("#", "#35;")
        .replace("%", "#37;")
        .replace('"', "#quot;")
        .replace(";", "#59;")
        .replace("<", "#60;")
        .replace(">", "#62;")
    )
    return line or "#160;"


def mmd(text: object, max_len: int = 120) -> str:
    """Safe inside ["quoted"] node labels, |"edge labels"|, and message text."""
    return _mmd_line(clean(text, max_len))


def mmd_wrapped(text: object, width: int = 24, max_len: int = 120) -> str:
    return "<br>".join(_mmd_line(line) for line in wrap(clean(text, max_len), width))


def mmd_member(text: object, max_len: int = 60, fallback: str = "item") -> str:
    """
    Mermaid classDiagram members and relation labels accept far less than
    node labels (braces, '<', '[[', a leading ':' all break parsing), so keep
    only word characters and a few safe punctuation marks.
    """
    value = re.sub(r"[^\w .,'/+\-]", " ", clean(text, max_len), flags=re.UNICODE)
    value = _WS.sub(" ", value).strip().strip("+-").strip()
    return value or fallback


def mmd_ident(text: object, fallback: str = "x") -> str:
    value = re.sub(r"\W", "_", clean(text, 60), flags=re.UNICODE).strip("_")
    return value or fallback


# ----------------------------------------------------------------------------
# Identifiers
# ----------------------------------------------------------------------------
# Words that are keywords in at least one of the three syntaxes; an alias
# equal to one of them (case-insensitively) is suffixed instead.
_RESERVED = {
    "end", "start", "stop", "graph", "digraph", "subgraph", "node", "edge", "strict",
    "flowchart", "style", "class", "classdef", "click", "linkstyle", "direction",
    "default", "alt", "opt", "loop", "par", "and", "else", "note", "participant",
    "actor", "activate", "deactivate", "rect", "box", "critical", "break",
    "autonumber", "title", "link", "links", "create", "destroy", "if", "endif",
    "fork", "repeat", "while", "package", "component", "database", "interface",
}


class AliasMap:
    """
    Maps arbitrary spec ids ("EE-001", "it_3f2a...", "A 1") to identifiers
    that are valid in PlantUML, DOT and Mermaid, stable within one diagram,
    and unique even when two raw ids sanitise to the same text.
    """

    def __init__(self, prefix: str = "n") -> None:
        self._prefix = prefix
        self._map: Dict[str, str] = {}
        self._used: set[str] = set()

    def __call__(self, raw_id: object) -> str:
        key = "" if raw_id is None else str(raw_id)
        if key in self._map:
            return self._map[key]
        base = re.sub(r"[^0-9A-Za-z_]", "_", key).strip("_") or self._prefix
        if not base[0].isalpha():
            base = f"{self._prefix}_{base}"
        candidate, n = base, 2
        while candidate.lower() in self._used or candidate.lower() in _RESERVED:
            candidate = f"{base}_{n}"
            n += 1
        self._used.add(candidate.lower())
        self._map[key] = candidate
        return candidate

    def __contains__(self, raw_id: object) -> bool:
        return str(raw_id) in self._map


def unique_by_id(items: Iterable, key: str = "id") -> list:
    """First occurrence wins, so a duplicated id can never be declared twice."""
    seen: set[str] = set()
    out = []
    for item in items:
        value = getattr(item, key)
        if value in seen:
            continue
        seen.add(value)
        out.append(item)
    return out
