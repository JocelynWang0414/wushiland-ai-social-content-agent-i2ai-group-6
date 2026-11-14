# Wushiland Weekly Briefs

Plan up to three ranked short-form videos for a Pittsburgh store week.
[Project scope](PROJECT_SCOPE.md) · [Team board](https://github.com/users/JocelynWang0414/projects/1/views/1)

## Run locally

On the `wushiland-weekly-brief-mvp` branch, run `python -m wushiland.web`
and open [localhost:8000](http://127.0.0.1:8000). Use Python 3.10+ with
IANA time zone data. Install `tzdata` if Python cannot find America/New_York.

Set `GEMINI_API_KEY` in the server environment for model drafting. The
default is `gemini-3.5-flash-lite`. Override it with
`WUSHILAND_GEMINI_MODEL`. Without a key, the app uses templates.

## Run in Colab

For model drafting, add `GEMINI_API_KEY` in Colab Secrets and enable
notebook access. Paste this into one cell. It fetches the current MVP
branch and starts the app on a free port.

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

## Generate briefs

Pick a week start and select **Generate briefs**. Try **April 12, 2027**
for Spring Carnival or **July 12, 2027** for simulated summer break. Each
brief includes a hook, concept, script, shots, suggested Eastern Time
posting window, rationale, and sources. **LLM-assisted**, **Mixed**, and
**Templates** indicate how much of the output came from Gemini. Open
**Agent decisions** for review feedback or API errors.

## How it works

| File | Role |
| --- | --- |
| [web.py](wushiland/web.py) | Date form, local server, and results. |
| [agent.py](wushiland/agent.py) | Gathers inputs, checks drafts and posting windows, retries once, fills gaps with templates, and ranks by event and seasonal fit. |
| [llm.py](wushiland/llm.py) | Gemini JSON planning and API diagnostics. |
| [brightdata.py](wushiland/brightdata.py) | Reads saved exports and extracts creative cues and source links. |
| [data/](wushiland/data/) | Spring Carnival dates, public U.S. menu, and bundled Bright Data samples. |

The calendar adds National Tartan Day as an observance and calculates
selected U.S. holidays. Weather and break windows are simulated. Staff
confirm Pittsburgh availability, store hours, filming consent, and HQ approval.

### Use newer Bright Data exports

Set `WUSHILAND_BRIGHTDATA_DIR` to a directory containing `signals.json`
or `trends.json`. In Colab, mount or upload the directory and set
`env["WUSHILAND_BRIGHTDATA_DIR"]` before the server starts. Each request
selects the newest eligible export per file type. Signals guide hooks and
formats. Older references are labeled historical, and missing or unusable
exports fall back to local formats. The app reads saved files without a
Bright Data key. Keep keys and full exports out of Git.

## Test

Run `python -m unittest discover -s tests -v`. Tests use mocked Gemini
responses. For a live check, run both example weeks with a Gemini key
and review grounding, weather fit, and filmability.
