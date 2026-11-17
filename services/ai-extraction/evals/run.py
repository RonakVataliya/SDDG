"""Eval harness CLI: runs the real pipeline (the configured LLM) over the golden set and scores it.

    python -m evals.run --provider groq --docs all --repeat 3 --out evals/results/2026-11-10-groq.json
    python -m evals.run --provider gemini --docs library,clinic --repeat 1

Per document and run: split the text (as the API's input job does), extract every node over the split
requirements (as generation does), score names against the hand labels, and draw a Use Case diagram (spec
validation; Kroki rendering only with --render). Then flags: the quality checker over evals/flags.json.
Output: one JSON file with per-document scores, the summary, and pass/fail against TARGETS. Needs the provider
key in the environment or services/ai-extraction/.env; never logs or stores requirement text beyond the
golden documents themselves.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path
from statistics import mean

from evals import score

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
TARGETS = {  # plan 1.1; adjust with Raj if the baseline says they are unrealistic
    "actors_f1": 0.80, "processes_f1": 0.80, "entities_f1": 0.70, "relationships_f1": 0.70,
    "consistency": 0.85, "flag_precision": 0.70, "diagram_valid_rate": 0.95,
}


def load_docs(selection: str) -> list[dict]:
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(GOLDEN.glob("*.json"))]
    if selection != "all":
        wanted = set(selection.split(","))
        docs = [d for d in docs if d["id"] in wanted]
        missing = wanted - {d["id"] for d in docs}
        if missing:
            raise SystemExit(f"unknown document id(s): {', '.join(sorted(missing))}")
    return docs


class CallRecorder:
    """Wraps AIService.structured_extract to keep each call's metadata (no content)."""

    def __init__(self):
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def install(self, service):
        original = service.structured_extract

        def recorded(**kwargs):
            start = time.perf_counter()
            try:
                result, meta = original(**kwargs)
            except Exception as exc:
                with self._lock:
                    self.calls.append({"node": kwargs.get("node_name"), "status": "error", "error_type": type(exc).__name__,
                                       "seconds": round(time.perf_counter() - start, 3)})
                raise
            with self._lock:
                self.calls.append({**meta, "seconds": round(time.perf_counter() - start, 3)})
            return result, meta

        service.structured_extract = recorded

    def take(self) -> list[dict]:
        with self._lock:
            out, self.calls = self.calls, []
        return out


class _NoRender:
    def render_svg(self, source, engine="plantuml"):
        return "", 0.0


def draw_use_case(result: dict, render: bool) -> dict:
    """Use Case spec from the extracted actors/processes/interactions; valid = no spec errors (and rendered)."""
    from app.schemas.usecase import UseCaseApprovalRequest
    from app.services import usecase_service

    if not render:
        usecase_service.get_kroki_service = lambda: _NoRender()
    request = UseCaseApprovalRequest(project_name="Eval", actors=result.get("actors", []),
                                     processes=result.get("processes", []), interactions=result.get("interactions", []))
    try:
        out = usecase_service.run_usecase_diagram_generation(request)
    except Exception as exc:  # noqa: BLE001 -- a failed draw is a result here, not a crash
        return {"type": "use_case", "valid": False, "error": type(exc).__name__}
    rendered = bool(out.svg) if render else None
    return {"type": "use_case", "valid": not out.errors and rendered is not False, "errors": len(out.errors),
            "use_cases": len(out.spec.usecases), "rendered": rendered}


def run_document(doc: dict, render: bool, recorder: CallRecorder) -> dict:
    from app.services.extraction_service import run_extraction_pipeline, run_split

    start = time.perf_counter()
    split = run_split(doc["text"], project_name=doc["title"])
    result = run_extraction_pipeline(requirements=split.requirements, project_name=doc["title"]).model_dump(mode="json")
    req_ids = [r.id for r in split.requirements]
    diagram = draw_use_case(result, render)
    calls = recorder.take()
    expected = doc.get("requirement_count")
    return {
        "scores": score.score_document(result, doc["labels"]),
        "requirements": len(req_ids),
        "split_error": round(abs(len(req_ids) - expected) / expected, 3) if expected else None,
        "coverage": score.coverage(result, req_ids),
        "assumption_rate": score.assumption_rate(result),
        "issues": len(result.get("issues", [])),
        # prompt-injection cases: extracted names that the injected text asked for (should be 0)
        "forbidden_hits": sum(score.similarity(e["name"], f) >= score.THRESHOLD for f in doc.get("forbidden", [])
                              for cat in score.ELEMENT_CATEGORIES for e in result.get(cat, [])),
        "diagram": diagram,
        "cost": {"calls": len(calls), "errors": sum(c.get("status") == "error" for c in calls),
                 "attempts": sum(c.get("attempts", 1) for c in calls),
                 "input_chars": sum(c.get("input_chars", 0) for c in calls),
                 "input_tokens": sum(c.get("input_tokens", 0) for c in calls) or None,
                 "output_tokens": sum(c.get("output_tokens", 0) for c in calls) or None,
                 "seconds": round(time.perf_counter() - start, 2)},
        "_elements": sorted(score.element_set(result)),
    }


def run_flags() -> dict:
    from app.services.quality_checker import analyze_requirements

    labelled = json.loads((HERE / "flags.json").read_text(encoding="utf-8"))
    out = analyze_requirements([{"id": s["id"], "text": s["text"]} for s in labelled])
    predicted: dict[str, set[str]] = {}
    for f in out.flags:
        for rid in [f.requirement_id, *f.related_requirement_ids]:
            predicted.setdefault(rid, set()).add(getattr(f.type, "value", str(f.type)))
    return score.score_flags(predicted, labelled)


def summarise(docs: list[dict]) -> dict:
    runs = [r for d in docs for r in d["runs"] if "error" not in r]
    per_category = score.aggregate([r["scores"] for r in runs])
    consistencies = [d["consistency"] for d in docs if d["consistency"] is not None]
    diagrams = [r["diagram"]["valid"] for r in runs]
    seconds = sorted(r["cost"]["seconds"] for r in runs)
    return {
        "runs": len(runs), "failed_runs": sum("error" in r for d in docs for r in d["runs"]),
        "per_category": per_category,
        "consistency": round(mean(consistencies), 3) if consistencies else None,
        "coverage": round(mean(r["coverage"] for r in runs), 3) if runs else None,
        "assumption_rate": round(mean(r["assumption_rate"] for r in runs), 3) if runs else None,
        "diagram_valid_rate": round(sum(diagrams) / len(diagrams), 3) if diagrams else None,
        "seconds_median": seconds[len(seconds) // 2] if seconds else None,
        "seconds_p95": seconds[min(len(seconds) - 1, int(len(seconds) * 0.95))] if seconds else None,
        "calls": sum(r["cost"]["calls"] for r in runs),
        "forbidden_hits": sum(r["forbidden_hits"] for r in runs),
        "input_tokens": sum(r["cost"]["input_tokens"] or 0 for r in runs) or None,
        # gpt-oss counts hidden reasoning as output: this is what uses up Groq's tokens/day
        "output_tokens": sum(r["cost"]["output_tokens"] or 0 for r in runs) or None,
    }


def check_targets(summary: dict, flags: dict) -> dict:
    cat = summary["per_category"]
    values = {
        "actors_f1": cat.get("actors", {}).get("f1"), "processes_f1": cat.get("processes", {}).get("f1"),
        "entities_f1": cat.get("entities", {}).get("f1"), "relationships_f1": cat.get("relationships", {}).get("f1"),
        "consistency": summary["consistency"], "flag_precision": flags["precision"],
        "diagram_valid_rate": summary["diagram_valid_rate"],
    }
    return {k: {"value": v, "target": TARGETS[k], "pass": v is not None and v >= TARGETS[k]} for k, v in values.items()}


def git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def evaluate(docs: list[dict], repeat: int, render: bool, log=print) -> dict:
    from app.config import get_settings
    from app.services.ai_service import get_ai_service

    recorder = CallRecorder()
    recorder.install(get_ai_service())
    out_docs = []
    for doc in docs:
        runs = []
        for i in range(repeat):
            try:
                runs.append(run_document(doc, render, recorder))
            except Exception as exc:  # noqa: BLE001 -- a failed run is recorded; the rest still runs
                recorder.take()
                runs.append({"error": type(exc).__name__})
            log(f"{doc['id']} run {i + 1}/{repeat}: " + ("failed: " + runs[-1]["error"] if "error" in runs[-1] else
                ", ".join(f"{c} {s['f1']}" for c, s in runs[-1]["scores"].items())))
        ok = [r for r in runs if "error" not in r]
        consistency = score.consistency([set(r["_elements"]) for r in ok])
        for r in ok:
            r.pop("_elements")
        out_docs.append({"id": doc["id"], "style": doc.get("style"), "reviewed": doc.get("reviewed", False),
                         "consistency": consistency, "runs": runs})
    flags = run_flags()
    summary = summarise(out_docs)
    settings = get_settings()
    return {
        "meta": {"date": date.today().isoformat(), "provider": settings.LLM_PROVIDER, "model": settings.active_model,
                 "git": git_sha(), "repeat": repeat, "render": render, "documents": len(docs)},
        "summary": summary, "flags": flags, "targets": check_targets(summary, flags), "documents": out_docs,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--provider", choices=["groq", "gemini"], help="overrides LLM_PROVIDER")
    parser.add_argument("--docs", default="all", help="'all' or comma-separated ids from evals/golden")
    parser.add_argument("--repeat", type=int, default=3, help="runs per document (consistency needs >= 2)")
    parser.add_argument("--render", action="store_true", help="also render each Use Case through Kroki")
    parser.add_argument("--out", help="write the JSON report here (default: evals/results/<date>-<provider>.json)")
    args = parser.parse_args(argv)
    if args.provider:  # only this provider: an eval run must never fail over to the other one
        os.environ["LLM_PROVIDER"] = args.provider
        os.environ["LLM_PROVIDERS"] = args.provider
    report = evaluate(load_docs(args.docs), args.repeat, args.render)
    out = Path(args.out) if args.out else HERE / "results" / f"{report['meta']['date']}-{report['meta']['provider']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")
    for k, t in report["targets"].items():
        print(f"  {'PASS' if t['pass'] else 'FAIL'}  {k:<20} {t['value']}  (target {t['target']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
