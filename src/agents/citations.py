"""What counts as a line an agent read.

Every agent here proposes and cites what it read, and a rule keeps a citation only if a
tool returned it this run. That rule was weaker than it sounded, in four ways:

- The tools say back what they were asked ("nothing counted for <subject>"), so a model
  could write its own evidence into a call and then quote the echo.
- Some agents had no minimum length for a quote, so one letter passed.
- The loop's own words ("no such tool", "nothing found") sat in the same list as the
  tools' output and could be quoted as if a tool had said them. One run scored a package
  4 out of 5 on the single citation "nothing found".
- The judges kept only the last output of each tool, so a true line from an earlier
  call to the same tool was dropped.

This is the one place that decides, so seven agents cannot drift apart on it again.
"""

import re

# Shorter than this, a quote cannot say anything a score could rest on.
MIN_QUOTE = 12


def flat(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def tool_name(said) -> str:
    """The tool it meant, with the brackets it wrote it with taken off."""
    return re.sub(r"[^a-z0-9_]", "", str(said or "").lower())


def note(tool, args, text: str) -> dict:
    """A step the loop wrote itself. The model is shown it; nobody can cite it."""
    return {"tool": str(tool), "args": args if isinstance(args, dict) else {}, "text": text, "note": True}


def step(tool, args, result, limit: int) -> dict:
    """What a tool returned, flattened and cut, or a note when it returned nothing."""
    text = flat(result)[:limit]

    if not text:
        return note(tool, args, "nothing found")

    return {"tool": tool, "args": args, "text": text}


def given(args) -> list[str]:
    """Every value the model passed to a tool, as flattened text."""
    if isinstance(args, dict):
        return [text for value in args.values() for text in given(value)]

    if isinstance(args, (list, tuple)):
        return [text for value in args for text in given(value)]

    return [flat(args)] if flat(args) else []


def echoed(text, each: dict) -> bool:
    """Whether this is the model's own words handed back by the tool.

    It is, when it sits inside something the model passed in, or when it carries a phrase
    or a link the model passed in. A plain name is neither: a package name is in nearly
    every line a tool returns about that package, and the line is still the tool's.
    """
    text = flat(text)

    for value in given(each.get("args")):
        if text in value:
            return True

        if (len(value.split()) >= 3 or "://" in value) and value in text:
            return True

    return False


def backed(quote, steps, tool=None) -> bool:
    """Whether a tool returned this quote this run, in its own words and not the model's.

    With a tool named, only that tool's calls count, every one of them.
    """
    wanted = flat(quote)

    if len(wanted) < MIN_QUOTE:
        return False

    for each in steps or []:
        if each.get("note"):
            continue

        if tool is not None and tool_name(each.get("tool")) != tool_name(tool):
            continue

        if wanted in flat(each.get("text")) and not echoed(wanted, each):
            return True

    return False
