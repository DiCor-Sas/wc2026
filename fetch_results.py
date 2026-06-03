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


def _parse_espn_friendlies(html):
    """Extract completed friendly scores from ESPN HTML (best-effort JSON blob parsing)."""
    matches = []
    for pattern in [
        r"window\[.?__espnfitt__.?\]\s*=\s*(\{.+?\});\s*</script>",
        r'"scoreboard"\s*:\s*(\{.+?"events".+?\})',
    ]:
        try:
            m = re.search(pattern, html, re.DOTALL)
            if not m:
                continue
            blob = json.loads(m.group(1))
            events = (
                blob.get("page", {}).get("content", {}).get("scoreboard", {}).get("events", [])
                or blob.get("events", [])
                or blob.get("scoreboard", {}).get("events", [])
            )
            for evt in events:
                state = evt.get("status", {}).get("type", {}).get("state", "")
                if state != "post":
                    continue
                comps = evt.get("competitions", [evt])
                for comp in comps:
                    competitors = comp.get("competitors", [])
                    if len(competitors) < 2:
                        continue
                    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                    h_name = _fn(home.get("team", {}).get("displayName", ""))
                    a_name = _fn(away.get("team", {}).get("displayName", ""))
                    if not (_is_wc(h_name) or _is_wc(a_name)):
                        continue
                    try:
                        h_s = int(home.get("score", ""))
                        a_s = int(away.get("score", ""))
                    except (ValueError, TypeError):
                        continue
                    date_str = evt.get("date", "")[:10]
                    matches.append({"date": date_str, "home_team": h_name, "away_team": a_name,
                                    "home_score": h_s, "away_score": a_s})
            if matches:
                break
        except Exception:
            continue
    return matches


def _parse_flashscore_html(html):
    """Extract completed friendly scores from Flashscore HTML (best-effort)."""
    matches = []
    try:
        parts = html.split("¬")
        for i, part in enumerate(parts):
            if ":" not in part or len(part) > 7:
                continue
            scores = part.split(":")
            if len(scores) != 2 or not scores[0].isdigit() or not scores[1].isdigit():
                continue
            h_name = _fn(parts[i - 1].strip()) if i > 0 else ""
            a_name = _fn(parts[i + 1].strip()) if i < len(parts) - 1 else ""
            if not (_is_wc(h_name) or _is_wc(a_name)):
                continue
            matches.append({"date": date.today().isoformat(), "home_team": h_name, "away_team": a_name,
                            "home_score": int(scores[0]), "away_score": int(scores[1])})
    except Exception:
        pass
    return matches


def _parse_bbc_html(html):
    """Extract completed match scores from BBC Sport HTML (best-effort regex)."""
    matches = []
    try:
        pattern = re.compile(
            r'([A-Z][a-zA-Z\s\-\'\.]+?)\s+(\d)\s*[-–]\s*(\d)\s+([A-Z][a-zA-Z\s\-\'\.]+?)(?=\s*<|\s*\n)',
            re.MULTILINE,
        )
        for m in pattern.finditer(html):
            h_name = _fn(m.group(1).strip())
            a_name = _fn(m.group(4).strip())
            if not (_is_wc(h_name) or _is_wc(a_name)):
                continue
            matches.append({"date": date.today().isoformat(), "home_team": h_name, "away_team": a_name,
                            "home_score": int(m.group(2)), "away_score": int(m.group(3))})
    except Exception:
        pass
    return matches


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
    """Fetch completed international friendly results from the last 48h and apply ELO updates."""
    now_utc = datetime.now(timezone.utc)
    cutoff = (now_utc - timedelta(hours=48)).date().isoformat()

    sources = [
        ("espn",       "https://www.espn.com/soccer/scoreboard/_/league/fifa.friendly",            _parse_espn_friendlies),
        ("flashscore", "https://www.flashscoreusa.com/soccer/world/friendly-international/",       _parse_flashscore_html),
        ("bbc",        "https://www.bbc.com/sport/football/scores-fixtures",                       _parse_bbc_html),
    ]

    matches = []
    source_used = "none"

    for src_name, url, parser in sources:
        try:
            html = fetch_url_browser(url)
            parsed = parser(html)
            filtered = [m for m in parsed if m.get("date", "") >= cutoff]
            if filtered:
                matches = filtered
                source_used = src_name
                print(f"[daily] {src_name}: {len(matches)} relevant match(es) found")
                break
            else:
                print(f"[daily] {src_name}: connected but no relevant matches")
        except Exception as e:
            print(f"[daily] {src_name} failed: {e}")

    out = {
        "fetched_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source_used,
        "matches": matches,
    }
    with open(ROOT / "daily_results.json", "w") as f:
        json.dump(out, f, indent=2)

    if not matches:
        print("[daily] Daily results: all sources blocked, no updates")
        return

    # Apply ELO updates with K=20 (friendly weight)
    K_FRIENDLY = 20
    elo_path = ROOT / "elo_ratings.json"
    with open(elo_path) as f:
        elo_data = json.load(f)
    elo = {team: d["elo"] for team, d in elo_data.items()}

    wc_updates = 0
    for m in matches:
        h_team, a_team = m["home_team"], m["away_team"]
        h_s, a_s = m["home_score"], m["away_score"]
        h_wc, a_wc = _is_wc(h_team), _is_wc(a_team)
        if not (h_wc or a_wc):
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
            key=lambda p: p.get("goals", 0) / p["minutes"] * 90,
            reverse=True,
        )
        xi_lower = [n.lower() for n in xi]
        for player in ranked[:3]:
            pname = player.get("name", "")
            if not pname:
                continue
            pname_lower = pname.lower()
            in_xi = any(pname_lower in xi_n or xi_n in pname_lower for xi_n in xi_lower)
            if in_xi:
                continue
            g90 = player.get("goals", 0) / player["minutes"] * 90
            contribution = g90 / 1.5
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
    """Fetch starting lineup via API-Football (primary) or Google search (fallback)."""
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    ctx = ssl.create_default_context()
    lineup_data = None

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

                    lineup_data = {
                        "match": f"{home_team} vs {away_team}",
                        "date": match_date,
                        "kickoff_cot": "",
                        "source": "api-football",
                        "home_xi": _xi(home_lu),
                        "away_xi": _xi(away_lu),
                        "key_absences": [],
                        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
        except Exception as e:
            print(f"[lineup] API-Football failed: {e}")

    if not lineup_data or not (lineup_data.get("home_xi") or lineup_data.get("away_xi")):
        try:
            query = f"{home_team} {away_team} starting lineup World Cup 2026 {match_date}"
            url = "https://www.google.com/search?q=" + query.replace(" ", "+")
            html = fetch_url_browser(url)
            home_xi, away_xi = _parse_lineup_from_html(html, home_team, away_team)
            lineup_data = {
                "match": f"{home_team} vs {away_team}",
                "date": match_date,
                "kickoff_cot": "",
                "source": "web-search" if (home_xi or away_xi) else "none",
                "home_xi": home_xi,
                "away_xi": away_xi,
                "key_absences": [],
                "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        except Exception as e:
            print(f"[lineup] Google fallback failed: {e}")

    if not lineup_data:
        lineup_data = {
            "match": f"{home_team} vs {away_team}",
            "date": match_date,
            "kickoff_cot": "",
            "source": "none",
            "home_xi": [],
            "away_xi": [],
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

    src = lineup_data["source"]
    h_count = len(lineup_data["home_xi"])
    a_count = len(lineup_data["away_xi"])
    print(f"[lineup] {home_team} vs {away_team}: source={src}, home_xi={h_count}, away_xi={a_count}")
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
        print("[lineup-only] Lineup fetch: pending, no matches within 75 min window yet")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--lineup-only" in sys.argv:
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
