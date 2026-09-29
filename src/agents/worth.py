"""What a change to the material is worth, and what it costs.

The package side has a judge: it looks at what moved, what the course uses, what
employers ask for, and scores how much the change is worth teaching. A quarter of every
package's priority is that number. The material side has had nothing of the kind.

What decided a notebook's fate instead was the severity of a status. Any finding that
says removed, deprecated, superseded or unsafe produced "replace", anything else
"revise", nothing "keep". So a one-line import that moved and a credential pattern a
student will copy into their own code came out the same, and the effort beside each of
the eighty-nine entries was the word "medium", written once, in the driver, for all of
them.

Severity is not worth. A deprecated helper with a drop-in replacement is an afternoon
nobody needs to think about; the same status on a technique six notebooks teach is a
decision about the course. Nothing was asking which of those it was looking at.

So this asks. It reads the reviewer's findings, searches the course for how far the
technique reaches, and can check whether the field has actually moved, then says how
much a teacher should care and how much work it is.

Two rules stand under it, the same two the package judge lives by:

  1. Every line it cites is looked for in what the tools actually returned. A citation
     nothing supports is dropped.
  2. A score with no surviving citation is not a score, and the rules answer instead,
     as they did before this existed.

The effort it gives replaces the constant. The worth is recorded beside it: the page
still orders by verdict, and the number is there for the day it orders by more.
"""

import json
import re

from src import trace
from src.adapters import model

MAX_STEPS = 3
MAX_TOOL_CHARS = 1800
EFFORTS = ("small", "medium", "large")
SCALE = range(1, 6)

SYSTEM = (
    "You decide how much a change to a bootcamp's teaching material is worth, and how much "
    "work it is. You are given one notebook, what a reviewer found about what it teaches, and "
    "tools to check how far each technique reaches through the course. "
    "Answer with one JSON object and nothing else, either "
    '{"tool": <name>, "args": {...}} to look, or, when you are ready, '
    '{"answer": {"worth": <1 to 5>, "effort": "small"|"medium"|"large", '
    '"reason": <one or two sentences>, '
    '"cites": [{"factor": <what it supports>, "tool": <which tool>, '
    '"quote": <text copied from what that tool returned>}]}}. '
    "Worth is what a teacher loses by leaving it alone, not how severe the label is. A helper "
    "that moved and has a drop in replacement is worth little however it is labelled; something "
    "a student will carry into their own code, or a method several notebooks teach, is worth a "
    "great deal. Effort is the work to change it: one line is small, rewriting a notebook's "
    "approach is large. Look before you answer, and quote what you read: a reason nothing "
    "supports is thrown away and the rules decide instead. "
    "Search the course for the name as it is written in code, like create_react_agent or "
    "TfidfVectorizer, not for the label you gave the technique: a notebook contains the one "
    "and never the other."
)

TOOL_HELP = ("findings(): what the reviewer found about this notebook.\n"
             "course_uses(term): the notebooks of the course that already use a name.\n"
             "papers(term): how much the field has published on a name recently.")


def flat(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def tool_name(said) -> str:
    """The tool it meant, with the brackets it wrote it with taken off.

    A model that credits a line to "findings()" has named the tool that returned it, and
    a lookup that misses on the punctuation drops a citation that was good.
    """
    return re.sub(r"[^a-z0-9_]", "", str(said or "").lower())


def named(kwargs: dict) -> str:
    """The one thing it named, whatever it called the parameter."""
    for value in kwargs.values():
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def turn(entry: dict, seen: list[dict], left: int = MAX_STEPS) -> str:
    moved = [item for item in entry.get("findings") or [] if item["status"] != "current"]
    lines = [f"Notebook: {entry.get('title')} ({entry.get('week')})",
             f"It teaches: {', '.join(claim['technique'] for claim in entry.get('teaches') or []) or 'nothing located'}",
             f"The reviewer found these have moved on: "
             f"{', '.join(f'{item['technique']} ({item['status']})' for item in moved) or 'none'}",
             "", "Tools:", TOOL_HELP, ""]

    if seen:
        lines.append("What you have read so far:")

        for step in seen:
            lines.append(f"- {step['tool']}({json.dumps(step['args'], ensure_ascii=False)}): {step['text']}")
    else:
        lines.append("You have read nothing yet. Start with the findings.")

    lines += ["", (f"You have {left} tool calls left." if left > 0
                   else "You have no tool calls left. Answer now, with what you have.")]
    return "\n".join(lines)


def run(entry: dict, tools: dict, ask=None, max_steps: int = MAX_STEPS) -> dict | None:
    ask = ask or (lambda system, user: model.ask_json(system, user, max_tokens=600, timeout=60,
                                                      action="worth_agent"))
    seen: list[dict] = []

    for step in range(max_steps + 1):
        answer = ask(SYSTEM, turn(entry, seen, max_steps - step))

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
        again = next((item for item in seen if item["tool"] == name and item["args"] == args), None)

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


def check(gathered: dict) -> dict | None:
    """Keep the citations the tools support, and refuse a score left standing on none."""
    proposal = (gathered or {}).get("proposal") or {}
    returned = {tool_name(step["tool"]): step["text"] for step in (gathered or {}).get("seen") or []}

    try:
        score = int(proposal.get("worth"))
    except (TypeError, ValueError):
        return None

    if score not in SCALE:
        return None

    effort = str(proposal.get("effort") or "").strip().lower()

    if effort not in EFFORTS:
        return None

    kept, dropped = [], 0

    for cite in proposal.get("cites") or []:
        if not isinstance(cite, dict):
            dropped += 1
            continue

        tool = tool_name(cite.get("tool"))
        quote = flat(cite.get("quote"))

        if len(quote) < 6 or quote not in returned.get(tool, ""):
            # It cited a line that tool never returned, so the line is not evidence.
            dropped += 1
            continue

        kept.append({"factor": str(cite.get("factor") or "")[:90], "tool": tool,
                     "quote": str(cite.get("quote"))[:200]})

    if not kept:
        # A score with nothing left under it is not a score.
        return None

    return {"worth": score, "effort": effort, "reason": str(proposal.get("reason") or "")[:300],
            "cites": kept, "dropped": dropped,
            "looked": [{"tool": step["tool"], "args": step.get("args", {})} for step in gathered["seen"]]}


def tools_for(findings, course_uses=None, papers=None) -> dict:
    return {
        "findings": findings,
        "course_uses": (lambda **kwargs: course_uses(named(kwargs))) if course_uses else (
            lambda **kwargs: "the course was not searched on this run"),
        "papers": (lambda **kwargs: papers(named(kwargs))) if papers else (
            lambda **kwargs: "research was not checked on this run"),
    }


def judge(entry: dict, tools: dict, ask=None, max_steps: int = MAX_STEPS) -> dict | None:
    """What this notebook's findings are worth to a teacher, or None when it cannot say."""
    if not any(item["status"] != "current" for item in entry.get("findings") or []):
        # Nothing has moved, so there is nothing to weigh. The rules already say keep.
        return None

    gathered = run(entry, tools, ask=ask, max_steps=max_steps)
    weighed = check(gathered) if gathered else None

    trace.current.record("worth_agent", 0, ok=weighed is not None, note=(
        f"{entry.get('title')}: "
        f"{str(weighed['worth']) + '/5, ' + weighed['effort'] if weighed else 'nothing it could stand behind'}"))
    return weighed
