# Member C — Stage 2a: Clustering + Claim Extraction

**Mission:** Stage 1 hands you a pile of 100+ mixed signals. You group the ones talking
about the same thing into **trends**, and turn each trend into checkable **claims**
("langgraph version 2.0.0 was released"). You are the NLP person: you start with TF-IDF,
then upgrade to a **Hugging Face pretrained model** and measure the difference — that
comparison is one of the strongest slides in our demo.

**You will learn:** TF-IDF, cosine similarity, sentence embeddings (Hugging Face
sentence-transformers), clustering with scikit-learn, regex, measuring instead of guessing.

**Files you own:**
- `src/stages/stage2a_cluster.py`
- `tests/test_stage2a.py`
- `docs/TUNING.md` (your measurements log)

**Your contract:** read `signals.json`. Write `trends.json` — every claim starts
`verdict="unverified"`, `evidence_url=None`, `confidence=0.2`. Member D fills those in.
You never decide truth; you only group and extract.

---

## Sep 16 — hand-made fixture + feel the similarity math

Real data does not exist yet (B is building it). Make your own — 12 signals covering
3 obvious groups + noise. Create `fixtures/samples/signals_fixture.json` by hand:

- 4 signals about langgraph 2.0 (two github tier-1, two hackernews tier-2)
- 3 signals about transformers 5.1.0
- 2 signals about openai-python 2.9.0
- 3 unrelated one-off stories

Copy the Signal JSON shape from TEAM-PLAN.md exactly. Validate your handwork:

```bash
python -c "import json; from src.schema import Signal; [Signal.model_validate(s) for s in json.load(open('fixtures/samples/signals_fixture.json', encoding='utf-8'))]; print('fixture valid')"
```

Now play with similarity in a Python shell — this is today's real work, understanding:

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import json

signals = json.load(open("fixtures/samples/signals_fixture.json", encoding="utf-8"))
texts = [s["title"] + " " + s["body"] for s in signals]
matrix = TfidfVectorizer().fit_transform(texts)
sim = cosine_similarity(matrix)
for i, row in enumerate(sim):
    print(signals[i]["title"][:40], [round(x, 2) for x in row])
```

Stare at the numbers. Same-topic pairs should score high (0.3+), unrelated near 0.
Try thresholds in your head: which value separates groups correctly? Write what you
found into `docs/TUNING.md` — date, threshold, observation. Every number you ever pick
gets a line in that file.

## Sep 17 — clustering function + tests

```python
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

from src.schema import Signal, Trend


def signal_text(s: Signal) -> str:
    return f"{s.subject or ''} {s.title} {s.body[:500]}"


def cluster_signals(signals: list[Signal], distance_threshold: float = 0.8) -> list[list[Signal]]:
    """Group signals about the same topic. Returns list of groups (singletons allowed)."""
    # TODO:
    #  vectors = TfidfVectorizer().fit_transform([signal_text(s) for s in signals])
    #  labels = AgglomerativeClustering(
    #      n_clusters=None, distance_threshold=distance_threshold,
    #      metric="cosine", linkage="average",
    #  ).fit_predict(vectors.toarray())
    #  collect signals by label
    # Special case first: 0 or 1 signals -> return trivially (clustering needs 2+).
    ...
```

Shortcut that beats fancy math: signals whose `subject` field is already set (GitHub
releases) can be grouped by subject DIRECTLY — exact, free, correct. Cluster only the
subject-less ones (HN posts), then attach a cluster to a subject-group when they share
a subject word in the title. Do the simple exact grouping FIRST, clustering second.

Tests:
- the 4 langgraph fixture signals end in one group
- transformers and openai signals never merge
- 1 signal in, 1 group out, no crash
- empty list in, empty list out, no crash

**Test trap from the original build:** TF-IDF weights depend on corpus size. A word looks
distinctive among 4 signals and generic among 900. Never test with 3 toy signals — always
use the full 12-signal fixture.

## Sep 18 — claim extraction

A claim = (subject, version, sentence). v1 is regex — a model comes later, maybe.

```python
import re

VERSION_RE = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?)\b")


def extract_version(text: str) -> str | None:
    """First version-looking number, WITHOUT the leading v. None if absent."""
    ...


def make_claims(group: list[Signal]) -> list[Claim]:
    """Best signal to read a version from = the tier-1 (github) one; its tag is exact.
    Claim text: '{subject} version {version} was released'.
    Group with no subject and no version -> claim from the title verbatim, version=None.
    Every claim: verdict='unverified', evidence_url=None, confidence=0.2."""
    ...


def run(run_dir: Path) -> None:
    # load signals -> cluster -> claims -> Trend objects (id = 'trend_001', 002, ...)
    # -> runio.save_artifact(run_dir, 'trends', trends)
    ...
```

Tests that MUST exist (Member D's stage dies on these if you get them wrong):
- `extract_version("Release v2.0.0")` == `"2.0.0"`
- `extract_version("GPT-5.6.1 launched")` == `"5.6.1"` — NOT `"5.6"`
- `extract_version("no numbers here")` is None
- a trend built from the langgraph fixture group carries subject `"langgraph"` and version from the tier-1 signal

Full stage check:

```bash
python -c "from pathlib import Path; import shutil; from src import runio; from src.stages import stage2a_cluster; rd = runio.run_dir('run_test_c'); shutil.copy('fixtures/samples/signals_fixture.json', rd / 'signals.json'); stage2a_cluster.run(rd); print((rd / 'trends.json').read_text(encoding='utf-8')[:800])"
```

## Sep 19 — polish + PR

Edge cases: signal with empty body; two versions in one title (take the first);
duplicate claims in one trend (deduplicate by (subject, version)).
`pytest` green, push, tell Lead.

## Sep 21–22 — the Hugging Face upgrade (after Integration 1)

Now real data exists. Swap the vectorizer for a pretrained sentence-embedding model:

```python
from sentence_transformers import SentenceTransformer

_model = None  # load once, lazily — loading takes ~10s


def embed(texts: list[str]):
    global _model
    if _model is None:
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model.encode(texts)
```

`cluster_signals` gets a parameter `method="tfidf" | "embeddings"` — same
AgglomerativeClustering after, only the vectors change. KEEP the TF-IDF path working;
it is the fallback and the baseline.

First install (~2GB with PyTorch — home wifi, not bootcamp wifi):

```bash
pip install sentence-transformers
```

Then MEASURE on the same real run, both methods:
- number of trends found
- number of singleton groups
- 3 example groups from each — which grouping reads more correct to a human?

Record all numbers in `docs/TUNING.md`. That table becomes a demo slide:
"TF-IDF vs pretrained transformer embeddings, measured on our own data."

## Traps

1. **Version by substring lies.** `"5.6" in "5.6.1"` is True in Python. That is why
   `extract_version` returns the FULL match and D compares with `==` only.
2. **`.toarray()` on huge corpora** eats RAM. Under 2,000 signals it is fine. If B
   delivers 10,000+, tell Lead — we cap ingestion, you do not fix it with clever code.
3. **Model download on first run** (~90MB) needs internet once, then it is cached locally.
   Never let tests trigger it — tests use TF-IDF only.
4. **Clustering with n_clusters=None requires distance_threshold** — forgetting it is the
   most common sklearn error message you will see this week.

## Definition of done

- [ ] `cluster_signals` + `make_claims` + `run` written
- [ ] 8+ tests green, TF-IDF only, offline
- [ ] `trends.json` produced from the fixture, shape matches TEAM-PLAN.md exactly
- [ ] Every threshold you chose has a line in `docs/TUNING.md`
- [ ] (Sep 22) embeddings path working + comparison table written
