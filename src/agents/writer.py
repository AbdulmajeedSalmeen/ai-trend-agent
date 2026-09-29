"""The sentence on a card, written until it passes.

A recommendation carries one sentence telling a curriculum owner what to do and why.
The rules can write it, and do, but they write like rules: correct, and read like a
form. So a model is asked first, and its sentence is checked against what it was given.

The checking already existed. What did not was a second chance. A sentence that dropped
a version number it was told to keep, or that said the chapter is up to date when the
whole point is that it is not, was thrown away without comment and the rule's sentence
printed instead. Three of thirty-six on the last run. The model never learned what was
wrong with them, because nobody told it.

So this is the smallest loop in the project and the most visible one: write, check,
say what is wrong, write again. Three attempts, and the rules are the same on every
one of them.

The rules are the point, not the loop:

  1. Every fact it was told to keep has to be in the sentence, exactly as given. A
     version number rewritten is a version number invented.
  2. It may not assert what the decision denies. Saying a chapter is up to date, in a
     recommendation to update it, undoes the work rather than explaining it.
  3. It has to fit on a card. The system prompt has always asked for two sentences under
     forty-five words; nothing checked, so nothing held.

What never happens is the sentence passing because it was written twice. Failing three
times means the rules write it, exactly as before.
"""

import re

from src import trace
from src.adapters import model

TRIES = 3
MAX_WORDS = 45

WRITE_SYSTEM = (
    "You tell a curriculum owner what to do and, above all, why. "
    "Think like a school, not a changelog. Lead with the strongest fact you are given, in this "
    "order: an API the notebooks still call that a newer release removed; a breaking change or a "
    "new concept in what the releases changed; whether employers ask for the tool; and only then "
    "the version distance. A version number is evidence, never the reason on its own. "
    "Never lead with how many releases landed, and never make release counts the whole reason. "
    "The reason must name what changed and what it means for the chapter's material - "
    "never restate the decision as its own reason, and never write 'due to N confirmed claims'. "
    "Use only the facts given. Never add numbers, versions or claims that are not in the input, "
    "and never count anything yourself: if you mention how many releases landed, copy the "
    "number from the Staleness line exactly. "
    "If the input says the version the chapter teaches is not recorded, say that instead of "
    "asserting the chapter is outdated. "
    "Say the action exactly as it is described to you: optional material is not a new lesson, "
    "and watching is not a change. "
    "Every item on the Must appear line has to appear in your sentence exactly as written. "
    'Answer with one JSON object: {"sentence": <two sentences at most, under 45 words>}.'
)

# A sentence can pass every structural check and still say the opposite of what the
# rules decided. These are the phrases that would contradict a verdict of "behind",
# unless the phrase is itself negated.
CONTRADICTIONS = [
    "up to date", "no action", "no changes needed", "nothing to change",
    "already current", "still supported", "not affected", "no update needed",
]

NEGATED = re.compile(
    r"(?:\bnot|\bnever|\bno longer|\bisn't|\baren't|\bis not|\bare not|\bwasn't)\s+(?:\w+\s+){0,1}$"
)


def keeps_the_facts(sentence: str, must_mention: list[str]) -> bool:
    """A written sentence is only worth keeping if it still carries the facts it was given."""
    return all(fact in sentence for fact in must_mention if fact)


def missing_facts(sentence: str, must_mention: list[str]) -> list[str]:
    return [fact for fact in must_mention or [] if fact and fact not in sentence]


def contradicts_the_verdict(sentence: str) -> str | None:
    """The phrase that undoes the decision, or None.

    A phrase only counts when it is asserted. "not up to date" agrees with us;
    "up to date" does not.
    """
    lower = sentence.lower()

    for phrase in CONTRADICTIONS:
        for match in re.finditer(re.escape(phrase), lower):
            before = lower[max(0, match.start() - 40):match.start()]

            if not NEGATED.search(before):
                return phrase

    return None


# The end of a sentence: a stop followed by a space or the end, so 1.4.2 is not three.
SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


def too_long(sentence: str) -> int:
    """How many words over the limit, or zero. A card has a width, and the prompt says
    under 45, so 45 is one too many."""
    return max(0, len(sentence.split()) - (MAX_WORDS - 1))


def sentences(text: str) -> int:
    """How many sentences, counting one for text with no stop at all."""
    return max(1, len(SENTENCE_END.findall(text.strip())))


def faults(sentence: str, must_mention: list[str] | None, action: str) -> list[str]:
    """What is wrong with a sentence, said the way it would be said to whoever wrote it."""
    said = []
    dropped = missing_facts(sentence, must_mention or [])

    if dropped:
        said.append("You left out " + ", ".join(f'"{fact}"' for fact in dropped)
                    + ". Every one of those has to appear in the sentence exactly as written.")

    if action != "watch":
        contradiction = contradicts_the_verdict(sentence)

        if contradiction:
            said.append(f'You wrote "{contradiction}", which says the opposite of the decision you '
                        f"are explaining. Explain why the change is needed instead of denying it.")

    over = too_long(sentence)

    if over:
        said.append(f"It is {over} word{'s' if over > 1 else ''} too long. Two sentences, "
                    f"under {MAX_WORDS} words.")

    count = sentences(sentence)

    if count > 2:
        said.append(f"It is {count} sentences. Write two at most.")

    return said


def turn(brief: str, complaint: str, attempt: int, last: str = "") -> str:
    if not complaint:
        return brief

    # Each call is its own conversation, so the sentence it is to keep what was right
    # from has to be in front of it.
    said = f' It said: "{last}"' if last else ""
    return (f"{brief}\n\n"
            f"Attempt {attempt - 1} was thrown away.{said} What was wrong: {complaint} "
            f"Write it again, fixing that and keeping what was right.")


def write(brief: str, must_mention: list[str] | None = None, action: str = "",
          ask=None, tries: int = TRIES) -> dict | None:
    """The sentence, and what it took to get one.

    None when the model wrote nothing; a sentence of None, with the complaints, when every
    attempt broke a rule. Either way the rules write it.
    """
    if not model.available() and ask is None:
        return None

    ask = ask or (lambda system, user: model.ask_json(system, user, max_tokens=380,
                                                      action="write_reason"))
    complaint, complaints, last = "", [], ""

    for attempt in range(1, tries + 1):
        answer = ask(WRITE_SYSTEM, turn(brief, complaint, attempt, last))
        sentence = (answer or {}).get("sentence") if isinstance(answer, dict) else None

        if not isinstance(sentence, str) or not sentence.strip():
            return None

        sentence = sentence.strip()
        said = faults(sentence, must_mention, action)

        if not said:
            trace.current.record("writer_agent", 0, note=(
                f"kept on attempt {attempt}" + (f" after: {complaints[-1][:70]}" if complaints else "")))
            return {"sentence": sentence, "tries": attempt, "complaints": complaints}

        complaint, last = " ".join(said), sentence
        complaints.append(complaint)

    trace.current.record("writer_agent", 0, ok=False, note=(
        f"{tries} attempts, still wrong: {complaints[-1][:80]}"))
    # Every attempt broke a rule. Saying so, rather than returning nothing, lets the
    # caller tell this apart from a model that wrote nothing at all.
    return {"sentence": None, "tries": tries, "complaints": complaints}
