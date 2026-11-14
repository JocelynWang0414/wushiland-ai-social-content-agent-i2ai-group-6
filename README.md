# Wushiland AI Social Content Agent — I2AI Group 6

Prototype AI-assisted social content planning tool for Wushiland.

## Project Management

- [GitHub Kanban Board](https://github.com/users/JocelynWang0414/projects/1/views/1)
- [Project Scope](./PROJECT_SCOPE.md)

## Current Workstreams

- Client requirements and brand materials
- Trend-data/API investigation
- Trend and local-context retrieval
- AI content recommendation workflow
- Brand-fit and safety guardrails
- User interface
- Evaluation and client feedback
- Final documentation and presentation

## Board Workflow

Recommended status flow:

**Backlog → To Do → In Progress → Client Review / Blocked → Done**

Issues in this repository are the team's trackable work items. Each issue includes a suggested initial status and completion criteria.

## Run the weekly brief MVP

Use Python 3.10+ with the system IANA time zone database available.
From the repository root:

```sh
python -m wushiland.web
python -m unittest discover -s tests -v
```

Open [the local staff interface](http://127.0.0.1:8000), choose the first
day of a seven-day window, and select **Generate briefs**. April 12, 2027
is a Spring Carnival scenario. The app works with local templates by default.

### Enable the model

Set `OPENAI_API_KEY` before launching the server. The default model is
`gpt-4.1-mini`; set `WUSHILAND_MODEL` to override it. In Colab, add
`OPENAI_API_KEY` to notebook Secrets, grant the notebook access, and put
the following before the existing server launch. Restart the runtime or
stop any prior server first.

```python
import os
from google.colab import userdata
os.environ["OPENAI_API_KEY"] = userdata.get("OPENAI_API_KEY")
```

The model receives only the selected dates and bundled public product and
calendar context plus simulated weather. Keep private client inputs out of
the model request and repository. The interface reports Templates, Mixed,
or LLM-assisted based on the drafts that passed review.

### Agent workflow and evaluation

1. Read the date window, public calendar entries, simulated Pittsburgh weather
   and break audience, and public U.S. menu. Confirm Pittsburgh menu
   availability with staff. Tartan Day is an observance.
2. Ask the model for three distinct, filmable ideas grounded in those inputs.
3. Validate product, event, format, shot and script structure, posting dates
   and flagged wording. Retry once with feedback and approved formats. Fill
   gaps with reviewed templates. Holiday timing uses configured dates and
   suggested local windows. Staff confirm store hours and HQ approval.
4. Rank by event tie-in and seasonal product fit. Show the supporting signals,
   source links, and validation decisions.

Local tests exercise a rainy Carnival week, a winter break crossing years,
Tartan Day, a hot summer week, model rejection and retry, and fallback.
Programmed model replies test orchestration. To evaluate live reasoning,
run Carnival and a July break week with the API enabled and score each
brief from 0 to 2 on calendar accuracy, audience and weather fit, product
grounding, and filmability. A useful pilot target is 7/8 with zero invented
events or products, promotions, and unsupported local-availability claims.
Review model rationales and creative copy manually, since the brand checks
cover known wording patterns and structured fields.
