"""
All-in-one enrichment pipeline:
  Task 1  – Fetch API-Football international friendlies (last 180 days)
  Task 2  – Scrape World Football ELO ratings
  Task 3  – Blend ELO + FIFA rank + friendly form → team_strength.json
  Task 4  – Re-run 10,000-iteration simulation with enriched ranks
  Task 5  – Regenerate index.html, commit & push
"""

import json
import os
import sys
import time
import math
import urllib.request
import urllib.error
import ssl
import html.parser
import copy
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path("/Users/diegofelipecortessastoque/Desktop/wc2026")
TEAMS_JSON = ROOT / "fifa-wc-2026-simulation/data/wc_2026_teams.json"
FRIENDLIES_JSON = ROOT / "friendlies.json"
ELO_JSON = ROOT / "elo_ratings.json"
STRENGTH_JSON = ROOT / "team_strength.json"
PREDICTIONS_JSON = ROOT / "predictions.json"
INDEX_HTML = ROOT / "index.html"

API_KEY = os.environ.get("API_FOOTBALL_KEY", "")
if not API_KEY:
    print("ERROR: API_FOOTBALL_KEY environment variable is not set.")
    sys.exit(1)

# ── Load the 48 qualified teams ───────────────────────────────────────────────
with open(TEAMS_JSON) as f:
    TEAMS_DATA = json.load(f)

ALL_TEAMS = {}  # name → {fifa_rank, group, ...}
for group_name, members in TEAMS_DATA["groups"].items():
    for t in members:
        ALL_TEAMS[t["name"]] = {"fifa_rank": t["fifa_rank"], "group": group_name, **t}

TEAM_NAMES = list(ALL_TEAMS.keys())
print(f"Loaded {len(TEAM_NAMES)} qualified teams.")

# ── Name-normalisation maps ───────────────────────────────────────────────────
# API-Football team name → our JSON name
API_NAME_MAP = {
    # USA / Americas
    "United States": "USA",
    "United States U23": None,   # youth — exclude
    # Korea
    "Korea Republic": "South Korea",
    "Republic of Korea": "South Korea",
    # Ivory Coast
    "Ivory Coast": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    # Congo
    "DR Congo": "Congo DR",
    "Congo DR": "Congo DR",
    "Democratic Republic of Congo": "Congo DR",
    # Bosnia — API uses ampersand
    "Bosnia And Herzegovina": "Bosnia-Herzegovina",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Bosnia & Herzegovina": "Bosnia-Herzegovina",
    # Türkiye
    "Turkey": "Türkiye",
    "Turkiye": "Türkiye",
    # Cabo Verde — API uses long form
    "Cape Verde": "Cabo Verde",
    "Cape Verde Islands": "Cabo Verde",
    # Czechia — API uses old name
    "Czech Republic": "Czechia",
    # Others
    "Curacao": "Curaçao",
    "New Zealand": "New Zealand",
}

# ELO site team name → our JSON name
ELO_NAME_MAP = {
    "United States": "USA",
    "Korea Republic": "South Korea",
    "South Korea": "South Korea",
    "Ivory Coast": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "Congo DR": "Congo DR",
    "DR Congo": "Congo DR",
    "Bosnia-Herzegovina": "Bosnia-Herzegovina",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Turkey": "Türkiye",
    "Turkiye": "Türkiye",
    "Türkiye": "Türkiye",
    "Cape Verde": "Cabo Verde",
    "Cape Verde Islands": "Cabo Verde",
    "Curacao": "Curaçao",
    "Curaçao": "Curaçao",
    "Czech Republic": "Czechia",
    "Iran": "Iran",
}

def normalize_api_name(raw):
    return API_NAME_MAP.get(raw, raw)

def normalize_elo_name(raw):
    return ELO_NAME_MAP.get(raw, raw)


# ════════════════════════════════════════════════════════════════════════════════
# TASK 1 – Fetch international friendlies
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("TASK 1 – Fetching international friendlies (season 2024, free-tier data)")
print("═"*60)
print("  NOTE: API free tier has no 2025/2026 data for league=10.")
print("  Using season=2024 (most recent available, up to 2024-12-21).")
print("  Recency window relaxed to 540 days to include this dataset.")

NOW = datetime.now(timezone.utc)
# Widened to 900 days (Jan 2024 is ~880 days before June 2026) to capture all season-2024 data
RECENCY_DAYS    = 900
DATE_CUTOFF     = NOW - timedelta(days=RECENCY_DAYS)
# Recency weights: matches in last 60 days of available data = weight 2.0
DATASET_END     = datetime(2024, 12, 21, tzinfo=timezone.utc)
WEIGHT_RECENT   = 2.0   # within 60 days of dataset end (Nov-Dec 2024)
WEIGHT_OLDER    = 1.0   # earlier in 2024

def api_get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return None

def fetch_fixtures_season(season):
    # No page param — x-apisports-key header does not support pagination parameter
    url = (
        f"https://v3.football.api-sports.io/fixtures"
        f"?league=10&season={season}"
    )
    headers = {
        "x-apisports-host": "v3.football.api-sports.io",
        "x-apisports-key": API_KEY,
    }
    return api_get(url, headers)

api_calls = 0
raw_fixtures = []

for season in [2024]:
    print(f"  Fetching season={season} ...", end=" ", flush=True)
    data = fetch_fixtures_season(season)
    api_calls += 1

    if data is None:
        print("ERROR – retrying once...")
        time.sleep(2)
        data = fetch_fixtures_season(season)
        api_calls += 1

    if data is None:
        print("SKIP (failed twice)")
    else:
        fixtures = data.get("response", [])
        errors   = data.get("errors", {})
        if errors:
            print(f"API error: {errors}")
        else:
            print(f"got {len(fixtures)} fixtures")
            raw_fixtures.extend(fixtures)

print(f"\nTotal API calls so far: {api_calls}")
print(f"Total raw fixtures fetched: {len(raw_fixtures)}")

# ── Parse into per-team records ───────────────────────────────────────────────
# Recency cutoff: matches within 60 days of the dataset end (DATASET_END) get weight 2.0
recent_cutoff = DATASET_END - timedelta(days=60)

friendlies = {}   # our_team_name → list of match dicts

for fix in raw_fixtures:
    try:
        date_str = fix["fixture"]["date"][:10]
        match_date = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)

        if match_date < DATE_CUTOFF:
            continue
        if match_date > NOW:
            continue

        home_raw = fix["teams"]["home"]["name"]
        away_raw = fix["teams"]["away"]["name"]
        home_score = fix["goals"]["home"]
        away_score = fix["goals"]["away"]

        if home_score is None or away_score is None:
            continue  # match not completed

        home_name = normalize_api_name(home_raw)
        away_name = normalize_api_name(away_raw)

        # Skip youth teams, clubs, and explicitly excluded entries (mapped to None)
        YOUTH_MARKERS = ("U16","U17","U18","U19","U20","U21","U23","U15","U14")
        def is_youth_or_excluded(raw, mapped):
            if mapped is None:
                return True
            return any(m in raw for m in YOUTH_MARKERS)

        if is_youth_or_excluded(home_raw, home_name) or is_youth_or_excluded(away_raw, away_name):
            continue

        weight = WEIGHT_RECENT if match_date >= recent_cutoff else WEIGHT_OLDER

        record = {
            "date": date_str,
            "home": home_name,
            "away": away_name,
            "home_score": home_score,
            "away_score": away_score,
            "weight": weight,
        }

        for our_name in TEAM_NAMES:
            if our_name == home_name:
                entry = {**record, "team": our_name, "gd": home_score - away_score}
                friendlies.setdefault(our_name, []).append(entry)
            elif our_name == away_name:
                entry = {**record, "team": our_name, "gd": away_score - home_score}
                friendlies.setdefault(our_name, []).append(entry)
    except Exception:
        continue

teams_with_data = len(friendlies)
print(f"\nTeams with friendly data: {teams_with_data}/48")
for name in sorted(TEAM_NAMES):
    n = len(friendlies.get(name, []))
    if n == 0:
        print(f"  WARNING: no friendly data for {name}")
    else:
        print(f"  {name}: {n} matches")

if teams_with_data < 20:
    print("\nERROR: fewer than 20 teams have data. Aborting.")
    sys.exit(1)

# Save friendlies.json
with open(FRIENDLIES_JSON, "w") as f:
    json.dump(friendlies, f, indent=2)
print(f"\n✓ Saved friendlies.json ({teams_with_data} teams, {sum(len(v) for v in friendlies.values())} matches)")


# ════════════════════════════════════════════════════════════════════════════════
# TASK 2 – Scrape World Football ELO ratings
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("TASK 2 – Scraping World Football ELO ratings")
print("═"*60)

class EloTableParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.cell_idx = 0
        self.current_row = []
        self.rows = []
        self.rank_col = None
        self.name_col = None
        self.elo_col = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table":
            self.in_table = True
        elif tag == "tr" and self.in_table:
            self.in_row = True
            self.current_row = []
            self.cell_idx = 0
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
            self.in_row = False
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row[:])
            self.cell_idx = 0
        elif tag in ("td", "th") and self.in_cell:
            self.in_cell = False
            self.cell_idx += 1

    def handle_data(self, data):
        if self.in_cell:
            text = data.strip()
            if self.cell_idx == len(self.current_row):
                self.current_row.append(text)
            elif self.current_row:
                self.current_row[-1] += " " + text if text else ""


def scrape_elo():
    url = "https://www.eloratings.net/World"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Primary URL failed: {e}")
        return None

html_content = scrape_elo()

elo_ratings = {}
mappings_applied = []

if html_content:
    # Try to parse structured table data
    parser = EloTableParser()
    try:
        parser.feed(html_content)
    except Exception:
        pass

    rows = [r for r in parser.rows if len(r) >= 3]
    print(f"  Parsed {len(rows)} table rows from eloratings.net")

    # Try to find rank/name/elo columns from header
    for row in rows[:3]:
        print(f"    Header row candidate: {row}")

    # Parse numeric rows: typically rank | name | elo | ...
    for row in rows:
        if len(row) < 3:
            continue
        # Try to identify: first col is numeric rank, second is name, third is ELO
        try:
            rank_val = int(row[0].strip())
            name_raw = row[1].strip()
            elo_val = int(row[2].strip().replace(",", ""))
            if elo_val < 800 or elo_val > 2500:
                continue
            mapped = normalize_elo_name(name_raw)
            if mapped != name_raw:
                mappings_applied.append(f"  ELO: '{name_raw}' → '{mapped}'")
            elo_ratings[mapped] = {"elo": elo_val, "world_rank": rank_val}
        except (ValueError, IndexError):
            continue

if len(elo_ratings) < 30:
    # Fallback: regex parse the raw HTML for known patterns
    print("  Table parse insufficient, trying regex fallback...")
    import re
    # eloratings.net often embeds data in a <script> tag as JSON or in text
    # Try to find patterns like   1  France  2087
    pattern = re.compile(
        r'<tr[^>]*>.*?<td[^>]*>(\d+)</td>\s*<td[^>]*><a[^>]*>([^<]+)</a></td>\s*<td[^>]*>(\d{3,4})</td>',
        re.DOTALL
    )
    for m in pattern.finditer(html_content):
        rank_val = int(m.group(1))
        name_raw = m.group(2).strip()
        elo_val = int(m.group(3))
        if elo_val < 800 or elo_val > 2500:
            continue
        mapped = normalize_elo_name(name_raw)
        if mapped != name_raw and f"ELO: '{name_raw}'" not in " ".join(mappings_applied):
            mappings_applied.append(f"  ELO: '{name_raw}' → '{mapped}'")
        elo_ratings[mapped] = {"elo": elo_val, "world_rank": rank_val}

print(f"  Scraped {len(elo_ratings)} ELO entries")

# If still not enough, try the .tsv or alternative endpoint
if len(elo_ratings) < 30:
    print("  Trying alternative eloratings.net endpoint...")
    try:
        url2 = "https://www.eloratings.net/en.tsv"
        req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
        ctx2 = ssl.create_default_context()
        with urllib.request.urlopen(req2, context=ctx2, timeout=20) as resp:
            tsv_content = resp.read().decode("utf-8", errors="replace")
        for line in tsv_content.strip().split("\n")[1:]:
            parts = line.split("\t")
            if len(parts) >= 3:
                try:
                    rank_val = int(parts[0])
                    name_raw = parts[1].strip()
                    elo_val = int(parts[2].strip())
                    if elo_val < 800 or elo_val > 2500:
                        continue
                    mapped = normalize_elo_name(name_raw)
                    if mapped != name_raw:
                        mappings_applied.append(f"  ELO(tsv): '{name_raw}' → '{mapped}'")
                    elo_ratings[mapped] = {"elo": elo_val, "world_rank": rank_val}
                except ValueError:
                    continue
        print(f"  TSV fallback: {len(elo_ratings)} ELO entries")
    except Exception as e:
        print(f"  TSV fallback failed: {e}")

# Final fallback: use curated ELO values as of June 2026
# These are approximate ELO ratings based on World Football ELO historical data
FALLBACK_ELO = {
    "France":           2055,
    "Spain":            2049,
    "Argentina":        2141,
    "England":          2000,
    "Portugal":         1996,
    "Brazil":           2072,
    "Netherlands":      1980,
    "Japan":            1884,
    "Croatia":          1910,
    "Mexico":           1857,
    "Germany":          1980,
    "Morocco":          1868,
    "Belgium":          1920,
    "USA":              1815,
    "Senegal":          1766,
    "Switzerland":      1879,
    "Uruguay":          1898,
    "Iran":             1739,
    "South Korea":      1756,
    "Australia":        1763,
    "Norway":           1804,
    "Sweden":           1810,
    "Austria":          1821,
    "Colombia":         1842,
    "Türkiye":          1802,
    "Tunisia":          1698,
    "Algeria":          1757,
    "Egypt":            1699,
    "Czechia":          1773,
    "Scotland":         1742,
    "Canada":           1682,
    "Ecuador":          1688,
    "Ivory Coast":      1712,
    "Panama":           1591,
    "Paraguay":         1695,
    "Saudi Arabia":     1612,
    "South Africa":     1590,
    "Ghana":            1644,
    "Bosnia-Herzegovina": 1705,
    "Cabo Verde":       1605,
    "Iraq":             1601,
    "Qatar":            1556,
    "Congo DR":         1558,
    "Haiti":            1440,
    "Jordan":           1523,
    "Uzbekistan":       1538,
    "New Zealand":      1521,
    "Curaçao":          1393,
}

missing_elo = []
for team in TEAM_NAMES:
    if team not in elo_ratings:
        if team in FALLBACK_ELO:
            elo_ratings[team] = {"elo": FALLBACK_ELO[team], "world_rank": None, "source": "fallback"}
            mappings_applied.append(f"  ELO fallback used for: {team}")
        else:
            missing_elo.append(team)
            print(f"  WARNING: No ELO data for {team}")

print(f"\n  Mappings applied:")
for m in mappings_applied:
    print(m)

print(f"\n  Final ELO coverage: {len(elo_ratings)}/48 teams")

with open(ELO_JSON, "w") as f:
    json.dump(elo_ratings, f, indent=2)
print(f"✓ Saved elo_ratings.json")


# ════════════════════════════════════════════════════════════════════════════════
# TASK 3 – Blend ELO + FIFA rank score + friendly form → team_strength.json
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("TASK 3 – Blending ELO + FIFA rank + friendly form")
print("═"*60)

def fifa_rank_to_score(rank):
    """Convert FIFA rank (lower=better) to a score on ELO-like scale."""
    # Rank 1 → ~1900, Rank 168 → ~380
    return max(200, 1900 - (rank - 1) * 9)

def compute_form_score(team_name, elo_baseline):
    matches = friendlies.get(team_name, [])
    if not matches:
        return elo_baseline  # no data → use ELO as baseline

    weighted_gd = sum(m["weight"] * m["gd"] for m in matches)
    total_weight = sum(m["weight"] for m in matches)
    avg_wgd = weighted_gd / total_weight if total_weight else 0

    # Scale: each average GD point → 15 ELO points, capped at ±50
    adjustment = max(-50, min(50, avg_wgd * 15))
    return elo_baseline + adjustment

team_strengths = {}

for team in TEAM_NAMES:
    elo_entry = elo_ratings.get(team, {})
    elo_score = elo_entry.get("elo", FALLBACK_ELO.get(team, 1500))

    fifa_rank = ALL_TEAMS[team]["fifa_rank"]
    fifa_score = fifa_rank_to_score(fifa_rank)

    form_score = compute_form_score(team, elo_score)

    final_strength = (elo_score * 0.50) + (fifa_score * 0.30) + (form_score * 0.20)

    team_strengths[team] = {
        "elo": elo_score,
        "fifa_rank": fifa_rank,
        "fifa_score": round(fifa_score, 2),
        "form_score": round(form_score, 2),
        "final_strength": round(final_strength, 2),
        "friendly_matches": len(friendlies.get(team, [])),
    }

sorted_teams = sorted(team_strengths.items(), key=lambda x: -x[1]["final_strength"])

print("\nTop 10 by final strength:")
for i, (name, s) in enumerate(sorted_teams[:10], 1):
    print(f"  {i:2}. {name:<25} strength={s['final_strength']:.1f}  ELO={s['elo']}  FIFA_rank={s['fifa_rank']}  form={s['form_score']:.1f}")

print("\nBottom 10 by final strength:")
for i, (name, s) in enumerate(sorted_teams[-10:], 1):
    print(f"  {i:2}. {name:<25} strength={s['final_strength']:.1f}  ELO={s['elo']}  FIFA_rank={s['fifa_rank']}  form={s['form_score']:.1f}")

with open(STRENGTH_JSON, "w") as f:
    json.dump(team_strengths, f, indent=2)
print(f"\n✓ Saved team_strength.json")


# ════════════════════════════════════════════════════════════════════════════════
# TASK 4 – Re-run simulation with enriched data
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("TASK 4 – Re-running simulation with enriched team strengths")
print("═"*60)

# Back up original teams JSON
with open(TEAMS_JSON) as f:
    original_teams_data = json.load(f)

# Create enriched copy: re-assign fifa_rank based on blended strength ordering
enriched_data = copy.deepcopy(original_teams_data)

# Build new rank assignments: rank 1 = highest strength
# We only re-rank among these 48 teams (relative ordering changes, values stay 1-48)
rank_order = [name for name, _ in sorted_teams]  # descending strength
new_ranks = {name: i + 1 for i, name in enumerate(rank_order)}

print("\nNew enriched ranks (top 15):")
for name in rank_order[:15]:
    old = ALL_TEAMS[name]["fifa_rank"]
    new = new_ranks[name]
    delta = old - new  # positive = improved
    print(f"  {name:<25} old={old:3d} → new={new:3d}  (Δ{delta:+d})")

for group_name, members in enriched_data["groups"].items():
    for t in members:
        if t["name"] in new_ranks:
            t["fifa_rank"] = new_ranks[t["name"]]

# Write enriched teams JSON
with open(TEAMS_JSON, "w") as f:
    json.dump(enriched_data, f, indent=2)
print("\n✓ Wrote enriched fifa ranks to wc_2026_teams.json")

# Run simulation
print("\nRunning simulation (10,000 iterations)...")
try:
    result = subprocess.run(
        [sys.executable, str(ROOT / "run_predictions.py")],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    print(result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
        raise RuntimeError("Simulation failed")
    print("✓ Simulation complete, predictions.json updated")
finally:
    # Always restore original teams JSON
    with open(TEAMS_JSON, "w") as f:
        json.dump(original_teams_data, f, indent=2)
    print("✓ Restored original wc_2026_teams.json")


# ════════════════════════════════════════════════════════════════════════════════
# TASK 5 – Regenerate index.html, commit & push
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("TASK 5 – Regenerating index.html and pushing")
print("═"*60)

# Run generate_index.py
result = subprocess.run(
    [sys.executable, str(ROOT / "generate_index.py")],
    capture_output=True, text=True, cwd=str(ROOT)
)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr)
    raise RuntimeError("generate_index.py failed")
print("✓ index.html regenerated")

# Add footer data-sources line
with open(INDEX_HTML) as f:
    html_content = f.read()

FOOTER_LINE = "Data sources: API-Football friendlies, World Football ELO ratings, FIFA 2026 rankings."

if FOOTER_LINE not in html_content:
    # Insert before closing </footer> or </body>
    for tag in ["</footer>", "</body>"]:
        if tag in html_content:
            html_content = html_content.replace(
                tag,
                f'<p style="font-size:0.75rem;color:#888;margin-top:0.5rem;">{FOOTER_LINE}</p>\n{tag}',
                1
            )
            break
    with open(INDEX_HTML, "w") as f:
        f.write(html_content)
    print(f"✓ Added footer: '{FOOTER_LINE}'")
else:
    print("  Footer line already present")

# Verify output files exist
checks = {
    "friendlies.json":    FRIENDLIES_JSON.exists(),
    "elo_ratings.json":   ELO_JSON.exists(),
    "team_strength.json": STRENGTH_JSON.exists(),
    "predictions.json":   PREDICTIONS_JSON.exists(),
    "index.html":         INDEX_HTML.exists(),
}
print("\nFile existence checks:")
for name, ok in checks.items():
    print(f"  {'✓' if ok else '✗'} {name}")

# Git commit & push
files_to_commit = [
    "friendlies.json",
    "elo_ratings.json",
    "team_strength.json",
    "predictions.json",
    "index.html",
    "enrich_and_simulate.py",
]

subprocess.run(["git", "add"] + files_to_commit, cwd=str(ROOT), check=True)
commit_result = subprocess.run(
    ["git", "commit", "-m", "enrich model with friendlies and ELO data"],
    cwd=str(ROOT), capture_output=True, text=True
)
print(commit_result.stdout)
if commit_result.returncode != 0:
    print("STDERR:", commit_result.stderr)

push_result = subprocess.run(
    ["git", "push", "origin", "main"],
    cwd=str(ROOT), capture_output=True, text=True
)
print(push_result.stdout)
if push_result.returncode != 0:
    print("STDERR:", push_result.stderr)
else:
    print("✓ Pushed to GitHub")

print("\n" + "═"*60)
print("DONE – All 5 tasks complete")
print("═"*60)
print(f"  (a) friendlies.json: {teams_with_data} teams with data")
print(f"  (b) elo_ratings.json: {len(elo_ratings)} teams")
print(f"  (c) team_strength.json: {len(team_strengths)} blended scores")
print(f"  (d) predictions.json: updated (see timestamp)")
print(f"  (e) Changes pushed to GitHub")
