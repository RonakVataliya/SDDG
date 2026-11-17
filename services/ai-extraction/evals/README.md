# Eval harness

Measures whether the AI output is right (plan 1.1). Runs the real pipeline with the configured LLM.

```bash
cd services/ai-extraction
python -m evals.run --provider groq --docs all --repeat 3          # writes evals/results/<date>-groq.json
python -m evals.run --provider gemini --docs library,parking --repeat 1
python -m evals.build_golden                                        # after editing the golden set
```

- `golden/` — 15 hand-labelled documents (5 to 45 requirements; numbered SRS, "shall" lists, user stories, prose,
  NFR-heavy, deliberately vague, two prompt-injection cases, and this project's own SRS FR1–FR30). Edit them in
  `build_golden.py`, not by hand. `reviewed: false` = labels not yet checked by a second person.
- `flags.json` — 40 statements labelled ambiguous / incomplete / conflict / fine, for the quality checker.
- Scores: precision / recall / F1 per category (names matched with `difflib`, synonyms allowed), requirement
  coverage, assumption rate (elements with no source requirement), consistency (mean Jaccard over repeated
  runs), Use Case validity, prompt-injection hits, calls / tokens / seconds. Targets are in `run.py` (`TARGETS`).
- Adopt a prompt, model, chunking or routing change only if the score stays within tolerance of the committed
  baseline in `results/`.
