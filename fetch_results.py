"""
fetch_results.py
Task 1: Fetch WC 2026 results from openfootball (fallback: worldcup26.ir)
Task 2: Update ELO ratings from completed matches
Task 3: Update bracket state (CONFIRMED / PROJECTED) for all 48 slots
"""

import json
import os
import re
import ssl
import sys
import urllib.request
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

ROOT = Path("/Users/diegofelipecortessastoque/Desktop/wc2026")

# ── WC 2026 groups (from wc_2026_teams.json) ──────────────────────────────────
GROUPS = {
    "A": ["Mexico", "South Korea", "South Africa", "Czechia"],
    "B": ["Canada", "Switzerland", "Qatar", "Bosnia-Herzegovina"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["USA", "Paraguay", "Australia", "Türkiye"],
    "E": ["Germany", "Curaçao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cabo Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Norway", "Iraq"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "Colombia", "Congo DR", "Uzbekistan"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# Which group does each team belong to
TEAM_TO_GROUP = {}
for grp, teams in GROUPS.items():
    for t in teams:
        TEAM_TO_GROUP[t] = grp

WC_TEAMS = {t for teams in GROUPS.values() for t in teams}

FRIENDLY_NAME_MAP = {
    "Korea Republic": "South Korea",
    "Türkiye": "Türkiye", "Turkey": "Türkiye",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Ivory Coast": "Ivory Coast", "Côte d'Ivoire": "Ivory Coast",
    "DR Congo": "Congo DR",
    "USA": "USA", "United States": "USA",
    "IR Iran": "Iran",
    "Cabo Verde": "Cabo Verde", "Cape Verde": "Cabo Verde",
    "Curaçao": "Curaçao", "Curacao": "Curaçao",
    "Czech Republic": "Czechia",
}

SQUAD_SCALE_MIN = 800
SQUAD_SCALE_MAX = 2200

DEFAULT_ELO = 1500.0


def _fn(name):
    return FRIENDLY_NAME_MAP.get(name.strip(), name.strip())


def _is_wc(name):
    return name in WC_TEAMS


# All 6 group-stage matchups (combinatorial) per group — used to check completion
def group_matchups(teams):
    pairs = []
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            pairs.append((teams[i], teams[j]))
    return pairs  # 6 pairs for 4 teams


# ── TASK 1: Fetch results ──────────────────────────────────────────────────────

def fetch_url(url):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "wc2026-dashboard/1.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
        return r.read().decode("utf-8")


def fetch_url_browser(url):
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def _parse_espn_evts_html(html):
    """Parse ESPN's inline evts[] compact format. Only Method 3 — confirmed working."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    decoder = json.JSONDecoder()

    for script in soup.find_all("script"):
        text = script.string or ""
        if '"evts"' not in text or "competitors" not in text:
            continue
        # raw_decode handles scripts with multiple consecutive JSON assignments
        pos = 0
        while pos < len(text):
            start = text.find("{", pos)
            if start < 0:
                break
            try:
                blob, _ = decoder.raw_decode(text, start)
                if isinstance(blob, dict):
                    evts = _find_evts_key(blob)
                    if evts:
                        return _parse_evts_list(evts)
            except Exception:
                pass
            pos = start + 1
    return []


def _find_evts_key(obj):
    """Recursively find the first 'evts' list in a nested dict."""
    if isinstance(obj, dict):
        if "evts" in obj:
            return obj["evts"]
        for v in obj.values():
            result = _find_evts_key(v)
            if result is not None:
                return result
    return None


def _parse_evts_list(evts):
    """Convert ESPN evts[] entries to normalised match dicts, WC teams only."""
    matches = []
    for evt in evts:
        if not isinstance(evt, dict) or not evt.get("completed", False):
            continue
        competitors = evt.get("competitors", [])
        if len(competitors) < 2:
            continue
        home = next((c for c in competitors if c.get("isHome") is True), competitors[0])
        away = next((c for c in competitors if c.get("isHome") is False), competitors[1])
        h_name = _fn(home.get("displayName", home.get("name", home.get("abbrev", ""))))
        a_name = _fn(away.get("displayName", away.get("name", away.get("abbrev", ""))))
        if not (_is_wc(h_name) or _is_wc(a_name)):
            continue
        try:
            h_s = int(home.get("score", ""))
            a_s = int(away.get("score", ""))
        except (ValueError, TypeError):
            continue
        evt_date = (evt.get("date", "") or "")[:10]
        matches.append({"date": evt_date, "home_team": h_name, "away_team": a_name,
                        "home_score": h_s, "away_score": a_s})
    return matches


def _scrape_espn_matches(url):
    """Playwright fallback scraper — only fires when lightweight sources return nothing."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            html = page.content()
            browser.close()
        return _parse_espn_evts_html(html)
    except Exception as e:
        print(f"[playwright] Scraper failed: {e}")
        return []




def parse_openfootball(data):
    """Parse openfootball worldcup.json format into normalized match list."""
    matches = []
    for rnd in data.get("rounds", []):
        round_name = rnd.get("name", "")
        # Determine group from round name e.g. "Matchday 1 (Group A)"
        group = ""
        if "Group" in round_name:
            parts = round_name.split("Group")
            if len(parts) > 1:
                group = parts[-1].strip().rstrip(")")

        for m in rnd.get("matches", []):
            score = m.get("score")
            if not score:
                continue
            ft = score.get("ft")
            if not ft or len(ft) < 2:
                continue
            home_score = ft[0]
            away_score = ft[1]
            if home_score is None or away_score is None:
                continue
            t1 = m.get("team1", {}).get("name", "")
            t2 = m.get("team2", {}).get("name", "")
            if not t1 or not t2:
                continue
            match_date = m.get("date", "")
            matches.append({
                "date": match_date,
                "group": group,
                "round": round_name,
                "team1": t1,
                "team2": t2,
                "home_score": home_score,
                "away_score": away_score,
            })
    return matches


def parse_worldcup26ir(data):
    """Parse worldcup26.ir /get/games response into normalized match list."""
    matches = []
    games = data if isinstance(data, list) else data.get("games", data.get("data", []))
    for m in games:
        # Field names may vary — handle common variants
        home_score = m.get("home_score") or m.get("homeScore") or m.get("score1")
        away_score = m.get("away_score") or m.get("awayScore") or m.get("score2")
        if home_score is None or away_score is None:
            continue
        try:
            home_score = int(home_score)
            away_score = int(away_score)
        except (TypeError, ValueError):
            continue
        t1 = (m.get("home_team") or m.get("homeTeam") or m.get("team1") or "").strip()
        t2 = (m.get("away_team") or m.get("awayTeam") or m.get("team2") or "").strip()
        if not t1 or not t2:
            continue
        match_date = str(m.get("date") or m.get("match_date") or "")
        round_name = str(m.get("round") or m.get("stage") or "")
        group = str(m.get("group") or "")
        matches.append({
            "date": match_date,
            "group": group,
            "round": round_name,
            "team1": t1,
            "team2": t2,
            "home_score": home_score,
            "away_score": away_score,
        })
    return matches


def fetch_results():
    primary_url = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
    fallback_url = "https://worldcup26.ir/get/games"

    source = "openfootball"
    matches = []

    try:
        raw = fetch_url(primary_url)
        data = json.loads(raw)
        matches = parse_openfootball(data)
        print(f"[fetch] openfootball: {len(matches)} completed matches")
    except Exception as e:
        print(f"[fetch] openfootball failed: {e}")
        matches = []

    if not matches:
        source = "worldcup26.ir"
        try:
            raw = fetch_url(fallback_url)
            data = json.loads(raw)
            matches = parse_worldcup26ir(data)
            print(f"[fetch] worldcup26.ir: {len(matches)} completed matches")
        except Exception as e:
            print(f"[fetch] worldcup26.ir failed: {e}")
            matches = []

    # ── Playwright ESPN WC fallback (last resort, only after June 11) ─────────
    today = date.today()
    tournament_started = today >= date(2026, 6, 11)
    if not matches and tournament_started:
        wc_url = (
            f"https://www.espn.com/soccer/scoreboard"
            f"/_/date/{today.strftime('%Y%m%d')}"
            f"/league/fifa.worldcup"
        )
        print("[fetch] Both primary sources empty after June 11 — trying Playwright ESPN WC fallback")
        try:
            pw_matches = _scrape_espn_matches(wc_url)
            if pw_matches:
                source = "espn-playwright-wc"
                # Normalise to wc2026_results.json format
                matches = [
                    {"date": m["date"], "group": "", "round": "",
                     "team1": m["home_team"], "team2": m["away_team"],
                     "home_score": m["home_score"], "away_score": m["away_score"]}
                    for m in pw_matches
                ]
                print(f"[fetch] Playwright ESPN WC fallback: {len(matches)} completed match(es)")
            else:
                print("[fetch] Playwright ESPN WC fallback: no completed WC matches found")
        except Exception as e:
            print(f"[fetch] Playwright ESPN WC fallback failed: {e}")

    # Sort by date
    matches.sort(key=lambda m: m.get("date", ""))

    out_path = ROOT / "wc2026_results.json"
    with open(out_path, "w") as f:
        json.dump(matches, f, indent=2)

    print(f"[fetch] Source used: {source}")
    print(f"[fetch] Total completed matches: {len(matches)}")
    print(f"[fetch] Saved to wc2026_results.json")
    return matches, source


# ── DAILY INTERNATIONAL RESULTS ───────────────────────────────────────────────

def fetch_daily_results():
    """Fetch completed international friendly results for yesterday + today and apply ELO updates.

    Priority chain:
    1. openfootball int.json  (lightweight, checked every run in case it gets published)
    2. Playwright ESPN date-specific scraper  (fallback if openfootball returns 404)
    3. FOX Sports HTML fallback if ESPN Playwright is blocked
    """
    now_utc = datetime.now(timezone.utc)
    today_str   = now_utc.date().strftime("%Y%m%d")
    yesterday_str = (now_utc.date() - timedelta(days=1)).strftime("%Y%m%d")
    cutoff = (now_utc - timedelta(hours=48)).date().isoformat()

    matches = []
    source_used = "none"

    # ── 1. openfootball int.json (primary, lightweight) ───────────────────────
    openfootball_int_url = (
        "https://raw.githubusercontent.com/openfootball/football.json/"
        "master/2026/int.json"
    )
    try:
        raw = fetch_url(openfootball_int_url)
        data = json.loads(raw)
        parsed = []
        for rnd in data.get("rounds", []):
            for m in rnd.get("matches", []):
                ft = m.get("score", {}).get("ft")
                if not ft or len(ft) < 2 or ft[0] is None:
                    continue
                h = _fn(m.get("team1", {}).get("name", ""))
                a = _fn(m.get("team2", {}).get("name", ""))
                if not (_is_wc(h) or _is_wc(a)):
                    continue
                parsed.append({"date": m.get("date", ""), "home_team": h, "away_team": a,
                                "home_score": ft[0], "away_score": ft[1]})
        filtered = [m for m in parsed if m.get("date", "") >= cutoff]
        if filtered:
            matches = filtered
            source_used = "openfootball-int"
            print(f"[daily] openfootball int.json: {len(matches)} relevant match(es) found")
        else:
            print(f"[daily] openfootball int.json: connected but no relevant matches in window")
    except Exception as e:
        print(f"[daily] openfootball int.json: {e} — trying Playwright ESPN fallback")

    # ── 2. Playwright ESPN date-specific scraper (fallback) ───────────────────
    if not matches:
        espn_dates = [yesterday_str, today_str]
        espn_matches = []
        for date_str in espn_dates:
            url = (f"https://www.espn.com/soccer/scoreboard"
                   f"/_/date/{date_str}/league/fifa.friendly")
            try:
                found = _scrape_espn_matches(url)
                filtered = [m for m in found if m.get("date", "") >= cutoff]
                if filtered:
                    espn_matches.extend(filtered)
                    print(f"[daily] ESPN Playwright {date_str}: {len(filtered)} match(es) found")
                else:
                    print(f"[daily] ESPN Playwright {date_str}: no relevant matches")
            except Exception as e:
                print(f"[daily] ESPN Playwright {date_str} failed: {e}")
        # Deduplicate by (date, home_team, away_team)
        seen = set()
        for m in espn_matches:
            key = (m["date"], m["home_team"], m["away_team"])
            if key not in seen:
                seen.add(key)
                matches.append(m)
        if matches:
            source_used = "espn-playwright"
            print(f"[daily] Using Playwright ESPN fallback: {len(matches)} total match(es)")

    # ── 3. FOX Sports HTML fallback if ESPN Playwright blocked ────────────────
    if not matches:
        fox_url = "https://www.foxsports.com/soccer/friendlies-men"
        try:
            html = fetch_url_browser(fox_url)
            # Best-effort score regex: "TeamA N-N TeamB"
            pattern = re.compile(
                r'([A-Z][a-zA-Z\s\-\'\.]+?)\s+(\d+)\s*[-–]\s*(\d+)\s+([A-Z][a-zA-Z\s\-\'\.]+?)(?=\s*[<\n])',
                re.MULTILINE,
            )
            fox_matches = []
            for m in pattern.finditer(html):
                h = _fn(m.group(1).strip())
                a = _fn(m.group(4).strip())
                if not (_is_wc(h) or _is_wc(a)):
                    continue
                fox_matches.append({"date": now_utc.date().isoformat(), "home_team": h, "away_team": a,
                                    "home_score": int(m.group(2)), "away_score": int(m.group(3))})
            if fox_matches:
                matches = fox_matches
                source_used = "foxsports"
                print(f"[daily] FOX Sports fallback: {len(matches)} match(es) found")
            else:
                print("[daily] FOX Sports: connected but no WC team matches parsed")
        except Exception as e:
            print(f"[daily] FOX Sports fallback failed: {e}")

    # Load previously applied match keys to prevent double-counting ELO on re-runs
    daily_path = ROOT / "daily_results.json"
    try:
        with open(daily_path) as f:
            prev = json.load(f)
        applied_keys = set(tuple(k) for k in prev.get("applied_keys", []))
    except Exception:
        applied_keys = set()

    out = {
        "fetched_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source_used,
        "matches": matches,
        "applied_keys": [list(k) for k in applied_keys],  # persisted; updated below
    }
    with open(daily_path, "w") as f:
        json.dump(out, f, indent=2)

    if not matches:
        print("[daily] Daily results: all sources blocked, no updates")
        return

    # Apply ELO updates with K=20 — skip any match already applied in a previous run
    K_FRIENDLY = 20
    elo_path = ROOT / "elo_ratings.json"
    with open(elo_path) as f:
        elo_data = json.load(f)
    elo = {team: d["elo"] for team, d in elo_data.items()}

    wc_updates = 0
    newly_applied = set()
    for m in matches:
        h_team, a_team = m["home_team"], m["away_team"]
        h_s, a_s = m["home_score"], m["away_score"]
        h_wc, a_wc = _is_wc(h_team), _is_wc(a_team)
        if not (h_wc or a_wc):
            continue

        match_key = (m.get("date", ""), h_team, a_team)
        if match_key in applied_keys:
            print(f"[daily] Skipping {h_team} vs {a_team} on {m.get('date','')} — ELO already applied")
            continue

        h_elo = elo.get(h_team, DEFAULT_ELO)
        a_elo = elo.get(a_team, DEFAULT_ELO)

        exp_h = 1.0 / (1.0 + 10 ** ((a_elo - h_elo) / 400.0))
        exp_a = 1.0 - exp_h

        if h_s > a_s:
            act_h, act_a, res_h, res_a = 1.0, 0.0, "win", "loss"
        elif h_s < a_s:
            act_h, act_a, res_h, res_a = 0.0, 1.0, "loss", "win"
        else:
            act_h = act_a = 0.5
            res_h = res_a = "draw"

        new_h = round(h_elo + K_FRIENDLY * (act_h - exp_h), 1)
        new_a = round(a_elo + K_FRIENDLY * (act_a - exp_a), 1)

        if h_wc and h_team in elo:
            elo[h_team] = new_h
            print(f"[daily] {h_team} ELO: {h_elo} → {new_h} after {h_s}-{a_s} {res_h} vs {a_team} (friendly K=20)")
            wc_updates += 1
        if a_wc and a_team in elo:
            elo[a_team] = new_a
            print(f"[daily] {a_team} ELO: {a_elo} → {new_a} after {a_s}-{h_s} {res_a} vs {h_team} (friendly K=20)")
            wc_updates += 1

        newly_applied.add(match_key)

    for team in elo_data:
        if team in elo:
            elo_data[team]["elo"] = elo[team]
    with open(elo_path, "w") as f:
        json.dump(elo_data, f, indent=2)

    # Recalculate team_strength.json for updated teams
    ts_path = ROOT / "team_strength.json"
    with open(ts_path) as f:
        ts = json.load(f)
    for team, s in ts.items():
        if team not in elo_data:
            continue
        new_elo = elo_data[team]["elo"]
        if new_elo == s.get("elo"):
            continue
        s["elo"] = new_elo
        base = (new_elo * 0.50) + (s["fifa_score"] * 0.30) + (s["form_score"] * 0.20)
        squad_elo_like = SQUAD_SCALE_MIN + s["squad_score_norm"] * (SQUAD_SCALE_MAX - SQUAD_SCALE_MIN)
        s["final_strength"] = round(base * 0.70 + squad_elo_like * 0.30, 2)
    with open(ts_path, "w") as f:
        json.dump(ts, f, indent=2)

    # Persist the full set of applied keys (old + new) back to daily_results.json
    all_applied = applied_keys | newly_applied
    out["applied_keys"] = [list(k) for k in all_applied]
    with open(daily_path, "w") as f:
        json.dump(out, f, indent=2)

    print(f"[daily] Daily results: {len(matches)} matches fetched from {source_used}, "
          f"{wc_updates} World Cup team(s) ELO updated")


# ── TASK 2: Update ELO from results ───────────────────────────────────────────

K = 40

def expected_score(elo_a, elo_b):
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def update_elo_from_results():
    results_path = ROOT / "wc2026_results.json"
    elo_path = ROOT / "elo_ratings.json"

    with open(results_path) as f:
        matches = json.load(f)
    with open(elo_path) as f:
        elo_data = json.load(f)

    if not matches:
        print("[elo] No completed matches — ELO unchanged.")
        return

    # Build mutable elo dict {team: elo_value}
    elo = {team: d["elo"] for team, d in elo_data.items()}

    for m in matches:
        t1 = m["team1"]
        t2 = m["team2"]
        hs = m["home_score"]
        as_ = m["away_score"]

        if t1 not in elo or t2 not in elo:
            missing = [t for t in [t1, t2] if t not in elo]
            print(f"[elo] WARNING: team(s) not in elo_ratings.json: {missing} — skipping")
            continue

        e1 = elo[t1]
        e2 = elo[t2]
        exp1 = expected_score(e1, e2)
        exp2 = 1.0 - exp1

        if hs > as_:
            actual1, actual2 = 1.0, 0.0
        elif hs < as_:
            actual1, actual2 = 0.0, 1.0
        else:
            actual1 = actual2 = 0.5

        delta1 = K * (actual1 - exp1)
        delta2 = K * (actual2 - exp2)

        elo[t1] = round(e1 + delta1, 1)
        elo[t2] = round(e2 + delta2, 1)

        print(f"[elo] {t1} {hs}-{as_} {t2}  |  "
              f"{t1}: {e1}→{elo[t1]} ({delta1:+.1f})  "
              f"{t2}: {e2}→{elo[t2]} ({delta2:+.1f})")

    # Write back
    for team in elo_data:
        if team in elo:
            elo_data[team]["elo"] = elo[team]

    with open(elo_path, "w") as f:
        json.dump(elo_data, f, indent=2)

    print(f"[elo] elo_ratings.json updated.")


# ── TASK 3: Bracket state ──────────────────────────────────────────────────────

# FIFA 2026 R32 bracket: maps group positions to match slots
# Format: slot_label -> (team_position_description, match_number)
# Based on run_predictions.py R32_LABELS
R32_SLOTS = [
    # (slot_label, match_num) — positions filled from group results
    {"slot": "Group A 1st", "match": None},
    {"slot": "Group A 2nd", "match": None},
    {"slot": "Group B 1st", "match": None},
    {"slot": "Group B 2nd", "match": None},
    {"slot": "Group C 1st", "match": None},
    {"slot": "Group C 2nd", "match": None},
    {"slot": "Group D 1st", "match": None},
    {"slot": "Group D 2nd", "match": None},
    {"slot": "Group E 1st", "match": None},
    {"slot": "Group E 2nd", "match": None},
    {"slot": "Group F 1st", "match": None},
    {"slot": "Group F 2nd", "match": None},
    {"slot": "Group G 1st", "match": None},
    {"slot": "Group G 2nd", "match": None},
    {"slot": "Group H 1st", "match": None},
    {"slot": "Group H 2nd", "match": None},
    {"slot": "Group I 1st", "match": None},
    {"slot": "Group I 2nd", "match": None},
    {"slot": "Group J 1st", "match": None},
    {"slot": "Group J 2nd", "match": None},
    {"slot": "Group K 1st", "match": None},
    {"slot": "Group K 2nd", "match": None},
    {"slot": "Group L 1st", "match": None},
    {"slot": "Group L 2nd", "match": None},
    # 8 best third-place slots
    {"slot": "3rd Place Best 1", "match": None},
    {"slot": "3rd Place Best 2", "match": None},
    {"slot": "3rd Place Best 3", "match": None},
    {"slot": "3rd Place Best 4", "match": None},
    {"slot": "3rd Place Best 5", "match": None},
    {"slot": "3rd Place Best 6", "match": None},
    {"slot": "3rd Place Best 7", "match": None},
    {"slot": "3rd Place Best 8", "match": None},
]


def get_group_standings(matches, group):
    """Calculate standings for a group from completed matches."""
    teams = GROUPS[group]
    stats = {t: {"pts": 0, "gf": 0, "ga": 0, "played": 0} for t in teams}

    for m in matches:
        if m.get("group", "").strip().upper() != group:
            # Also try to infer group from team names
            t1g = TEAM_TO_GROUP.get(m["team1"])
            t2g = TEAM_TO_GROUP.get(m["team2"])
            if t1g != group or t2g != group:
                continue
        t1, t2 = m["team1"], m["team2"]
        hs, as_ = m["home_score"], m["away_score"]
        if t1 not in stats or t2 not in stats:
            continue
        stats[t1]["gf"] += hs
        stats[t1]["ga"] += as_
        stats[t2]["gf"] += as_
        stats[t2]["ga"] += hs
        stats[t1]["played"] += 1
        stats[t2]["played"] += 1
        if hs > as_:
            stats[t1]["pts"] += 3
        elif hs < as_:
            stats[t2]["pts"] += 3
        else:
            stats[t1]["pts"] += 1
            stats[t2]["pts"] += 1

    return stats


def rank_standings(stats):
    """Sort teams by pts desc, GD desc, GF desc."""
    def key(item):
        t, s = item
        gd = s["gf"] - s["ga"]
        return (-s["pts"], -gd, -s["gf"])
    return sorted(stats.items(), key=key)


def count_group_matches(matches, group):
    """Count how many group-stage matches for this group are in results."""
    count = 0
    for m in matches:
        t1g = TEAM_TO_GROUP.get(m["team1"])
        t2g = TEAM_TO_GROUP.get(m["team2"])
        if t1g == group and t2g == group:
            count += 1
    return count


def update_bracket_state():
    results_path = ROOT / "wc2026_results.json"
    predictions_path = ROOT / "predictions.json"

    with open(results_path) as f:
        results = json.load(f)
    with open(predictions_path) as f:
        predictions = json.load(f)

    # Build bracket state: one entry per qualification slot
    bracket = {}

    # ── Step A: Group standings ────────────────────────────────────────────────
    group_third_place = {}  # group -> {team, stats}

    for group, teams in GROUPS.items():
        played = count_group_matches(results, group)
        group_complete = (played >= 6)

        # Find simulation probabilities for this group's teams
        sim_probs = {t["team"]: t["probability"] for t in predictions.get("all_teams", [])}

        if group_complete:
            stats = get_group_standings(results, group)
            ranked = rank_standings(stats)
            # 1st and 2nd CONFIRMED
            for pos_idx, (team, s) in enumerate(ranked[:2]):
                pos = pos_idx + 1
                pos_label = "1st" if pos == 1 else "2nd"
                slot_key = f"Group {group} {pos_label}"
                gd = s["gf"] - s["ga"]
                result_str = f"W{s['pts']//3} D{s['pts']%3//1} L{3-s['played']+(s['pts']//3)+(s['pts']%3//1)} GF{s['gf']} GA{s['ga']}"
                # Simpler result string
                result_str = f"P{s['played']} Pts{s['pts']} GD{gd:+d} GF{s['gf']}"
                bracket[slot_key] = {
                    "slot": slot_key,
                    "status": "CONFIRMED",
                    "team": team,
                    "probability": 1.0,
                    "qualified_via": f"Group {group} {pos_label}",
                    "result": result_str,
                }
            # 3rd place — may qualify as best third
            if len(ranked) >= 3:
                t3, s3 = ranked[2]
                gd3 = s3["gf"] - s3["ga"]
                group_third_place[group] = {
                    "team": t3,
                    "pts": s3["pts"],
                    "gd": gd3,
                    "gf": s3["gf"],
                    "group": group,
                    "result": f"P{s3['played']} Pts{s3['pts']} GD{gd3:+d} GF{s3['gf']}",
                }
        else:
            # PROJECTED — use simulation probabilities
            for pos, pos_label in [(1, "1st"), (2, "2nd")]:
                slot_key = f"Group {group} {pos_label}"
                # Most probable team for this position based on win prob
                # Use group's teams sorted by sim probability
                group_team_probs = sorted(
                    [(t, sim_probs.get(t, 0)) for t in teams],
                    key=lambda x: -x[1]
                )
                # 1st -> highest prob, 2nd -> second highest
                projected_team, prob = group_team_probs[pos - 1]
                bracket[slot_key] = {
                    "slot": slot_key,
                    "status": "PROJECTED",
                    "team": projected_team,
                    "probability": round(prob / 100, 4),
                    "qualified_via": f"Group {group} {pos_label} (projected)",
                    "result": "",
                }

    # ── Step B: Third-place qualification ─────────────────────────────────────
    all_groups_complete = all(count_group_matches(results, g) >= 6 for g in GROUPS)

    if all_groups_complete and group_third_place:
        # Rank all 12 third-place teams
        thirds = list(group_third_place.values())
        thirds.sort(key=lambda x: (-x["pts"], -x["gd"], -x["gf"]))
        best_8 = thirds[:8]
        for i, t in enumerate(best_8, 1):
            slot_key = f"3rd Place Best {i}"
            bracket[slot_key] = {
                "slot": slot_key,
                "status": "CONFIRMED",
                "team": t["team"],
                "probability": 1.0,
                "qualified_via": f"Best 3rd (Group {t['group']})",
                "result": t["result"],
            }
        # Remaining 4 third-place teams eliminated
        for i, t in enumerate(thirds[8:], 9):
            slot_key = f"3rd Place Best {i}"
            bracket[slot_key] = {
                "slot": slot_key,
                "status": "ELIMINATED",
                "team": t["team"],
                "probability": 0.0,
                "qualified_via": f"3rd place Group {t['group']} — did not advance",
                "result": t["result"],
            }
    else:
        # PROJECTED third-place slots
        sim_probs = {t["team"]: t["probability"] for t in predictions.get("all_teams", [])}
        all_thirds = []
        for group, teams in GROUPS.items():
            # Use 3rd-lowest probability team in each group as projected 3rd place
            group_probs = sorted([(t, sim_probs.get(t, 0)) for t in teams], key=lambda x: -x[1])
            if len(group_probs) >= 3:
                t3, p3 = group_probs[2]
                all_thirds.append((t3, p3, group))
        all_thirds.sort(key=lambda x: -x[1])
        for i, (team, prob, group) in enumerate(all_thirds[:8], 1):
            slot_key = f"3rd Place Best {i}"
            bracket[slot_key] = {
                "slot": slot_key,
                "status": "PROJECTED",
                "team": team,
                "probability": round(prob / 100, 4),
                "qualified_via": f"Best 3rd projected (Group {group})",
                "result": "",
            }

    # ── Step C & D: Knockout rounds — PROJECTED from simulation ───────────────
    # Build knockout slots from predictions knockout_bracket
    kb = predictions.get("knockout_bracket", {})

    # Round of 32
    for m in kb.get("round_of_32", []):
        slot_key = f"R32 M{m['match']}"
        teams = m.get("teams", [])
        likely = m.get("likely_winner", "TBD")
        if teams:
            t1 = teams[0]
            bracket[slot_key] = {
                "slot": slot_key,
                "status": "PROJECTED",
                "team": likely or t1["name"],
                "probability": round((t1.get("overall_win_pct", 0)) / 100, 4) if likely == t1["name"] else
                               round((teams[1].get("overall_win_pct", 0) if len(teams) > 1 else 0) / 100, 4),
                "qualified_via": m.get("label", ""),
                "result": m.get("predicted_score", ""),
            }

    # Round of 16
    for i, m in enumerate(kb.get("round_of_16", []), 1):
        slot_key = f"R16 M{m['match']}"
        likely = m.get("likely_winner", "TBD")
        teams = m.get("teams", [])
        prob = 0.0
        if teams and likely:
            for t in teams:
                if t["name"] == likely:
                    prob = round(t.get("overall_win_pct", 0) / 100, 4)
        bracket[slot_key] = {
            "slot": slot_key,
            "status": "PROJECTED",
            "team": likely or "TBD",
            "probability": prob,
            "qualified_via": "Round of 16",
            "result": m.get("predicted_score", ""),
        }

    # Quarter-finals
    for m in kb.get("quarter_finals", []):
        slot_key = f"QF M{m['match']}"
        likely = m.get("likely_winner", "TBD")
        teams = m.get("teams", [])
        prob = 0.0
        if teams and likely:
            for t in teams:
                if t["name"] == likely:
                    prob = round(t.get("overall_win_pct", 0) / 100, 4)
        bracket[slot_key] = {
            "slot": slot_key,
            "status": "PROJECTED",
            "team": likely or "TBD",
            "probability": prob,
            "qualified_via": "Quarter-final",
            "result": m.get("predicted_score", ""),
        }

    # Semi-finals
    for m in kb.get("semi_finals", []):
        slot_key = f"SF M{m['match']}"
        likely = m.get("likely_winner", "TBD")
        teams = m.get("teams", [])
        prob = 0.0
        if teams and likely:
            for t in teams:
                if t["name"] == likely:
                    prob = round(t.get("overall_win_pct", 0) / 100, 4)
        bracket[slot_key] = {
            "slot": slot_key,
            "status": "PROJECTED",
            "team": likely or "TBD",
            "probability": prob,
            "qualified_via": "Semi-final",
            "result": m.get("predicted_score", ""),
        }

    # Final
    final = kb.get("final", {})
    likely_finalist = final.get("likely_winner", "TBD")
    final_teams = final.get("teams", [])
    final_prob = 0.0
    if final_teams and likely_finalist:
        for t in final_teams:
            if t["name"] == likely_finalist:
                final_prob = round(t.get("overall_win_pct", 0) / 100, 4)
    bracket["Final Winner"] = {
        "slot": "Final Winner",
        "status": "PROJECTED",
        "team": likely_finalist,
        "probability": final_prob,
        "qualified_via": "Final",
        "result": final.get("predicted_score", ""),
    }

    # ── Step E: Dashboard display metadata ────────────────────────────────────
    # Attach display rules to each slot entry
    for key, entry in bracket.items():
        status = entry["status"]
        if status == "CONFIRMED":
            entry["display"] = {
                "color": "confirmed",
                "icon": "✓",
                "label": "CONFIRMED",
                "style": "solid",
            }
        elif status == "PROJECTED":
            pct_str = f"{round(entry['probability'] * 100, 1)}%"
            entry["display"] = {
                "color": "projected",
                "icon": "~",
                "label": f"PROJECTED {pct_str}",
                "style": "muted",
            }
        elif status == "ELIMINATED":
            entry["display"] = {
                "color": "eliminated",
                "icon": "✗",
                "label": "ELIMINATED",
                "style": "strikethrough",
            }

    out_path = ROOT / "bracket_state.json"
    with open(out_path, "w") as f:
        json.dump(bracket, f, indent=2)

    confirmed = sum(1 for e in bracket.values() if e["status"] == "CONFIRMED")
    projected = sum(1 for e in bracket.values() if e["status"] == "PROJECTED")
    print(f"[bracket] {confirmed} CONFIRMED  {projected} PROJECTED  — bracket_state.json saved")
    return bracket


# ── LINEUP FETCH ──────────────────────────────────────────────────────────────

def _is_wc_match(home_team, away_team):
    """Return True if this pair appears in fixtures.json (either order)."""
    try:
        with open(ROOT / "fixtures.json") as f:
            fixtures = json.load(f)
        for fx in fixtures:
            h = _fn(fx.get("home", ""))
            a = _fn(fx.get("away", ""))
            if (h == home_team and a == away_team) or (h == away_team and a == home_team):
                return True
    except Exception:
        pass
    return False


def _espn_find_game_id(match_date_str, home_team, away_team):
    """Find ESPN game ID by scraping the WC scoreboard for a given date."""
    date_nodash = match_date_str.replace("-", "")
    url = (f"https://www.espn.com/soccer/scoreboard"
           f"/_/date/{date_nodash}/league/fifa.worldcup")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            html = page.content()
            browser.close()
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except ImportError:
            return None
        decoder = json.JSONDecoder()
        for script in soup.find_all("script"):
            text = script.string or ""
            if '"evts"' not in text:
                continue
            pos = 0
            while pos < len(text):
                start = text.find("{", pos)
                if start < 0:
                    break
                try:
                    blob, end_pos = decoder.raw_decode(text, start)
                    if isinstance(blob, dict):
                        evts = _find_evts_key(blob)
                        if evts:
                            for evt in evts:
                                competitors = evt.get("competitors", [])
                                names = [
                                    _fn(c.get("displayName", c.get("name", c.get("abbrev", ""))))
                                    for c in competitors
                                ]
                                if home_team in names and away_team in names:
                                    game_id = str(evt.get("id", ""))
                                    if game_id:
                                        print(f"[lineup] ESPN game ID found: {game_id}")
                                        return game_id
                    pos = end_pos
                except Exception:
                    pos = start + 1
    except Exception as e:
        print(f"[lineup] ESPN scoreboard scrape failed: {e}")
    return None


def _extract_lineup_blob(obj, home_team, away_team, depth=0):
    """Recursively search a JSON blob for team starting XI arrays."""
    if depth > 8 or not isinstance(obj, dict):
        return [], []
    home_xi, away_xi = [], []

    # Handle homeTeam/awayTeam or home/away keys
    for home_key, away_key in (("homeTeam", "awayTeam"), ("home", "away")):
        home_obj = obj.get(home_key, {})
        away_obj = obj.get(away_key, {})
        if not isinstance(home_obj, dict) or not isinstance(away_obj, dict):
            continue
        for sub_key in ("startingLineup", "starters", "athletes", "roster"):
            for team_obj, container in ((home_obj, "home"), (away_obj, "away")):
                athletes = team_obj.get(sub_key, [])
                if not isinstance(athletes, list):
                    continue
                names = []
                for a in athletes:
                    if not isinstance(a, dict):
                        continue
                    n = (a.get("displayName") or a.get("name") or
                         (a.get("athlete") or {}).get("displayName") or
                         (a.get("athlete") or {}).get("name") or "")
                    starter = a.get("starter", a.get("isStarter", True))
                    if n and starter is not False:
                        names.append(n)
                if len(names) >= 5:
                    if container == "home":
                        home_xi = names
                    else:
                        away_xi = names
        if home_xi or away_xi:
            return home_xi, away_xi

    # Handle competitors[] array
    competitors = obj.get("competitors", [])
    if isinstance(competitors, list) and len(competitors) >= 2:
        for comp in competitors:
            if not isinstance(comp, dict):
                continue
            cname = _fn(comp.get("displayName", comp.get("name", "")))
            for sub_key in ("startingLineup", "starters", "athletes", "roster"):
                athletes = comp.get(sub_key, [])
                if not isinstance(athletes, list):
                    continue
                names = []
                for a in athletes:
                    if not isinstance(a, dict):
                        continue
                    n = (a.get("displayName") or a.get("name") or
                         (a.get("athlete") or {}).get("displayName") or
                         (a.get("athlete") or {}).get("name") or "")
                    starter = a.get("starter", a.get("isStarter", True))
                    if n and starter is not False:
                        names.append(n)
                if len(names) >= 5:
                    if cname == home_team:
                        home_xi = names
                    elif cname == away_team:
                        away_xi = names
        if home_xi or away_xi:
            return home_xi, away_xi

    # Recurse into nested dicts and lists
    for v in obj.values():
        if isinstance(v, dict):
            h, a = _extract_lineup_blob(v, home_team, away_team, depth + 1)
            if h or a:
                return h, a
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    h, a = _extract_lineup_blob(item, home_team, away_team, depth + 1)
                    if h or a:
                        return h, a
    return [], []


def _parse_espn_lineup_html(html, home_team, away_team):
    """Extract starting XI from ESPN match page HTML."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        decoder = json.JSONDecoder()
        for script in soup.find_all("script"):
            text = script.string or ""
            if not any(k in text for k in ("startingLineup", "starters", "starter", "roster")):
                continue
            pos = 0
            while pos < len(text):
                start = text.find("{", pos)
                if start < 0:
                    break
                try:
                    blob, end_pos = decoder.raw_decode(text, start)
                    if isinstance(blob, dict):
                        h, a = _extract_lineup_blob(blob, home_team, away_team)
                        if h or a:
                            return h, a
                    pos = end_pos
                except Exception:
                    pos = start + 1
    except Exception as e:
        print(f"[lineup] ESPN lineup parse error: {e}")
    return [], []


def _espn_fetch_lineup(game_id, home_team, away_team):
    """Fetch and parse starting XI from ESPN match page given a game ID."""
    url = f"https://www.espn.com/soccer/match/_/gameId/{game_id}"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            html = page.content()
            browser.close()
        return _parse_espn_lineup_html(html, home_team, away_team)
    except Exception as e:
        print(f"[lineup] ESPN match page scrape failed: {e}")
        return [], []


def _parse_bbc_lineup_html(html, home_team, away_team):
    """Extract starting XI from BBC Sport match page HTML."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        decoder = json.JSONDecoder()

        # JSON-LD script tags
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                h, a = _extract_lineup_blob(data if isinstance(data, dict) else {}, home_team, away_team)
                if h or a:
                    return h, a
            except Exception:
                pass

        # Embedded JSON in regular script tags
        for script in soup.find_all("script"):
            text = script.string or ""
            if not any(k in text for k in ("lineup", "startingEleven", "formation", "teamSheet")):
                continue
            pos = 0
            while pos < len(text):
                start = text.find("{", pos)
                if start < 0:
                    break
                try:
                    blob, end_pos = decoder.raw_decode(text, start)
                    if isinstance(blob, dict):
                        h, a = _extract_lineup_blob(blob, home_team, away_team)
                        if h or a:
                            return h, a
                    pos = end_pos
                except Exception:
                    pos = start + 1

        # CSS class-based fallback
        name_re = re.compile(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z\-]+){1,3})\b')
        for cls in ("team-lineups", "starting-eleven", "lineup", "team-sheet"):
            container = soup.find(class_=re.compile(cls, re.I))
            if not container:
                continue
            teams_divs = container.find_all(recursive=False)
            if len(teams_divs) >= 2:
                h_names = list(dict.fromkeys(name_re.findall(teams_divs[0].get_text())))[:11]
                a_names = list(dict.fromkeys(name_re.findall(teams_divs[1].get_text())))[:11]
                if len(h_names) >= 5 or len(a_names) >= 5:
                    return h_names, a_names
    except Exception as e:
        print(f"[lineup] BBC lineup parse error: {e}")
    return [], []


def _bbc_fetch_lineup(match_date_str, home_team, away_team):
    """Find and scrape BBC Sport match page for lineup data."""
    fixtures_url = f"https://www.bbc.com/sport/football/scores-fixtures/{match_date_str}"
    try:
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # Step A: find the match page link
            page = browser.new_page()
            page.goto(fixtures_url, wait_until="domcontentloaded", timeout=30000)
            html = page.content()

            soup = BeautifulSoup(html, "html.parser")
            match_url = None
            home_lower = home_team.lower()
            away_lower = away_team.lower()
            for a_tag in soup.find_all("a", href=True):
                link_text = (a_tag.get_text() or "").strip().lower()
                href = a_tag["href"]
                if (home_lower in link_text and away_lower in link_text
                        and "/sport/football/" in href):
                    match_url = ("https://www.bbc.com" + href
                                 if href.startswith("/") else href)
                    break

            if not match_url:
                browser.close()
                print(f"[lineup] BBC: no match link for {home_team} vs {away_team} on {match_date_str}")
                return [], []

            # Step B: fetch match page
            page2 = browser.new_page()
            page2.goto(match_url, wait_until="domcontentloaded", timeout=30000)
            match_html = page2.content()
            browser.close()

        return _parse_bbc_lineup_html(match_html, home_team, away_team)
    except Exception as e:
        print(f"[lineup] BBC scrape failed: {e}")
        return [], []


def _parse_lineup_from_html(html, home_team, away_team):
    """Best-effort extraction of player name lists from search result HTML."""
    home_xi, away_xi = [], []
    try:
        name_re = re.compile(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z\-]+){1,3})\b')
        # Look for sections mentioning team names then lists of names
        ht_idx = html.lower().find(home_team.lower())
        at_idx = html.lower().find(away_team.lower())
        if ht_idx > 0:
            snippet = html[ht_idx:ht_idx + 1500]
            home_xi = list(dict.fromkeys(name_re.findall(snippet)))[:11]
        if at_idx > 0:
            snippet = html[at_idx:at_idx + 1500]
            away_xi = list(dict.fromkeys(name_re.findall(snippet)))[:11]
    except Exception:
        pass
    return home_xi, away_xi


def _detect_key_absences(lineup_data, home_team, away_team):
    """Detect top-3 player absences and compute lambda penalties. Updates lineup_data in-place."""
    if not (lineup_data.get("home_xi") or lineup_data.get("away_xi")):
        return

    try:
        with open(ROOT / "player_stats.json") as f:
            player_stats = json.load(f)
        with open(ROOT / "team_strength.json") as f:
            team_strength = json.load(f)
    except Exception:
        return

    adjustments = []
    avg_strength = sum(v["final_strength"] for v in team_strength.values()) / max(len(team_strength), 1)

    for team, xi in [(home_team, lineup_data.get("home_xi", [])),
                     (away_team, lineup_data.get("away_xi", []))]:
        if not xi:
            continue
        players = player_stats.get(team, [])
        if not players:
            continue
        ranked = sorted(
            [p for p in players if p.get("minutes", 0) > 0],
            key=lambda p: (p.get("goals", 0) * 0.6 + p.get("assists", 0) * 0.4) / (p["minutes"] / 90),
            reverse=True,
        )
        # Gap 5: log when fewer than 3 players have tracked minutes
        if len(ranked) < 3:
            ts_data = team_strength.get(team, {})
            sq_norm = ts_data.get("squad_score_norm", None)
            sq_str = f"{sq_norm:.3f}" if sq_norm is not None else "N/A"
            print(f"[lineup] {team}: only {len(ranked)} player(s) with tracked minutes "
                  f"(squad_score_norm={sq_str}). "
                  f"{3 - len(ranked)} slot(s) cannot be checked — using proxy contribution=0.25.")
        xi_lower = [n.lower() for n in xi]
        for player in ranked[:3]:
            pname = player.get("name", "")
            if not pname:
                continue
            pname_lower = pname.lower()
            in_xi = any(pname_lower in xi_n or xi_n in pname_lower for xi_n in xi_lower)
            if in_xi:
                continue
            g90 = player.get("goals", 0) / (player["minutes"] / 90)
            a90 = player.get("assists", 0) / (player["minutes"] / 90)
            contribution = (g90 * 0.6 + a90 * 0.4) / 1.5
            penalty = min(contribution * 0.4, 0.30)
            ts = team_strength.get(team, {})
            base_s = ts.get("final_strength", avg_strength)
            base_lambda = max(0.3, min(3.5, 1.5 * (base_s / avg_strength) ** 2.0))
            adj_lambda = round(base_lambda * (1 - penalty), 2)
            print(f"[lineup] ⚠ {pname} not in {team} XI. Lambda adjusted: "
                  f"{base_lambda:.2f} → {adj_lambda:.2f} (-{penalty*100:.0f}%)")
            lineup_data["key_absences"].append({
                "player": pname, "team": team,
                "penalty": round(penalty, 3),
                "base_lambda": round(base_lambda, 2),
                "adjusted_lambda": adj_lambda,
            })
            adjustments.append({
                "match": lineup_data["match"], "date": lineup_data["date"],
                "team": team, "player": pname,
                "base_lambda": round(base_lambda, 2),
                "adjusted_lambda": adj_lambda,
                "penalty_pct": round(penalty * 100, 1),
            })

    if adjustments:
        adj_path = ROOT / "match_adjustments.json"
        try:
            with open(adj_path) as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
        existing = [a for a in existing if a.get("match") != lineup_data["match"]]
        existing.extend(adjustments)
        with open(adj_path, "w") as f:
            json.dump(existing, f, indent=2)


def fetch_lineup(home_team, away_team, match_date):
    """Fetch starting lineup for a WC match via cascading fallback chain.

    Source 1: API-Football
    Source 2: ESPN Playwright (scoreboard → match page)
    Source 3: BBC Sport Playwright (fixtures page → match page)
    Source 4: Graceful degradation (unavailable)

    Returns None if the pair is not a confirmed WC fixture.
    """
    if not _is_wc_match(home_team, away_team):
        print(f"[lineup] {home_team} vs {away_team} is not a WC fixture — skipping")
        return None

    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    ctx = ssl.create_default_context()
    home_xi: list = []
    away_xi: list = []
    source = "unavailable"

    # ── Source 1: API-Football ────────────────────────────────────────────────
    if api_key:
        try:
            fix_url = (f"https://v3.football.api-sports.io/fixtures"
                       f"?date={match_date}&league=1&season=2026")
            req = urllib.request.Request(fix_url, headers={
                "x-apisports-key": api_key,
                "User-Agent": "wc2026-dashboard/1.0",
            })
            with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
                fixtures_resp = json.loads(r.read())

            fixture_id = None
            for fx in fixtures_resp.get("response", []):
                h_name = _fn(fx.get("teams", {}).get("home", {}).get("name", ""))
                a_name = _fn(fx.get("teams", {}).get("away", {}).get("name", ""))
                if h_name == home_team and a_name == away_team:
                    fixture_id = fx.get("fixture", {}).get("id")
                    break

            if fixture_id:
                lu_url = f"https://v3.football.api-sports.io/fixtures/lineups?fixture={fixture_id}"
                req2 = urllib.request.Request(lu_url, headers={
                    "x-apisports-key": api_key,
                    "User-Agent": "wc2026-dashboard/1.0",
                })
                with urllib.request.urlopen(req2, context=ctx, timeout=15) as r:
                    lu_resp = json.loads(r.read())

                lineups = lu_resp.get("response", [])
                if lineups:
                    home_lu = next((l for l in lineups if _fn(l.get("team", {}).get("name", "")) == home_team), None)
                    away_lu = next((l for l in lineups if _fn(l.get("team", {}).get("name", "")) == away_team), None)

                    def _xi(lu_entry):
                        if not lu_entry:
                            return []
                        return [p.get("player", {}).get("name", "") for p in lu_entry.get("startXI", [])]

                    h_xi = _xi(home_lu)
                    a_xi = _xi(away_lu)
                    if len(h_xi) >= 5 or len(a_xi) >= 5:
                        home_xi, away_xi = h_xi, a_xi
                        source = "api-football"
                        print(f"[lineup] API-Football lineup: {len(home_xi)} home, {len(away_xi)} away players")
                    else:
                        print(f"[lineup] API-Football lineup: insufficient data "
                              f"({len(h_xi)} home, {len(a_xi)} away) — trying ESPN")
                else:
                    print(f"[lineup] API-Football lineup: no lineup data for fixture {fixture_id} — trying ESPN")
            else:
                print(f"[lineup] API-Football lineup: fixture not found for "
                      f"{home_team} vs {away_team} on {match_date} — trying ESPN")
        except Exception as e:
            print(f"[lineup] API-Football failed: {e} — trying ESPN")
    else:
        print(f"[lineup] API-Football: no API key — trying ESPN")

    # ── Source 2: ESPN Playwright ─────────────────────────────────────────────
    if not (len(home_xi) >= 5 or len(away_xi) >= 5):
        try:
            game_id = _espn_find_game_id(match_date, home_team, away_team)
            if game_id:
                h_xi, a_xi = _espn_fetch_lineup(game_id, home_team, away_team)
                if len(h_xi) >= 5 or len(a_xi) >= 5:
                    home_xi, away_xi = h_xi, a_xi
                    source = "espn-playwright"
                    print(f"[lineup] ESPN Playwright lineup: found "
                          f"{len(home_xi)} home players, {len(away_xi)} away players")
                else:
                    print(f"[lineup] ESPN Playwright lineup: insufficient data "
                          f"({len(h_xi)} home, {len(a_xi)} away) — trying BBC")
            else:
                print(f"[lineup] ESPN Playwright: game not found on scoreboard — trying BBC")
        except Exception as e:
            print(f"[lineup] ESPN Playwright failed: {e} — trying BBC")

    # ── Source 3: BBC Sport Playwright ────────────────────────────────────────
    if not (len(home_xi) >= 5 or len(away_xi) >= 5):
        try:
            h_xi, a_xi = _bbc_fetch_lineup(match_date, home_team, away_team)
            if len(h_xi) >= 5 or len(a_xi) >= 5:
                home_xi, away_xi = h_xi, a_xi
                source = "bbc-playwright"
                print(f"[lineup] BBC Playwright lineup: found "
                      f"{len(home_xi)} home, {len(away_xi)} away players")
            else:
                print(f"[lineup] BBC Playwright lineup: insufficient data "
                      f"({len(h_xi)} home, {len(a_xi)} away)")
        except Exception as e:
            print(f"[lineup] BBC Playwright failed: {e}")

    # ── Source 4: Graceful degradation ───────────────────────────────────────
    if not (len(home_xi) >= 5 or len(away_xi) >= 5):
        print(f"[lineup] All lineup sources failed for {home_team} vs {away_team}. "
              f"Badge: STARTING XI PENDING")
        source = "unavailable"
        home_xi, away_xi = [], []

    lineup_data = {
        "match": f"{home_team} vs {away_team}",
        "date": match_date,
        "kickoff_cot": "",
        "source": source,
        "home_xi": home_xi,
        "away_xi": away_xi,
        "key_absences": [],
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    _detect_key_absences(lineup_data, home_team, away_team)

    lineups_path = ROOT / "lineups.json"
    try:
        with open(lineups_path) as f:
            all_lineups = json.load(f)
        if not isinstance(all_lineups, list):
            all_lineups = []
    except Exception:
        all_lineups = []

    all_lineups = [l for l in all_lineups
                   if not (l.get("match") == lineup_data["match"] and l.get("date") == lineup_data["date"])]
    all_lineups.append(lineup_data)
    with open(lineups_path, "w") as f:
        json.dump(all_lineups, f, indent=2)

    print(f"[lineup] {home_team} vs {away_team}: source={source}, "
          f"home_xi={len(home_xi)}, away_xi={len(away_xi)}")
    return lineup_data


def _lineup_only_run():
    """Fetch lineups for matches starting within the next 90 minutes (COT)."""
    now_utc = datetime.now(timezone.utc)
    now_cot = now_utc.replace(tzinfo=None) - timedelta(hours=5)

    try:
        with open(ROOT / "fixtures.json") as f:
            fixtures = json.load(f)
    except Exception as e:
        print(f"[lineup-only] Could not load fixtures.json: {e}")
        return

    window_start = now_cot - timedelta(minutes=5)
    window_end = now_cot + timedelta(minutes=90)

    fetched = 0
    for fx in fixtures:
        date_str = fx.get("date", "")
        time_str = fx.get("time", "00:00")
        home = _fn(fx.get("home", "TBD"))
        away = _fn(fx.get("away", "TBD"))
        try:
            h, mi = int(time_str[:2]), int(time_str[3:5])
            ko = datetime(int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]), h, mi)
        except Exception:
            continue
        if window_start <= ko <= window_end:
            print(f"[lineup-only] Fetching {home} vs {away} ({date_str} {time_str} COT)")
            fetch_lineup(home, away, date_str)
            fetched += 1

    if fetched == 0:
        print("[lineup-only] Lineup fetch: pending, no matches within 90 min window yet")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--lineup-only" in sys.argv:
        if "--match" in sys.argv:
            idx = sys.argv.index("--match")
            try:
                forced_home = sys.argv[idx + 1]
                forced_away = sys.argv[idx + 2]
                forced_date = sys.argv[idx + 3]
                print(f"[lineup] Force-fetching lineup: {forced_home} vs {forced_away} on {forced_date}")
                fetch_lineup(forced_home, forced_away, forced_date)
            except IndexError:
                print("[lineup] --match requires three arguments: home_team away_team YYYY-MM-DD")
                sys.exit(1)
        else:
            _lineup_only_run()
        sys.exit(0)

    print("=" * 60)
    print("TASK 1 — Fetching results")
    print("=" * 60)
    matches, source = fetch_results()

    print()
    print("=" * 60)
    print("TASK 2 — Updating ELO ratings")
    print("=" * 60)
    update_elo_from_results()

    print()
    print("=" * 60)
    print("TASK 3 — Updating bracket state")
    print("=" * 60)
    update_bracket_state()

    print()
    print("Done.")
