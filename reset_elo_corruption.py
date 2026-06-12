# COMPLETED 2026-06-12. Do not re-run. See CLAUDE.md C1 fix.
"""
One-time reset for C1 (ELO double-counting).

Resets elo/rd for Mexico, South Korea, Czechia, South Africa to corrected
post-match values, by applying each of the 2 completed WC matches exactly
once from realistic pre-match baselines. Seeds wc_applied_keys in
elo_ratings.json so the patched update_elo_from_results() treats both
matches as already processed.

Run once, manually. Do NOT add to the pipeline or CI workflow.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
ELO_PATH = ROOT / "elo_ratings.json"

# Pre-match baselines (realistic ELO/RD before either match was played)
BASELINES = {
    "Mexico":       {"elo": 1820.0, "rd": 196.0},
    "South Africa": {"elo": 1480.0, "rd": 196.0},
    "South Korea":  {"elo": 1780.0, "rd": 196.0},
    "Czechia":      {"elo": 1750.0, "rd": 196.0},
}

# Matches to apply, in order, exactly once each
MATCHES = [
    {"date": "2026-06-11", "team1": "South Korea", "team2": "Czechia",
     "home_score": 2, "away_score": 1},
    {"date": "2026-06-11", "team1": "Mexico", "team2": "South Africa",
     "home_score": 2, "away_score": 0},
]

# K = 40 * decay_weight; decay_weight = 1.0 for days_ago = 0
# (match date treated as "today" for this reset)
K = 40.0


def expected_score(elo_a, elo_b):
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def apply_match(elo, rd, m):
    t1, t2 = m["team1"], m["team2"]
    hs, as_ = m["home_score"], m["away_score"]

    e1, e2 = elo[t1], elo[t2]
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

    # Glicko-1 RD update — both teams updated symmetrically
    q = math.log(10) / 400
    rd1, rd2 = rd[t1], rd[t2]

    g_rd2 = 1 / math.sqrt(1 + 3 * q**2 * rd2**2 / math.pi**2)
    E1 = 1 / (1 + 10 ** (-(e1 - e2) / 400))
    d_sq1 = 1 / (q**2 * g_rd2**2 * E1 * (1 - E1))
    rd1_new = math.sqrt(1 / (1/rd1**2 + 1/d_sq1))
    rd1_new = max(30.0, min(350.0, rd1_new))

    g_rd1 = 1 / math.sqrt(1 + 3 * q**2 * rd1**2 / math.pi**2)
    E2 = 1 / (1 + 10 ** (-(e2 - e1) / 400))
    d_sq2 = 1 / (q**2 * g_rd1**2 * E2 * (1 - E2))
    rd2_new = math.sqrt(1 / (1/rd2**2 + 1/d_sq2))
    rd2_new = max(30.0, min(350.0, rd2_new))

    rd[t1] = rd1_new
    rd[t2] = rd2_new

    print(f"  {t1} {hs}-{as_} {t2}  |  "
          f"{t1}: {e1}->{elo[t1]} (rd {rd1:.2f}->{rd1_new:.2f})  "
          f"{t2}: {e2}->{elo[t2]} (rd {rd2:.2f}->{rd2_new:.2f})")


def main():
    with open(ELO_PATH) as f:
        elo_data = json.load(f)

    affected = list(BASELINES.keys())

    print("BEFORE (current, corrupted):")
    for team in affected:
        print(f"  {team}: elo={elo_data[team]['elo']}  rd={elo_data[team]['rd']:.4f}")

    # Replay starts from pre-match baselines, not from the corrupted values
    elo = {team: BASELINES[team]["elo"] for team in affected}
    rd = {team: BASELINES[team]["rd"] for team in affected}

    print("\nApplying matches:")
    for m in MATCHES:
        apply_match(elo, rd, m)

    print("\nAFTER (corrected):")
    for team in affected:
        print(f"  {team}: elo={elo[team]}  rd={rd[team]:.4f}")
        elo_data[team]["elo"] = elo[team]
        elo_data[team]["rd"] = rd[team]

    # Seed wc_applied_keys so the patched update_elo_from_results() skips
    # both matches on its next run.
    applied_keys = sorted(
        f"{m['date']}|{m['team1']}|{m['team2']}" for m in MATCHES
    )
    elo_data["wc_applied_keys"] = applied_keys

    with open(ELO_PATH, "w") as f:
        json.dump(elo_data, f, indent=2)

    print(f"\nwc_applied_keys seeded: {applied_keys}")
    print("elo_ratings.json written.")


if __name__ == "__main__":
    main()
