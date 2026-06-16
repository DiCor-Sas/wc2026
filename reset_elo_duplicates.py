# COMPLETED 2026-06-16. Do not re-run.
# See CLAUDE.md duplicate ELO key fix.
"""
reset_elo_duplicates.py — One-time cleanup of double-applied ELO for 5 matches.

Background: update_elo_from_results() built match keys from the scraper-reported
date, which shifted across pipeline runs (Sky Sports stamps today's date;
worldcup26.ir sometimes reports wrong local_date). When the date shifted, the
old key stayed in wc_applied_keys and the new date triggered a second ELO
application for the same match. Observed for 5 matches across June 12-14.

Fix: resets ELO/RD for 10 affected teams to correct single-application values
computed from git-history pre-match baselines (commit immediately before each
match first appeared in wc2026_results.json), then removes 6 spurious
wrong-date keys from wc_applied_keys.

Iran vs New Zealand is excluded — its ELO was applied correctly once.
"""

import json
import math
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

# Pre-match ELO/RD from git history — DO NOT EDIT
# Source: elo_ratings.json at the commit immediately before each match
# first appeared in wc2026_results.json (verified via git show)
PRE_MATCH = [
    {
        "team1": "USA", "team2": "Paraguay",
        "home_score": 4, "away_score": 1,
        "date": "2026-06-12",
        "pre_elo1": 1823.6, "pre_rd1": 200.0,
        "pre_elo2": 1699.9, "pre_rd2": 184.5039,
    },
    {
        "team1": "Haiti", "team2": "Scotland",
        "home_score": 0, "away_score": 1,
        "date": "2026-06-13",
        "pre_elo1": 1443.7, "pre_rd1": 180.2016,
        "pre_elo2": 1746.0, "pre_rd2": 186.4559,
    },
    {
        "team1": "Australia", "team2": "Türkiye",
        "home_score": 2, "away_score": 0,
        "date": "2026-06-13",
        "pre_elo1": 1766.3, "pre_rd1": 181.7578,
        "pre_elo2": 1807.9, "pre_rd2": 189.0929,
    },
    {
        "team1": "Ivory Coast", "team2": "Ecuador",
        "home_score": 1, "away_score": 0,
        "date": "2026-06-14",
        "pre_elo1": 1729.5, "pre_rd1": 190.5938,
        "pre_elo2": 1693.0, "pre_rd2": 184.2241,
    },
    {
        "team1": "Sweden", "team2": "Tunisia",
        "home_score": 5, "away_score": 1,
        "date": "2026-06-14",
        "pre_elo1": 1792.8, "pre_rd1": 188.8804,
        "pre_elo2": 1687.4, "pre_rd2": 186.2995,
    },
]

SPURIOUS_KEYS = {
    "2026-06-13|USA|Paraguay",
    "2026-06-14|Australia|Türkiye",
    "2026-06-14|Haiti|Scotland",
    "2026-06-15|Ivory Coast|Ecuador",
    "2026-06-15|Sweden|Tunisia",
    "2026-06-16|Iran|New Zealand",
}


def _decay_weight(date_str):
    try:
        match_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        days_ago = (date.today() - match_date).days
    except Exception:
        return 1.0
    return 0.5 ** (days_ago / 180)


def _expected_score(elo_a, elo_b):
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))


def _apply_match(elo1, rd1, elo2, rd2, hs, as_, match_date):
    """Apply one match result using the same K and Glicko-1 formulas as
    update_elo_from_results(). Returns (new_elo1, new_rd1, new_elo2, new_rd2)."""
    K = 40 * _decay_weight(match_date)

    exp1 = _expected_score(elo1, elo2)
    exp2 = 1.0 - exp1

    if hs > as_:
        actual1, actual2 = 1.0, 0.0
    elif hs < as_:
        actual1, actual2 = 0.0, 1.0
    else:
        actual1 = actual2 = 0.5

    new_elo1 = round(elo1 + K * (actual1 - exp1), 1)
    new_elo2 = round(elo2 + K * (actual2 - exp2), 1)

    q = math.log(10) / 400

    g_rd2 = 1 / math.sqrt(1 + 3 * q**2 * rd2**2 / math.pi**2)
    E1 = 1 / (1 + 10 ** (-(elo1 - elo2) / 400))
    d_sq1 = 1 / (q**2 * g_rd2**2 * E1 * (1 - E1))
    new_rd1 = math.sqrt(1 / (1 / rd1**2 + 1 / d_sq1))
    new_rd1 = max(30.0, min(350.0, new_rd1))

    g_rd1 = 1 / math.sqrt(1 + 3 * q**2 * rd1**2 / math.pi**2)
    E2 = 1 / (1 + 10 ** (-(elo2 - elo1) / 400))
    d_sq2 = 1 / (q**2 * g_rd1**2 * E2 * (1 - E2))
    new_rd2 = math.sqrt(1 / (1 / rd2**2 + 1 / d_sq2))
    new_rd2 = max(30.0, min(350.0, new_rd2))

    return new_elo1, new_rd1, new_elo2, new_rd2


def main():
    elo_path = ROOT / "elo_ratings.json"
    with open(elo_path) as f:
        elo_data = json.load(f)

    wc_applied_keys = set(elo_data.pop("wc_applied_keys", []))

    print("=" * 60)
    print("ELO DUPLICATE KEY RESET — 2026-06-16")
    print("=" * 60)

    corrected = {}

    for m in PRE_MATCH:
        t1, t2 = m["team1"], m["team2"]
        new_elo1, new_rd1, new_elo2, new_rd2 = _apply_match(
            m["pre_elo1"], m["pre_rd1"],
            m["pre_elo2"], m["pre_rd2"],
            m["home_score"], m["away_score"],
            m["date"],
        )

        cur1 = elo_data.get(t1, {})
        cur2 = elo_data.get(t2, {})
        print(f"\n  {t1} {m['home_score']}-{m['away_score']} {t2}  [{m['date']}]")
        print(f"    {t1:15s}  elo  {cur1.get('elo','?'):>8} → {new_elo1:>8}   "
              f"rd  {round(cur1.get('rd', 200), 4):>10} → {round(new_rd1, 4):>10}")
        print(f"    {t2:15s}  elo  {cur2.get('elo','?'):>8} → {new_elo2:>8}   "
              f"rd  {round(cur2.get('rd', 200), 4):>10} → {round(new_rd2, 4):>10}")

        corrected[t1] = (new_elo1, new_rd1)
        corrected[t2] = (new_elo2, new_rd2)

    print("\n" + "=" * 60)
    print("Removing spurious keys:")
    removed = wc_applied_keys & SPURIOUS_KEYS
    not_found = SPURIOUS_KEYS - wc_applied_keys
    for k in sorted(removed):
        print(f"  - {k}")
    if not_found:
        print(f"  (already absent — no action needed: {sorted(not_found)})")
    wc_applied_keys -= SPURIOUS_KEYS
    print(f"wc_applied_keys: 22 → {len(wc_applied_keys)} entries")

    for team, (new_elo, new_rd) in corrected.items():
        if team in elo_data:
            elo_data[team]["elo"] = new_elo
            elo_data[team]["rd"] = new_rd

    elo_data["wc_applied_keys"] = sorted(wc_applied_keys)

    with open(elo_path, "w") as f:
        json.dump(elo_data, f, indent=2)

    print("\n✓ elo_ratings.json updated. Do not run this script again.")


if __name__ == "__main__":
    main()
