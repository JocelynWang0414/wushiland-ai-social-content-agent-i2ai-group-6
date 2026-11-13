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

Open [the local staff interface](http://127.0.0.1:8000). Select the first day
of the seven-day planning window. Paste trend-report records if available,
generate briefs, review the evidence and suggested posting windows, and send
selected ideas to HQ for review. For a repeatable demo, enable sample data
and select April 12, 2027. Demo mode uses the first day as its simulated
planning date.

Each trend input needs `title`, `format`, `published` (ISO date), and `source`
(an HTTPS link to a public report). Supported formats are `routine`, `pour`,
`choice`, `pov`, and `checklist`. The agent considers reports from up to 14
days before the selected window, only if they were available on the planning
date. Weeks without eligible entries use evergreen concepts. Public report
links and dates are staff-supplied and should be verified before entry.

## MVP implementation plan and decisions

1. **Inventory.** The original GitHub repository held the project scope and
   workflow documentation. The separate Drive demo implemented Bright Data
   collection, normalization and candidate filtering. The weekly MVP uses
   report inputs to meet the scope boundary around platform data collection.
2. **Inputs.** Seed dated Spring Carnival entries, annual National Tartan
   Day and selected U.S. holidays. National Tartan Day is an observance.
   Add future Carnival dates to `wushiland/data/events.json` as CMU publishes
   them. Seasonal weather and break windows are simulated planning inputs.
   The seed catalog comes from Wushiland's public U.S. menu. Staff should
   confirm Pittsburgh availability. Keep client-only inputs out of Git.
3. **Agent.** Gather calendar, simulated weather, trend-report formats and
   products. Select candidate formats and products, check posting windows,
   draft and review. The agent switches to evergreen timing when event
   timing fails and retries with another product if brand review rejects
   a brief. It ranks the passing briefs by trend evidence, event tie-in
   and seasonal product fit. The interface shows those decisions.
4. **Delivery.** Return up to three ranked briefs with a hook, concept,
   script, shot list, posting time, rationale and source links. Posting
   times are suggested local windows. The conflict check avoids posting
   on the configured holiday dates. Staff still verify store hours,
   event timing, filming consent and HQ approval.
5. **Validation and extension.** Test calendar boundaries, seasonality,
   trend freshness, fallback behavior and brand-review retries. The
   dependency-free MVP uses a deterministic planning loop and editable
   draft templates. The draft function is the integration point for a
   future approved LLM. Review Pittsburgh product availability, approved
   brand language and real report examples with staff before a pilot.
