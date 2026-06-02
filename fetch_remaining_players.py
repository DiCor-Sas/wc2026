"""
Fetch player stats for the 11 remaining priority teams (slow mode: 1s between calls).
Merges results into existing player_stats.json, then re-runs Tasks 2 and 3.
Stops before Task 4.
"""

import json, os, sys, time, ssl, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path("/Users/diegofelipecortessastoque/Desktop/wc2026")
KEY  = os.environ.get("API_FOOTBALL_KEY", "")
if not KEY:
    print("ERROR: API_FOOTBALL_KEY not set"); sys.exit(1)

api_calls = 0
CALL_LOG  = []

def get(url, label=""):
    global api_calls
    api_calls += 1
    tag = f"[call {api_calls}] {label or url}"
    print(f"    {tag}")
    CALL_LOG.append(tag)
    req = urllib.request.Request(url, headers={
        "x-apisports-key":  KEY,
        "x-apisports-host": "v3.football.api-sports.io",
    })
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            data = json.loads(r.read())
        time.sleep(1.0)   # 1-second pause after EVERY call
        return data
    except Exception as e:
        print(f"    ERROR: {e}")
        time.sleep(1.0)
        return None

# ── Load existing player data (keep Argentina, France, Brazil, Spain, England) ─
with open(ROOT / "player_stats.json") as f:
    player_stats = json.load(f)
print(f"Existing player data: {list(player_stats.keys())}")

# ── Load supporting data ──────────────────────────────────────────────────────
with open(ROOT / "team_strength.json") as f:
    team_strength = json.load(f)

with open(ROOT / "fifa-wc-2026-simulation/data/wc_2026_teams.json") as f:
    wc_data = json.load(f)
ALL_TEAMS = [t["name"] for g, tlist in wc_data["groups"].items() for t in tlist]

sorted_by_strength = sorted(team_strength.items(), key=lambda x: -x[1]["final_strength"])
strength_order = [name for name, _ in sorted_by_strength]

# ── 11 teams still needed ─────────────────────────────────────────────────────
MISSING_11 = [
    "Portugal", "Netherlands", "Germany", "Croatia", "Belgium",
    "Uruguay", "Morocco", "Senegal", "Japan", "USA", "Colombia",
]

SEARCH_MAP = {
    "USA": "United States",
}
YOUTH_MARKERS = ("U14","U15","U16","U17","U18","U19","U20","U21","U23")

def search_term(name):
    return SEARCH_MAP.get(name, name)

def get_national_id(team_name):
    term = search_term(team_name)
    d = get(f"https://v3.football.api-sports.io/teams?search={urllib.parse.quote(term)}",
            f"teams?search={term}")
    if not d or not d.get("response"):
        return None
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
        return None
    for cid, cname in candidates:
        if team_name.lower() in cname.lower() or term.lower() in cname.lower():
            return cid
    return candidates[0][0]

def fetch_players(team_id, team_name):
    d = get(f"https://v3.football.api-sports.io/players?team={team_id}&season=2024",
            f"players?team={team_id} ({team_name})")
    if not d or d.get("errors") or not d.get("response"):
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
        pos     = sts[0]["games"].get("position", "Unknown") if sts else "Unknown"
        players.append({
            "name": p["name"], "nationality": p.get("nationality",""),
            "position": pos, "club": club,
            "goals": goals, "assists": assists,
            "minutes": mins, "appearances": apps,
            "g_plus_a": goals + assists,
        })
    top5 = sorted(players, key=lambda x: -x["g_plus_a"])[:5]
    return top5 if top5 else None

# ════════════════════════════════════════════════════════════════════════════════
# TASK 1 (continued) — fetch 11 remaining teams
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("TASK 1 – Fetching 11 remaining priority teams (1s delay)")
print("═"*60)

no_data = []
for team_name in MISSING_11:
    print(f"\n  → {team_name}")
    team_id = get_national_id(team_name)
    if team_id is None:
        print(f"    No ID found — skipping")
        no_data.append(team_name)
        continue
    print(f"    ID={team_id}")

    players = fetch_players(team_id, team_name)
    if not players:
        print(f"    No player data — skipping")
        no_data.append(team_name)
        continue

    player_stats[team_name] = players
    total_ga = sum(p["g_plus_a"] for p in players)
    print(f"    {len(players)} players  G+A={total_ga}")
    for p in players:
        print(f"      {p['name']} ({p['club']})  G={p['goals']} A={p['assists']}")

print(f"\nTotal API calls this run: {api_calls}")
print(f"Teams now with data: {len(player_stats)}: {sorted(player_stats.keys())}")
if no_data:
    print(f"Still no data: {no_data}")

with open(ROOT / "player_stats.json", "w") as f:
    json.dump(player_stats, f, indent=2)
print("✓ player_stats.json updated")

# ════════════════════════════════════════════════════════════════════════════════
# TASK 2 — Recompute squad strength for all 48 teams
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("TASK 2 – Computing squad strength scores")
print("═"*60)

def squad_score(players):
    if not players:
        return None
    total_goals   = sum(p["goals"]       for p in players)
    total_assists = sum(p["assists"]     for p in players)
    total_mins    = sum(p["minutes"]     for p in players)
    total_apps    = sum(p["appearances"] for p in players)
    n = len(players)
    if total_mins == 0:
        return None
    g_per_90  = total_goals   / (total_mins / 90)
    a_per_90  = total_assists / (total_mins / 90)
    min_ratio = min(1.0, (total_mins / n) / 90)
    app_ratio = min(1.0, (total_apps / n) / 38)
    score = (g_per_90 * 0.40) + (a_per_90 * 0.20) + (min_ratio * 0.20) + (app_ratio * 0.20)
    return round(score, 6)

squad_scores_raw = {}
print("\nReal API scores:")
for team, players in player_stats.items():
    s = squad_score(players)
    if s is not None:
        squad_scores_raw[team] = s
        print(f"  {team:<25} {s:.4f}")

# Normalise to [0,1]
min_s = min(squad_scores_raw.values())
max_s = max(squad_scores_raw.values())
span  = max_s - min_s if max_s != min_s else 1.0
squad_scores_norm = {t: (v - min_s) / span for t, v in squad_scores_raw.items()}

# Assign proxies for remaining 32 teams
squad_strength = {}
proxy_log = []

for team in ALL_TEAMS:
    if team in squad_scores_norm:
        squad_strength[team] = {
            "squad_score":      squad_scores_raw[team],
            "squad_score_norm": round(squad_scores_norm[team], 6),
            "source":           "api",
        }

# Second pass: assign proxies (iterate sorted list so neighbours already resolved)
for team in strength_order:
    if team in squad_strength:
        continue
    my_idx = strength_order.index(team)
    best_proxy, best_dist = None, 9999
    for other, vals in squad_strength.items():
        if vals["source"] == "api":
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
for p in proxy_log: print(p)

with open(ROOT / "squad_strength.json", "w") as f:
    json.dump(squad_strength, f, indent=2)
print(f"\n✓ squad_strength.json saved ({len(squad_strength)} teams)")

# ════════════════════════════════════════════════════════════════════════════════
# TASK 3 — Blend squad layer into team_strength.json
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("TASK 3 – Blending squad strength into team_strength.json")
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
    src = "✅" if s["squad_source"] == "api" else "⚠️ "
    print(f"  {i:2}. {name:<25} strength={s['final_strength']:.1f}  {src} {s['squad_source']}")

print("\nBottom 10 by updated final strength:")
for i, (name, s) in enumerate(updated_sorted[-10:], 1):
    src = "✅" if s["squad_source"] == "api" else "⚠️ "
    print(f"  {i:2}. {name:<25} strength={s['final_strength']:.1f}  {src} {s['squad_source']}")

with open(ROOT / "team_strength.json", "w") as f:
    json.dump(team_strength, f, indent=2)
print("\n✓ team_strength.json updated")

# ── Final checks ──────────────────────────────────────────────────────────────
real_count  = sum(1 for v in squad_strength.values() if v["source"] == "api")
proxy_count = sum(1 for v in squad_strength.values() if "proxy" in v["source"])
print(f"\n{'─'*60}")
print(f"  (a) player_stats.json: {len(player_stats)} teams with real data")
print(f"      API: {real_count}  Proxy: {proxy_count}  Total: {len(squad_strength)}/48")
print(f"  (b) squad_strength.json: {len(squad_strength)}/48 teams ✓")
print(f"  (c) team_strength.json: squad layer applied ✓")
print(f"  (d) API calls this run: {api_calls}")
print()
print("━"*60)
print("STOPPED — waiting for your confirmation to run Task 4.")
print("Reply with 'confirmed' to rerun the simulation.")
print("━"*60)
