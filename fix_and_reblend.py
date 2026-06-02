"""
Fix 2: retry 6 remaining teams (3s sleep, 1 retry max).
Then re-apply Task 2 + Task 3 with corrected Germany score and any new data.
"""

import json, os, sys, time, ssl, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path("/Users/diegofelipecortessastoque/Desktop/wc2026")
KEY  = os.environ.get("API_FOOTBALL_KEY", "")
if not KEY:
    print("ERROR: API_FOOTBALL_KEY not set"); sys.exit(1)

api_calls = 0

def get(url, label=""):
    global api_calls
    api_calls += 1
    print(f"    [call {api_calls}] {label or url}")
    req = urllib.request.Request(url, headers={
        "x-apisports-key":  KEY,
        "x-apisports-host": "v3.football.api-sports.io",
    })
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            data = json.loads(r.read())
        time.sleep(3.0)
        return data
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"    429 rate-limited")
        else:
            print(f"    HTTP {e.code}")
        time.sleep(3.0)
        return {"_error": e.code}
    except Exception as e:
        print(f"    ERROR: {e}")
        time.sleep(3.0)
        return None

# ── Load existing data ────────────────────────────────────────────────────────
with open(ROOT / "player_stats.json") as f:
    ps = json.load(f)

with open(ROOT / "team_strength.json") as f:
    team_strength_raw = json.load(f)

with open(ROOT / "fifa-wc-2026-simulation/data/wc_2026_teams.json") as f:
    wc_data = json.load(f)
ALL_TEAMS = [t["name"] for g, tlist in wc_data["groups"].items() for t in tlist]

# Revert team_strength to pre-Task-3 values (recalculate from components)
team_strength = {}
for team, s in team_strength_raw.items():
    orig = (s["elo"]*0.50) + (s["fifa_score"]*0.30) + (s["form_score"]*0.20)
    team_strength[team] = {k: v for k, v in s.items()
                           if k not in ("squad_score_norm","squad_source")}
    team_strength[team]["final_strength"] = round(orig, 2)

sorted_by_strength = sorted(team_strength.items(), key=lambda x: -x[1]["final_strength"])
strength_order = [name for name, _ in sorted_by_strength]

# ── Fix 2: retry 6 remaining teams ───────────────────────────────────────────
RETRY_6 = ["Uruguay", "Morocco", "Senegal", "Japan", "USA", "Colombia"]
SEARCH_MAP = {"USA": "United States"}
YOUTH_MARKERS = ("U14","U15","U16","U17","U18","U19","U20","U21","U23")

def search_term(name):
    return SEARCH_MAP.get(name, name)

def get_national_id(team_name):
    term = search_term(team_name)
    d = get(f"https://v3.football.api-sports.io/teams?search={urllib.parse.quote(term)}",
            f"teams?search={term}")
    if not d or "_error" in d or not d.get("response"):
        return None, d
    candidates = []
    for t in d["response"]:
        if not t["team"].get("national"):
            continue
        tname = t["team"]["name"]
        if any(m in tname for m in YOUTH_MARKERS):
            continue
        if tname.endswith(" W") or " W " in tname:
            continue
        candidates.append((t["team"]["id"], tname))
    if not candidates:
        return None, d
    for cid, cname in candidates:
        if team_name.lower() in cname.lower() or term.lower() in cname.lower():
            return cid, d
    return candidates[0][0], d

def fetch_players(team_id, team_name):
    d = get(f"https://v3.football.api-sports.io/players?team={team_id}&season=2024",
            f"players?team={team_id} ({team_name})")
    if not d or "_error" in d or not d.get("response"):
        return None
    players = []
    for entry in d["response"]:
        p   = entry["player"]
        sts = entry["statistics"]
        if not sts:
            continue
        goals   = sum((s["goals"].get("total")      or 0) for s in sts)
        assists = sum((s["goals"].get("assists")     or 0) for s in sts)
        mins    = sum((s["games"].get("minutes")     or 0) for s in sts)
        apps    = sum((s["games"].get("appearences") or 0) for s in sts)
        club    = sts[0]["team"]["name"] if sts else "Unknown"
        pos     = sts[0]["games"].get("position","Unknown")
        players.append({
            "name": p["name"], "nationality": p.get("nationality",""),
            "position": pos, "club": club,
            "goals": goals, "assists": assists,
            "minutes": mins, "appearances": apps,
            "g_plus_a": goals + assists,
        })
    top5 = sorted(players, key=lambda x: -x["g_plus_a"])[:5]
    return top5 if top5 else None

print("\n" + "═"*60)
print("FIX 2 – Retrying 6 remaining teams (3s sleep, 1 retry max)")
print("═"*60)

skipped = []
for team_name in RETRY_6:
    print(f"\n  → {team_name}")
    team_id, raw = get_national_id(team_name)
    if team_id is None:
        print(f"    No ID — keeping proxy")
        skipped.append(team_name)
        continue
    print(f"    ID={team_id}")
    players = fetch_players(team_id, team_name)
    if not players:
        print(f"    No player data — keeping proxy")
        skipped.append(team_name)
        continue
    ps[team_name] = players
    total_ga = sum(p["g_plus_a"] for p in players)
    print(f"    ✓ {len(players)} players  G+A={total_ga}")
    for p in players:
        print(f"      {p['name']} ({p['club']})  G={p['goals']} A={p['assists']}")

print(f"\nFix 2 API calls: {api_calls}")
print(f"Skipped (keeping proxy): {skipped}")

with open(ROOT / "player_stats.json", "w") as f:
    json.dump(ps, f, indent=2)
print("✓ player_stats.json saved")

# ════════════════════════════════════════════════════════════════════════════════
# TASK 2 — Recompute all squad scores including Germany correction
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("TASK 2 – Recomputing squad strength (all teams)")
print("═"*60)

def squad_score_from_players(players):
    # Skip placeholder entries (Germany manual correction)
    real = [p for p in players if p.get("minutes", 0) > 0]
    if not real:
        return None
    total_goals   = sum(p["goals"]       for p in real)
    total_assists = sum(p["assists"]     for p in real)
    total_mins    = sum(p["minutes"]     for p in real)
    total_apps    = sum(p["appearances"] for p in real)
    n = len(real)
    if total_mins == 0:
        return None
    g_per_90  = total_goals   / (total_mins / 90)
    a_per_90  = total_assists / (total_mins / 90)
    min_ratio = min(1.0, (total_mins / n) / 90)
    app_ratio = min(1.0, (total_apps / n) / 38)
    return round((g_per_90*0.40) + (a_per_90*0.20) + (min_ratio*0.20) + (app_ratio*0.20), 6)

squad_scores_raw = {}

# Pull pre-stored Germany corrected score
de_corrected = ps.get("Germany_corrected_raw_score")

for team, players in ps.items():
    if team == "Germany_corrected_raw_score":
        continue
    if team == "Germany":
        if de_corrected is not None:
            squad_scores_raw["Germany"] = de_corrected
            print(f"  {'Germany':<25} {de_corrected:.4f}  [manual: club form proxy]")
        continue
    s = squad_score_from_players(players)
    if s is not None:
        squad_scores_raw[team] = s

print("\nAll real squad scores:")
for team, s in sorted(squad_scores_raw.items(), key=lambda x: -x[1]):
    src = "[manual]" if team == "Germany" else ""
    print(f"  {team:<25} {s:.4f}  {src}")

# Normalise to [0,1]
min_s = min(squad_scores_raw.values())
max_s = max(squad_scores_raw.values())
span  = (max_s - min_s) if max_s != min_s else 1.0
squad_scores_norm = {t: (v - min_s) / span for t, v in squad_scores_raw.items()}

# Assign proxies for remaining teams
squad_strength = {}
proxy_log = []

# First pass: teams with real data
for team in ALL_TEAMS:
    if team in squad_scores_norm:
        squad_strength[team] = {
            "squad_score":      squad_scores_raw[team],
            "squad_score_norm": round(squad_scores_norm[team], 6),
            "source": "manual correction: club form proxy" if team == "Germany" else "api",
        }

# Second pass: proxies (iterate by strength so neighbours are resolved first)
for team in strength_order:
    if team in squad_strength:
        continue
    my_idx = strength_order.index(team)
    best_proxy, best_dist = None, 9999
    for other, vals in squad_strength.items():
        if "proxy" not in vals["source"]:   # only use real/manual as proxy sources
            other_idx = strength_order.index(other) if other in strength_order else 9999
            dist = abs(other_idx - my_idx)
            if dist < best_dist:
                best_dist, best_proxy = dist, other
    if best_proxy is None and squad_scores_norm:
        best_proxy = next(iter(squad_scores_norm)); best_dist = 99
    if best_proxy:
        squad_strength[team] = {
            "squad_score":      squad_scores_raw[best_proxy],
            "squad_score_norm": round(squad_scores_norm[best_proxy], 6),
            "source":           f"proxy:{best_proxy}",
        }
        proxy_log.append(f"  {team:<25} ← proxy:{best_proxy} (dist={best_dist})")
    else:
        squad_strength[team] = {"squad_score": 0.0, "squad_score_norm": 0.0, "source": "no_data"}

print(f"\nProxy assignments ({len(proxy_log)}):")
for p in proxy_log:
    print(p)

with open(ROOT / "squad_strength.json", "w") as f:
    json.dump(squad_strength, f, indent=2)
print(f"\n✓ squad_strength.json saved ({len(squad_strength)} teams)")

# ════════════════════════════════════════════════════════════════════════════════
# TASK 3 — Re-blend squad layer into team_strength.json
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("TASK 3 – Re-blending squad layer into team_strength.json")
print("═"*60)

SQUAD_SCALE_MIN = 800
SQUAD_SCALE_MAX = 2200

for team in ALL_TEAMS:
    current        = team_strength[team]["final_strength"]
    norm           = squad_strength[team]["squad_score_norm"]
    squad_elo_like = SQUAD_SCALE_MIN + norm * (SQUAD_SCALE_MAX - SQUAD_SCALE_MIN)
    new_strength   = (current * 0.70) + (squad_elo_like * 0.30)
    team_strength[team]["squad_score_norm"] = squad_strength[team]["squad_score_norm"]
    team_strength[team]["squad_source"]     = squad_strength[team]["source"]
    team_strength[team]["final_strength"]   = round(new_strength, 2)

updated_sorted = sorted(team_strength.items(), key=lambda x: -x[1]["final_strength"])

print("\nTop 10 by updated final strength:")
for i, (name, s) in enumerate(updated_sorted[:10], 1):
    icon = "✅" if s["squad_source"] in ("api","manual correction: club form proxy") else "⚠️ "
    print(f"  {i:2}. {name:<25} strength={s['final_strength']:.1f}  {icon} {s['squad_source']}")

print("\nBottom 10 by updated final strength:")
for i, (name, s) in enumerate(updated_sorted[-10:], 1):
    icon = "✅" if s["squad_source"] in ("api","manual correction: club form proxy") else "⚠️ "
    print(f"  {i:2}. {name:<25} strength={s['final_strength']:.1f}  {icon} {s['squad_source']}")

# Spotlight the 4 teams we asked about
print("\nSpotlight ranks:")
for i, (name, s) in enumerate(updated_sorted, 1):
    if name in ("Germany","Uruguay","Colombia","Japan"):
        icon = "✅" if s["squad_source"] in ("api","manual correction: club form proxy") else "⚠️ "
        print(f"  {i:2}. {name:<25} strength={s['final_strength']:.1f}  {icon} {s['squad_source']}")

with open(ROOT / "team_strength.json", "w") as f:
    json.dump(team_strength, f, indent=2)
print("\n✓ team_strength.json saved")

# ── Summary ───────────────────────────────────────────────────────────────────
real_count  = sum(1 for v in squad_strength.values()
                  if v["source"] in ("api","manual correction: club form proxy"))
proxy_count = sum(1 for v in squad_strength.values() if "proxy" in v["source"])
print(f"\n{'─'*60}")
print(f"  player_stats.json : {len([k for k in ps if k != 'Germany_corrected_raw_score'])} team entries")
print(f"  Squad sources     : {real_count} real/manual  |  {proxy_count} proxy  |  48 total")
print(f"  Fix 2 API calls   : {api_calls}")
print()
print("━"*60)
print("STOPPED — waiting for your confirmation to run Task 4.")
print("Reply with 'confirmed' to rerun the simulation.")
print("━"*60)
