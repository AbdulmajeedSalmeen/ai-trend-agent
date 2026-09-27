"""Whether employers ask for what a proposed lesson adds.

The AI reviewers proposed new lessons. A proposal is an opinion until it is
measured the way MCP was: the name an employer would write for what the lesson
adds, counted in the "Ask HN: Who is hiring?" threads, and looked for in the
notebooks, so a lesson on something the course already mentions is not counted
as new.

A model picks the name, because the right one is often a phrase ("prompt
injection") that no pattern finds. The rules keep it honest: the name has to be
written in the lesson's own title or topics, it cannot be a word every AI job
post carries, and its count is Hacker News' own. With no model, or no name that
passes, the demand is unmeasured and the lesson is watched, never promoted.

Lesson titles are the reviewers' words about the course, so the result is kept
beside the review, in fixtures/lesson_demand.json, which git ignores.
"""
import argparse
import json
import re
from datetime import date
from pathlib import Path

from src import arabic, concepts, trace
from src.adapters import model
from src.notebooks import NOTEBOOK_DIR
from src.sources import market

DEMAND_PATH = Path("fixtures/lesson_demand.json")
MONTHS = 3
TERMS_PER_LESSON = 3
RUNS = 5

# Words nearly every AI job post carries. Counting them would measure the field,
# not the lesson.
GENERIC = {
    "ai", "llm", "llms", "api", "apis", "python", "agent", "agents", "agentic", "model", "models",
    "evaluation", "evaluations", "eval", "evals", "rag", "ml", "machine learning", "genai", "openai",
    "data", "cloud", "sql", "json", "ci", "sdk", "testing", "production", "memory", "tools", "tool",
}

PICK_SYSTEM = (
    "You choose search terms for counting job posts. For each proposed lesson, give up to "
    f"{TERMS_PER_LESSON} names an employer would write in a job post for the new thing this lesson "
    "teaches: a product, protocol, standard or technique, such as MCP, OpenTelemetry or prompt "
    "injection. Pick the plain words a job post uses (prompt injection, not OWASP LLM01), never a "
    "class, function or code name, and never a library the lesson only builds on. Copy each name "
    "exactly as it is written in the lesson's title or topics, one to three words. Never a generic "
    "word such as LLM, AI, agent, API, Python, RAG or evaluation. "
    'Answer as JSON: {"terms": {"<lesson number>": ["name", ...]}}.'
)

# Code, not a name anyone writes in a job post: gen_ai.* spans, recall@k, st.secrets.
CODE_RE = re.compile(r"[_.*@()/=<>\[\]{}]")


def proposals(material: dict, copies: set[str]) -> list[dict]:
    """Each proposed lesson once, from the notebook that proposed it. A copy's
    proposal is its original's, so it is not counted twice."""
    found = []

    for entry in material["notebooks"]:
        lesson = entry.get("new_lesson")

        if lesson and entry["notebook"] not in copies:
            found.append({"notebook": entry["notebook"], "id": entry["id"], "title": lesson["title"],
                          "covers": list(lesson.get("covers", []))})

    return found


def lesson_text(lesson: dict) -> str:
    return " \n".join([lesson["title"], *lesson["covers"]])


def valid(term: str, lesson: dict) -> bool:
    """A name the lesson itself uses, short enough to be a name, and not a word
    that would match every AI job post.

    One word in lower case is an ordinary word, and counts noise: "retention" found
    9 posts, about keeping customers and users, none about agent memory. A name has a
    capital or a digit (MCP, OpenTelemetry, LoRA), or is a phrase searched whole
    (prompt injection)."""
    term = term.strip()

    if not 2 <= len(term) <= 40 or len(term.split()) > 3 or term.lower() in GENERIC or CODE_RE.search(term):
        return False

    if " " not in term and term == term.lower() and not any(character.isdigit() for character in term):
        return False

    return named_in(term, lesson_text(lesson))


def offered_terms(answer, number: int, lesson: dict) -> list[str]:
    """What one answer offered for one lesson, keeping only names that pass the rules."""
    terms = answer.get("terms") if isinstance(answer, dict) else None
    offered = (terms or {}).get(str(number)) or []
    kept = []

    for term in offered if isinstance(offered, list) else []:
        if isinstance(term, str) and valid(term, lesson) and term.strip().lower() not in {k.lower() for k in kept}:
            kept.append(term.strip())

    return kept[:TERMS_PER_LESSON]


def pick_terms(lessons: list[dict], ask=None,
               runs: int = RUNS) -> tuple[dict[str, list[str]], dict[str, list[list[str]]]]:
    """The names to count for each lesson, asked `runs` times. A name counts only when
    the model gives it every time: pass^k, not pass@k. Asked once each, one run named
    Streamlit and the next "Streamlit chat app", and the lesson's decision flipped
    between them. A name the model does not repeat is its choice of the moment, not
    the lesson's subject. A run that fails to answer holds nothing, so nothing holds.
    Returns the names that held, and what each run offered."""
    ask = ask or (lambda system, user: model.ask_json(system, user, max_tokens=900, timeout=60,
                                                      action="pick_lesson_terms"))
    listed = "\n\n".join(f"Lesson {number}: {lesson['title']}\nTopics: " + "; ".join(lesson["covers"])
                         for number, lesson in enumerate(lessons, start=1))
    answers = [ask(PICK_SYSTEM, listed) for _ in range(runs)]
    picked, offered = {}, {}

    for number, lesson in enumerate(lessons, start=1):
        each = [offered_terms(answer, number, lesson) for answer in answers]
        offered[lesson["notebook"]] = each
        picked[lesson["notebook"]] = [term for term in (each[0] if each else [])
                                      if all(term.lower() in {other.lower() for other in run} for run in each[1:])]

    return picked, offered


def taught(term: str, texts: list[str]) -> int:
    """Notebooks that already name the term anywhere, prose or code."""
    pattern = re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])", re.I)
    return sum(1 for text in texts if pattern.search(text))


def decide(jobs: int | None, mentioned: int) -> str:
    """The same rule as a concept: enough job posts and nothing in the course makes a
    new lesson; a few makes optional content. A lesson on something the course
    already names deepens it, so it is optional content at most."""
    if not jobs:
        return "watch"

    if mentioned:
        return "add_optional_content"

    return "add_new_lesson" if jobs >= concepts.LESSON_JOBS else "add_optional_content"


def named_in(term: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, re.I) is not None


def settle(terms: list[dict], title: str = "") -> dict:
    """Which counted name speaks for the lesson, and what that decides. A name the
    course does not teach yet speaks for what the lesson adds. One it already
    teaches speaks only when the lesson offered nothing new and the name is its
    subject, in its title: a Streamlit lesson is about Streamlit, but 17 posts
    naming LangChain are demand for what the course has, not for a multi-agent
    lesson that happens to build on it. Run when the page is built, from the saved
    counts, so a rule can change without asking the model or Hacker News again."""
    new = [item for item in terms if item["notebooks"] == 0]
    pool = new or [item for item in terms if named_in(item["term"], title)]
    best = max(pool, key=lambda item: (item["jobs"] or 0, -item["notebooks"]), default=None)
    jobs = best["jobs"] if best else None
    mentioned = best["notebooks"] if best else 0

    return {"term": best["term"] if best else None, "jobs": jobs, "mentioned": mentioned,
            "act": decide(jobs, mentioned)}


def measure(lessons: list[dict], picked: dict[str, list[str]], count_jobs, texts: list[str],
            offered: dict[str, list[list[str]]] | None = None) -> list[dict]:
    found = []

    for lesson in lessons:
        tries = (offered or {}).get(lesson["notebook"], [])
        terms = [{"term": term, "jobs": count_jobs(term), "notebooks": taught(term, texts)}
                 for term in picked.get(lesson["notebook"], [])]
        found.append({**lesson, "terms": terms, "offered": tries, "unstable": not terms and any(tries),
                      **settle(terms, lesson["title"])})

    return found


def why(lesson: dict, months: int = MONTHS, runs: int = RUNS) -> tuple[str, str]:
    term, jobs, mentioned, act = lesson["term"], lesson["jobs"], lesson["mentioned"], lesson["act"]

    if term is None and lesson.get("unstable"):
        return (f"The model was asked {runs} times and no name came back every time, so demand is "
                "not measured and the lesson is watched.", arabic.lesson_unstable(runs))

    if term is None:
        return ("Demand not measured: no name in the proposal passed the rules, so it is watched, "
                "not promoted.", arabic.lesson_unmeasured())

    posts = f"{jobs} job post{'s' if jobs != 1 else ''} named {term} in the last {months} months"

    if not jobs:
        english = f"No job post named {term} in the last {months} months, so it is watched."
    elif mentioned:
        english = (f"{posts}, but {mentioned} notebook{'s' if mentioned != 1 else ''} already "
                   f"name{'s' if mentioned == 1 else ''} it: a deeper lesson on something the course "
                   "touches, so optional content.")
    elif act == "add_new_lesson":
        english = f"{posts}, and no notebook names it: a new lesson."
    else:
        english = f"{posts}, and no notebook names it: optional content until more employers ask."

    return english, arabic.lesson_demand(term, jobs, months, mentioned, act)


def answered_by(action: str) -> str | None:
    """The provider and model that answered, from the trace, not the chain that was tried."""
    answered = [step.action.split("@", 1)[1] for step in trace.current.steps
                if step.ok and step.action.startswith(f"{action}@")]

    if not answered:
        return None

    chain = dict(entry.split(":", 1) for entry in model.describe().split(", ") if ":" in entry)
    return ", ".join(f"{name}:{chain.get(name, '')}".rstrip(":") for name in dict.fromkeys(answered))


def main() -> None:
    parser = argparse.ArgumentParser(description="Count job posts for the lessons the review proposed.")
    parser.add_argument("--notebooks", default=str(NOTEBOOK_DIR))
    args = parser.parse_args()

    from src import review

    material = review.load()

    if material is None:
        raise SystemExit(f"no review at {review.REVIEW_PATH}")

    curriculum = json.loads(review.CURRICULUM_PATH.read_text(encoding="utf-8"))
    lessons = proposals(material, {copy["notebook"] for copy in curriculum.get("copies", [])})
    picked, offered = pick_terms(lessons)
    texts = [concepts.notebook_text(json.loads(path.read_text(encoding="utf-8")))
             for path in sorted(Path(args.notebooks).rglob("*.ipynb"))]
    threads = [thread["id"] for thread in market.hiring_threads(MONTHS)]
    counts: dict[str, int] = {}

    def count_jobs(term: str) -> int:
        if term.lower() not in counts:
            counts[term.lower()] = market.job_posts(term, threads)
        return counts[term.lower()]

    measured = measure(lessons, picked, count_jobs, texts, offered)
    held = sum(1 for lesson in measured if lesson["terms"])
    DEMAND_PATH.write_text(json.dumps({
        "checked_on": date.today().isoformat(), "months": MONTHS, "threads": threads,
        "picked_by": answered_by("pick_lesson_terms"), "runs": RUNS, "held": held,
        "lessons": measured,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"pass^{RUNS}: a name held in all {RUNS} runs for {held} of {len(measured)} lessons")

    for lesson in sorted(measured, key=lambda item: (item["act"], -(item["jobs"] or 0))):
        print(f"{lesson['act']:<22} {str(lesson['jobs']):>4}  {lesson['term'] or '-':<24} {lesson['title'][:60]}")


if __name__ == "__main__":
    main()
