"""Optional Gemini planner using public seed data."""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL = "gemini-3.5-flash-lite"
INSTRUCTIONS = """Plan three distinct, filmable short videos for Wushiland in Pittsburgh.
Return a JSON object with a briefs array. Every brief needs product (exact supplied name),
event (exact supplied name or null), format (one supplied name), hook, concept,
script (three lines), shots (three instructions), and why (a short staff-facing explanation).
Creative signals are optional ideas for format and hook only. When using one, return
its exact ID as creative_signal_id with the matching format; otherwise return null.
Keep product and event choices grounded in the catalog, weather, and calendar. Do not
claim platform popularity, copy captions or audio, or add products from the references.
Tie each reason to the product and the supplied audience, event, or seasonal scenario.
Use an indoor shoot in rain or cold. During breaks, target Oakland neighbors and workers.
Treat simulated weather as planning context, never as a forecast in public-facing copy.
Use only supplied facts. A holiday or observance is not evidence of a campus event.
Avoid discounts, store hours, local availability claims, implied partnerships, and filming
people without consent. Address any review feedback and avoid previously approved formats."""


def plan(evidence, feedback, used_formats):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY is missing.")
    model = os.getenv("WUSHILAND_GEMINI_MODEL", MODEL).removeprefix("models/")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", model):
        raise ValueError("WUSHILAND_GEMINI_MODEL must be a Gemini model ID.")
    body = {
        "systemInstruction": {"parts": [{"text": INSTRUCTIONS}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps({
            "evidence": evidence, "review_feedback": feedback, "used_formats": used_formats,
        })}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode("utf-8"),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=55) as response:
            payload = json.load(response)
        parts = payload["candidates"][0]["content"]["parts"]
        content = "".join(part.get("text", "") for part in parts if not part.get("thought"))
        briefs = json.loads(content)["briefs"]
        if not isinstance(briefs, list):
            raise ValueError
        return briefs
    except HTTPError as error:
        try:
            detail = json.load(error)["error"]["message"].replace(key, "[redacted]")[:300]
        except (ValueError, KeyError, TypeError, AttributeError):
            detail = "No error detail returned."
        raise ValueError(f"Gemini HTTP {error.code}: {detail}") from None
    except (URLError, TimeoutError):
        raise ValueError("Gemini connection failed or timed out.") from None
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        raise ValueError("Gemini returned an unreadable brief response.") from None
