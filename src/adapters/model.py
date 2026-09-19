import json
import os
import re
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()

PROVIDERS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "nvidia/nemotron-3.5-lightning-30b-a3b", "NVIDIA_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY"),
}

FENCE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)


def config() -> dict | None:
    """Base url, model and key for the first provider that has a key set."""
    explicit_key = os.environ.get("MODEL_API_KEY")
    if explicit_key:
        return {
            "base_url": os.environ.get("MODEL_BASE_URL", PROVIDERS["openai"][0]),
            "model": os.environ.get("MODEL_NAME", PROVIDERS["openai"][1]),
            "key": explicit_key,
            "provider": os.environ.get("MODEL_PROVIDER", "custom"),
        }

    for provider, (base_url, model, env_name) in PROVIDERS.items():
        key = os.environ.get(env_name)
        if key:
            return {
                "base_url": os.environ.get("MODEL_BASE_URL", base_url),
                "model": os.environ.get("MODEL_NAME", model),
                "key": key,
                "provider": provider,
            }
    return None


def available() -> bool:
    return config() is not None


def ask_json(system: str, user: str, max_tokens: int = 400, timeout: int = 40) -> dict | None:
    """One model call that must answer with a JSON object. None on any failure."""
    settings = config()
    if settings is None:
        return None

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

    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            text = payload["choices"][0]["message"]["content"]
            return json.loads(FENCE.sub("", text).strip())
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError):
            if attempt == 0:
                time.sleep(1.5)
                continue
            return None
    return None


def describe() -> str:
    settings = config()
    return f"{settings['provider']}:{settings['model']}" if settings else "no model configured"
