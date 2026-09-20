import json
import os
import re
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

from src import trace

load_dotenv()

PROVIDERS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "nvidia/nemotron-3.5-lightning-30b-a3b", "NVIDIA_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY"),
}

FENCE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)

# A refused key, a revoked key or a spent quota will refuse the next call too.
# Retrying them cost one run 170 failed calls and three minutes before the
# stages fell back to rules anyway.
FATAL_STATUS = {401, 402, 403, 429}

# Which provider is out, and why. A key is refused per provider, not globally:
# OpenAI running out of quota should not stop a working Groq key.
_halted: dict[str, str] = {}

# A provider that times out is not refusing us, so it is worth one more try.
# A provider that times out twice running is costing the run two timeouts per
# call and is dropped like a refused one.
STRIKES = 2
_strikes: dict[str, int] = {}


def reset() -> None:
    """Start of a run: give every provider another chance."""
    _halted.clear()
    _strikes.clear()


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

    order = [name.strip() for name in os.environ.get("MODEL_ORDER", "").split(",") if name.strip()]
    names = [name for name in order if name in PROVIDERS]
    names += [name for name in PROVIDERS if name not in names]

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


def halted() -> str | None:
    """Why the model is unavailable, when every configured provider is out."""
    configured = _configured()

    if not configured or providers():
        return None

    return _halted.get(configured[-1]["provider"]) or next(iter(_halted.values()), None)


def _call(settings: dict, system: str, user: str, max_tokens: int, timeout: int,
          action: str) -> tuple[dict | None, str | None]:
    """One provider, one question. Returns (answer, fatal_reason)."""
    body = json.dumps({
        "model": settings["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    request = urllib.request.Request(
        f"{settings['base_url']}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {settings['key']}", "Content-Type": "application/json"},
    )
    label = f"{action}@{settings['provider']}"

    for attempt in range(2):
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            text = payload["choices"][0]["message"]["content"]
            answer = json.loads(FENCE.sub("", text).strip())
            usage = payload.get("usage") or {}
            trace.current.record(
                label, (time.perf_counter() - started) * 1000,
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
            )
            return answer, None
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as problem:
            fatal = isinstance(problem, urllib.error.HTTPError) and problem.code in FATAL_STATUS
            note = f"HTTP {problem.code}" if isinstance(problem, urllib.error.HTTPError) else type(problem).__name__
            trace.current.record(
                label, (time.perf_counter() - started) * 1000, ok=False, note=note,
            )

            if fatal:
                return None, note

            if attempt == 0:
                time.sleep(1.5)
                continue

    return None, None


def ask_json(system: str, user: str, max_tokens: int = 400, timeout: int = 40,
             action: str = "ask") -> dict | None:
    """One question, answered as JSON, by the first provider that can.

    Every call is timed and counted against the run budget. A provider that
    refuses the key or has spent its quota is dropped for the rest of the run
    and the next one is tried; when none are left the stages fall back to rules.
    """
    candidates = providers()

    if not candidates:
        if config() is not None:
            trace.current.record(action, 0.0, ok=False, note=f"skipped, {halted()}")
        return None

    if trace.current.over_budget():
        trace.current.record(action, 0.0, ok=False, note="budget spent")
        return None

    for settings in candidates:
        name = settings["provider"]
        answer, fatal = _call(settings, system, user, max_tokens, timeout, action)

        if answer is not None:
            _strikes[name] = 0
            return answer

        if fatal is None:
            _strikes[name] = _strikes.get(name, 0) + 1

            if _strikes[name] < STRIKES:
                return None

            fatal = f"{STRIKES} failed calls running"

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
