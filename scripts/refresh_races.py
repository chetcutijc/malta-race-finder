#!/usr/bin/env python3
"""
Refreshes races-auto.json from the racescalendar.com public ICS feed.

Deliberately does NOT touch races-curated.json. That file is for entries
that needed a human to read the actual event site (like the Malta
Marathon's tiered entry fees) — this script only knows what's in the
feed, so it stays out of that file's way entirely.

Safe-by-default: a failed fetch, an unparsable response, or a
suspiciously small event count all leave the existing races-auto.json
untouched and exit with a non-zero status, so a bad run can't wipe out
good data — it just shows up as a failed run in the Actions tab.

No third-party dependencies, so the workflow doesn't need a pip install
step: everything here is Python 3 standard library.
"""
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

ICS_URL = "https://racescalendar.com/races/list/?ical=1"
OUTPUT_FILE = "races-auto.json"
MIN_EXPECTED_EVENTS = 3  # floor below which we assume parsing broke, not that races dried up

# Checked FIRST, against the event name, regardless of what CATEGORIES
# says. These are strong, unambiguous signals for hybrid/special
# formats — a race literally named "SwimRun" should win over generic
# "Running,Swimming" category tags, which is why this tier exists
# ahead of the category-based rules below.
TYPE_RULES_BY_NAME_STRONG = [
    (r"swimrun", "multisport"),
    (r"\btri(athlon)?\b", "multisport"),
    (r"\brelay\b", "multisport"),
    (r"hyrox", "obstacle"),
    (r"\bocr\b|obstacle|\bgrid\b", "obstacle"),
]

# Checked next, as substrings against the lowercased CATEGORIES field.
TYPE_RULES_BY_CATEGORY = [
    ("triathlon", "multisport"),
    ("hyrox", "obstacle"),
    ("ocr", "obstacle"),
    ("trail running", "trail"),
    ("swimming", "swim"),
    ("road cycling", "bike"),
    ("cycling", "bike"),
    ("road running", "run"),
    ("running", "run"),
]

# Last resort when CATEGORIES is missing or matches nothing above.
TYPE_RULES_BY_NAME_WEAK = [
    (r"trail", "trail"),
    (r"swim", "swim"),
    (r"cycl|\bbike\b|gran fondo|criterium|\btime trial\b", "bike"),
]

DISTANCE_PATTERN = re.compile(r"\b\d{1,4}(?:\.\d+)?\s?(?:km|k|m)\b", re.IGNORECASE)


def fetch(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "malta-race-finder/1.0 (+personal calendar sync, low frequency)"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def unfold(ics_text):
    """RFC 5545 line unfolding: a line starting with a single space or
    tab is a continuation of the previous line."""
    lines = ics_text.replace("\r\n", "\n").split("\n")
    out = []
    for line in lines:
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def unescape(value):
    return (
        value.replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\N", " ")
        .replace("\\n", " ")
        .replace("\\\\", "\\")
        .strip()
    )


def parse_date(value):
    """Accepts DATE (20260809) or DATE-TIME (20260809T070000Z) forms."""
    if not value:
        return None
    m = re.match(r"(\d{4})(\d{2})(\d{2})", value)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_ics(ics_text):
    lines = unfold(ics_text)
    events = []
    cur = None
    for line in lines:
        stripped = line.strip()
        if stripped == "BEGIN:VEVENT":
            cur = {}
            continue
        if stripped == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        key_part, _, value = line.partition(":")
        key = key_part.split(";")[0].strip().upper()
        cur[key] = value
    return events


def classify_type(categories_raw, name):
    lname = (name or "").lower()
    for pattern, t in TYPE_RULES_BY_NAME_STRONG:
        if re.search(pattern, lname):
            return t

    hay = (categories_raw or "").lower()
    for needle, t in TYPE_RULES_BY_CATEGORY:
        if needle in hay:
            return t

    for pattern, t in TYPE_RULES_BY_NAME_WEAK:
        if re.search(pattern, lname):
            return t
    return "run"


def guess_distance(name, description):
    text = f"{name} {description or ''}"
    found = DISTANCE_PATTERN.findall(text)
    seen = []
    for f in found:
        norm = f.strip()
        if norm not in seen:
            seen.append(norm)
    if not seen:
        return None
    return " / ".join(seen[:4])


def slugify(name, date_str):
    base = re.sub(r"[^a-z0-9]+", "-", f"{name}-{date_str}".lower()).strip("-")
    return "auto-" + base[:60]


def build_races(events):
    races = []
    today = date.today()
    for ev in events:
        name = unescape(ev.get("SUMMARY", "")).strip()
        dtstart_raw = ev.get("DTSTART", "")
        start = parse_date(dtstart_raw)
        if not start or not name:
            continue
        if start < today:
            continue  # feed is "upcoming", but be defensive anyway

        end = parse_date(ev.get("DTEND", ""))
        end_date = None
        if end and end > start:
            adjusted = end - timedelta(days=1)  # all-day DTEND is exclusive per RFC 5545
            if adjusted > start:
                end_date = adjusted.isoformat()

        url = unescape(ev.get("URL", "")).strip() or "https://racescalendar.com/"
        location = unescape(ev.get("LOCATION", "")).strip()
        city = location.split(",")[0].strip() if location else "Malta"
        categories = unescape(ev.get("CATEGORIES", ""))
        description = unescape(ev.get("DESCRIPTION", ""))
        description_snippet = description[:220].strip()

        race_type = classify_type(categories, name)
        distance_guess = guess_distance(name, description)
        distance = (
            f"{distance_guess} (auto-detected from listing — confirm on event site)"
            if distance_guess
            else "Check event site for distance"
        )

        races.append(
            {
                "id": slugify(name, dtstart_raw),
                "name": name,
                "date": start.isoformat(),
                "endDate": end_date,
                "type": race_type,
                "distance": distance,
                "city": city or "Malta",
                "country": "Malta",
                "fee": "Check event site",
                "website": url,
                "notes": description_snippet,
                "source": "auto",
            }
        )

    races.sort(key=lambda r: r["date"])
    return races


def main():
    try:
        raw = fetch(ICS_URL)
    except Exception as exc:  # noqa: BLE001 — deliberately broad, this is a scheduled job
        print(f"::error::Fetch failed: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        events = parse_ics(raw)
        races = build_races(events)
    except Exception as exc:  # noqa: BLE001
        print(f"::error::Parsing failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if len(races) < MIN_EXPECTED_EVENTS:
        print(
            f"::error::Only parsed {len(races)} upcoming events (expected at least {MIN_EXPECTED_EVENTS}). "
            "Leaving races-auto.json untouched — the feed format may have changed.",
            file=sys.stderr,
        )
        sys.exit(1)

    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": ICS_URL,
        "races": races,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote {len(races)} races to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
