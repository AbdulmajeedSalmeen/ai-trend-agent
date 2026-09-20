import re

from src.adapters import model
from src.schema import Signal

EXTRACT_SYSTEM = (
    "You read posts about software and extract what is being claimed, so a checker can "
    "verify it against official release notes. Answer with one JSON object and nothing else: "
    '{"subject": <exact package name from the list or null>, '
    '"assertion": <one short factual sentence, or null if the post claims nothing checkable>, '
    '"version": <version string stated in the post, or null>}. '
    "Never guess a version that is not written in the post. "
    "Choose a subject only when the post names that exact package. A different product from the "
    "same company is not the package: a post about Claude Code is not about anthropic-sdk-python, "
    "and a post about ChatGPT is not about openai-python. When in doubt, answer null."
)

JUDGE_SYSTEM = (
    "You rate how much a change matters for a bootcamp that teaches AI agents. "
    "Answer with one JSON object and nothing else: "
    '{"educational_value": <integer 1-5>, "reason": <one short sentence>}. '
    "5 means students must learn it now; 1 means a routine patch nobody needs to teach."
)

WRITE_SYSTEM = (
    "You tell a curriculum owner what to do and, above all, why. "
    "Lead with the strongest fact you are given, in this order: an API the notebooks still call "
    "that a newer release removed, then the version distance, then how stale the chapter is. "
    "Never lead with how many releases landed, and never make release counts the whole reason. "
    "The reason must name what changed and what it means for the chapter's material - "
    "never restate the decision as its own reason, and never write 'due to N confirmed claims'. "
    "Use only the facts given. Never add numbers, versions or claims that are not in the input, "
    "and never count anything yourself: if you mention how many releases landed, copy the "
    "number from the Staleness line exactly. "
    "If the input says the version the chapter teaches is not recorded, say that instead of "
    "asserting the chapter is outdated. "
    'Answer with one JSON object: {"sentence": <two sentences at most, under 45 words>}.'
)


def read_claim(signal: Signal, known_subjects: list[str]) -> dict | None:
    """What does this discussion post actually claim? None when the model is off or unsure."""
    if not model.available():
        return None

    body = signal.body[:600].strip()
    answer = model.ask_json(
        EXTRACT_SYSTEM,
        f"Packages we track: {', '.join(sorted(known_subjects))}\n\nTitle: {signal.title}\n\nBody: {body or '(none)'}",
        max_tokens=700,
        action="read_post",
    )
    if not answer or not isinstance(answer, dict):
        return None

    subject = answer.get("subject")
    if subject not in known_subjects:
        print(f"think: no tracked package in \"{signal.title[:58]}\"")
        return None

    assertion = (answer.get("assertion") or "").strip()
    if not assertion:
        print(f"think: {subject} mentioned, nothing checkable said")
        return None

    version = answer.get("version")
    version = str(version).strip() if version else None
    print(f"think: {subject} · {'v' + version if version else 'no version'} · \"{assertion[:52]}\"")
    return {"subject": subject, "assertion": assertion, "version": version}


def judge_educational_value(subject: str, claim_texts: list[str], chapter_title: str | None) -> dict | None:
    if not model.available():
        return None

    where = f"The course already has a chapter: {chapter_title}." if chapter_title else "No chapter covers this yet."
    answer = model.ask_json(
        JUDGE_SYSTEM,
        f"Package: {subject}\n{where}\nWhat changed:\n- " + "\n- ".join(claim_texts[:6]),
        max_tokens=600,
        action="judge_value",
    )
    if not answer:
        return None

    try:
        value = int(answer.get("educational_value"))
    except (TypeError, ValueError):
        return None
    if not 1 <= value <= 5:
        return None

    reason = (answer.get("reason") or "").strip()
    print(f"think: {subject} scored {value}/5 for teaching · {reason[:60]}")
    return {"value": value, "reason": reason}


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


def write_recommendation(subject: str, action: str, chapter: str | None, confirmed: int,
                         unverified: int, priority: float, teaches: str | None = None,
                         gap_sentence: str = "", staleness: str = "", legacy: str = "",
                         claim_texts: list[str] | None = None,
                         must_mention: list[str] | None = None) -> str | None:
    if not model.available():
        return None

    changes = "\n- ".join((claim_texts or [])[:5]) or "nothing specific"
    answer = model.ask_json(
        WRITE_SYSTEM,
        f"Package: {subject}\n"
        f"Action decided by our rules: {action}\n"
        f"Chapter: {chapter or 'none, this is a curriculum gap'}\n"
        f"What that chapter teaches: {teaches or 'not recorded'}\n"
        f"Version distance: {gap_sentence or 'not measured'}\n"
        f"Staleness: {staleness or 'the chapter is not measurably behind'}\n"
        f"What changed:\n- {changes}\n"
        f"Evidence: {confirmed} confirmed claims, {unverified} unverified\n"
        f"Priority score: {priority:.2f}",
        max_tokens=600,
        action="write_reason",
    )
    sentence = (answer or {}).get("sentence")

    if not isinstance(sentence, str) or not sentence.strip():
        return None

    sentence = sentence.strip()

    if not keeps_the_facts(sentence, must_mention or []):
        print(f"think: the written sentence for {subject} dropped the facts, keeping ours")
        return None

    if action != "watch":
        contradiction = contradicts_the_verdict(sentence)

        if contradiction:
            print(f"think: the written sentence for {subject} said \"{contradiction}\", keeping ours")
            return None

    return sentence
