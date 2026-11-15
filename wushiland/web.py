"""Run the staff preview on a loopback-only development server."""
import os
from datetime import date, datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .agent import ET, generate
from .llm import plan, review_trends


def render_trend_reviews(result):
    packet = result.get('trend_evidence', {})
    reviews = result.get('trend_reviews', [])
    header = ('<section><h2>Candidate topics & creative drafts</h2>'
              f"<p>Saved snapshot: {escape(str(packet.get('snapshot_at', 'Unavailable')))}. "
              f"{packet.get('evidence_count', 0)} source videos; {len(reviews)} candidates assessed. "
              f"Discovery method: {escape(str(packet.get('discovery_method','keyword-search sample')))}. "
              'Not an independently verified platform-wide trending chart. '
              'Popularity and local audience fit remain unverified.</p>')
    if not reviews:
        return header + '<p>No complete eligible trend evidence. Briefs below use evergreen/local context.</p></section>'
    shown_urls = set()
    reviews = sorted(reviews, key=lambda r: bool(r.get('creative_draft')), reverse=True)
    for r in reviews:
        urls = set(r.get('evidence_urls', []))
        duplicate = bool(urls and urls <= shown_urls)
        compact = duplicate or not r.get('creative_draft')
        if not duplicate:
            shown_urls.update(urls)
        title = str(r['label'])
        if title.isdigit():
            title = 'Audio-based candidate'
        if compact:
            header += '<details><summary>' + escape(title) + (' — shared video evidence' if duplicate else ' — assessment details') + '</summary>'
        label = {'adapt': 'Adapt — staff approval required', 'watch': 'Watch — not approved as a trend', 'reject': 'Do not use'}[r['decision']]
        header += f"<article><h3>{escape(title)}</h3><p><strong>{label}</strong> · {escape(r['review_mode'])}</p>"
        evidence_label='Multi-creator evidence in this sample; not platform-wide verification' if r.get('evidence_level')=='multi_creator_sample' else 'Candidate inspiration — insufficient trend evidence'
        header += f'<p><strong>Evidence level:</strong> {evidence_label}</p>'
        header += '<p><small>Metadata-based assessment: descriptions of the source are unverified until the video is reviewed.</small></p>'
        header += f"<p>{escape(r['reason'])}</p>"
        if r.get('product'):
            header += f"<p>Existing product: {escape(r['product'])}</p>"
        if r.get('adaptation_concept'):
            header += f"<p><strong>Provisional idea:</strong> {escape(r['adaptation_concept'])}</p>"
        draft = r.get('creative_draft')
        if draft:
            header += ('<section><h4>Trend-inspired draft — pending staff review</h4>'
                       '<p>Source: Gemini metadata analysis. The model has not watched the video. '
                       'This proposed shoot is not evidence of a verified trend.</p>'
                       f"<p><strong>Connection to source:</strong> {escape(draft['source_basis'])}</p>"
                       f"<p><strong>Hook:</strong> {escape(draft['hook'])}</p>"
                       f"<h4>Proposed script</h4>{items(draft['script'])}"
                       f"<h4>Proposed shots</h4>{items(draft['shots'])}</section>")
        if r.get('validation_errors'):
            header += '<details><summary>Model response validation</summary>' + items(r['validation_errors']) + '</details>'
        header += f"<p><strong>Next step:</strong> {escape(r['next_step'])}</p>"
        if r['blockers']:
            header += '<details><summary>Evidence checks</summary>' + items(r['blockers']) + '</details>'
        header += '<details><summary>Original videos and metrics</summary><ul>'
        for e in r['evidence']:
            m = e['metrics']
            metrics = ', '.join(f"{k}: {v if v is not None else 'unavailable'}" for k,v in m.items())
            header += (f'<li><a href="{escape(e["source_url"], quote=True)}">Open original video</a> '
                       f'· Published {escape(e["published_at"])} · Observed {escape(e["observed_at"])}'
                       f'<p>{escape(metrics)}</p><p>Platform: {escape(str(e.get("platform","unknown")))}. {escape(str(e.get("source_note","")))}</p></li>')
        header += '</ul></details></article>'
        if compact:
            header += '</details>'
    return header + '<details><summary>Sampling limitations</summary>' + items(packet.get('limitations', [])) + '</details></section>'


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
        if result['mode'] == 'Templates':
            cards += '<p role="alert">Weekly scripts use fallback templates, not a successful AI drafting result. Candidate assessments below have their own status.</p>'
        cards += render_trend_reviews(result)
        if not any(b.get('trend_candidate_id') for b in result['briefs']):
            cards += ('<h2>Evergreen alternatives</h2><p>None of the briefs below adopts a verified trend. '
                      'Review the provisional trend-inspired ideas above separately.</p>')
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
            has_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
            result = generate(week, planner=plan if has_key else None, reviewer=review_trends if has_key else None)
        except (ValueError, OverflowError) as error:
            self.reply(render(start, error=str(error)), 400)
            return
        self.reply(render(start, result))


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 8000), Handler) as server:
        print("Open http://127.0.0.1:8000", flush=True)
        server.serve_forever()
