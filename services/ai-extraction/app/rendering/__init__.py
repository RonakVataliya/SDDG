"""
Shared code for the post-approval diagram stage of every diagram type except
use case (which keeps its original, self-contained app/usecase/ package):

- engines.py  ENGINE_FOR_DIAGRAM, the one place to choose a renderer per type
- escape.py   text escaping + safe identifiers for PlantUML / Graphviz / Mermaid
- context.py  formatting approved items into LLM context text
"""
