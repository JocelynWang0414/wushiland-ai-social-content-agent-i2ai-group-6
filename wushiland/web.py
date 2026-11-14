"""Run the staff preview on a loopback-only development server."""
import os
from datetime import date, datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .agent import ET, generate
from .llm import plan


def items(values):
    return "<ul>" + "".join(f"<li>{escape(value)}</li>" for value in values) + "</ul>"


def render(start="", result=None, error=""):
    cards = ""
    if result:
        weather = result["weather"]
        events = ", ".join(event["name"] for event in result["events"]) or "None in the catalog for this week"
        cards = (
            f"<h2>Briefs for {result['start']} to {result['end']}</h2>"
            f"<p><strong>Simulated weather</strong> · {weather['condition']} · {weather['fahrenheit']}°F"
            f" · {weather['audience']}</p><p><strong>Calendar</strong> · {escape(events)}</p>"
            f"<p><strong>Drafting mode</strong> · {result['mode']}</p>"
        )
        for index, brief in enumerate(result["briefs"], 1):
            posting = datetime.fromisoformat(brief["posting_time"]).strftime("%a %b %d, %I:%M %p ET")
            sources = "".join(f'<li><a href="{escape(source, quote=True)}">{escape(source)}</a></li>'
                              for source in dict.fromkeys(brief["sources"]))
            cards += (
                f"<article><h3>{index}. {escape(brief['hook'])}</h3>"
                f"<p><strong>{escape(brief['product'])}</strong> · Suggested post {posting}</p>"
                f"<p>{escape(brief['concept'])}</p><h4>Script outline</h4>{items(brief['script'])}"
                f"<h4>Shot list</h4>{items(brief['shots'])}<h4>Why this fits</h4>{items(brief['rationale'])}"
                f"<details><summary>Sources</summary><ul>{sources}</ul></details>"
                f"<p><small>{escape(brief['staff_review'])}</small></p></article>"
            )
        cards += f"<details><summary>Agent decisions</summary>{items(result['trace'])}</details>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wushiland Weekly Briefs</title>
<style>
* {{box-sizing:border-box}} body {{margin:0;background:#f6f4ed;color:#242d25;font:16px/1.5 'DM Sans',system-ui,sans-serif}}
main {{max-width:790px;margin:auto;padding:36px 20px}} h1 {{font-size:clamp(2rem,6vw,3.1rem);line-height:1.1}}
form,article {{background:#fff;padding:22px;border:1px solid #dadfd5;border-radius:15px;margin:18px 0}}
label {{display:block;margin:12px 0 5px;font-weight:650}} textarea {{width:100%;min-height:110px}}
input,textarea,button {{font:inherit;padding:8px;border:1px solid #9ca99d;border-radius:6px}}
button {{background:#204b39;color:#fff;cursor:pointer;font-weight:650}} a {{color:#204b39;overflow-wrap:anywhere}}
.actions {{display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin-top:15px}}
.actions label {{margin:0;font-weight:400}} summary {{cursor:pointer}} [role=alert] {{color:#9e1f1f}}
</style></head><body><main>
<h1>Wushiland Weekly Briefs</h1>
<p>Choose a seven-day window, then review the ranked briefs before sending ideas to HQ.</p>
<form method="post">
<label for="start">First day of the week</label><input type="date" id="start" name="start" value="{escape(start)}" required>
<div class="actions"><button type="submit">Generate briefs</button></div>
<small>Try April 12, 2027 for a Spring Carnival example.</small>
</form>
{"<p role='alert'>" + escape(error) + "</p>" if error else ""}
{cards}
</main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def reply(self, page, status=200):
        body = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        self.reply(render(start=str(datetime.now(ET).date())))

    def do_POST(self):
        if self.path != "/":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 64_000:
            self.send_error(400, "Submit a form under 64 KB.")
            return
        form = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
        start = form.get("start", [""])[0]
        try:
            week = date.fromisoformat(start)
            result = generate(week, planner=plan if os.getenv("GEMINI_API_KEY", "").strip() else None)
        except (ValueError, OverflowError) as error:
            self.reply(render(start, error=str(error)), 400)
            return
        self.reply(render(start, result))


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 8000), Handler) as server:
        print("Open http://127.0.0.1:8000", flush=True)
        server.serve_forever()
