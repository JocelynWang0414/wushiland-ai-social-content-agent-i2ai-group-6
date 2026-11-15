"""Local tools and a goal-driven weekly brief agent."""
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .brightdata import load_creative_signals
from .trend_review import load_trend_evidence, assess_trends

DATA = Path(__file__).parent / "data"
ET = ZoneInfo("America/New_York")
DAY = timedelta(days=1)
FORMATS = {
    "routine": ("Three stops, one tea break", "Cut from the outing to the storefront to the first sip."),
    "pour": ("A closer look at your tea break", "Open with a tight pour shot and cut to the finished drink."),
    "choice": ("Pick your next tea break", "Show two ways to frame the same drink, then ask viewers to pick a shot."),
    "pov": ("POV: You found your Oakland tea stop", "Film the approach and handoff from the customer's point of view."),
    "checklist": ("Add a tea stop to your Oakland plans", "Use three on-screen checklist beats ending with the drink."),
}


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def calendar(start, end):
    events = load("events")
    for year in range(start.year, end.year + 1):
        november = date(year, 11, 1)
        thanksgiving = november + DAY * ((3 - november.weekday()) % 7 + 21)
        holidays = [
            ("New Year's Day", date(year, 1, 1)),
            ("National Tartan Day", date(year, 4, 6)),
            ("Independence Day", date(year, 7, 4)),
            ("Thanksgiving", thanksgiving),
            ("Christmas Day", date(year, 12, 25)),
        ]
        for name, day in holidays:
            source = ("https://www.govinfo.gov/app/details/BILLS-105sres155rs"
                      if name == "National Tartan Day"
                      else "https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/")
            events.append({"name": name, "start": str(day), "end": str(day), "source": source})
    return sorted(
        (event for event in events if event["start"] <= str(end) and event["end"] >= str(start)),
        key=lambda event: event["start"],
    )


def seasonal_weather(start):
    midpoint = start + DAY * 3
    month = midpoint.month
    season, condition, temperature = {
        12: ("winter", "cold", 34), 1: ("winter", "cold", 31), 2: ("winter", "cold", 36),
        3: ("spring", "cool", 47), 4: ("spring", "rainy", 56), 5: ("spring", "mild", 66),
        6: ("summer", "warm", 77), 7: ("summer", "hot", 84), 8: ("summer", "warm", 81),
        9: ("fall", "mild", 72), 10: ("fall", "cool", 59), 11: ("fall", "cool", 48),
    }[month]
    break_proxy = month in (6, 7) or month == 12 and midpoint.day >= 20 or month == 1 and midpoint.day <= 10
    audience = "Oakland neighbors and local workers" if break_proxy else "CMU students and Oakland visitors"
    return {"season": season, "condition": condition, "fahrenheit": temperature,
            "audience": audience, "break_proxy": break_proxy, "source": "Simulated Pittsburgh weather and approximate break windows"}


def posting_window(start, end, events, event, as_of, attempt):
    earliest = max(start, as_of)
    if event and date.fromisoformat(event["end"]) < earliest:
        return None
    last = min(end, date.fromisoformat(event["end"])) if event else end
    preferred = max(earliest, date.fromisoformat(event["start"]) - DAY) if event else earliest
    blocked = {date.fromisoformat(item["start"]) for item in events
               if item["name"] in {"Thanksgiving", "Christmas Day", "New Year's Day", "Independence Day"}}
    candidates = [preferred + DAY * offset for offset in range((last - preferred).days + 1)
                  if preferred + DAY * offset not in blocked]
    if not candidates:
        return None
    index = min(attempt, len(candidates) - 1)
    return datetime.combine(candidates[index], datetime.strptime("15:00" if attempt % 2 == 0 else "12:00", "%H:%M").time(), ET)


def brand_review(brief, catalog):
    problems = []
    if brief["product"] not in {product["name"] for product in catalog}:
        problems.append("Product is missing from catalog")
    if len(brief["shots"]) != 3 or len(brief["script"]) != 3:
        problems.append("Brief does not contain three production beats")
    copy = " ".join([brief["hook"], brief["concept"], *brief["script"], *brief["shots"], *brief["rationale"]]).lower()
    for phrase in ("official partner", "guaranteed", "free boba", "% off", "cures", "film strangers"):
        if phrase in copy:
            problems.append(f"Review required for wording: {phrase}")
    return problems


def draft_brief(product, format_name, event, weather, window):
    hook, direction = FORMATS[format_name]
    occasion = event["name"] if event else f"a {weather['season']} afternoon in Oakland"
    if event:
        hook = f"{occasion} tea break: {hook}"
    elif weather["break_proxy"]:
        hook = f"Staying in Oakland this break? {hook}"
    weather_direction = ("Keep the shoot indoors."
                         if weather["condition"] in {"rainy", "cold"} else "Use daylight near the storefront.")
    seasonal_fit = (product["profile"] == "refreshing") == (weather["condition"] in {"warm", "hot"})
    rank = (2 if event else 0) + int(seasonal_fit)
    return {
        "product": product["name"], "format": format_name, "hook": hook,
        "concept": f"{direction} Feature {product['name']} around {occasion}. {weather_direction}",
        "script": [hook, f"Show the {product['name']} handoff.", "Save this for your next Oakland tea break."],
        "shots": ["Open on the storefront or counter.", product["shot"], "Close on the drink and storefront name."],
        "posting_time": window.isoformat(), "audience": weather["audience"], "score": rank,
        "rationale": [f"Audience: {weather['audience']}.",
                      f"Simulated {weather['condition']} weather ({weather['fahrenheit']}°F). {weather_direction}",
                      "Drink profile matches the seasonal preference." if seasonal_fit else "Adds variety to the drink lineup.",
                      ("Event tie-in: " + occasion + ".") if event else "An Oakland concept that works without an event."],
        "sources": [product["source"]] + ([event["source"]] if event else []),
        "staff_review": "Confirm Pittsburgh availability, hours, filming consent and HQ approval before publishing.",
    }


def generate(start, *, as_of=None, planner=None, reviewer=None):
    """Gather evidence and pursue three distinct publishable candidates."""
    as_of = as_of or datetime.now(ET).date()
    end = start + DAY * 6
    if end < as_of:
        raise ValueError("Choose a week that includes today or a future date.")
    events = calendar(start, end)
    weather = seasonal_weather(start)
    catalog = load("products")
    trace = ["Read the calendar, seasonal scenario, and product catalog."]
    signals = load_creative_signals(as_of, trace)
    trend_packet = load_trend_evidence(as_of, trace)
    trend_reviews = assess_trends(trend_packet, catalog, reviewer, trace)
    briefs = []
    if planner:
        briefs = model_briefs(planner, start, end, as_of, events, weather, catalog, signals, trace, trend_packet, trend_reviews)
    model_count = len(briefs)
    event_options = [event for event in events if event["name"] not in
                     {"Thanksgiving", "Christmas Day", "New Year's Day", "Independence Day"}]
    event_options += [event for event in events if event not in event_options]
    signal_formats = {signal["format"]: signal for signal in reversed(signals)}
    formats = dict.fromkeys([*signal_formats, *FORMATS])
    for attempt, format_name in enumerate(formats):
        if len(briefs) >= 3:
            break
        if any(brief["format"] == format_name for brief in briefs):
            continue
        event = event_options[attempt % len(event_options)] if event_options else None
        window = posting_window(start, end, events, event, as_of, attempt)
        if window is None and event:
            trace.append(f"Switched {format_name} to evergreen timing because its event window was unavailable.")
            event = None
            window = posting_window(start, end, events, None, as_of, attempt)
        if window is None:
            trace.append(f"Skipped {format_name}: no eligible posting date.")
            continue
        warm = weather["condition"] in {"warm", "hot"}
        ordered = sorted(catalog, key=lambda product: (product["profile"] == "refreshing") != warm)
        used = {brief["product"] for brief in briefs}
        ordered.sort(key=lambda product: product["name"] in used)
        for product in ordered:
            brief = draft_brief(product, format_name, event, weather, window)
            add_reference(brief, signal_formats.get(format_name))
            problems = brand_review(brief, catalog)
            if problems:
                trace.append(f"Rejected {format_name} with {product['name']}: {', '.join(problems)}.")
                continue
            briefs.append(brief)
            break
        if len(briefs) == 3:
            break
    trace.append(f"Approved {len(briefs)} of 3 requested briefs after rule-based review.")
    mode = "LLM-assisted" if model_count == len(briefs) and model_count else "Mixed" if model_count else "Templates"
    return {"start": str(start), "end": str(end), "as_of": str(as_of), "mode": mode,
            "events": events, "weather": weather,
            "briefs": sorted(briefs, key=lambda brief: -brief["score"]), "trace": trace,
            "trend_evidence": trend_packet, "trend_reviews": trend_reviews}


def model_briefs(planner, start, end, as_of, events, weather, catalog, signals, trace, trend_packet, trend_reviews):
    evidence = {"week": [str(start), str(end)], "planning_date": str(as_of),
                "events": events, "weather": weather, "products": catalog,
                "formats": list(FORMATS), "trend_evidence": trend_packet, "trend_reviews": trend_reviews, "creative_signals": [
                    {key: signal[key] for key in ("id", "format", "cue")} for signal in signals]}
    approved = []
    feedback = []
    for attempt in range(2):
        try:
            candidates = planner(evidence, feedback, [brief["format"] for brief in approved])
        except ValueError as error:
            trace.append(str(error))
            from .llm import ResponseFormatError
            if isinstance(error, ResponseFormatError) and attempt == 0:
                feedback = ['Return a complete JSON object matching the supplied schema. Keep every field concise.']
                trace.append('Retrying malformed model output once; no new collection.')
                continue
            break
        feedback = []
        for candidate in candidates[:5]:
            brief, problem = validate_candidate(candidate, evidence, start, end, as_of, attempt, approved, signals)
            if problem:
                feedback.append(problem)
            else:
                approved.append(brief)
            if len(approved) == 3:
                break
        trace.append(f"Model round {attempt + 1}: {len(approved)} approved; {len(feedback)} rejected.")
        trace.extend(feedback)
        if len(approved) == 3:
            return approved
    trace.append("Filled remaining slots with reviewed templates where possible.")
    return approved


def validate_candidate(candidate, evidence, start, end, as_of, attempt, approved, signals):
    if not isinstance(candidate, dict):
        return None, "Each proposed brief must be a JSON object."
    catalog, events, weather = evidence["products"], evidence["events"], evidence["weather"]
    product = next((item for item in catalog if item["name"] == candidate.get("product")), None)
    event_name = candidate.get("event")
    event = next((item for item in events if item["name"] == event_name), None)
    format_name = candidate.get("format")
    if (not product or (event_name is not None and not event)
            or not isinstance(format_name, str) or format_name not in FORMATS or any(brief["format"] == format_name for brief in approved)):
        return None, "Choose an exact catalog product, an available event or null, and an unused format."
    fields = ("hook", "concept", "why")
    lists = ("script", "shots")
    if any(not valid_text(candidate.get(field)) for field in fields):
        return None, "Provide a concise hook, concept, and evidence-based reason."
    for field in lists:
        values = candidate.get(field)
        if not isinstance(values, list) or len(values) != 3 or not all(map(valid_text, values)):
            return None, "Provide exactly three text beats for both script and shots."
    window = posting_window(start, end, events, event, as_of, attempt + len(approved))
    if window is None:
        return None, "The event has no eligible posting window. Try another event or use null."
    brief = draft_brief(product, format_name, event, weather, window)
    brief.update({field: candidate[field] for field in ("hook", "concept", *lists)})
    brief["rationale"].append(candidate["why"])
    signal_id = candidate.get("creative_signal_id")
    if signal_id is not None:
        signal = next((item for item in signals if item["id"] == signal_id and item["format"] == format_name), None)
        if signal is None:
            return None, "Use a supplied creative signal ID matching the format, or use null."
        add_reference(brief, signal)
    trend_id = candidate.get('trend_candidate_id')
    if trend_id is not None:
        review = next((r for r in evidence.get('trend_reviews', []) if r['candidate_id'] == trend_id), None)
        if not review or review['decision'] != 'adapt' or review['product'] != product['name']:
            return None, 'Use only an eligible adapt decision with its exact reviewed product, or set trend_candidate_id to null.'
        brief['sources'].extend(review['evidence_urls'])
        brief['rationale'].append('Trend adaptation: ' + review['reason'])
        brief['trend_candidate_id'] = trend_id
    else:
        brief['trend_candidate_id'] = None
    problems = brand_review(brief, catalog)
    if problems:
        return None, ", ".join(problems)
    return brief, None


def valid_text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 600


def add_reference(brief, signal):
    if signal:
        age = "Historical example. " if signal["historical"] else ""
        brief["rationale"].append(f"{age}{signal['label']} {signal['cue']} Snapshot: {signal['snapshot']}.")
        brief["sources"].append(signal["url"])
