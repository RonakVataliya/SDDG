"""Diagram look (issue #38): colour scheme, layout direction and font size.

A style is stored per diagram (diagrams.style) apart from the diagram's source and is applied only while
drawing, so it can never change elements or relationships. apply_style() rewrites the stored PlantUML,
Graphviz DOT or Mermaid source just before it goes to Kroki; the stored source is never written back.

font_size is in points. 12 pt is "normal": it draws each engine's labels at the sizes the generators chose,
and other sizes scale them in proportion. PlantUML and Graphviz size every box to its label, so a bigger
font makes bigger boxes instead of clipping.
"""
import json
import re

from psycopg.errors import UndefinedColumn

from core import db

FONT_SIZE_MIN, FONT_SIZE_MAX, NORMAL_FONT_SIZE = 8, 24, 12
DIRECTIONS = ("auto", "TB", "LR")
COLOUR_KEYS = ("background", "fill", "text", "line")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Same values as apps/web/src/features/viewer/style.ts (the "default" preset).
DEFAULT_STYLE = {
    "preset": "default",
    "background": "#FFFFFF",
    "fill": "#F4F6F8",
    "text": "#1F2933",
    "line": "#52606D",
    "direction": "auto",
    "font_size": NORMAL_FONT_SIZE,
}


class StyleError(ValueError):
    """A style the API must refuse; the message is plain language, safe to show the user."""


def parse_style(body) -> dict:
    """The style from a request body with only the known fields, or StyleError with the first problem.
    The messages match styleProblems() in the web app."""
    if not isinstance(body, dict):
        raise StyleError("Send a style.")
    for key in COLOUR_KEYS:
        if not isinstance(body.get(key), str) or not _HEX.match(body[key]):
            raise StyleError(f"The {key} colour must look like #1A2B3C.")
    if body.get("direction") not in DIRECTIONS:
        raise StyleError("Choose a layout direction.")
    size = body.get("font_size")
    if isinstance(size, bool) or not isinstance(size, int) or not FONT_SIZE_MIN <= size <= FONT_SIZE_MAX:
        raise StyleError(f"Font size must be a whole number from {FONT_SIZE_MIN} to {FONT_SIZE_MAX} pt.")
    preset = body.get("preset")
    return {
        "preset": preset if isinstance(preset, str) and preset else None,
        **{key: body[key].upper() for key in COLOUR_KEYS},
        "direction": body["direction"],
        "font_size": size,
    }


# ============================================================================
# Storage: a version with no style of its own uses the nearest earlier version's
# ============================================================================

def saved_style(diagram_id):
    """The diagram's own style, else the nearest ancestor's (parent_id chain), else None.

    Until the diagrams.style column exists (schema.sql), no diagram has a saved style, so export keeps
    working on a database that has not been migrated yet."""
    try:
        row = db.one(
            "WITH RECURSIVE chain AS ("
            "  SELECT id, parent_id, style, 0 AS depth FROM diagrams WHERE id=%s"
            "  UNION ALL"
            "  SELECT d.id, d.parent_id, d.style, c.depth + 1 FROM diagrams d JOIN chain c ON d.id = c.parent_id"
            "  WHERE c.style IS NULL AND c.depth < 1000"
            ") SELECT style FROM chain WHERE style IS NOT NULL ORDER BY depth LIMIT 1",
            diagram_id,
        )
    except UndefinedColumn:
        return None
    if not row:
        return None
    return json.loads(row["style"]) if isinstance(row["style"], str) else row["style"]


def style_for(diagram_id) -> dict:
    return saved_style(diagram_id) or dict(DEFAULT_STYLE)


def save_style(diagram_id, style):
    db.run("UPDATE diagrams SET style=%s WHERE id=%s", json.dumps(style), diagram_id)


# ============================================================================
# Drawing
# ============================================================================

def direction_supported(diagram_type) -> bool:
    """Sequence diagrams always run top to bottom: lifelines have no other direction."""
    return diagram_type != "sequence"


def apply_style(source: str, engine: str, style: dict, diagram_type: str) -> str:
    """The source with the style applied, for one drawing. Unknown engines are returned unchanged."""
    direction = style["direction"] if direction_supported(diagram_type) else "auto"
    scale = style["font_size"] / NORMAL_FONT_SIZE
    if engine == "plantuml":
        return _plantuml(source, style, direction, scale, diagram_type)
    if engine == "graphviz":
        return _graphviz(source, style, direction, scale)
    if engine == "mermaid":
        return _mermaid(source, style, direction, scale)
    return source


# Element kinds whose box colours PlantUML sets separately. Unknown names are ignored by PlantUML.
_PUML_BOXES = (
    "actor", "usecase", "rectangle", "class", "interface", "enum", "abstract", "object", "component",
    "package", "node", "database", "queue", "collections", "participant", "entity", "boundary", "control",
    "state", "activity", "activityDiamond", "partition", "note", "frame", "folder", "card", "agent", "storage",
)
_PUML_DIRECTION = re.compile(r"^\s*(left to right|top to bottom) direction\s*$", re.IGNORECASE)
_PUML_FONT = 14  # PlantUML's default font size


def _plantuml(source, s, direction, scale, diagram_type):
    lines = source.splitlines()
    if direction != "auto":
        lines = [ln for ln in lines if not _PUML_DIRECTION.match(ln)]
    size = max(6, round(_PUML_FONT * scale))
    skin = [
        f"skinparam backgroundColor {s['background']}",
        f"skinparam defaultFontColor {s['text']}",
        f"skinparam defaultFontSize {size}",
        f"skinparam titleFontSize {round(size * 1.2)}",
        f"skinparam titleFontColor {s['text']}",
        f"skinparam arrowColor {s['line']}",
        f"skinparam arrowFontColor {s['text']}",
        f"skinparam arrowFontSize {max(6, size - 2)}",
        f"skinparam sequenceLifeLineBorderColor {s['line']}",
        f"skinparam sequenceGroupBorderColor {s['line']}",
        f"skinparam sequenceGroupBackgroundColor {s['fill']}",
        f"skinparam swimlaneBorderColor {s['line']}",
        # Start/end dots and fork bars are black by default, which vanishes on a dark background.
        f"skinparam activityBarColor {s['line']}",
        # Start/stop dots ignore skinparams in current PlantUML; only a style block reaches them.
        "<style>",
        f"activityDiagram {{ circle {{ BackgroundColor {s['text']}; LineColor {s['text']} }} }}",
        f"stateDiagram {{ circle {{ BackgroundColor {s['text']}; LineColor {s['text']} }} }}",
        "</style>",
    ]
    for kind in _PUML_BOXES:
        skin += [f"skinparam {kind}BackgroundColor {s['fill']}", f"skinparam {kind}BorderColor {s['line']}"]
    if direction != "auto" and diagram_type != "activity":  # activity diagrams always flow top to bottom
        skin.insert(0, "left to right direction" if direction == "LR" else "top to bottom direction")
    # Right after @startuml: PlantUML fixes an arrow's colours when it reads the arrow, so skinparams placed
    # after the diagram body would miss them. The generators' own skinparams (shadowing, stereotypes) follow.
    start = next((i + 1 for i, ln in enumerate(lines) if ln.strip().lower().startswith("@start")), 0)
    return "\n".join(lines[:start] + skin + lines[start:])


_DOT_HEX_FILL = re.compile(r'\bfillcolor="#[0-9A-Fa-f]{3,8}"')
_DOT_BLACK_FILL = re.compile(r'\bfillcolor="?black"?')
_DOT_HEX_LINE = re.compile(r'\bcolor="#[0-9A-Fa-f]{3,8}"')
_DOT_BGCOLOR = re.compile(r'\bBGCOLOR="[^"]*"')
_DOT_FONTSIZE = re.compile(r"\bfontsize=(\d+(?:\.\d+)?)")
_DOT_RANKDIR = re.compile(r"\brankdir=\w+")


def _graphviz(source, s, direction, scale):
    def size(m):
        return f"fontsize={round(float(m.group(1)) * scale, 1):g}"

    out = _DOT_FONTSIZE.sub(size, source)
    out = _DOT_HEX_FILL.sub(f'fillcolor="{s["fill"]}"', out)
    out = _DOT_BLACK_FILL.sub(f'fillcolor="{s["text"]}"', out)  # start/end dots, so they show on dark backgrounds
    out = _DOT_HEX_LINE.sub(f'color="{s["line"]}"', out)
    out = _DOT_BGCOLOR.sub(f'BGCOLOR="{s["fill"]}"', out)
    out = out.replace("<TABLE ", f'<TABLE COLOR="{s["line"]}" ')
    if direction != "auto":
        out = _DOT_RANKDIR.sub(f"rankdir={direction}", out) if _DOT_RANKDIR.search(out) else out
    # Defaults go first, so the generator's own node/edge attributes still win where it set them.
    defaults = (
        f'  graph [bgcolor="{s["background"]}", fontcolor="{s["text"]}"'
        + (f", rankdir={direction}" if direction != "auto" and not _DOT_RANKDIR.search(out) else "")
        + "];\n"
        f'  node [color="{s["line"]}", fontcolor="{s["text"]}"];\n'
        f'  edge [color="{s["line"]}", fontcolor="{s["text"]}"];'
    )
    brace = out.find("{")
    return out if brace < 0 else out[: brace + 1] + "\n" + defaults + out[brace + 1 :]


_MERMAID_FLOW = re.compile(r"^(\s*)(flowchart|graph)\s+(TB|TD|BT|LR|RL)\b", re.MULTILINE)


def _mermaid(source, s, direction, scale):
    variables = {
        "background": s["background"],
        "primaryColor": s["fill"],
        "primaryTextColor": s["text"],
        "primaryBorderColor": s["line"],
        "lineColor": s["line"],
        "textColor": s["text"],
        "fontSize": f"{round(16 * scale)}px",
    }
    out = source
    if direction != "auto":
        out = _MERMAID_FLOW.sub(lambda m: f"{m.group(1)}{m.group(2)} {direction}", out, count=1)
    init = "%%{init: " + json.dumps({"theme": "base", "themeVariables": variables}) + "}%%"
    return init + "\n" + out
