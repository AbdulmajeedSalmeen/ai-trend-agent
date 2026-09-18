# Stage 2a — Clustering Tuning Log

This document records clustering experiments for Stage 2a.

The goal is to compare clustering quality while keeping the process
reproducible and easy to tune.

---

## Dataset

Initial offline test dataset:

`fixtures/samples/signals_fixture.json`

Total signals: 12

Expected topics:

- LangGraph 2.0 — 4 signals
- Transformers 5.1.0 — 3 signals
- OpenAI Python 2.9.0 — 2 signals
- Unrelated news — 3 signals

The full 12-signal fixture should be used when evaluating clustering
because TF-IDF depends on the full corpus.

---

## Experiment 1 — TF-IDF Baseline
- Date: 2026-09-16
- Method: TF-IDF + Cosine Distance + Agglomerative Clustering
- Distance threshold: 0.8
- Dataset: fixtures/samples/signals_fixture.json
- Total signals: 12
- Number of clusters: 6
- Singleton clusters: 3
- Status: Passed baseline evaluation

### Observed groups

1. LangGraph — 4 signals
2. Transformers — 3 signals
3. OpenAI Python — 2 signals
4. PostgreSQL — 1 signal
5. Linux Kernel — 1 signal
6. SQLite — 1 signal

### Observation

The 0.8 threshold correctly grouped the three expected AI topics while keeping
the three unrelated signals as singleton clusters on the fixture dataset.
This threshold is a baseline and must be re-evaluated on real Stage 1 data.
---

## Experiment 2 — TF-IDF Tuned

Date:
TBD

Method:
TF-IDF + Cosine Distance + Agglomerative Clustering

Distance threshold:
TBD

Number of trends:
TBD

Number of singleton clusters:
TBD

Example groups:
1. TBD
2. TBD
3. TBD

Observation:
TBD

---

## Experiment 3 — Hugging Face Embeddings

Date:
TBD

Method:
Sentence Transformers — all-MiniLM-L6-v2

Distance threshold:
TBD

Dataset:
Same dataset used for the TF-IDF comparison.

Number of trends:
TBD

Number of singleton clusters:
TBD

Example groups:
1. TBD
2. TBD
3. TBD

Observation:
TBD

---

## Final Comparison

| Metric | TF-IDF | Embeddings |
|---|---:|---:|
| Number of trends | TBD | TBD |
| Singleton clusters | TBD | TBD |
| LangGraph grouping quality | TBD | TBD |
| Transformers grouping quality | TBD | TBD |
| OpenAI Python grouping quality | TBD | TBD |
| Overall logical grouping | TBD | TBD |

Preferred method:
TBD

Reason:
TBD

---

## Notes

- TF-IDF remains the offline baseline and fallback method.
- Hugging Face embeddings will be added after Integration 1.
- Embedding model loading must be lazy and must not happen during import.
- Threshold changes must be recorded in this document.
- Both methods should be compared using the same dataset.
- Decision (2026-09-18): A Trend represents one subject, not one version.
- Multiple distinct Tier-1 versions for the same subject are emitted as separate Claims inside the same Trend.
- Duplicate release Claims are deduplicated by `(subject, version)`.
- Release Claims are ordered newest version first.
- The discussion Claim remains in the Trend alongside release Claims.
- Clustering threshold tuning is deferred for now; the current priority is claim coverage and accuracy rather than reducing subject-group size.