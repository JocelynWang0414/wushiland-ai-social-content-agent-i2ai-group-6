"""Local tools and a goal-driven weekly brief agent."""
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

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


def trend_lookup(start, end, as_of, reports, demo):
    if not isinstance(reports, list):
        raise ValueError("Trend reports must be a JSON array.")
    cutoff = min(end, as_of)
    matches = {}
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("Each trend report must be a JSON object.")
        title, source = report.get("title"), report.get("source")
        format_name = report.get("format")
        if not isinstance(title, str) or not title.strip() or len(title) > 120 or not isinstance(format_name, str) or format_name not in FORMATS:
            raise ValueError("Trend reports require a title and a supported format.")
        try:
            published = date.fromisoformat(report["published"])
        except (KeyError, ValueError, TypeError) as error:
            raise ValueError("Each trend report needs a YYYY-MM-DD publication date.") from error
        fixture = report.get("fixture", False)
        if not isinstance(fixture, bool):
            raise ValueError("The fixture flag must be a boolean.")
        if fixture and not demo:
            continue
        if not fixture:
            parsed = urlsplit(source or "") if isinstance(source, str) else None
            host = parsed.hostname if parsed else ""
            if (not parsed or parsed.scheme != "https" or not host or "." not in host
                    or parsed.username or parsed.password
                    or any(host == domain or host.endswith("." + domain)
                           for domain in ("tiktok.com", "instagram.com"))):
                raise ValueError("Use an HTTPS public trend-report link outside TikTok and Instagram.")
        if start - DAY * 14 <= published <= cutoff:
            existing = matches.get(format_name)
            if existing is None or published > date.fromisoformat(existing["published"]):
                matches[format_name] = {"title": title.strip(), "format": format_name,
                                        "published": str(published), "source": source if not fixture else "",
                                        "fixture": fixture}
    return list(matches.values())


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
    copy = " ".join([brief["hook"], brief["concept"], *brief["script"], *brief["shots"]]).lower()
    for phrase in ("official partner", "guaranteed", "free boba", "% off", "cures", "film strangers"):
        if phrase in copy:
            problems.append(f"Review required for wording: {phrase}")
    return problems


def draft_brief(product, format_name, trend, event, weather, window):
    hook, direction = FORMATS[format_name]
    occasion = event["name"] if event else f"a {weather['season']} afternoon in Oakland"
    if event:
        hook = f"{occasion} tea break: {hook}"
    elif weather["break_proxy"]:
        hook = f"Staying in Oakland this break? {hook}"
    weather_direction = ("Keep the shoot indoors."
                         if weather["condition"] in {"rainy", "cold"} else "Use daylight near the storefront.")
    seasonal_fit = (product["profile"] == "refreshing") == (weather["condition"] in {"warm", "hot"})
    rank = (3 if trend else 0) + (2 if event else 0) + int(seasonal_fit)
    return {
        "product": product["name"], "format": format_name, "hook": hook,
        "concept": f"{direction} Feature {product['name']} around {occasion}. {weather_direction}",
        "script": [hook, f"Show the {product['name']} handoff.", "Save this for your next Oakland tea break."],
        "shots": ["Open on the storefront or counter.", product["shot"], "Close on the drink and storefront name."],
        "posting_time": window.isoformat(), "audience": weather["audience"], "score": rank,
        "rationale": [f"Audience: {weather['audience']}.",
                      f"Simulated {weather['condition']} weather ({weather['fahrenheit']}°F). {weather_direction}",
                      "Drink profile matches the seasonal preference." if seasonal_fit else "Adds variety to the drink lineup.",
                      ("Event tie-in: " + occasion + ".") if event else "An Oakland concept that works without an event.",
                      ("Demo trend: " if trend and trend["fixture"] else "Report format: ") + trend["title"]
                      if trend else "Evergreen format. No fresh public trend report was used."],
        "sources": [source for source in [product["source"], event["source"] if event else "",
                                         trend["source"] if trend else ""] if source],
        "staff_review": "Confirm Pittsburgh availability, hours, filming consent and HQ approval before publishing.",
    }


def generate(start, reports=None, *, as_of=None, demo=False):
    """Gather evidence and pursue three distinct publishable candidates."""
    as_of = as_of or datetime.now(ET).date()
    end = start + DAY * 6
    if end < as_of:
        raise ValueError("Choose a week that includes today or a future date.")
    events = calendar(start, end)
    weather = seasonal_weather(start)
    catalog = load("products")
    reports = load("trends") if reports is None and demo else ([] if reports is None else reports)
    trends = trend_lookup(start, end, as_of, reports, demo)
    trace = ["Read the calendar, seasonal scenario, product catalog, and eligible trend reports."]
    if not trends:
        trace.append("No eligible trend reports. Switched to evergreen formats.")
    event_options = [event for event in events if event["name"] not in
                     {"Thanksgiving", "Christmas Day", "New Year's Day", "Independence Day"}]
    event_options += [event for event in events if event not in event_options]
    briefs = []
    formats = {trend["format"]: trend for trend in trends}
    for format_name in FORMATS:
        formats.setdefault(format_name, None)
    for attempt, (format_name, trend) in enumerate(formats.items()):
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
            brief = draft_brief(product, format_name, trend, event, weather, window)
            problems = brand_review(brief, catalog)
            if problems:
                trace.append(f"Rejected {format_name} with {product['name']}: {', '.join(problems)}.")
                continue
            briefs.append(brief)
            break
        if len(briefs) == 3:
            break
    trace.append(f"Approved {len(briefs)} of 3 requested briefs after rule-based review.")
    return {"start": str(start), "end": str(end), "as_of": str(as_of), "demo": demo,
            "events": events, "weather": weather, "trends": trends,
            "briefs": sorted(briefs, key=lambda brief: -brief["score"]), "trace": trace}
