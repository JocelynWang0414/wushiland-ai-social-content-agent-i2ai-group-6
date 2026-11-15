# Wushiland Weekly Briefs — TP2 Integration

This branch integrates Jocelyn's weekly-brief MVP with video-evidence reviews, optional CSV/JSON uploads, and bounded TikTok discovery. It does not replace or merge the original `wushiland-weekly-brief-mvp` branch.

## Quick start

Use Python 3.10+.

```sh
git clone --branch griffin-tp2-integration --single-branch https://github.com/JocelynWang0414/wushiland-ai-social-content-agent-i2ai-group-6.git
cd wushiland-ai-social-content-agent-i2ai-group-6
python -m pip install tzdata
python -m wushiland.app
```

On Windows, you can double-click **START_APP.cmd** instead of running the last command. Open the localhost URL printed in the terminal and keep the server running.

1. Expand **API connections**, enter your Gemini key, and click **Connect for this session**. The default model is `gemini-3-flash-preview`; availability depends on your account.
2. Choose **My uploaded video data** or **Online TikTok discovery**.
3. For uploads, expand **Data sources**, download the CSV template, fill it with real video records, and upload it. UTF-8 CSV and JSON are supported. No Bright Data key is needed.
4. For online TikTok discovery, connect Bright Data too. Recent saved data is reused for 24 hours; otherwise collection uses your provider quota.
5. Select a planning week and click **Generate weekly recommendations**.

Keys entered in the interface remain in server memory. Reconnect after restarting. Do not commit credentials or local runtime data.

## What the output means

- **Candidate topics and creative drafts:** source-linked assessments and provisional ideas for existing menu products.
- **Evergreen alternatives:** separate ideas that do not depend on a verified trend.
- **LLM-assisted / Mixed / Templates:** indicates whether weekly scripts came from Gemini, a mixture, or fallback templates. Candidate assessments have their own status.

The model reads captions, dates and metrics; it does not watch videos. Keyword search results are not an official trending chart. Uploaded Instagram Reel records are supported, but automatic Instagram discovery is not implemented. Weather and break windows are simulated. Staff must verify factual claims, product availability, scheduling, consent and suitability before publication.

## Guides and implementation

- [START_HERE.md](START_HERE.md): detailed startup and data-source instructions.
- [TP2_CHANGES.md](TP2_CHANGES.md): upload fields, changes and limitations.
- [REPAIR_NOTES.md](REPAIR_NOTES.md): response-format and presentation repairs.
- [Project scope](PROJECT_SCOPE.md): original project context.
- [app.py](wushiland/app.py): current interactive server and collection jobs.
- [agent.py](wushiland/agent.py): existing planning logic with evidence integration.
- [data_sources.py](wushiland/data_sources.py): CSV/JSON import.
- [trend_review.py](wushiland/trend_review.py): evidence assessment.
- [llm.py](wushiland/llm.py): Gemini structured responses.

## Colab

The local workflow above is the verified startup path. For Colab, clone **this integration branch**, use `wushiland.app.Handler`, and assign `Application()` to `server.app` in your port-display wrapper. The original MVP Colab snippet uses a different server and must not be copied unchanged. The integration has not been end-to-end tested through Colab's proxy.

## Tests

```sh
python -m unittest discover -s tests -v
```

46 offline/mock tests passed before publication. New tests use clearly labeled synthetic records under `tests/fixtures`; these are not live trend evidence. No new live collection data or credentials were added to this integration branch. A fresh live model run requires your own API connection.
