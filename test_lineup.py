#!/usr/bin/env python3
"""
test_lineup.py — Manual lineup fetch and lambda adjustment tester.

Usage:
    python3 test_lineup.py "Spain" "Cabo Verde"
    python3 test_lineup.py "France" "Senegal"

Fetches lineup using today's date, runs absence detection, and prints a
full human-readable report. Writes to lineups.json and match_adjustments.json
locally. Does NOT push to GitHub.
"""

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent

# Import shared helpers from fetch_results.py
sys.path.insert(0, str(ROOT))
from fetch_results import (
    fetch_lineup,
    _detect_key_absences,
    _is_wc_match,
    _fn,
    FRIENDLY_NAME_MAP,
)

SQUAD_SCALE_MIN = 800
SQUAD_SCALE_MAX = 2200


def _load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _badge_text(lineup_data):
    src = lineup_data.get("source", "unavailable")
    home_xi = lineup_data.get("home_xi", [])
    away_xi = lineup_data.get("away_xi", [])
    absences = lineup_data.get("key_absences", [])
    xi_confirmed = src == "api-football" and len(home_xi) >= 5 and len(away_xi) >= 5
    xi_estimated = src in ("espn-playwright", "bbc-playwright", "web-search") and bool(home_xi or away_xi)
    if absences:
        absent_name = absences[0]["player"].split()[-1]
        return f"⚠ {absent_name} NOT STARTING"
    if xi_confirmed:
        return "LINEUP CONFIRMED"
    if xi_estimated:
        return "LINEUP ESTIMATED"
    return "STARTING XI PENDING"


def _base_lambda(team, avg_strength, team_strength):
    ts = team_strength.get(team, {})
    base_s = ts.get("final_strength", avg_strength)
    return max(0.3, min(3.5, 1.5 * (base_s / avg_strength) ** 2.0))


def _team_report(team, xi, player_stats, team_strength, avg_strength, key_absences):
    lines = []
    lines.append(f"\n{team.upper()} STARTING XI ({len(xi)} players):")
    if xi:
        for p in xi:
            lines.append(f"  {p}")
    else:
        lines.append("  Not available")

    players = player_stats.get(team, [])
    tracked = sorted(
        [p for p in players if p.get("minutes", 0) > 0],
        key=lambda p: (p.get("goals", 0) * 0.6 + p.get("assists", 0) * 0.4) / (p["minutes"] / 90),
        reverse=True,
    )

    lines.append(f"\nKey players tracked:")
    if not tracked:
        lines.append("  (no player data available)")
    else:
        xi_lower = [n.lower() for n in xi]
        for i, p in enumerate(tracked[:3], 1):
            pname = p.get("name", "?")
            mins_per90 = p["minutes"] / 90
            g90 = round(p.get("goals", 0) / mins_per90, 3)
            a90 = round(p.get("assists", 0) / mins_per90, 3)
            contrib = round((g90 * 0.6 + a90 * 0.4) / 1.5, 3)
            pname_lower = pname.lower()
            in_xi = any(pname_lower in xi_n or xi_n in pname_lower for xi_n in xi_lower)
            status = "IN XI" if in_xi else "ABSENT"
            lines.append(f"  {i}. {pname} — G90:{g90} A90:{a90} Contribution:{contrib:.1%} — {status}")

    # Lambda adjustment
    base_lam = round(_base_lambda(team, avg_strength, team_strength), 2)
    team_absences = [a for a in key_absences if a.get("team") == team]
    lines.append(f"\nLambda adjustment for {team}:")
    lines.append(f"  Base lambda: {base_lam}")
    if team_absences:
        adj_lam = team_absences[-1]["adjusted_lambda"]
        pct_change = round((adj_lam - base_lam) / base_lam * 100, 1)
        for ab in team_absences:
            lines.append(f"  ⚠ {ab['player']}: base={ab['base_lambda']} → "
                         f"adjusted={ab['adjusted_lambda']} (penalty={ab['penalty_pct']}%)")
        lines.append(f"  Adjusted lambda: {adj_lam} ({pct_change:+.1f}%)")
    elif xi:
        lines.append("  No adjustment — all key players present or data insufficient")
    else:
        lines.append("  No adjustment — no lineup data available")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 test_lineup.py \"Home Team\" \"Away Team\"")
        sys.exit(1)

    home_team = _fn(sys.argv[1])
    away_team = _fn(sys.argv[2])
    today = date.today().isoformat()

    print(f"\n{'='*50}")
    print(f"=== LINEUP TEST: {home_team} vs {away_team} ===")
    print(f"{'='*50}")
    print(f"Date: {today}")
    print()

    # Verify WC match
    if not _is_wc_match(home_team, away_team):
        print(f"WARNING: {home_team} vs {away_team} is not found in fixtures.json.")
        print("This is not a confirmed WC match. Proceeding with test anyway...")
        print()

    # Run full lineup fetch (writes lineups.json + match_adjustments.json)
    print("[Fetching lineup — trying all sources in order...]")
    print()
    lineup_data = fetch_lineup(home_team, away_team, today)

    if lineup_data is None:
        print(f"fetch_lineup() returned None — not a WC match in fixtures.json")
        sys.exit(0)

    # Load supporting data for report
    player_stats = _load_json(ROOT / "player_stats.json")
    team_strength = _load_json(ROOT / "team_strength.json")
    avg_strength = (sum(v["final_strength"] for v in team_strength.values()) /
                    max(len(team_strength), 1)) if team_strength else 1600.0

    source = lineup_data.get("source", "unavailable")
    home_xi = lineup_data.get("home_xi", [])
    away_xi = lineup_data.get("away_xi", [])
    key_absences = lineup_data.get("key_absences", [])

    print()
    print(f"{'='*50}")
    print(f"=== LINEUP TEST: {home_team} vs {away_team} ===")
    print(f"Date: {today} | Source: {source}")

    print(_team_report(home_team, home_xi, player_stats, team_strength, avg_strength, key_absences))
    print(_team_report(away_team, away_xi, player_stats, team_strength, avg_strength, key_absences))

    badge = _badge_text(lineup_data)
    print(f"\nDashboard badge: \"{badge}\"")

    print(f"{'='*50}")
    print(f"=== END REPORT ===")
    print()

    # Confirm written files
    lineups_path = ROOT / "lineups.json"
    adj_path = ROOT / "match_adjustments.json"
    if lineups_path.exists():
        print(f"✓ lineups.json written ({lineups_path})")
    if adj_path.exists() and key_absences:
        print(f"✓ match_adjustments.json written ({adj_path})")
    elif not key_absences:
        print("✓ match_adjustments.json: no adjustments needed (no key absences detected)")
    print("✗ Not pushed to GitHub (local test only)")


if __name__ == "__main__":
    main()
