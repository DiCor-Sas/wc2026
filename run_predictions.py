import sys
import json
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

# ── helpers ────────────────────────────────────────────────────────────────

def pct(n, d):
    return round(n / d * 100, 2) if d else 0.0

def format_team_list(counter, top_n=None):
    items = sorted(counter.items(), key=lambda x: -x[1])
    if top_n:
        items = items[:top_n]
    return [{"team": t, "count": c, "probability": pct(c, total)} for t, c in items]

def format_ko_match(match_num):
    apps = ko_appearances[match_num]
    wins = ko_wins[match_num]

    # Top 2 by appearances (covers the rare 3rd-place slot variation)
    top = apps.most_common(2)
    teams_out = []
    for team_name, app_count in top:
        win_count = wins.get(team_name, 0)
        teams_out.append({
            "name": team_name,
            # how often this team reaches this match
            "reach_pct": pct(app_count, total),
            # given they reach the match, probability they win it
            "win_if_reached_pct": pct(win_count, app_count),
            # overall probability of winning this specific match slot
            "overall_win_pct": pct(win_count, total),
        })

    likely_winner = None
    predicted_score = None
    if teams_out:
        likely_winner = max(teams_out, key=lambda x: x["overall_win_pct"])["name"]
        # Find the most common score for the likely winner
        scores = {(w, wg, lg): c for (w, wg, lg), c in ko_score_tracker[match_num].items() if w == likely_winner}
        if scores:
            best = max(scores, key=scores.__getitem__)
            _, w_g, l_g = best
            likely_loser = next((t["name"] for t in teams_out if t["name"] != likely_winner), "?")
            win_pct = max(teams_out, key=lambda x: x["overall_win_pct"])["overall_win_pct"]
            predicted_score = f"{likely_winner} {w_g}-{l_g} {likely_loser} ({win_pct}%)"

    return {
        "match": match_num,
        "likely_winner": likely_winner,
        "predicted_score": predicted_score,
        "teams": teams_out,
    }

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

output = {
    "simulations": total,
    "predicted_winner": format_team_list(winners, 1)[0]["team"],
    "predicted_winner_probability_pct": pct(winners.most_common(1)[0][1], total),
    "all_teams": format_team_list(winners),
    "runners_up": format_team_list(runners_up, 10),
    "third_place": format_team_list(third_place_counter, 10),
    "knockout_bracket": {
        "round_of_32": [
            {**format_ko_match(mn), "label": R32_LABELS[mn], "city": R32_CITIES[mn]}
            for mn in range(73, 89)
        ],
        "round_of_16": [format_ko_match(mn) for mn in range(89, 97)],
        "quarter_finals": [format_ko_match(mn) for mn in range(97, 101)],
        "semi_finals": [format_ko_match(mn) for mn in range(101, 103)],
        # Raw M103 data (who actually appeared in the 3rd-place match slot)
        "third_place_match": format_ko_match(103),
        # Derived 3rd-place match: the projected LOSERS of each SF.
        # SF1 loser = the SF1 participant with the LOWER overall_win_pct.
        # SF2 loser = the SF2 participant with the LOWER overall_win_pct.
        # These are always different teams from the Final (who are the SF winners).
        "third_place_match_derived": None,  # filled in below
        "final": format_ko_match(104),
    },
}

# ── Derive the 3rd-place display from SF projected losers ─────────────────
# SF1 = M101, SF2 = M102.  The projected loser of each SF is the participant
# with lower overall_win_pct (they lose the SF more often than they win it).
sf1_data = output["knockout_bracket"]["semi_finals"][0]   # M101
sf2_data = output["knockout_bracket"]["semi_finals"][1]   # M102

def sf_loser_entry(sf_data):
    """Return the team entry (reach_pct, etc.) for the projected SF loser,
    but pull the conditional win probability from the actual M103 appearances."""
    teams = sorted(sf_data["teams"], key=lambda t: t["overall_win_pct"])
    loser = teams[0]   # lower overall_win_pct → projected loser
    # Get their M103 stats from ko_appearances/ko_wins for accurate 3p numbers
    app = ko_appearances[103][loser["name"]]
    win = ko_wins[103][loser["name"]]
    return {
        "name": loser["name"],
        "reach_pct":          pct(app, total),
        "win_if_reached_pct": pct(win, app) if app else 0.0,
        "overall_win_pct":    pct(win, total),
    }

tp_t1 = sf_loser_entry(sf1_data)
tp_t2 = sf_loser_entry(sf2_data)
tp_winner = max([tp_t1, tp_t2], key=lambda t: t["overall_win_pct"])["name"]

# Predicted score for 3rd-place derived match
tp_scores = {(w, wg, lg): c for (w, wg, lg), c in ko_score_tracker[103].items() if w == tp_winner}
tp_predicted_score = None
if tp_scores:
    best_tp = max(tp_scores, key=tp_scores.__getitem__)
    _, tp_wg, tp_lg = best_tp
    tp_loser = tp_t2["name"] if tp_winner == tp_t1["name"] else tp_t1["name"]
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
fin_teams = {t["name"] for t in output["knockout_bracket"]["final"]["teams"][:2]}
tp_teams  = {t["name"] for t in output["knockout_bracket"]["third_place_match_derived"]["teams"]}
assert fin_teams.isdisjoint(tp_teams), (
    f"Derived 3P teams {tp_teams} still overlap with Final teams {fin_teams}. "
    "Check SF data ordering."
)
print(f"✓ Final teams: {fin_teams}")
print(f"✓ 3P teams:    {tp_teams}  (all distinct from Final) ✓")

with open("/Users/diegofelipecortessastoque/Desktop/wc2026/predictions.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\n✓ Predicted winner : {output['predicted_winner']} ({output['predicted_winner_probability_pct']}%)")
print(f"✓ Runner-up (most likely): {output['runners_up'][0]['team']} ({output['runners_up'][0]['probability']}%)")
print(f"✓ Third place (most likely): {output['third_place'][0]['team']} ({output['third_place'][0]['probability']}%)")
print("✓ Saved to predictions.json")
