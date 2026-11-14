# Wushiland Weekly Briefs

A staff-facing prototype for planning short-form videos around a selected
seven-day window in Pittsburgh. [Project scope](PROJECT_SCOPE.md) ·
[Team board](https://github.com/users/JocelynWang0414/projects/1/views/1)

## Run locally

From the repository root, use Python 3.10+ with IANA time zone data
(including America/New_York). The app uses the Python standard library.
On Windows, install `tzdata` if Python cannot find the time zone.

```sh
python -m wushiland.web
```

Open [localhost:8000](http://127.0.0.1:8000). To enable Gemini, set
`GEMINI_API_KEY` in the server environment before launch. The default is
`gemini-3.5-flash-lite`. Set `WUSHILAND_GEMINI_MODEL` to override it.
With no key, the app uses local templates.

## Run in Google Colab

Add the `GEMINI_API_KEY` secret and enable notebook access for Gemini mode.
Paste this into one cell. It checks out the current MVP branch and binds
to a free port, so it works alongside an older server on port 8000.

```python
import os
import subprocess
import sys
from pathlib import Path
from tempfile import mkdtemp

from google.colab import output, userdata

repo = "https://github.com/JocelynWang0414/wushiland-ai-social-content-agent-i2ai-group-6.git"
app_dir = Path(mkdtemp(prefix="wushiland-"))
subprocess.run(
    ["git", "clone", "--quiet", "--branch", "wushiland-weekly-brief-mvp", repo, str(app_dir)],
    check=True,
)

env = os.environ.copy()
if not env.get("GEMINI_API_KEY", "").strip():
    try:
        env["GEMINI_API_KEY"] = userdata.get("GEMINI_API_KEY")
    except (userdata.SecretNotFoundError, userdata.NotebookAccessError):
        print("Gemini secret unavailable. Template mode is ready.")

previous = globals().get("wushiland_server")
if previous is not None and previous.poll() is None:
    previous.terminate()
    previous.wait(timeout=5)

wushiland_server = subprocess.Popen(
    [sys.executable, "-u", "-c", """
from http.server import ThreadingHTTPServer
from wushiland.web import Handler
with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
    print(server.server_port)
    server.serve_forever()
"""],
    cwd=app_dir, env=env, stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT, text=True,
)
port = wushiland_server.stdout.readline().strip()
if not port.isdigit():
    raise RuntimeError(port + "\n" + wushiland_server.stdout.read())
output.serve_kernel_port_as_iframe(int(port), height=850)
```

## Staff workflow

Choose the first date of a week and select **Generate briefs**. Start with
April 12, 2027 for Spring Carnival or July 12, 2027 for a hot summer-break
scenario. The app returns up to three ranked ideas with a hook, concept,
three script beats, three shots, a suggested Eastern Time posting window,
rationale, and source links. Open **Agent decisions** to review validation
feedback and any Gemini API errors. Staff confirm store hours, local menu
availability, filming consent, and HQ approval before publishing.

- **LLM-assisted** means Gemini drafted all displayed briefs.
- **Mixed** means Gemini drafted some briefs and templates filled gaps.
- **Templates** means no Gemini drafts passed or Gemini was unavailable.

## Implementation

| File | Responsibility |
| --- | --- |
| `wushiland/web.py` | Loopback HTTP server, date form, input handling, result rendering, and planner selection. |
| `wushiland/agent.py` | Calendar and seasonal lookups, candidate validation, retry and template fallback, posting-window selection, and ranking. |
| `wushiland/llm.py` | Gemini native JSON request, brief extraction, and request diagnostics. |
| `wushiland/data/events.json` | Dated Spring Carnival entries with sources. Add future dates once CMU publishes them. |
| `wushiland/data/products.json` | Public U.S. menu seed catalog, product profiles, and shot suggestions. |
| `tests/test_mvp.py` | Calendar, audience, orchestration, and Gemini adapter regression tests. |

The agent sends the selected week, event and catalog records, simulated
weather, approximate break audience, and allowed formats to Gemini. It
checks product and event names, distinct formats, script and shot structure,
suggested dates, and flagged wording. It can request one revision with
validation feedback, then fills remaining slots with templates. Ranking
uses event tie-in and seasonal product fit. Human review still covers
creative plausibility and brand claims.

National Tartan Day is represented as an annual observance. Selected U.S.
holidays are calculated locally. Weather and academic break windows are
simulated. Trend-report ingestion and Bright Data are outside the current
implementation. Keep API keys and private client inputs out of Git.

## Test

```sh
python -m unittest discover -s tests -v
```

The suite stubs model responses and HTTP calls and needs no credentials.
For a live check, run both staff scenarios with a key and inspect the
drafting mode and decision log. Score each brief 0–2 on calendar accuracy,
audience and weather fit, product grounding, and filmability. A pilot
target is 7/8 with zero invented products, events, or promotions.
