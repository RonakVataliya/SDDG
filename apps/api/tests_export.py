"""Unit tests for the export helpers that need no database, Kroki or AI service.

Run:  cd apps/api && python tests_export.py
"""
import os
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "postgresql://unused")  # core.db builds a pool at import; it is never opened

from core.diagram_models import kroki_engine_for_source  # noqa: E402
from routers.integrated import ENGINE_EXPORT_FORMATS, SOURCE_TYPES, latest_only, moved_note, slugify, zip_layout, zip_path  # noqa: E402


def t(minute):
    return datetime(2026, 11, 1, 10, minute)


def test_zip_layout():
    rows = [
        {"id": "a", "parent_id": None, "title": "Library · Use Case", "created_at": t(1)},
        {"id": "b", "parent_id": "a", "title": "Library · Use Case", "created_at": t(2)},   # edit
        {"id": "c", "parent_id": "b", "title": "Library · Use Case", "created_at": t(3)},   # edit
        {"id": "d", "parent_id": None, "title": "Library · Use Case", "created_at": t(4)},  # "Generate again"
        {"id": "e", "parent_id": None, "title": "Library · DFD", "created_at": t(5)},
        {"id": "f", "parent_id": "a", "title": "Library · Use Case", "created_at": t(6)},   # edit of an older version
    ]
    names = zip_layout(rows)
    # Every diagram with the same title is a version of one diagram, numbered by creation time.
    assert names == {
        "a": "library-use-case/v1", "b": "library-use-case/v2", "c": "library-use-case/v3",
        "d": "library-use-case/v4", "f": "library-use-case/v5", "e": "library-dfd/v1",
    }, names
    assert len(set(names.values())) == len(rows), "every version gets its own file name"

    # versions=latest: one file per diagram, its newest version, without the version folder.
    assert latest_only(names) == {"f": "library-use-case", "e": "library-dfd"}


def test_zip_path():
    assert zip_path("library-use-case/v2", "png") == "library-use-case/v2/library-use-case-v2.png"
    assert zip_path("library-use-case", "puml") == "library-use-case.puml"  # versions=latest: no folders


def test_latest_only_compares_versions_as_numbers():
    assert latest_only({"x": "a/v2", "y": "a/v10"}) == {"y": "a"}  # v10 is newer than v2


def test_slugify():
    assert slugify("Hospital Management · Use Case") == "hospital-management-use-case"
    assert slugify("···") == "diagram"


def test_source_types_cover_every_engine():
    for source, ext in [("@startuml\nA -> B\n@enduml", "puml"), ("digraph G { a -> b }", "dot"),
                        ("flowchart LR\n a --> b", "mmd")]:
        engine = kroki_engine_for_source(source)
        assert SOURCE_TYPES[engine][1] == ext, (engine, ext)
        assert engine in ENGINE_EXPORT_FORMATS
    assert "pdf" not in ENGINE_EXPORT_FORMATS["mermaid"], "Kroki has no Mermaid PDF output"


def test_moved_note_lists_versions_with_a_saved_layout():
    names = {"a": "library-use-case/v1", "b": "library-use-case/v2"}
    assert moved_note(names, [{"id": "a", "layout": None}, {"id": "b", "layout": {}}]) == []
    note = moved_note(names, [{"id": "a", "layout": None}, {"id": "b", "layout": {"uc1": [10, 20]}}])
    assert note[-1] == "library-use-case/v2" and "Export there" in note[2]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("export unit tests passed")
