"""The lesson to teach instead, written rather than named.

The reviewer says what a notebook teaches and what the field has done since. That is
half an answer. A course owner reading "create_react_agent was superseded" still has to
decide what the class does on that morning instead, and the review as it stands leaves
every one of those decisions on their desk.

So this writes the lesson: a title, why the course needs it, and what it covers. It is
the piece the product was named for, and it is the piece a rule cannot do, because the
right lesson is not a lookup from the finding. It depends on what the course already
teaches, what the field publishes now, and which of the findings are one idea a student
should meet once rather than four edits in four notebooks.

Three rules stand under it:

  1. It must answer findings the reviewer actually located in that notebook. A lesson
     about something nobody found wanting is a lesson about nothing.
  2. It must name the thing it adds, by the same rule src/lessons.py uses to decide a
     name is measurable: written in its own title or in what it covers, short enough to
     be a name, and not a word every AI job post carries. That is not a second opinion
     about names, it is the same one, so a proposal that passes here can be counted in
     the hiring threads later instead of being dropped there.
  3. The course must not already teach it. That is counted here, in the notebooks, not
     taken from the agent: a name the course uses in several notebooks is not new, and
     proposing it as new is how a review starts inventing work.

What survives is a proposal and nothing more. src/lessons.py then measures whether
employers ask for it, and the rules there decide whether it is a lesson to add, optional
content, or something to watch. An agent writes; the rules still decide.
"""

import json
import re
from pathlib import Path

from src import concepts, lessons, trace
from src.adapters import model
from src.agents import citations
from src.notebooks import NOTEBOOK_DIR

MAX_STEPS = 4
MAX_TOOL_CHARS = 1800
MAX_COVERS = 6
MIN_COVERS = 2
# A name the course already uses this widely is part of the course, whatever the
# proposal calls it. One or two mentions is a passing reference, not a lesson.
ALREADY_TAUGHT = 3

SYSTEM = (
    "You write a lesson for a bootcamp that trains people to build AI agents. You are given "
    "one notebook, what it teaches, and what a reviewer found has moved on since it was "
    "written. Decide what the class should do instead, and write that lesson. "
    "Answer with one JSON object and nothing else, either "
    '{"tool": <name>, "args": {...}} to look, or, when you are ready, '
    '{"answer": {"title": <one line>, "term": <the name of the thing it adds>, '
    '"why": <two or three sentences on why the course needs it>, '
    '"covers": [<three to six things a student does in it>], '
    '"answers": [<the techniques from the findings this lesson settles>]}}. '
    "Write the lesson the findings ask for, not a lesson you would like to teach: every "
    "technique in answers must be one of the findings you were given. Check that the course "
    "does not already teach it before you propose it, and check that the field is actually "
    "doing it. One lesson that settles several findings is better than one per finding. "
    "Choose the term before you write the title, then write the title around it. The term is "
    "what an employer would write in a job post, at most three words, and your title or one of "
    "your covers lines must contain it letter for letter, because it is searched for in hiring "
    "threads afterwards. A title that merely gestures at the term is thrown away: if you cannot "
    "write a natural title containing your term word for word, the term is the wrong one, so "
    "pick the name an employer would actually write and build the title on that. "
    "If the findings do not add up to a lesson, answer with answers empty and say so in why."
)

TOOL_HELP = ("findings(): what the reviewer found about this notebook.\n"
             "course_uses(term): the notebooks of the course that already use a name.\n"
             "papers(term): how much the field has published on a name recently.")


def flat(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def named(kwargs: dict) -> str:
    """The one thing it named, whatever it called the parameter."""
    for value in kwargs.values():
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def findings_tool(entry: dict):
    """What the reviewer said about this notebook, in the words it said it in."""
    def findings(**_kwargs) -> str:
        lines = [f"{claim['technique']} (cell {claim['cell']}): {claim['as_taught']}"
                 for claim in entry.get("teaches") or []]
        lines += [f"{item['technique']} is {item['status']}: {item['why1']} "
                  f"Instead: {item['instead'] or 'nothing named'}"
                  for item in entry.get("findings") or []]
        return " || ".join(lines) or "the reviewer found nothing about this notebook"

    return findings


def taught_in(term: str, root: Path | None = None) -> int:
    """How many of the course's notebooks name a term, counted here rather than asked.

    It is counted by the rule src/lessons.py measures demand with: the whole name, any
    case, in the cells a student reads or runs. So a lesson this lets through is one the
    demand count will not call taught, and the other way round.

    Stored outputs do not count. Searching the raw file found MCP in five notebooks, every
    time inside an embedded image, and would have refused the MCP lesson as one the
    course already runs, when no notebook mentions it.
    """
    if len(flat(term)) < 3:
        return 0

    texts = []

    for path in sorted(Path(root or NOTEBOOK_DIR).glob("*/*.ipynb")):
        try:
            texts.append(concepts.notebook_text(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue

    return lessons.taught(term, texts)


def tools_for(entry: dict, course_uses=None, papers=None) -> dict:
    kit = {"findings": findings_tool(entry)}
    kit["course_uses"] = (lambda **kwargs: course_uses(named(kwargs))) if course_uses else (
        lambda **kwargs: "the course was not searched on this run")
    kit["papers"] = (lambda **kwargs: papers(named(kwargs))) if papers else (
        lambda **kwargs: "research was not checked on this run")
    return kit


def turn(entry: dict, seen: list[dict], complaint: str = "", left: int = MAX_STEPS) -> str:
    moved = [item for item in entry.get("findings") or [] if item["status"] != "current"]
    lines = [f"Notebook: {entry['title']} ({entry['week']})",
             f"It teaches: {', '.join(claim['technique'] for claim in entry.get('teaches') or []) or 'nothing located'}",
             f"The reviewer found {len(moved)} of those have moved on: "
             f"{', '.join(item['technique'] for item in moved) or 'none'}",
             "", "Tools:", TOOL_HELP, ""]

    if seen:
        lines.append("What you have read so far:")

        for step in seen:
            lines.append(f"- {step['tool']}({json.dumps(step['args'], ensure_ascii=False)}): {step['text']}")
    else:
        lines.append("You have read nothing yet. Start with the findings.")

    # A rewrite has no tool calls, so it must not be told it has four.
    lines += ["", f"You have {left} tool calls left, then you must answer." if left > 0
              else "You have no tool calls left. Answer now."]

    if complaint:
        lines += ["", "Your last answer was thrown away:", complaint,
                  "Write it again, fixing that. Do not start over: keep what was right."]

    return "\n".join(lines)


def run(entry: dict, tools: dict, ask=None, max_steps: int = MAX_STEPS,
        complaint: str = "", seen: list[dict] | None = None) -> dict | None:
    ask = ask or (lambda system, user: model.ask_json(system, user, max_tokens=900, timeout=90,
                                                      action="lesson_agent"))
    seen = list(seen or [])

    for step in range(max_steps + 1):
        answer = ask(SYSTEM, turn(entry, seen, complaint, max_steps - step))

        if not isinstance(answer, dict) or not answer:
            return None

        if "answer" in answer:
            proposal = answer.get("answer")
            return {"proposal": proposal if isinstance(proposal, dict) else {}, "seen": seen}

        if step == max_steps:
            # Its last turn was for answering, and it looked again instead.
            break

        name = answer.get("tool")
        tool = tools.get(name) if isinstance(name, str) else None

        if tool is None:
            seen.append(citations.note(name, {}, "no such tool"))
            continue

        args = answer.get("args") if isinstance(answer.get("args"), dict) else {}
        again = next((step for step in seen if step["tool"] == name and step["args"] == args), None)

        if again is not None:
            seen.append(citations.note(name, args, "you already called this and it said the same thing. "
                                                   "Call something else, or answer."))
            continue

        try:
            result = tool(**args)
        except TypeError:
            seen.append(citations.note(name, args, "wrong arguments for this tool"))
            continue

        seen.append(citations.step(name, args, result, MAX_TOOL_CHARS))

    return None


def read_proposal(proposal: dict, entry: dict) -> dict:
    """The proposal trimmed to what travels, with its answers matched to real findings."""
    moved = [item["technique"] for item in entry.get("findings") or [] if item["status"] != "current"]
    answers = []

    given = (proposal or {}).get("answers")
    # One answer written as text is one answer, not a list of its letters.
    given = [given] if isinstance(given, str) else given if isinstance(given, list) else []

    for said in given:
        if not isinstance(said, str):
            continue

        # It names the finding in its own words ("tf-idf vectorization is superseded"),
        # so match on the technique inside what it said and keep the reviewer's spelling,
        # which is what the page and the counts are keyed on. The other way round, what it
        # said has to be most of the technique's name: "e" is inside "ReAct agent" too.
        found = next((name for name in moved if flat(name) in flat(said)
                      or (len(flat(said)) >= max(4, len(flat(name)) / 2) and flat(said) in flat(name))), None)

        if found and found not in answers:
            answers.append(found)

    return {
        "moved": moved,
        "title": str((proposal or {}).get("title") or "").strip()[:140],
        "term": str((proposal or {}).get("term") or "").strip()[:60],
        "why": str((proposal or {}).get("why") or "").strip()[:600],
        "covers": [str(item).strip()[:200] for item in ((proposal or {}).get("covers") or [])
                   if isinstance(item, str) and item.strip()][:MAX_COVERS],
        "answers": answers,
    }


def faults(clean: dict, count=taught_in) -> list[str]:
    """What is wrong with a proposal, said the way it would be said to its author.

    These are the rules. Putting them in words costs nothing and means a proposal that
    broke one can be told which, instead of being dropped for a reason only the code knows.
    """
    said = []

    if not clean["title"] or not clean["why"] or len(clean["covers"]) < MIN_COVERS:
        said.append(f"A lesson needs a title, a why, and at least {MIN_COVERS} things a student does in it.")

    if not clean["answers"]:
        # A lesson about something nobody found wanting is a lesson about nothing.
        # Naming the choices is the difference between a complaint and a shrug: the first
        # rewrite failed twice on this, repeating itself word for word both times.
        listed = ", ".join(f'"{name}"' for name in clean.get("moved") or []) or "none, so propose nothing"
        said.append(f"None of your answers matches a finding you were given. Copy them from this "
                    f"list exactly as written: {listed}.")

    if not clean["term"]:
        said.append("You did not say what the lesson adds. Give a term of at most three words.")
    elif reason := lessons.why_not(clean["term"], {"title": clean["title"], "covers": clean["covers"]}):
        # The rule that decides a name is measurable lives in src/lessons.py, and so do its
        # words: a proposal it would drop later is dropped here, told which test it failed.
        said.append(f'Your term "{clean["term"]}" {reason}. It is searched for in hiring threads, so '
                    f"it has to be a name an employer writes, at most three words, in your title or a "
                    f'covers line. Your title is "{clean["title"]}".')
    elif count(clean["term"]) >= ALREADY_TAUGHT:
        # The course already runs this, whatever the proposal calls it.
        said.append(f'The course already teaches "{clean["term"]}" in {count(clean["term"])} of its '
                    f"notebooks, so this is not a new lesson. Propose what it does not teach, or nothing.")

    return said


def check(gathered: dict, entry: dict, count=taught_in) -> dict | None:
    """The three rules: it answers findings, it says what it is called measurably, and the
    course does not already teach it."""
    clean = read_proposal((gathered or {}).get("proposal") or {}, entry)

    if faults(clean, count):
        return None

    return {**{key: value for key, value in clean.items() if key != "moved"},
            "already_in": count(clean["term"]),
            "looked": [{"tool": step["tool"], "args": step.get("args", {})} for step in gathered["seen"]]}


def propose(entry: dict, tools: dict, ask=None, max_steps: int = MAX_STEPS, count=taught_in) -> dict | None:
    """The lesson this notebook's findings ask for, or None when they do not ask for one."""
    if not any(item["status"] != "current" for item in entry.get("findings") or []):
        return None

    gathered = run(entry, tools, ask=ask, max_steps=max_steps)
    written = check(gathered, entry, count=count) if gathered else None

    raw = (gathered or {}).get("proposal") or {}
    # Declining is an answer the prompt offers: no answers and nothing a student does,
    # only why. It is not a broken rule to be sent back.
    declined = not raw.get("answers") and not raw.get("covers")

    if written is None and gathered and not declined:
        # A rule that can say what is wrong should say it. One rewrite, with what it
        # already read still in front of it, and the same rules on the way back.
        said = faults(read_proposal(gathered.get("proposal") or {}, entry), count)

        if said:
            again = run(entry, tools, ask=ask, max_steps=0, complaint=" ".join(said),
                        seen=gathered["seen"])
            written = check(again, entry, count=count) if again else None
            trace.current.record("lesson_revise", 0, ok=written is not None,
                                 note=f"{entry['title']}: {said[0][:80]}")

    trace.current.record("lesson_agent", 0, ok=written is not None, note=(
        f"{entry['title']}: {written['title'] if written else 'no lesson its findings asked for'}"))
    return written
