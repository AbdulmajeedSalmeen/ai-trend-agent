"""The version a post talked about but never wrote down.

A claim with no version states nothing a release page can check, so the verify stage
has nothing to do with it and calls it unverified. That is the whole reason this run
has no cross-source confirmation: the posts name a package and leave the version to
the reader.

A rule cannot fill it in. "The new LangChain release breaks agents" names no number,
and picking the newest release is a guess dressed as a fact. So this is a loop: it
reads the post, lists the releases collected for that package, opens the notes of the
ones that look right, and says which release the post was about, or says it cannot
tell, which is most of the time and is the correct answer.

Three rules stand under it, and they are what separate this from guessing:

  1. The version it names must be one of the releases this run actually collected.
     A version it remembers is not evidence of anything.
  2. The release must not be published after the post. A post cannot report a release
     that did not exist yet, however well the notes match.
  3. The line it quotes to tie the two together must be in something a tool returned.

What survives fills in the claim's version and nothing else. The verify stage then
does what it always did, and records that this version was extracted rather than
stated, because a link somebody inferred is worth less than one somebody wrote down.
"""

import json
import re
from datetime import timezone

from src import trace
from src.adapters import model
from src.schema import Claim, Signal
from src.versions import extract_version

MAX_STEPS = 3
MAX_TOOL_CHARS = 2000
MAX_CANDIDATES = 8

SYSTEM = (
    "You work out which release of a package a post was talking about, when the post "
    "never said. You are given the post and the releases collected for that package. "
    "Answer with one JSON object and nothing else, either "
    '{"tool": <name>, "args": {...}} to look, or, when you are ready, '
    '{"answer": {"version": <one of the versions listed, or null>, '
    '"quote": <a line copied exactly from the post or from the notes that ties them together>, '
    '"why": <one sentence>}}. '
    "Name a version only when the post is about that release: the notes describe what the "
    "post describes, and the release came first. A post is often about a package in general, "
    "or about a release we did not collect. Then the answer is null, and null is a good answer. "
    "Guessing the newest release is not an answer."
)

TOOL_HELP = ("post(): the post itself, with its date.\n"
             "releases(): the releases collected for this package, newest first.\n"
             "notes(version): what one release's notes say.")


def flat(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def when(signal: Signal):
    """A date that can be compared with another, whatever tzinfo it arrived with."""
    moment = signal.published_at
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def candidates(subject: str, signals: list[Signal]) -> list[dict]:
    """Every release this run collected for this package, newest first, once per version.

    The same release arrives twice, from the registry and from the repository. The one
    with notes is the one worth reading, so it wins the version.
    """
    found: dict[str, dict] = {}

    for signal in signals:
        if signal.tier != 1 or signal.subject != subject:
            continue

        version = extract_version(f"{signal.title} {signal.body}")

        if version is None:
            continue

        seen = found.get(version)

        if seen is None or (not seen["notes"] and signal.body.strip()):
            found[version] = {"version": version, "published_at": when(signal),
                              "url": signal.url, "notes": signal.body.strip(), "id": signal.id}

    return sorted(found.values(), key=lambda row: row["published_at"], reverse=True)[:MAX_CANDIDATES]


def tools_for(post: Signal, releases: list[dict]) -> dict:
    by_version = {row["version"]: row for row in releases}

    def post_tool() -> str:
        return (f"posted {when(post).date().isoformat()}: {post.title}. "
                f"{post.body[:900]}").strip()

    def releases_tool() -> str:
        if not releases:
            return "this run collected no releases for that package"

        return "; ".join(f"{row['version']} on {row['published_at'].date().isoformat()}"
                         f"{': ' + row['notes'][:120] if row['notes'] else ''}" for row in releases)

    def notes_tool(version: str = "") -> str:
        row = by_version.get(str(version).strip())

        if row is None:
            return f"no release {version} was collected for that package"

        return row["notes"][:1200] or f"{row['version']} was collected with no notes"

    return {"post": post_tool, "releases": releases_tool, "notes": notes_tool}


def turn(claim: Claim, post: Signal, releases: list[dict], seen: list[dict]) -> str:
    lines = [f"Package: {claim.subject}", f"The post says: {post.title}",
             "It states no version. Releases collected: "
             f"{', '.join(row['version'] for row in releases) or 'none'}.",
             "", "Tools:", TOOL_HELP, ""]

    if seen:
        lines.append("What you have read so far:")

        for step in seen:
            lines.append(f"- {step['tool']}({json.dumps(step['args'], ensure_ascii=False)}): {step['text']}")
    else:
        lines.append("You have read nothing yet. Start with the post.")

    lines += ["", f"You may call at most {MAX_STEPS} tools, then you must answer."]
    return "\n".join(lines)


def run(claim: Claim, post: Signal, releases: list[dict], tools: dict,
        ask=None, max_steps: int = MAX_STEPS) -> dict | None:
    ask = ask or (lambda system, user: model.ask_json(system, user, max_tokens=500, timeout=60,
                                                      action="extractor_agent"))
    seen: list[dict] = []

    for _ in range(max_steps + 1):
        answer = ask(SYSTEM, turn(claim, post, releases, seen))

        if not answer:
            return None

        if "answer" in answer:
            # An answer of null is it saying it cannot tell, which is a finish, not a
            # turn to skip. Letting it fall through spends the rest of the budget.
            proposal = answer.get("answer")
            return {"proposal": proposal if isinstance(proposal, dict) else {}, "seen": seen}

        name = answer.get("tool")
        tool = tools.get(name) if isinstance(name, str) else None

        if tool is None:
            seen.append({"tool": str(name), "args": {}, "text": "no such tool"})
            continue

        args = answer.get("args") if isinstance(answer.get("args"), dict) else {}

        try:
            result = tool(**args)
        except TypeError:
            seen.append({"tool": name, "args": args, "text": "wrong arguments for this tool"})
            continue

        seen.append({"tool": name, "args": args, "text": flat(result)[:MAX_TOOL_CHARS] or "nothing found"})

    return None


def check(gathered: dict, post: Signal, releases: list[dict]) -> dict | None:
    """The three rules: a collected version, published before the post, quoting what it read."""
    proposal = (gathered or {}).get("proposal") or {}
    version = proposal.get("version")

    if not isinstance(version, str) or not version.strip():
        return None

    row = next((item for item in releases if item["version"] == version.strip()), None)

    if row is None:
        # A version it remembered rather than one this run collected.
        return None

    if row["published_at"] > when(post):
        # The post is older than the release, so it cannot be reporting it.
        return None

    returned = " ".join(step["text"] for step in (gathered or {}).get("seen") or [])
    quote = flat(proposal.get("quote"))

    if len(quote) < 8 or quote not in returned:
        return None

    return {"version": row["version"], "evidence_url": row["url"], "release_id": row["id"],
            "quote": str(proposal.get("quote"))[:220], "why": str(proposal.get("why") or "")[:240],
            "looked": [{"tool": step["tool"], "args": step.get("args", {})} for step in gathered["seen"]]}


def extract(claim: Claim, post: Signal, signals: list[Signal], ask=None,
            max_steps: int = MAX_STEPS) -> dict | None:
    """Which release this claim's post was about, or None, which is the usual answer."""
    releases = candidates(claim.subject, signals)

    if not releases:
        return None

    gathered = run(claim, post, releases, tools_for(post, releases), ask=ask, max_steps=max_steps)
    found = check(gathered, post, releases) if gathered else None

    trace.current.record("extractor_agent", 0, ok=found is not None, note=(
        f"{claim.subject}: {found['version'] if found else 'no version it could stand behind'} "
        f"from {len(releases)} releases"))
    return found
