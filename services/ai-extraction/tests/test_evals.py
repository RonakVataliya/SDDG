"""The eval harness (evals/): scoring maths, the golden set's shape, and one end-to-end run with a fake LLM."""
import json
from pathlib import Path

import pytest

from evals import score
from evals.run import GOLDEN, TARGETS, evaluate, load_docs, run_flags

from tests.test_pipeline import FakeAIService
from tests.test_usecase import FakeAIService as FakeUseCaseAI


def test_normalise_and_similarity():
    assert score.normalise("The Library Members") == "library member"
    assert score.normalise("Categories") == "category"
    assert score.similarity("Borrow a book", "borrow book") == 1.0
    assert score.similarity("member", "Library member") >= score.THRESHOLD  # whole-word containment
    assert score.similarity("Librarian", "Library") < score.THRESHOLD


def test_matching_is_one_to_one():
    gold = [["Member", "Library member"], ["Librarian"]]
    s = score.score_elements(["Member", "Library Member", "Librarian", "Clerk"], gold)
    assert (s["matched"], s["pred"], s["gold"]) == (2, 4, 2)
    assert (s["precision"], s["recall"]) == (0.5, 1.0)


def test_relations_use_synonyms_and_direction():
    labels = {"actors": [["Member", "Library member"]], "processes": [["Borrow book", "Issue book"]],
              "interactions": [["Member", "Borrow book"]], "data_flows": [["Member", "Borrow book"]]}
    result = {"actors": [{"id": "A1", "name": "Library member"}], "processes": [{"id": "P1", "name": "Issue book"}],
              "interactions": [{"source_id": "P1", "target_id": "A1"}], "data_flows": [{"source_id": "P1", "target_id": "A1"}]}
    out = score.score_document(result, labels)
    assert out["interactions"]["f1"] == 1.0  # undirected
    assert out["data_flows"]["f1"] == 0.0  # directed: reversed flow does not count
    assert "entities" not in out  # not labelled, not scored


def test_coverage_assumptions_consistency_and_flags():
    result = {"actors": [{"name": "A", "source_refs": ["R-001"]}, {"name": "B", "source_refs": []}]}
    assert score.coverage(result, ["R-001", "R-002"]) == 0.5
    assert score.assumption_rate(result) == 0.5
    assert score.consistency([{"a", "b"}, {"a", "b"}]) == 1.0
    assert score.consistency([{"a", "b"}, {"a", "c"}]) == round(1 / 3, 3)
    assert score.consistency([{"a"}]) is None
    flags = score.score_flags({"1": {"ambiguous"}, "3": {"incomplete"}},
                              [{"id": "1", "expected": ["ambiguous"]}, {"id": "2", "expected": ["conflict"]}, {"id": "3", "expected": []}])
    assert (flags["precision"], flags["recall"], flags["type_accuracy"]) == (0.5, 0.5, 1.0)


def test_golden_set_shape():
    docs = load_docs("all")
    assert len(docs) >= 15
    assert min(d["requirement_count"] for d in docs) <= 5 and max(d["requirement_count"] for d in docs) >= 40
    assert sum(d["style"] == "injection" and bool(d["forbidden"]) for d in docs) >= 2
    assert any(d["id"] == "sddg_srs" for d in docs)
    for d in docs:
        for cat in score.RELATION_CATEGORIES:
            canon = {score.normalise(e[0]) for c in score.ELEMENT_CATEGORIES for e in d["labels"].get(c, [])}
            for a, b in d["labels"].get(cat, []):
                assert score.normalise(a) in canon and score.normalise(b) in canon, (d["id"], cat, a, b)
    labelled = json.loads((GOLDEN.parent / "flags.json").read_text(encoding="utf-8"))
    assert len(labelled) == 40 and {t for s in labelled for t in s["expected"]} == {"ambiguous", "incomplete", "conflict"}


def test_flag_scoring_runs_the_real_checker():
    out = run_flags()
    assert out["gold"] == 26 and out["precision"] is not None


@pytest.fixture
def fake_llm(monkeypatch):
    import app.graph.nodes.extract_actors as a
    import app.graph.nodes.extract_dataflows as d
    import app.graph.nodes.extract_entities as e
    import app.graph.nodes.extract_interactions as i
    import app.graph.nodes.extract_processes as p
    import app.graph.nodes.extract_relationships as r
    import app.graph.node_runner as runner
    import app.graph.nodes.split as s
    import app.services.ai_service as ai_mod
    from app.services import usecase_service

    class Both(FakeAIService):
        def structured_extract(self, **kw):
            from app.schemas.usecase import UseCaseSpec
            if kw["schema"] is UseCaseSpec:
                return FakeUseCaseAI().structured_extract(**kw)
            return super().structured_extract(**kw)

    fake = Both()
    for mod in (a, d, e, i, p, r, s, runner, usecase_service):
        monkeypatch.setattr(mod, "get_ai_service", lambda: fake, raising=False)
    monkeypatch.setattr(ai_mod, "get_ai_service", lambda: fake)
    return fake


def test_evaluate_end_to_end_with_a_fake_llm(fake_llm, tmp_path: Path):
    report = evaluate(load_docs("parking"), repeat=2, render=False, log=lambda *_: None)
    run = report["documents"][0]["runs"][0]
    assert "error" not in run, run
    assert set(run["scores"]) == {"actors", "entities", "processes", "interactions", "relationships"}
    assert run["cost"]["calls"] == 8  # split + 6 nodes + use case spec
    assert report["documents"][0]["consistency"] == 1.0  # the fake answers the same every time
    assert set(report["targets"]) == set(TARGETS)
    assert report["meta"]["repeat"] == 2 and report["summary"]["runs"] == 2
    json.dumps(report)  # the report is plain JSON
