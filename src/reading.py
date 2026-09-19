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
    "You write one sentence telling a curriculum owner what to do and why. "
    "Use only the facts given. Never add numbers or claims that are not in the input. "
    'Answer with one JSON object: {"sentence": <one sentence, under 30 words>}.'
)


def read_claim(signal: Signal, known_subjects: list[str]) -> dict | None:
    """What does this discussion post actually claim? None when the model is off or unsure."""
    if not model.available():
        return None

    body = signal.body[:600].strip()
    answer = model.ask_json(
        EXTRACT_SYSTEM,
        f"Packages we track: {', '.join(sorted(known_subjects))}\n\nTitle: {signal.title}\n\nBody: {body or '(none)'}",
        max_tokens=220,
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
        max_tokens=160,
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


def write_recommendation(subject: str, action: str, chapter: str | None, confirmed: int,
                         unverified: int, priority: float) -> str | None:
    if not model.available():
        return None

    answer = model.ask_json(
        WRITE_SYSTEM,
        f"Package: {subject}\nAction decided by our rules: {action}\n"
        f"Chapter: {chapter or 'none, this is a curriculum gap'}\n"
        f"Evidence: {confirmed} confirmed claims, {unverified} unverified\nPriority score: {priority:.2f}",
        max_tokens=120,
    )
    sentence = (answer or {}).get("sentence")
    return sentence.strip() if isinstance(sentence, str) and sentence.strip() else None
