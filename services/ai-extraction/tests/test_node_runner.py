"""Chunking, canonical names and ids, and the single repair call (plan 1.4, 1.5, 1.7)."""
import app.graph.node_runner as runner
from app.graph.node_runner import canonical_elements, chunk_requirements, norm_key, run_node, stable_id, tidy_name
from app.schemas.elements import Actor, ActorExtraction, Entity, Interaction, InteractionExtraction
from app.schemas.requirements import RequirementStatement

REQS = [RequirementStatement(id=f"R-{i:03d}", text=f"The member shall do thing number {i} with the catalogue.") for i in range(1, 11)]


class Scripted:
    """Answers each call from a list; records what it was sent. budget = characters of content per call."""

    def __init__(self, answers, budget=10**9):
        self.answers, self.budget, self.sent = list(answers), budget, []

    def content_budget(self, node_name, system_prompt, schema):
        return self.budget

    def structured_extract(self, *, node_name, system_prompt, user_content, schema):
        self.sent.append((node_name, user_content))
        return self.answers.pop(0), {"node": node_name}


def patch(monkeypatch, fake):
    monkeypatch.setattr(runner, "get_ai_service", lambda: fake)
    return fake


def test_canonical_names_merge_duplicates_and_ids_are_reproducible():
    items = [Entity(id="E-001", name="  books ", source_refs=["R-001"]), Entity(id="E-002", name="Book.", source_refs=["R-002"]),
             Entity(id="E-003", name="Library Members", source_refs=["R-003"])]
    out, remap = canonical_elements("entities", items)
    assert [e.name for e in out] == ["Book", "Library Member"]
    assert out[0].source_refs == ["R-001", "R-002"]
    assert remap["E-001"] == remap["E-002"] == out[0].id == stable_id("entities", "book")
    again, _ = canonical_elements("entities", [Entity(id="X", name="Book")])
    assert again[0].id == out[0].id  # same name, same id, whatever the model numbered it
    assert tidy_name("SMS", "entities") == "SMS" and norm_key("The Categories") == "category"


def test_a_new_duplicate_of_a_known_element_folds_into_it():
    known = [Actor(id="it_123", name="Member")]
    out, remap = canonical_elements("actors", [Actor(id="A-001", name="member"), Actor(id="A-002", name="Librarian")], known)
    assert [a.name for a in out] == ["Librarian"] and remap["A-001"] == "it_123"


def test_chunking_keeps_order_and_tells_later_batches_the_names_so_far(monkeypatch):
    many = [RequirementStatement(id=f"R-{i:03d}", text=f"The member shall do thing number {i} with the catalogue.") for i in range(1, 61)]
    batches = chunk_requirements(many, 2000)  # the runner never chunks below 2000 characters
    assert [r.id for b in batches for r in b] == [r.id for r in many] and len(batches) == 3
    fake = patch(monkeypatch, Scripted(
        [ActorExtraction(actors=[Actor(id="A-001", name="Member", source_refs=["R-001"])])] +
        [ActorExtraction(actors=[Actor(id="A-001", name="member", source_refs=[b[0].id])]) for b in batches[1:]],
        budget=2400))  # 2400 - 400 safety = 2000 chars per batch
    out = run_node({"requirements": many}, node_name="extract_actors", system_prompt="s", schema=ActorExtraction, fields=["actors"])
    assert len(fake.sent) == len(batches)
    assert "ALREADY EXTRACTED" not in fake.sent[0][1] and "Member" in fake.sent[1][1].split("ALREADY EXTRACTED")[1]
    assert [(a.name, len(a.source_refs)) for a in out["actors"]] == [("Member", len(batches))]  # one actor, all refs


def test_invalid_relations_get_one_repair_call_then_are_dropped(monkeypatch):
    state = {"requirements": REQS[:2], "actors": [Actor(id="A-x", name="Member")]}
    bad = InteractionExtraction(interactions=[Interaction(id="I-1", source_id="A-x", target_id="P-nope", source_refs=["R-001", "R-999"])])
    good = InteractionExtraction(interactions=[Interaction(id="I-1", source_id="A-x", target_id="A-x")])  # self: dropped
    fake = patch(monkeypatch, Scripted([bad, bad]))
    out = run_node(state, node_name="extract_interactions", system_prompt="s", schema=InteractionExtraction,
                   fields=["interactions"], context="KNOWN ACTORS:\nA-x (human): Member", valid_ends={"A-x"})
    assert [n for n, _ in fake.sent] == ["extract_interactions", "extract_interactions_repair"]
    assert "unknown id P-nope" in fake.sent[1][1]
    assert out["interactions"] == []
    fake = patch(monkeypatch, Scripted([good]))
    out = run_node(state, node_name="extract_interactions", system_prompt="s", schema=InteractionExtraction,
                   fields=["interactions"], context="", valid_ends={"A-x"})
    assert len(fake.sent) == 1 and out["interactions"] == []  # valid ids, so no repair; the self-loop is dropped


def test_source_refs_are_limited_to_this_runs_requirements(monkeypatch):
    patch(monkeypatch, Scripted([ActorExtraction(actors=[Actor(id="A-1", name="Member", source_refs=["R-001", "R-404"])])]))
    out = run_node({"requirements": REQS[:1]}, node_name="extract_actors", system_prompt="s", schema=ActorExtraction, fields=["actors"])
    assert out["actors"][0].source_refs == ["R-001"]


def test_a_large_text_is_split_in_pieces_and_renumbered(monkeypatch):
    import app.graph.nodes.split as split_mod
    from app.graph.nodes.split import text_pieces
    from app.schemas.requirements import RequirementSplitResult, SourceLocation

    text = "\n".join(f"{i}. The member shall do thing number {i} with the library catalogue today." for i in range(1, 81))
    pieces = text_pieces(text, 1500)
    assert len(pieces) > 1 and "\n".join(p for _, p in pieces) == text  # nothing lost, nothing repeated

    class Fake(Scripted):
        def structured_extract(self, *, node_name, system_prompt, user_content, schema):
            self.sent.append((node_name, user_content))
            lines = user_content.split("\n")
            return RequirementSplitResult(requirements=[
                RequirementStatement(id=f"R-{i + 1:03d}", text=line, source_location=SourceLocation(line_start=i + 1, line_end=i + 1))
                for i, line in enumerate(lines)]), {"node": node_name}

    fake = Fake([], budget=3400)  # 3400 * 0.45 = 1530 characters per piece
    monkeypatch.setattr(split_mod, "get_ai_service", lambda: fake)
    out = split_mod.split_requirements({"raw_input": text})
    assert len(fake.sent) == len(pieces)
    assert [r.id for r in out["requirements"]] == [f"R-{i:03d}" for i in range(1, 81)]
    assert [r.source_location.line_start for r in out["requirements"]] == list(range(1, 81))  # lines of the full text


def test_rules_first_split_needs_no_llm_for_a_numbered_list(monkeypatch):
    import app.graph.nodes.split as split_mod
    from app.config import get_settings
    from app.graph.deterministic_split import deterministic_split

    text = "1. A member borrows a book.\n2. The librarian adds books\n   to the catalogue.\nNFR-1 Pages load within 2 s."
    out = deterministic_split(text)
    assert [(r.id, r.text, r.labels[0].value) for r in out] == [
        ("R-001", "A member borrows a book.", "unknown"),
        ("R-002", "The librarian adds books to the catalogue.", "unknown"),
        ("R-003", "Pages load within 2 s.", "non_functional")]
    assert out[1].source_location.line_start == 2 and out[1].source_location.line_end == 3
    assert deterministic_split("Customers open the app and order food. They pay in the app.\nRestaurants accept it.") is None

    fake = Scripted([])
    monkeypatch.setattr(split_mod, "get_ai_service", lambda: fake)
    monkeypatch.setattr(split_mod, "get_settings", lambda: get_settings().model_copy(update={"SPLIT_MODE": "rules_first"}))
    assert len(split_mod.split_requirements({"raw_input": text})["requirements"]) == 3 and fake.sent == []
