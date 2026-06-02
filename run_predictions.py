import sys
import json
import math
from collections import Counter, defaultdict

sys.path.insert(0, "/Users/diegofelipecortessastoque/Desktop/wc2026/fifa-wc-2026-simulation")

from engine import Competition, STAGE
from engine.match import ModeledMatch
from engine.schedule import ROUND_OF_32_BRACKET

NUM_SIMULATIONS = 10_000

winners = Counter()
runners_up = Counter()
third_place_counter = Counter()

# For every knockout match number, count team appearances and wins
ko_appearances = defaultdict(Counter)  # match_num -> {team_name: n_times_in_that_slot}
ko_wins = defaultdict(Counter)         # match_num -> {team_name: n_times_won_that_match}
# Track actual scores: match_num -> (winner_name, w_goals, l_goals) counter
ko_score_tracker = defaultdict(Counter)  # match_num -> Counter of (winner, w_g, l_g)

KNOCKOUT_STAGES = [
    STAGE.ROUND_OF_32,
    STAGE.ROUND_OF_16,
    STAGE.QUARTER_FINALS,
    STAGE.SEMI_FINALS,
    STAGE.THIRD_PLACE,
    STAGE.FINAL,
]

print(f"Running {NUM_SIMULATIONS:,} simulations...")
for i in range(NUM_SIMULATIONS):
    if (i + 1) % 1000 == 0:
        print(f"  {i + 1:,}/{NUM_SIMULATIONS:,} done...")

    comp = Competition.from_json_file(
        "/Users/diegofelipecortessastoque/Desktop/wc2026/fifa-wc-2026-simulation/data/wc_2026_teams.json",
        match_class=ModeledMatch,
    )
    comp.simulate()

    # ── FIX 1: Hard constraint — group-stage finishers can only appear in one slot ──
    # Build per-simulation mapping: team_name -> R32 match number they were assigned
    sim_r32_assignment = {}
    for match in comp.knockout_matches.get(STAGE.ROUND_OF_32, []):
        for team in [match.home_team, match.away_team]:
            if team is not None:
                sim_r32_assignment[team.name] = match.number

    # Verify each team appears in exactly one R32 slot in this simulation
    assert len(sim_r32_assignment) == 32, (
        f"Sim {i}: expected 32 unique teams in R32, got {len(sim_r32_assignment)}"
    )

    # ── Safety assertion: 3rd-place teams must be distinct from Final teams ──
    if comp.knockout_matches.get(STAGE.THIRD_PLACE) and comp.knockout_matches.get(STAGE.FINAL):
        tp_match  = comp.knockout_matches[STAGE.THIRD_PLACE][0]
        fin_match = comp.knockout_matches[STAGE.FINAL][0]
        tp_teams  = {tp_match.home_team.name, tp_match.away_team.name}
        fin_teams = {fin_match.home_team.name, fin_match.away_team.name}
        assert tp_teams.isdisjoint(fin_teams), (
            f"Sim {i}: 3rd-place teams {tp_teams} overlap with Final teams {fin_teams}"
        )

    winners[comp.champion.name] += 1
    if comp.runner_up:
        runners_up[comp.runner_up.name] += 1
    if comp.third_place:
        third_place_counter[comp.third_place.name] += 1

    for stage in KNOCKOUT_STAGES:
        for match in comp.knockout_matches.get(stage, []):
            mn = match.number
            if match.home_team:
                ko_appearances[mn][match.home_team.name] += 1
            if match.away_team:
                ko_appearances[mn][match.away_team.name] += 1
            winner = match.get_winner()
            if winner:
                ko_wins[mn][winner.name] += 1
                loser = match.get_loser()
                if loser and match.home_score is not None:
                    is_home_winner = winner == match.home_team
                    w_g = match.home_score if is_home_winner else match.away_score
                    l_g = match.away_score if is_home_winner else match.home_score
                    ko_score_tracker[mn][(winner.name, w_g, l_g)] += 1

total = sum(winners.values())

# ── Load team_strength for Poisson score calculation (Fix 3) ──────────────────
_TEAM_STRENGTH = json.load(
    open("/Users/diegofelipecortessastoque/Desktop/wc2026/team_strength.json")
)
_AVG_STRENGTH = sum(v["final_strength"] for v in _TEAM_STRENGTH.values()) / len(_TEAM_STRENGTH)
_BASE_GOALS = 1.5   # base goals per team for average-strength teams
_STRENGTH_EXP = 3.0  # exponent for per-team lambda: lam = base * (s/avg)^exp


def _poisson_pmf(lam, k):
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _poisson_most_probable_score(team1_name, team2_name, max_goals=5):
    """
    Compute the most-probable (team1_goals, team2_goals) using independent
    per-team lambdas derived from final_strength in team_strength.json.

    Each team's lambda = base * (team_strength / avg_strength)^exp.
    This allows 1-1 (equal averages), 2-1 (strong vs mid), 2-0 (strong vs weak),
    2-2 (two strong sides), 3-0 (dominant vs weak), producing varied scorelines.
    Returns (t1_goals, t2_goals).
    """
    s1 = _TEAM_STRENGTH.get(team1_name, {}).get("final_strength", _AVG_STRENGTH)
    s2 = _TEAM_STRENGTH.get(team2_name, {}).get("final_strength", _AVG_STRENGTH)
    lam1 = _BASE_GOALS * (s1 / _AVG_STRENGTH) ** _STRENGTH_EXP
    lam2 = _BASE_GOALS * (s2 / _AVG_STRENGTH) ** _STRENGTH_EXP
    # clamp to [0.2, 4.0] for sensible scores
    lam1 = max(0.2, min(4.0, lam1))
    lam2 = max(0.2, min(4.0, lam2))

    best_p, best_s = 0.0, (1, 0)
    for g1 in range(max_goals + 1):
        for g2 in range(max_goals + 1):
            p = _poisson_pmf(lam1, g1) * _poisson_pmf(lam2, g2)
            if p > best_p:
                best_p, best_s = p, (g1, g2)
    return best_s


# ── helpers ────────────────────────────────────────────────────────────────

def pct(n, d):
    return round(n / d * 100, 2) if d else 0.0

def format_team_list(counter, top_n=None):
    items = sorted(counter.items(), key=lambda x: -x[1])
    if top_n:
        items = items[:top_n]
    return [{"team": t, "count": c, "probability": pct(c, total)} for t, c in items]

def format_ko_match(match_num, team_pool=None):
    """
    Build match display data for match_num.
    team_pool: if provided, only consider teams in this set (for deduplication).
    """
    apps = ko_appearances[match_num]
    wins = ko_wins[match_num]

    # Top candidates by appearances, filtered to team_pool if given
    if team_pool is not None:
        candidates = [(t, c) for t, c in apps.most_common() if t in team_pool]
    else:
        candidates = apps.most_common()

    top = candidates[:2]
    teams_out = []
    for team_name, app_count in top:
        win_count = wins.get(team_name, 0)
        teams_out.append({
            "name": team_name,
            "reach_pct": pct(app_count, total),
            "win_if_reached_pct": pct(win_count, app_count),
            "overall_win_pct": pct(win_count, total),
        })

    likely_winner = None
    predicted_score = None
    if teams_out:
        likely_winner = max(teams_out, key=lambda x: x["overall_win_pct"])["name"]
        likely_loser = next((t["name"] for t in teams_out if t["name"] != likely_winner), "?")

        # Fix 3: Use Poisson most-probable score from team_strength.json
        w_g, l_g = _poisson_most_probable_score(likely_winner, likely_loser)
        win_pct = max(teams_out, key=lambda x: x["overall_win_pct"])["overall_win_pct"]
        predicted_score = f"{likely_winner} {w_g}-{l_g} {likely_loser} ({win_pct}%)"

    return {
        "match": match_num,
        "likely_winner": likely_winner,
        "predicted_score": predicted_score,
        "teams": teams_out,
    }


def build_r32_deduplicated():
    """
    Build R32 match display ensuring each team appears in exactly one slot.

    Strategy: for each team that appears in multiple slots across the aggregation,
    assign them to the slot where they have the highest reach_pct, then fill other
    slots with the next best available team.
    """
    match_nums = list(range(73, 89))

    # Step 1: For each slot, get the full ordered candidate list
    slot_candidates = {}
    for mn in match_nums:
        slot_candidates[mn] = ko_appearances[mn].most_common()

    # Step 2: Assign teams to slots greedily
    # For each slot, pick the top team not yet assigned elsewhere
    assigned_to_slot = {}   # team_name -> match_num
    slot_primary = {}       # match_num -> primary team_name
    slot_secondary = {}     # match_num -> secondary team_name

    # First pass: assign primary (most common) team for each slot
    # Process slots in order of "dominance" (how much bigger the top count is than 2nd)
    def dominance(mn):
        cands = slot_candidates[mn]
        if len(cands) < 2:
            return cands[0][1] if cands else 0
        return cands[0][1] - cands[1][1]

    sorted_slots = sorted(match_nums, key=dominance, reverse=True)

    for mn in sorted_slots:
        for team_name, _ in slot_candidates[mn]:
            if team_name not in assigned_to_slot:
                assigned_to_slot[team_name] = mn
                slot_primary[mn] = team_name
                break

    # Second pass: assign secondary team for each slot
    for mn in match_nums:
        primary = slot_primary.get(mn)
        for team_name, _ in slot_candidates[mn]:
            if team_name != primary and team_name not in assigned_to_slot:
                assigned_to_slot[team_name] = mn
                slot_secondary[mn] = team_name
                break
        if mn not in slot_secondary:
            # If still not found, allow a team already assigned to another slot
            # but only if it's the best remaining candidate
            for team_name, _ in slot_candidates[mn]:
                if team_name != primary:
                    slot_secondary[mn] = team_name
                    break

    # Step 3: Build output using the deduplicated team pools
    r32_out = []
    for mn in match_nums:
        pool = set()
        if mn in slot_primary:
            pool.add(slot_primary[mn])
        if mn in slot_secondary:
            pool.add(slot_secondary[mn])
        r32_out.append(
            {**format_ko_match(mn, team_pool=pool),
             "label": R32_LABELS[mn],
             "city": R32_CITIES[mn]}
        )

    # Verify: collect all team names across slots and check for duplicates
    all_r32_teams = [t["name"] for m in r32_out for t in m["teams"]]
    duplicates = {n for n in all_r32_teams if all_r32_teams.count(n) > 1}
    if duplicates:
        print(f"WARNING: still have R32 duplicates after dedup: {duplicates}")
    else:
        print(f"✓ R32 deduplication: {len(all_r32_teams)} unique teams across 16 slots")
        print("  Teams:", sorted(all_r32_teams))

    return r32_out


# ── R32 slot labels (for the dashboard) ────────────────────────────────────

R32_LABELS = {
    73: "2nd-A vs 2nd-B",
    74: "1st-E vs 3rd (A/B/C/D/F)",
    75: "1st-F vs 2nd-C",
    76: "1st-C vs 2nd-F",
    77: "1st-I vs 3rd (C/D/F/G/H)",
    78: "2nd-E vs 2nd-I",
    79: "1st-A vs 3rd (C/E/F/H/I)",
    80: "1st-L vs 3rd (E/H/I/J/K)",
    81: "1st-D vs 3rd (B/E/F/I/J)",
    82: "1st-G vs 3rd (A/E/H/I/J)",
    83: "2nd-K vs 2nd-L",
    84: "1st-H vs 2nd-J",
    85: "1st-B vs 3rd (E/F/G/I/J)",
    86: "1st-J vs 2nd-H",
    87: "1st-K vs 3rd (D/E/I/J/L)",
    88: "2nd-D vs 2nd-G",
}

R32_CITIES = {mn: info[0] for mn, info in ROUND_OF_32_BRACKET.items()}

# ── build output ────────────────────────────────────────────────────────────

r32_matches = build_r32_deduplicated()

# ── Fix 2: Runner-up and Third Place must be distinct from Winner ─────────────
winner_team = format_team_list(winners, 1)[0]["team"]
winner_pct = pct(winners.most_common(1)[0][1], total)

# Runner-up: highest final-appearance (non-winner) probability
runner_entry = next(
    e for e in format_team_list(runners_up)
    if e["team"] != winner_team
)

# Third place: highest 3rd-place-match win probability, NOT winner or runner-up
third_entry = next(
    e for e in format_team_list(third_place_counter)
    if e["team"] != winner_team and e["team"] != runner_entry["team"]
)

assert winner_team != runner_entry["team"], "Winner and Runner-Up are the same team!"
assert winner_team != third_entry["team"], "Winner and Third Place are the same team!"
assert runner_entry["team"] != third_entry["team"], "Runner-Up and Third Place are the same team!"
print(f"✓ Top predictions — distinct teams: Winner={winner_team}, "
      f"Runner-Up={runner_entry['team']}, Third={third_entry['team']}")

output = {
    "simulations": total,
    "predicted_winner": winner_team,
    "predicted_winner_probability_pct": winner_pct,
    "all_teams": format_team_list(winners),
    "runners_up": [runner_entry] + [e for e in format_team_list(runners_up, 10)
                                     if e["team"] != winner_team and e["team"] != runner_entry["team"]],
    "third_place": [third_entry] + [e for e in format_team_list(third_place_counter, 10)
                                     if e["team"] != winner_team and e["team"] != third_entry["team"]],
    "knockout_bracket": {
        "round_of_32": r32_matches,
        "round_of_16": [format_ko_match(mn) for mn in range(89, 97)],
        "quarter_finals": [format_ko_match(mn) for mn in range(97, 101)],
        "semi_finals": [format_ko_match(mn) for mn in range(101, 103)],
        "third_place_match": format_ko_match(103),
        "third_place_match_derived": None,  # filled in below
        "final": format_ko_match(104),
    },
}

# ── Derive 3rd-place display from actual M103 appearances ─────────────────
fin_teams = {t["name"] for t in output["knockout_bracket"]["final"]["teams"][:2]}

m103_top = [
    name for name, _ in ko_appearances[103].most_common()
    if name not in fin_teams
][:2]

def m103_entry(name):
    app = ko_appearances[103][name]
    win = ko_wins[103][name]
    return {
        "name": name,
        "reach_pct":          pct(app, total),
        "win_if_reached_pct": pct(win, app) if app else 0.0,
        "overall_win_pct":    pct(win, total),
    }

tp_t1, tp_t2 = m103_entry(m103_top[0]), m103_entry(m103_top[1])
tp_winner = max([tp_t1, tp_t2], key=lambda t: t["overall_win_pct"])["name"]
tp_loser = tp_t2["name"] if tp_winner == tp_t1["name"] else tp_t1["name"]

# Poisson-based predicted score for 3rd-place match
tp_wg, tp_lg = _poisson_most_probable_score(tp_winner, tp_loser)
tp_wp = max(tp_t1, tp_t2, key=lambda t: t["overall_win_pct"])["overall_win_pct"]
tp_predicted_score = f"{tp_winner} {tp_wg}-{tp_lg} {tp_loser} ({tp_wp}%)"

output["knockout_bracket"]["third_place_match_derived"] = {
    "match": 103,
    "city":  "Miami",
    "likely_winner": tp_winner,
    "predicted_score": tp_predicted_score,
    "teams": [tp_t1, tp_t2],
}

# Verify the four Final/3P teams are all distinct
tp_teams = {t["name"] for t in output["knockout_bracket"]["third_place_match_derived"]["teams"]}
assert fin_teams.isdisjoint(tp_teams), (
    f"Derived 3P teams {tp_teams} still overlap with Final teams {fin_teams}."
)
print(f"✓ Final teams: {fin_teams}")
print(f"✓ 3P teams:    {tp_teams}  (all distinct from Final) ✓")

with open("/Users/diegofelipecortessastoque/Desktop/wc2026/predictions.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\n✓ Predicted winner : {output['predicted_winner']} ({output['predicted_winner_probability_pct']}%)")
print(f"✓ Runner-up: {output['runners_up'][0]['team']} ({output['runners_up'][0]['probability']}%)")
print(f"✓ Third place: {output['third_place'][0]['team']} ({output['third_place'][0]['probability']}%)")
print("✓ Saved to predictions.json")
