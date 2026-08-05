# Malta Races

A dashboard of upcoming swim, run, trail and bike races — focused on Malta, with a search you can point at any city and date range for when you're travelling.

`races-auto.json` refreshes itself weekly via GitHub Actions, pulling from racescalendar.com's public calendar feed. No server to run yourself, no build step.

## How it's put together

```
index.html                       the dashboard — fetches both JSON files below and renders them
races-curated.json               hand-checked entries (starts with the Malta Marathon). Never touched by automation.
races-auto.json                  machine-refreshed entries. Overwritten by the workflow below — don't hand-edit.
scripts/refresh_races.py         pulls racescalendar.com's ICS feed and rewrites races-auto.json
.github/workflows/refresh-races.yml   runs the script every Monday, commits if anything changed
test/                            a fixture feed + test suite for the script, no network needed
```

Cards from `races-curated.json` show a small **✓ Hand-checked** tag so you can tell the two sources apart at a glance.

## One-time setup after you upload this

GitHub repos don't allow Actions to push commits by default — you have to turn it on once:

1. **Settings → Actions → General → Workflow permissions** → select **"Read and write permissions"** → Save.
2. **Settings → Pages** → Source: **Deploy from a branch**, branch **main**, folder **/ (root)** → Save. You'll get a `https://<you>.github.io/<repo>/` URL within a minute or two.
3. **Actions tab → "Refresh races" → Run workflow.** Trigger it once by hand rather than waiting for Monday — this both proves the automation works end-to-end and replaces the seeded data (which I wrote by hand today) with a genuinely fresh pull.

**Uploading without git**, if you're doing this from your phone: [github.com/new](https://github.com/new) → create the repo → "uploading an existing file" → drag in everything **except** the `.github` folder, since the web uploader doesn't handle folders starting with a dot well. For that one, either use the git CLI below, or on the repo page use "Add file → Create new file" and type the path `.github/workflows/refresh-races.yml` directly — GitHub will create the folders for you.

**With git, from a computer:**

```bash
cd malta-race-finder
git init && git add . && git commit -m "Malta race finder"
git branch -M main
git remote add origin https://github.com/<you>/malta-race-finder.git
git push -u origin main
```

## What the automation actually does — and its real limits

Every Monday at 06:00 UTC (and any time you hit "Run workflow"), the script fetches racescalendar.com's calendar export, keeps only future events, and rewrites `races-auto.json` from scratch. A few honest caveats:

- **It only knows racescalendar.com.** That's the one Malta race source I found with a feed built for exactly this kind of automated, repeat access — a calendar-subscription export, meant to be polled. The Malta Marathon and the Triathlon Federation's own sites don't offer anything like that (one blocks automated fetches outright), so those stay in the hand-checked file instead of getting picked up automatically.
- **Fees are always "Check event site."** They're not in the feed at all, so the script never invents a number.
- **Distance is a best-effort guess** — the script pattern-matches things like "5km" or "750m" out of the event description. When it can't find anything, it says so plainly rather than leaving a blank.
- **Type (run/trail/swim/etc.) is inferred**, not certain — from the feed's category tags first, then from keywords in the event name. It's tested against known tricky cases (a "SwimRun" correctly lands on multisport rather than trail, for instance — see `test/`), but a genuinely unusual event name could still get filed oddly. Worth a skim after each refresh.
- **It fails safely.** A broken fetch or a suspiciously small result (under 3 events) leaves the existing file alone and exits with an error rather than overwriting good data with bad — you'll see a red ✕ on that run in the Actions tab if that happens. GitHub emails the repo owner when a scheduled run fails, so you'll likely hear about it without needing to check manually. If you get that email, it usually means racescalendar.com changed its page structure — come back and I can take a look at updating `scripts/refresh_races.py`.

None of this applies to `races-curated.json` — that file only ever changes when you or I edit it directly, so anything you want pinned with full confidence (verified fee, exact distance) belongs there.

## Adding a race by hand

Usually to `races-curated.json`, so it doesn't get touched by the next refresh:

```json
{
  "id": "unique-slug-2027",
  "name": "Race name",
  "date": "2027-03-14",
  "endDate": null,
  "type": "run",
  "distance": "10 km",
  "city": "Mosta",
  "country": "Malta",
  "fee": "€20",
  "website": "https://...",
  "notes": "",
  "source": "curated"
}
```

`type` must be one of `run`, `trail`, `swim`, `bike`, `multisport`, `obstacle`. For a trip, just use a different `city`/`country` — the search box and date filter already work across everything in both files, not just Malta.

## Checking the automation script without waiting a week

```bash
python3 test/test_refresh_races.py -v
```

Runs entirely against the sample feed in `test/sample_feed.ics` — no network call, nothing gets written outside a temp directory. Worth running after any edit to `scripts/refresh_races.py`, and a good first thing to check if a scheduled run starts failing.

## Data provenance

Malta Marathon fee and course detail came from maltamarathon.com directly. Everything currently in `races-auto.json` was seeded from a manual pull of racescalendar.com on 5 August 2026, in the same shape the script produces — it'll read as slightly more polished (fuller notes, cleaner distances) than what pure automation turns up, since I hand-wrote this first batch. That gap closes the first time the workflow runs for real.
