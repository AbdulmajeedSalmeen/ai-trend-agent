"""Where in the course a change belongs, when no rule can tell.

The rules place a trend by overlap: a chapter that names the package, or installs it,
or shares three words with what was said about it. That is right most of the time and
silent the rest. Four of thirty-six trends on the last run landed nowhere, and every
lesson the lesson agent writes lands nowhere by construction, because a lesson that
does not exist yet is in no chapter's topic list.

Nowhere is sometimes the true answer. anthropic-sdk-python is not in this course, and
saying it belongs in the LangChain chapter because both mention models would be worse
than saying nothing. But "no chapter owns this" is not the end of the question a course
owner is asking, which is where it would go, and after what.

So this reads the chapters and answers in two parts: which chapter owns it, if one
does, and which chapter it follows, if none does. A thing that follows C8 is taught in
week 3 or later, whatever else is decided about it.

Three rules stand under it:

  1. Every chapter it names must be a chapter. An id that is not in the curriculum is
     not a placement, it is a typo with an opinion attached.
  2. The line it quotes must be in what a tool returned.
  3. "This chapter owns it" is checked here, not taken: the chapter's own topics, tools
     or pins have to carry the name. A chapter that has never heard of the thing does
     not own it, and the claim is lowered to following that chapter instead, which is
     what it actually established.
"""

import json
import re

from src import trace
from src.adapters import model

MAX_STEPS = 4
MAX_TOOL_CHARS = 2000
RELATIONS = ("owns", "follows")

SYSTEM = (
    "You decide where in a course a change belongs. You are given the chapters of the "
    "course, in order, and one thing to place: a package that changed, or a lesson somebody "
    "proposes adding. "
    "Answer with one JSON object and nothing else, either "
    '{"tool": <name>, "args": {...}} to look, or, when you are ready, '
    '{"answer": {"relation": "owns"|"follows", "chapter": <the chapter id>, '
    '"why": <one sentence>, "quote": <a line copied from what a tool returned>}}. '
    'Say "owns" when a chapter already teaches this and the change lands inside it, and give '
    "that chapter. Say \"follows\" when no chapter teaches it, and give the chapter it would "
    "come after: the last one whose material a student needs before this makes sense. Most "
    'things a course does not teach are "follows", and saying so is a real answer. Name a '
    "chapter by its id, and quote the line you read that put it there."
)

TOOL_HELP = ("chapters(): every chapter, in order, with what it teaches.\n"
             "chapter(id): one chapter in full, with its topics, tools and prerequisites.\n"
             "course_uses(term): the notebooks of the course that already use a name.")


def flat(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def named(kwargs: dict) -> str:
    """The one thing it named, whatever it called the parameter."""
    for value in kwargs.values():
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def vocabulary(chapter: dict) -> set[str]:
    """The words a chapter itself uses for what it covers, which is what owning means."""
    text = " ".join([chapter.get("title", ""), chapter.get("teaches", "")]
                    + list(chapter.get("topics_covered") or [])
                    + list(chapter.get("tools_covered") or []))
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def carries(chapter: dict, subject: str) -> bool:
    """Whether this chapter's own words or its installs carry the name.

    This is the check under "owns", and it is deliberately the chapter's word and not
    the agent's: a chapter that has never named the thing does not own it, however
    reasonable the argument sounds.
    """
    if subject in (chapter.get("pins") or {}) or subject in (chapter.get("installs_unpinned") or []):
        return True

    words = set(re.findall(r"[a-z0-9]+", str(subject or "").lower()))
    return bool(words) and words <= vocabulary(chapter)


def chapters_tool(chapters: list[dict]):
    def listing(**_kwargs) -> str:
        return " || ".join(f"{c['chapter_id']} (week {c.get('week')}): {c.get('title', '')}. "
                           f"{c.get('teaches', '')}" for c in chapters)

    return listing


def chapter_tool(chapters: list[dict]):
    by_id = {c["chapter_id"]: c for c in chapters}

    def one(**kwargs) -> str:
        chapter = by_id.get(named(kwargs).upper())

        if chapter is None:
            return f"no chapter {named(kwargs)}; the chapters are {', '.join(by_id)}"

        return (f"{chapter['chapter_id']} (week {chapter.get('week')}): {chapter.get('title', '')}. "
                f"Teaches: {chapter.get('teaches', '')} "
                f"Topics: {', '.join(chapter.get('topics_covered') or []) or 'none listed'}. "
                f"Tools: {', '.join(chapter.get('tools_covered') or []) or 'none listed'}. "
                f"Needs first: {', '.join(chapter.get('prerequisites') or []) or 'nothing'}. "
                f"Installs: {', '.join(sorted(chapter.get('pins') or {})) or 'nothing pinned'}.")

    return one


def tools_for(chapters: list[dict], course_uses=None) -> dict:
    return {
        "chapters": chapters_tool(chapters),
        "chapter": chapter_tool(chapters),
        "course_uses": (lambda **kwargs: course_uses(named(kwargs))) if course_uses else (
            lambda **kwargs: "the course was not searched on this run"),
    }


def turn(subject: str, about: str, chapters: list[dict], seen: list[dict],
         left: int = MAX_STEPS) -> str:
    lines = [f"To place: {subject}", f"What is known about it: {about[:600]}",
             f"The course has {len(chapters)} chapters over "
             f"{max((c.get('week') or 0) for c in chapters) if chapters else 0} weeks.",
             "", "Tools:", TOOL_HELP, ""]

    if seen:
        lines.append("What you have read so far:")

        for step in seen:
            lines.append(f"- {step['tool']}({json.dumps(step['args'], ensure_ascii=False)}): {step['text']}")
    else:
        lines.append("You have read nothing yet. Start with the chapters.")

    # A loop that runs out of turns while still looking has spent a whole call on
    # nothing. It is told when it is on its last one.
    lines += ["", (f"You have {left} tool calls left." if left > 0
                   else "You have no tool calls left. Answer now, with what you have.")]
    return "\n".join(lines)


def run(subject: str, about: str, chapters: list[dict], tools: dict, ask=None,
        max_steps: int = MAX_STEPS) -> dict | None:
    ask = ask or (lambda system, user: model.ask_json(system, user, max_tokens=500, timeout=60,
                                                      action="placement_agent"))
    seen: list[dict] = []

    for step in range(max_steps + 1):
        answer = ask(SYSTEM, turn(subject, about, chapters, seen, max_steps - step))

        if not answer:
            return None

        if "answer" in answer:
            proposal = answer.get("answer")
            return {"proposal": proposal if isinstance(proposal, dict) else {}, "seen": seen}

        name = answer.get("tool")
        tool = tools.get(name) if isinstance(name, str) else None

        if tool is None:
            seen.append({"tool": str(name), "args": {}, "text": "no such tool"})
            continue

        args = answer.get("args") if isinstance(answer.get("args"), dict) else {}
        again = next((step for step in seen if step["tool"] == name and step["args"] == args), None)

        if again is not None:
            seen.append({"tool": name, "args": args,
                         "text": "you already called this and it said the same thing. "
                                 "Call something else, or answer."})
            continue

        try:
            result = tool(**args)
        except TypeError:
            seen.append({"tool": name, "args": args, "text": "wrong arguments for this tool"})
            continue

        seen.append({"tool": name, "args": args, "text": flat(result)[:MAX_TOOL_CHARS] or "nothing found"})

    return None


def check(gathered: dict, subject: str, chapters: list[dict]) -> dict | None:
    """The three rules: a chapter that exists, a line it read, and owning that is earned."""
    proposal = (gathered or {}).get("proposal") or {}
    by_id = {c["chapter_id"]: c for c in chapters}
    chapter_id = str(proposal.get("chapter") or "").strip().upper()
    relation = str(proposal.get("relation") or "").strip().lower()

    if chapter_id not in by_id or relation not in RELATIONS:
        return None

    returned = " ".join(step["text"] for step in (gathered or {}).get("seen") or [])
    quote = flat(proposal.get("quote"))

    if len(quote) < 8 or quote not in returned:
        return None

    chapter = by_id[chapter_id]
    owned = carries(chapter, subject)

    if relation == "owns" and not owned:
        # It argued a chapter owns something the chapter has never named. What it did
        # establish is where the thing sits in the order, so that is what it keeps.
        relation = "follows"

    return {"relation": relation, "chapter": chapter_id, "week": chapter.get("week"),
            "owned": owned, "why": str(proposal.get("why") or "")[:240],
            "quote": str(proposal.get("quote"))[:220],
            "looked": [{"tool": step["tool"], "args": step.get("args", {})} for step in gathered["seen"]]}


def place(subject: str, about: str, chapters: list[dict], tools: dict | None = None, ask=None,
          max_steps: int = MAX_STEPS) -> dict | None:
    """Which chapter owns this, or which one it follows, or None when it cannot say."""
    if not chapters:
        return None

    gathered = run(subject, about, chapters, tools if tools is not None else tools_for(chapters),
                   ask=ask, max_steps=max_steps)
    found = check(gathered, subject, chapters) if gathered else None

    trace.current.record("placement_agent", 0, ok=found is not None, note=(
        f"{subject}: {found['relation'] + ' ' + found['chapter'] if found else 'nowhere it could point at'}"))
    return found
