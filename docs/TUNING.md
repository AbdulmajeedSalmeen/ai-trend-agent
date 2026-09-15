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

Date: 2026-09-15

Method:
TF-IDF + Cosine Distance + Agglomerative Clustering

Status:
Not evaluated yet

Planned distance threshold:
0.8

Dataset:
`fixtures/samples/signals_fixture.json`

Number of signals:
12

Number of trends:
TBD

Number of singleton clusters:
TBD

Example groups:
1. TBD
2. TBD
3. TBD

Observation:
Baseline experiment has not been run yet. The initial threshold of 0.8
will be evaluated against the 12-signal fixture and adjusted based on
grouping quality.

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