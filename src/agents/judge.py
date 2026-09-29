"""How much a change is worth teaching, decided after looking rather than before.

The old judge was one question: a package name, a line about whether a chapter covers
it, and six sentences of claims. From that it returned a number between 1 and 5 that
carries a quarter of every priority score, and when the model was absent it silently
defaulted to 3. Nobody could ask it how it decided.

This one is a loop. It may call three tools before it answers, and each tool reads the
run's own artifacts rather than the network, so a frozen run replays offline and the
tests need no key:

    release_notes(package)  what the releases in this run actually say
    course_uses(symbol)     which notebook cells of the course use a name
    demand(subject)         the job posts and installs this run already counted

Then the part that matters: it has to cite what it used, and `check` verifies every
citation against the tool output this run produced. A quote that is not in the text we
fetched is dropped. A cell that is not in the search result is dropped. If nothing it
cited survives, the score is not used at all and the caller falls back to the rules,
exactly as it does today when there is no model. The agent gathers and proposes; the
rule decides what the run is allowed to record.
"""

import json
import re
import time

from src import trace
from src.adapters import model

MAX_STEPS = 4
MAX_TOOL_CHARS = 2400

SYSTEM = (
    "You are the head of curriculum at a bootcamp that trains people to build AI agents. "
    "You decide how much a package's changes are worth teaching, and you look before you decide. "
    "You may call a tool, one per turn, then use what it returns. "
    "Answer with one JSON object and nothing else, either "
    '{"tool": <name>, "args": {...}} to look something up, or '
    '{"answer": {"educational_value": <integer 1 to 5>, "reason": <one short sentence>, '
    '"cites": [{"factor": <what this supports>, "tool": <the tool that showed it>, '
    '"quote": <the exact text or number it returned>}]}} when you are ready. '
    "Score 5 for a breaking change to something students are taught or a concept they will need "
    "in their first job, 4 for a new capability worth a lesson, 3 for a mention in class, "
    "2 for fixes a student would never notice, 1 for maintenance. Use 1 freely. "
    "Cite only what a tool actually returned to you in this conversation. "
    "An answer with no citation is worth less than an honest 1."
)

TOOL_HELP = (
    "release_notes(package): what this run's releases say about the package.\n"
    "course_uses(symbol): the notebook cells of the course that use a name.\n"
    "demand(subject): the job posts and installs this run counted for the package."
)


def _flat(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _turn(subject: str, chapter_title: str | None, claims: list[str], seen: list[dict]) -> str:
    where = f"The course already has a chapter: {chapter_title}." if chapter_title else "No chapter covers this yet."
    lines = [f"Package: {subject}", where, "What changed:"]
    lines += [f"- {c}" for c in claims[:6]]
    lines += ["", "Tools:", TOOL_HELP, ""]
    if seen:
        lines.append("What you have looked up so far:")
        for step in seen:
            lines.append(f"- {step['tool']}({json.dumps(step['args'], ensure_ascii=False)}) returned: {step['text']}")
    else:
        lines.append("You have not looked anything up yet.")
    lines.append("")
    lines.append(f"You may call at most {MAX_STEPS} tools in total, then you must answer.")
    return "\n".join(lines)


def run(subject: str, claims: list[str], chapter_title: str | None, tools: dict,
        ask=None, max_steps: int = MAX_STEPS) -> dict | None:
    """Gather, then propose. Returns the proposal and the tool output it was given."""
    ask = ask or (lambda system, user: model.ask_json(system, user, max_tokens=700, timeout=60,
                                                      action="judge_agent"))
    seen: list[dict] = []

    for _ in range(max_steps + 1):
        answer = ask(SYSTEM, _turn(subject, chapter_title, claims, seen))
        if not answer:
            return None

        proposal = answer.get("answer")
        if isinstance(proposal, dict):
            return {"proposal": proposal, "seen": seen}

        name = answer.get("tool")
        tool = tools.get(name) if isinstance(name, str) else None
        if tool is None:
            # A tool it invented is not a turn it gets to keep: say so and let it try again.
            seen.append({"tool": str(name), "args": {}, "text": "no such tool"})
            continue

        args = answer.get("args") if isinstance(answer.get("args"), dict) else {}
        started = time.time()
        try:
            result = tool(**args)
        except TypeError:
            seen.append({"tool": name, "args": args, "text": "wrong arguments for this tool"})
            continue
        text = _flat(result)[:MAX_TOOL_CHARS] or "nothing found"
        trace.current.record(f"judge_tool:{name}", (time.time() - started) * 1000,
                               note=f"{subject} · {json.dumps(args, ensure_ascii=False)[:60]}")
        seen.append({"tool": name, "args": args, "text": text, "raw": result})

    # It spent every turn looking and never answered, which is not a judgement.
    return None


def tool_name(said) -> str:
    """The tool it meant, with the brackets it wrote it with taken off."""
    return re.sub(r"[^a-z0-9_]", "", str(said or "").lower())


def check(gathered: dict) -> dict | None:
    """Keep the citations the tool output supports, and only those.

    A citation survives when its quote is in what the tool actually returned this run.
    Everything else is dropped, and a score with nothing left under it is no score.
    """
    if not gathered:
        return None

    proposal = gathered.get("proposal") or {}
    try:
        value = int(proposal.get("educational_value"))
    except (TypeError, ValueError):
        return None
    if not 1 <= value <= 5:
        return None

    # A model that credits a line to "demand()" has named the tool that returned it,
    # and a lookup that misses on the punctuation drops a citation that was good.
    returned = {tool_name(step["tool"]): step["text"] for step in gathered.get("seen", [])}
    kept, dropped = [], 0
    for cite in proposal.get("cites") or []:
        if not isinstance(cite, dict):
            dropped += 1
            continue
        quote = _flat(cite.get("quote"))
        text = returned.get(tool_name(cite.get("tool")), "")
        if quote and quote in text:
            kept.append({"factor": str(cite.get("factor") or "")[:80],
                         "tool": tool_name(cite.get("tool")),
                         "quote": str(cite.get("quote"))[:200]})
        else:
            dropped += 1

    if not kept:
        return None

    reason = (proposal.get("reason") or "").strip()
    return {"value": value, "reason": reason[:200], "cites": kept, "dropped": dropped,
            "looked": [{"tool": s["tool"], "args": s.get("args", {})} for s in gathered.get("seen", [])]}


def judge(subject: str, claims: list[str], chapter_title: str | None, tools: dict,
          ask=None, max_steps: int = MAX_STEPS) -> dict | None:
    """The whole move: look, propose, keep what the evidence supports."""
    if not tools:
        return None
    verdict = check(run(subject, claims, chapter_title, tools, ask=ask, max_steps=max_steps))
    if verdict:
        trace.current.record("judge_agent", 0, note=(
            f"{subject} scored {verdict['value']}/5 on {len(verdict['cites'])} cited, "
            f"{verdict['dropped']} dropped"))
    return verdict
