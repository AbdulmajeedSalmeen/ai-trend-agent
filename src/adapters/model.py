import contextlib
import json
import os
import re
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

from src import trace

load_dotenv()

# Order matters: this is the order a run tries them in. Groq sits ahead of
# NVIDIA because NVIDIA's endpoint answers in tens of seconds when it answers
# at all, and a fallback that slow costs more than having none.
#
# Groq's free tier caps tokens per day per model, so its two models are two
# providers with two budgets. qwen goes first: it answers our prompts in a third
# of a second on about half the tokens of gpt-oss-120b, which is a reasoning
# model that bills its thinking. A day of repeated runs spent 120b's 200,000
# tokens; qwen's allowance was untouched.
PROVIDERS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
    "groq-fast": ("https://api.groq.com/openai/v1", "qwen/qwen3.8-27b", "GROQ_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "GROQ_API_KEY"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "nvidia/nemotron-3.5-lightning-30b-a3b", "NVIDIA_API_KEY"),
}

FENCE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)

# Groq sits behind Cloudflare, which refuses Python's default urllib signature
# with a 403 before the request ever reaches the API. Naming ourselves fixes it
# and is the polite thing to do at every other provider too.
USER_AGENT = "ai-trend-agent/1.0 (SDA bootcamp capstone)"

# A refused key, a revoked key or a spent quota will refuse the next call too.
# Retrying them cost one run 170 failed calls and three minutes before the
# stages fell back to rules anyway.
FATAL_STATUS = {401, 402, 403}

# 429 is two different answers wearing one number. A free tier saying "too many
# requests this minute" wants us to wait; a spent account saying "you are out of
# credit" wants us to stop.
#
# Match the error code the API sends, not the prose. Reading the prose cost us a
# run: Groq's rate-limit message links to its billing page, the word "billing"
# was taken for "out of credit", and the model was dropped while it was only
# being asked to wait. Anything that is not an explicit out-of-credit code is
# treated as a wait.
OUT_OF_CREDIT = ("insufficient_quota", "spend_limit", "billing_hard_limit", "exceeded_current_quota")
# "tokens per day (TPD)" and "requests per day (RPD)" in Groq's message. Its
# error code is the same one a per-minute limit uses, so here the words decide.
SPENT_FOR_THE_DAY = re.compile(r"\bper day\b|\(tpd\)|\(rpd\)")
MAX_BACKOFF = 30.0

# Which provider is out, and why. A key is refused per provider, not globally:
# OpenAI running out of quota should not stop a working Groq key.
_halted: dict[str, str] = {}

# A provider that times out is not refusing us, so it is worth one more try.
# A provider that times out twice running is costing the run two timeouts per
# call and is dropped like a refused one.
STRIKES = 2
_strikes: dict[str, int] = {}

# What each provider said it had left, from its rate-limit headers. Groq counts a
# request's max_tokens against the minute's budget before it answers, so a run
# that ignored this bounced off the limit on almost every call: one replay took
# an hour and most of its answers never came back. Waiting for the budget to
# refill before asking is faster than being refused and retrying.
_budget: dict[str, dict] = {}
DURATION_RE = re.compile(r"(?:(?P<m>\d+(?:\.\d+)?)m)?(?:(?P<s>\d+(?:\.\d+)?)s)?(?:(?P<ms>\d+(?:\.\d+)?)ms)?$")
MAX_PACE_WAIT = 65.0


def reset() -> None:
    """Start of a run: give every provider another chance."""
    _halted.clear()
    _strikes.clear()
    _budget.clear()


def seconds(duration: str | None) -> float:
    """"577ms", "7.66s", "1m30s" in seconds. Anything unreadable is no wait."""
    if not duration:
        return 0.0

    match = DURATION_RE.match(duration.strip())

    if not match or not any(match.groupdict().values()):
        return 0.0

    minutes = float(match.group("m") or 0)
    secs = float(match.group("s") or 0)
    millis = float(match.group("ms") or 0)

    return minutes * 60 + secs + millis / 1000


def remember_budget(provider: str, headers) -> None:
    remaining = headers.get("x-ratelimit-remaining-tokens")

    if remaining is None:
        return

    try:
        left = int(float(remaining))
    except ValueError:
        return

    _budget[provider] = {
        "tokens": left,
        "refills_at": time.monotonic() + seconds(headers.get("x-ratelimit-reset-tokens")),
    }


def pace(provider: str, reserve: int) -> float:
    """Wait until the provider's minute has room for this request. Returns the wait."""
    known = _budget.get(provider)

    if known is None or known["tokens"] >= reserve:
        return 0.0

    wait = min(max(0.0, known["refills_at"] - time.monotonic()), MAX_PACE_WAIT)

    if wait:
        time.sleep(wait)

    _budget.pop(provider, None)
    return wait


def _configured() -> list[dict]:
    """Every provider with a key, in the order they should be tried.

    MODEL_ORDER overrides the order, so a team can put the key they trust first
    without editing code.
    """
    explicit_key = os.environ.get("MODEL_API_KEY")
    found = []

    if explicit_key:
        found.append({
            "base_url": os.environ.get("MODEL_BASE_URL", PROVIDERS["openai"][0]),
            "model": os.environ.get("MODEL_NAME", PROVIDERS["openai"][1]),
            "key": explicit_key,
            "provider": os.environ.get("MODEL_PROVIDER", "custom"),
        })

    # MODEL_ORDER is both the order and the guest list: naming any provider
    # leaves the unnamed ones out, which is how a key that is present but known
    # to be useless gets excluded without deleting it from the environment.
    order = [name.strip() for name in os.environ.get("MODEL_ORDER", "").split(",") if name.strip()]
    names = [name for name in order if name in PROVIDERS]

    if not names:
        names = list(PROVIDERS)

    for provider in names:
        base_url, model, env_name = PROVIDERS[provider]
        key = os.environ.get(env_name)

        if key:
            found.append({"base_url": base_url, "model": model, "key": key, "provider": provider})

    return found


def config() -> dict | None:
    """The provider a run would start with, or None when nothing is configured."""
    found = _configured()

    return found[0] if found else None


def providers() -> list[dict]:
    """Providers still worth asking. Reads config() first so that switching the
    model off in one place switches it off everywhere, tests included."""
    if config() is None:
        return []

    return [entry for entry in _configured() if entry["provider"] not in _halted]


def available() -> bool:
    return config() is not None


def parse_json(text: str) -> dict:
    """The JSON object in a model's answer.

    Asked for one object and nothing else, a reasoning model still sometimes
    says a sentence first or after. Two of those in a row dropped a working
    provider for the end of a run, when the object was right there in the text.
    """
    cleaned = FENCE.sub("", text).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")

        if start == -1 or end <= start:
            raise

        return json.loads(cleaned[start:end + 1])


def halted() -> str | None:
    """Why the model is unavailable, when every configured provider is out."""
    configured = _configured()

    if not configured or providers():
        return None

    return _halted.get(configured[-1]["provider"]) or next(iter(_halted.values()), None)


def _call(settings: dict, system: str, user: str, max_tokens: int, timeout: int,
          action: str) -> tuple[dict | None, str | None, bool]:
    """One provider, one question. Returns (answer, fatal_reason, rate_limited)."""
    body = json.dumps({
        "model": settings["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    request = urllib.request.Request(
        f"{settings['base_url']}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {settings['key']}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    label = f"{action}@{settings['provider']}"
    # Roughly four characters to a token, plus everything the answer may use.
    reserve = (len(system) + len(user)) // 4 + max_tokens

    for attempt in range(2):
        pace(settings["provider"], reserve)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                remember_budget(settings["provider"], getattr(response, "headers", None) or {})
                payload = json.load(response)
            choice = payload["choices"][0]
            text = choice["message"].get("content") or ""

            # A reasoning model bills its thinking against the same ceiling and
            # can hand back an empty answer having spent all of it. That is not
            # a broken model, it is too small a budget.
            if not text.strip() and choice.get("finish_reason") == "length":
                trace.current.record(
                    label, (time.perf_counter() - started) * 1000,
                    tokens_in=(payload.get("usage") or {}).get("prompt_tokens", 0),
                    tokens_out=(payload.get("usage") or {}).get("completion_tokens", 0),
                    ok=False, note="spent its budget reasoning",
                )

                if attempt == 0:
                    body = json.loads(request.data)
                    body["max_tokens"] = max_tokens * 4
                    request.data = json.dumps(body).encode("utf-8")
                    continue

                # Our ceiling was too low for this model, which is not the
                # provider failing. Counting it dropped a working key.
                return None, None, True

            answer = parse_json(text)
            usage = payload.get("usage") or {}
            trace.current.record(
                label, (time.perf_counter() - started) * 1000,
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
            )
            return answer, None, False
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as problem:
            http = isinstance(problem, urllib.error.HTTPError)
            fatal = http and problem.code in FATAL_STATUS
            note = f"HTTP {problem.code}" if http else type(problem).__name__
            wait = 0.0

            if http and problem.code == 429:
                detail = ""

                with contextlib.suppress(Exception):
                    detail = (problem.read() or b"").decode("utf-8", "replace").lower()

                retry_after = problem.headers.get("Retry-After")

                # Only an explicit out-of-credit code ends the run. An
                # ambiguous 429 waits once; two failures in a row drop the
                # provider anyway, so guessing wrong stays cheap.
                #
                # A spent daily allowance also ends it for this provider: the
                # day does not refill within a run. Waiting thirty seconds per
                # call on a spent day turned one replay into an hour of waits.
                if any(code in detail for code in OUT_OF_CREDIT):
                    fatal = True
                    note = "HTTP 429 out of credit"
                elif SPENT_FOR_THE_DAY.search(detail):
                    fatal = True
                    note = "HTTP 429 daily allowance spent"
                else:
                    wait = min(float(retry_after or 5), MAX_BACKOFF)
                    note = f"HTTP 429 rate limited, waiting {wait:.0f}s"
            trace.current.record(
                label, (time.perf_counter() - started) * 1000, ok=False, note=note,
            )

            if fatal:
                return None, note, False

            if attempt == 0:
                time.sleep(wait or 1.5)
                continue

    return None, None, bool(wait)


def ask_json(system: str, user: str, max_tokens: int = 400, timeout: int = 40,
             action: str = "ask") -> dict | None:
    """One question, answered as JSON, by the first provider that can.

    Every call is timed and counted against the run budget. A provider that
    refuses the key or has spent its quota is dropped for the rest of the run
    and the next one is tried; when none are left the stages fall back to rules.
    """
    candidates = providers()

    if not candidates:
        reason = halted()

        if reason:
            trace.current.record(action, 0.0, ok=False, note=f"skipped, {reason}")

        return None

    if trace.current.over_budget():
        trace.current.record(action, 0.0, ok=False, note="budget spent")
        return None

    for settings in candidates:
        name = settings["provider"]
        answer, fatal, rate_limited = _call(settings, system, user, max_tokens, timeout, action)

        if answer is not None:
            _strikes[name] = 0
            return answer

        # Being told to wait is not the provider failing. Counting it as one
        # dropped a working Groq key after two calls, because a free tier says
        # "wait" far more often than it says "no".
        if rate_limited:
            continue

        if fatal is None:
            _strikes[name] = _strikes.get(name, 0) + 1

            if _strikes[name] >= STRIKES:
                _halted[name] = f"{STRIKES} failed calls running"
                print(f"{name} keeps failing; dropped for the rest of this run")

            continue

        _halted[settings["provider"]] = fatal
        remaining = providers()
        moving = f"falling back to {remaining[0]['provider']}" if remaining else "no provider left"
        print(f"{settings['provider']} unavailable ({fatal}); {moving}")

    return None


def describe() -> str:
    """The chain a run will try, in order."""
    configured = _configured()

    if not configured:
        return "no model configured"

    return ", ".join(f"{entry['provider']}:{entry['model']}" for entry in configured)
