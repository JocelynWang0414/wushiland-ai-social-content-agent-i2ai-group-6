"""Optional OpenAI planner using public seed data."""
import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen

MODEL = "gpt-4.1-mini"
INSTRUCTIONS = """Plan three distinct, filmable short videos for Wushiland in Pittsburgh.
Return a JSON object with a briefs array. Every brief needs product (exact supplied name),
event (exact supplied name or null), format (one supplied name), hook, concept,
script (three lines), shots (three instructions), and why (a short staff-facing explanation).
Tie each reason to the product and the supplied audience, event, or seasonal scenario.
Use an indoor shoot in rain or cold. During breaks, target Oakland neighbors and workers.
Treat simulated weather as planning context, never as a forecast in public-facing copy.
Use only supplied facts. A holiday or observance is not evidence of a campus event.
Avoid discounts, store hours, local availability claims, implied partnerships, and filming
people without consent. Address any review feedback and avoid previously approved formats."""


def plan(evidence, feedback, used_formats):
    body = {"model": os.getenv("WUSHILAND_MODEL", MODEL), "store": False,
            "response_format": {"type": "json_object"}, "max_completion_tokens": 2400,
            "messages": [{"role": "system", "content": INSTRUCTIONS},
                         {"role": "user", "content": json.dumps({
                             "evidence": evidence, "review_feedback": feedback, "used_formats": used_formats})}]}
    request = Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
                      headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
                               "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=35) as response:
            payload = json.load(response)
        briefs = json.loads(payload["choices"][0]["message"]["content"])["briefs"]
        if not isinstance(briefs, list):
            raise ValueError
        return briefs
    except (URLError, TimeoutError) as error:
        raise ValueError("Model request failed. Check API access and try again.") from error
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ValueError("Model returned an unreadable brief response.") from error
