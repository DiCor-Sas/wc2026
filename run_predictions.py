import sys
import json
import math
import numpy as np
from scipy.stats import poisson as sp_poisson, skellam as sp_skellam
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).parent.resolve()

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

# Per-iteration team-level scores: list of lists of {"team": str, "goals": int}
per_sim_scores = []

KNOCKOUT_STAGES = [
    STAGE.ROUND_OF_32,
    STAGE.ROUND_OF_16,
    STAGE.QUARTER_FINALS,
    STAGE.SEMI_FINALS,
    STAGE.THIRD_PLACE,
    STAGE.FINAL,
]

# ── Conditioning on real results (2026-07-01) ───────────────────────────────
# The Monte Carlo previously re-simulated the whole tournament from scratch,
# ignoring wc2026_results.json and bracket_state.json entirely. Every
# simulation now replays real completed results and only samples matches
# that have not been played yet.

_REAL_RESULTS = json.load(open(_ROOT / "wc2026_results.json"))
_BRACKET_STATE = json.load(open(_ROOT / "bracket_state.json"))

# Group results keyed by unordered team pair; knockout results by match_num
# (engine match numbers 73-104 are identical to fixtures.json match_num).
FORCED_GROUP = {}
FORCED_KO = {}
for _rec in _REAL_RESULTS:
    if _rec.get("match_num"):
        FORCED_KO[_rec["match_num"]] = _rec
    else:
        FORCED_GROUP[frozenset({_rec["team1"], _rec["team2"]})] = _rec


def _forced_winner_loser(rec):
    """(winner_name, loser_name) for a completed knockout record.

    CLAUDE.md §7: the stored score is the 120-minute score; when a
    'shootout' schema is present the shootout winner is the match winner
    regardless of the (level) stored score. Penalties never change the
    stored score.
    """
    shootout = rec.get("shootout")
    if shootout:
        w = shootout["winner"]
        return (w, rec["team2"] if w == rec["team1"] else rec["team1"])
    if rec["home_score"] > rec["away_score"]:
        return rec["team1"], rec["team2"]
    if rec["away_score"] > rec["home_score"]:
        return rec["team2"], rec["team1"]
    raise ValueError(
        f"Knockout match {rec.get('match_num')} is level "
        f"{rec['home_score']}-{rec['away_score']} with no shootout schema"
    )


class ForcedModeledMatch(ModeledMatch):
    """ModeledMatch that replays real completed results instead of sampling.

    Group matches are matched by unordered team pair, knockout matches by
    match number. Forced matches skip model sampling but still apply the
    dynamic rank updates so later simulated matches see ranks shaped by
    the real results. Shootout-decided matches keep their real 120-minute
    score (for Golden Boot goal tracking) while get_winner()/get_loser()
    return the real shootout winner/loser.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._forced_winner = None
        self._forced_loser = None

    def _lookup_forced(self):
        if self.stage == STAGE.GROUP_STAGE:
            if self.home_team is None or self.away_team is None:
                return None
            return FORCED_GROUP.get(
                frozenset({self.home_team.name, self.away_team.name}))
        return FORCED_KO.get(self.number)

    def play(self):
        rec = self._lookup_forced()
        if rec is None:
            return super().play()

        names = {self.home_team.name, self.away_team.name}
        assert names == {rec["team1"], rec["team2"]}, (
            f"Match {self.number}: engine teams {names} do not match "
            f"real result teams {{{rec['team1']!r}, {rec['team2']!r}}}"
        )

        # Orient the real 120-minute score to the engine's home/away order.
        # For M74/M75 this stores the real 1-1, NOT a winner-adjusted score.
        if rec["team1"] == self.home_team.name:
            self.home_score, self.away_score = rec["home_score"], rec["away_score"]
        else:
            self.home_score, self.away_score = rec["away_score"], rec["home_score"]

        home_result = None
        if self.stage != STAGE.GROUP_STAGE:
            w_name, l_name = _forced_winner_loser(rec)
            self._forced_winner = (self.home_team
                                   if self.home_team.name == w_name
                                   else self.away_team)
            self._forced_loser = (self.home_team
                                  if self.home_team.name == l_name
                                  else self.away_team)
            # §7: a shootout win counts as a full win for rating updates
            home_result = 1.0 if self._forced_winner == self.home_team else 0.0

        self._apply_rank_updates(home_result=home_result)
        return self.home_score, self.away_score

    def get_winner(self):
        # Forced knockout matches: real winner, incl. shootout.winner for a
        # level 120-minute score (M74 -> Paraguay, M75 -> Morocco). Without
        # this override a forced 1-1 would return None and break bracket
        # propagation into the Round of 16.
        if self._forced_winner is not None:
            return self._forced_winner
        return super().get_winner()

    def get_loser(self):
        # M74 -> Germany, M75 -> Netherlands
        if self._forced_loser is not None:
            return self._forced_loser
        return super().get_loser()


class ConditionedCompetition(Competition):
    """Competition whose Round-of-32 build is conditioned on real results.

    Played R32 matches get their real team assignments from
    wc2026_results.json. Unplayed 1v2/2v2 slots come from the (real,
    forced) group standings. Unplayed 1v3 slots are allocated from the
    FIFA pool minus the third-place groups reality has already consumed —
    otherwise the engine's simplified alphabetical allocator would hand an
    already-eliminated third-place team (e.g. Sweden, real M77 loser) to a
    second slot and duplicate teams across the bracket.
    """

    def build_round_of_32(self):
        standings = self.get_group_standings()
        team_by_name = {t.name: t for t in self.teams}
        matches = []

        # Third-place groups already consumed by real played 1v3 matches
        used_third_place = set()
        for match_num, (_, pairing_type, _, _) in ROUND_OF_32_BRACKET.items():
            rec = FORCED_KO.get(match_num)
            if rec is not None and pairing_type == "1v3":
                for name in (rec["team1"], rec["team2"]):
                    team = team_by_name[name]
                    if team in self.advancing_third_place:
                        used_third_place.add(team.group.name)

        for match_num in sorted(ROUND_OF_32_BRACKET.keys()):
            city_name, pairing_type, source1, source2 = ROUND_OF_32_BRACKET[match_num]
            city = self._get_venue(city_name)
            match = self._create_match(match_num, STAGE.ROUND_OF_32, city)

            rec = FORCED_KO.get(match_num)
            if rec is not None:
                # Real played match: real teams in real home/away order
                team1 = team_by_name[rec["team1"]]
                team2 = team_by_name[rec["team2"]]
            elif pairing_type in ("2v2", "1v2"):
                team1 = self._get_team_from_source(source1, standings)
                team2 = self._get_team_from_source(source2, standings)
            elif pairing_type == "1v3":
                team1 = self._get_team_from_source(source1, standings)
                team2 = self._get_third_place_for_match_with_tracking(
                    match_num, used_third_place)
            else:
                raise ValueError(f"Unknown pairing type: {pairing_type}")

            match.assign_teams(team1, team2)
            matches.append(match)

        self.knockout_matches[STAGE.ROUND_OF_32] = matches
        self.match_counter = 88
        return matches


def _preflight_verify_conditioning():
    """Replay the real group results once and assert the engine reproduces
    the CONFIRMED standings in bracket_state.json exactly, so a divergence
    can never silently ship garbage predictions."""
    print(f"Conditioning on real results: {len(FORCED_GROUP)} group matches, "
          f"{len(FORCED_KO)} knockout matches (match_nums {sorted(FORCED_KO)})")

    comp = ConditionedCompetition.from_json_file(
        str(_ROOT / "fifa-wc-2026-simulation" / "data" / "wc_2026_teams.json"),
        match_class=ForcedModeledMatch,
    )
    comp.setup_group_matches()
    comp.play_group_stage()

    if len(FORCED_GROUP) < 72:
        print(f"  group stage incomplete ({len(FORCED_GROUP)}/72) — "
              f"skipping standings verification")
        return

    standings = comp.get_group_standings()
    for gname in sorted(comp.groups):
        for pos, slot in ((0, "1st"), (1, "2nd")):
            state = _BRACKET_STATE.get(f"Group {gname} {slot}", {})
            if state.get("status") != "CONFIRMED":
                continue
            engine_team = standings[gname][pos].name
            assert engine_team == state["team"], (
                f"Group {gname} {slot}: engine standings give {engine_team!r} "
                f"but bracket_state confirms {state['team']!r} — aborting"
            )

    comp.rank_third_place_teams()
    real_best8 = {
        _BRACKET_STATE[f"3rd Place Best {i}"]["team"]
        for i in range(1, 9)
        if _BRACKET_STATE.get(f"3rd Place Best {i}", {}).get("status") == "CONFIRMED"
    }
    if len(real_best8) == 8:
        engine_best8 = {t.name for t in comp.advancing_third_place}
        assert engine_best8 == real_best8, (
            f"Advancing third-place mismatch: engine {sorted(engine_best8)} "
            f"vs bracket_state {sorted(real_best8)}"
        )
    print("✓ Pre-flight: engine reproduces confirmed group standings and "
          "advancing third-place teams")


_preflight_verify_conditioning()

print(f"Running {NUM_SIMULATIONS:,} simulations...")
for i in range(NUM_SIMULATIONS):
    if (i + 1) % 1000 == 0:
        print(f"  {i + 1:,}/{NUM_SIMULATIONS:,} done...")

    comp = ConditionedCompetition.from_json_file(
        str(_ROOT / "fifa-wc-2026-simulation" / "data" / "wc_2026_teams.json"),
        match_class=ForcedModeledMatch,
    )
    comp.simulate()

    # ── Record per-iteration team scores (group + knockout) ───────────────
    sim_record = []
    for _m in comp.all_matches:
        if _m.home_team is not None and _m.home_score is not None:
            sim_record.append({"team": _m.home_team.name, "goals": _m.home_score})
        if _m.away_team is not None and _m.away_score is not None:
            sim_record.append({"team": _m.away_team.name, "goals": _m.away_score})
    per_sim_scores.append(sim_record)

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

print(f"[golden_boot] per_sim_scores populated: {len(per_sim_scores)} iterations")
total = sum(winners.values())

# ── Load team_strength for Poisson score calculation (Fix 3) ──────────────────
_TEAM_STRENGTH = json.load(
    open(_ROOT / "team_strength.json")
)


# ── Goals-based form modifier (2026-07-02, backtest-validated STABLE) ────────
# Decay-weighted (0.5x) goals scored/conceded per team from all completed WC
# matches, normalized by the tournament average goals per team per match,
# clamped [0.85, 1.15]. Pure function of wc2026_results.json, computed once
# per pipeline run. Applied ONLY to the final_strength Dixon-Coles lambda
# paths below — never to the engine Monte Carlo, whose dynamic off/def ranks
# already absorb real goals via the ForcedModeledMatch replay.

def _build_goals_form_modifiers():
    canon, ko_dates = {}, {}
    try:
        for fx in json.load(open(_ROOT / "fixtures.json")):
            if fx.get("home") and fx.get("away"):
                canon[frozenset({fx["home"], fx["away"]})] = fx.get("date")
            if fx.get("match_num"):
                ko_dates[fx["match_num"]] = fx.get("date")
    except Exception:
        pass

    dated = []
    for rec in _REAL_RESULTS:
        if rec.get("match_num"):
            dt = ko_dates.get(rec["match_num"]) or rec.get("date")
        else:
            dt = canon.get(frozenset({rec["team1"], rec["team2"]})) or rec.get("date")
        if dt:
            dated.append((dt, rec["team1"], rec["team2"],
                          rec["home_score"], rec["away_score"]))
    if not dated:
        return {}
    dated.sort(key=lambda m: m[0])

    # Tournament average goals per team per match (~1.47 at time of writing)
    avg = sum(hs + as_ for _, _, _, hs, as_ in dated) / (2 * len(dated))
    if avg <= 0:
        return {}

    per_team = {}
    for dt, t1, t2, hs, as_ in dated:
        per_team.setdefault(t1, []).append((dt, hs, as_))
        per_team.setdefault(t2, []).append((dt, as_, hs))

    mods = {}
    for team, recs in per_team.items():
        recs.sort(key=lambda r: r[0])  # oldest first
        n = len(recs)
        w = [0.5 ** (n - 1 - i) for i in range(n)]
        ws = sum(w)
        g_for = sum(wi * r[1] for wi, r in zip(w, recs)) / ws
        g_ag  = sum(wi * r[2] for wi, r in zip(w, recs)) / ws
        mods[team] = (max(0.85, min(1.15, g_for / avg)),
                      max(0.85, min(1.15, g_ag  / avg)))
    return mods


_GOALS_FORM_MODS = _build_goals_form_modifiers()


def _goals_form_mod(team):
    """(atk, def) goals-form modifier; neutral for teams with no completed matches."""
    return _GOALS_FORM_MODS.get(team, (1.0, 1.0))


def _dc_lambdas(team1_name, team2_name):
    """final_strength Dixon-Coles lambdas with the goals-form modifier applied."""
    s1 = _TEAM_STRENGTH.get(team1_name, {}).get("final_strength", 1600.0)
    s2 = _TEAM_STRENGTH.get(team2_name, {}).get("final_strength", 1600.0)
    lh = max(0.3, min(3.5, 1.5 * (s1 / s2) ** 2.0))
    la = max(0.3, min(3.5, 1.5 * (s2 / s1) ** 2.0))
    atk1, def1 = _goals_form_mod(team1_name)
    atk2, def2 = _goals_form_mod(team2_name)
    lh = max(0.3, min(3.5, lh * atk1 * def2))
    la = max(0.3, min(3.5, la * atk2 * def1))
    return lh, la


def _poisson_pmf(lam, k):
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def tau(x, y, lh, la, rho=0.08):
    if x == 0 and y == 0: return 1 - lh * la * rho
    if x == 1 and y == 0: return 1 + la * rho
    if x == 0 and y == 1: return 1 + lh * rho
    if x == 1 and y == 1: return 1 - rho
    return 1.0


def _poisson_most_probable_score(team1_name, team2_name, max_goals=7):
    """
    lambda = 1.5 * (s_attack / s_defend) ^ 2.0, capped [0.3, 3.5].
    Joint probability matrix corrected via Dixon-Coles tau for low-scoring cells.
    Score is the mode (argmax) of the corrected distribution.
    1-1 override applied after argmax: if win-prob diff > 15pp, pick 2nd most probable.
    """
    lh, la = _dc_lambdas(team1_name, team2_name)

    goals = list(range(max_goals + 1))
    h_pmf = sp_poisson.pmf(goals, lh)
    a_pmf = sp_poisson.pmf(goals, la)

    # Build Dixon-Coles corrected joint probability matrix
    scores = [(g1, g2) for g1 in goals for g2 in goals]
    raw = [h_pmf[g1] * a_pmf[g2] * tau(g1, g2, lh, la) for g1, g2 in scores]
    total_p = sum(raw)
    probs = [p / total_p for p in raw]

    # Most probable score: mode of the corrected distribution
    best_s = scores[max(range(len(scores)), key=lambda i: probs[i])]

    # 1-1 override: if sampled (1,1) but one team has a clear win advantage
    if best_s == (1, 1):
        win1 = sum(probs[i] for i, (g1, g2) in enumerate(scores) if g1 > g2)
        win2 = sum(probs[i] for i, (g1, g2) in enumerate(scores) if g2 > g1)
        if abs(win1 - win2) * 100 > 15:
            ranked = sorted(zip(scores, probs), key=lambda x: -x[1])
            best_s = next(s for s, _ in ranked if s != (1, 1))

    return best_s


def _extra_time_score(team1_name, team2_name):
    """
    Simulate extra time for a knockout match level after 90 minutes.
    Lambdas are reduced to 28% of the 90-minute lambdas (reflects ~0.3-0.4
    total ET goals per 30 min vs ~2.5 over 90 min), ET goals capped 0-3 per
    team. Score is the mode (argmax) of the resulting Poisson distribution.
    """
    lh, la = _dc_lambdas(team1_name, team2_name)
    et_lh = round(lh * 0.28, 4)
    et_la = round(la * 0.28, 4)

    goals = list(range(4))  # ET goals capped 0-3 per team
    h_pmf = sp_poisson.pmf(goals, et_lh)
    a_pmf = sp_poisson.pmf(goals, et_la)
    scores = [(g1, g2) for g1 in goals for g2 in goals]
    raw = [h_pmf[g1] * a_pmf[g2] for g1, g2 in scores]
    total_p = sum(raw)
    probs = [p / total_p for p in raw]
    et_g1, et_g2 = scores[max(range(len(scores)), key=lambda i: probs[i])]
    return et_g1, et_g2, et_lh, et_la


def _knockout_score(team1_name, team2_name, max_goals=7):
    """
    Full knockout scoreline for team1 vs team2: the 90-minute most-probable
    score, plus (if level after 90) extra time with fatigue-adjusted lambdas.
    Returns "display_score" (the score shown for Pollaya purposes) and, only
    when 90' was a draw, the ET fields.
    """
    g1, g2 = _poisson_most_probable_score(team1_name, team2_name, max_goals)
    info = {"display_score": (g1, g2)}
    if g1 == g2:
        et_g1, et_g2, et_lh, et_la = _extra_time_score(team1_name, team2_name)
        final1, final2 = g1 + et_g1, g2 + et_g2
        info.update({
            "score_90": f"{g1}-{g2}",
            "score_120": f"{final1}-{final2}",
            "went_to_et": True,
            "went_to_penalties": et_g1 == et_g2,
            "et_lambda_home": et_lh,
            "et_lambda_away": et_la,
            "display_score": (final1, final2),
        })
    return info


# ── helpers ────────────────────────────────────────────────────────────────

def pct(n, d):
    return round(n / d * 100, 2) if d else 0.0

def wilson_ci(wins, n=10000, z=1.282):
    """80% Wilson score confidence interval. Returns (ci_low, ci_high) as percentages."""
    p_hat = wins / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
    return (
        round(max(0.0, center - margin) * 100, 4),
        round(min(1.0, center + margin) * 100, 4),
    )

def format_team_list(counter, top_n=None):
    items = sorted(counter.items(), key=lambda x: -x[1])
    if top_n:
        items = items[:top_n]
    return [{"team": t, "count": c, "probability": pct(c, total)} for t, c in items]

def _mc_modal_score(match_num, winner_name):
    """Most frequent (winner_goals, loser_goals) scoreline among the Monte
    Carlo iterations in which winner_name won this match, read from
    ko_score_tracker. Returns None when no such iteration exists, in which
    case the caller silently falls back to the DC/ELO score path.
    """
    scores = Counter()
    for (w, w_g, l_g), n in ko_score_tracker[match_num].items():
        if w == winner_name:
            scores[(w_g, l_g)] += n
    if not scores:
        return None
    return scores.most_common(1)[0][0]

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

        # Modal MC scoreline conditioned on the likely winner, so the
        # displayed score and win probability come from the same
        # (tournament-conditioned) model. Silent fallback to the DC path
        # when the tracker has no entries for this winner; only that
        # fallback can produce the score_90/ET fields below.
        modal = _mc_modal_score(match_num, likely_winner)
        if modal is not None:
            score_info = {"display_score": modal}
        else:
            score_info = _knockout_score(likely_winner, likely_loser)
        w_g, l_g = score_info["display_score"]
        win_pct = max(teams_out, key=lambda x: x["overall_win_pct"])["overall_win_pct"]
        predicted_score = f"{likely_winner} {w_g}-{l_g} {likely_loser} ({win_pct}%)"

    result = {
        "match": match_num,
        "likely_winner": likely_winner,
        "predicted_score": predicted_score,
        "teams": teams_out,
    }
    if teams_out and "score_90" in score_info:
        result.update({
            "score_90": score_info["score_90"],
            "score_120": score_info["score_120"],
            "went_to_et": score_info["went_to_et"],
            "went_to_penalties": score_info["went_to_penalties"],
            "et_lambda_home": score_info["et_lambda_home"],
            "et_lambda_away": score_info["et_lambda_away"],
        })
    return result


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

# ── Task 2: Skellam win/draw/loss for every group-stage fixture ───────────────
_fixtures = json.load(open(_ROOT / "fixtures.json"))

match_probabilities = []
for fx in _fixtures:
    home = fx["home"]
    away = fx["away"]
    sh = _TEAM_STRENGTH.get(home, {}).get("final_strength", 1600.0)
    sa = _TEAM_STRENGTH.get(away, {}).get("final_strength", 1600.0)
    lh = max(0.3, min(3.5, 1.5 * (sh / sa) ** 2.0))
    la = max(0.3, min(3.5, 1.5 * (sa / sh) ** 2.0))

    sk = sp_skellam(mu1=lh, mu2=la)
    match_probabilities.append({
        "home":         home,
        "away":         away,
        "lambda_home":  round(lh, 4),
        "lambda_away":  round(la, 4),
        "skellam_win":  round(float(1 - sk.cdf(0)), 6),
        "skellam_draw": round(float(sk.pmf(0)),     6),
        "skellam_loss": round(float(sk.cdf(-1)),    6),
    })

output = {
    "simulations": total,
    "predicted_winner": winner_team,
    "predicted_winner_probability_pct": winner_pct,
    "all_teams": [
        {**entry,
         "ci_low":  wilson_ci(winners[entry["team"]])[0],
         "ci_high": wilson_ci(winners[entry["team"]])[1]}
        for entry in format_team_list(winners)
    ],
    "runners_up": [runner_entry] + [e for e in format_team_list(runners_up, 10)
                                     if e["team"] != winner_team and e["team"] != runner_entry["team"]],
    "third_place": [third_entry] + [e for e in format_team_list(third_place_counter, 10)
                                     if e["team"] != winner_team and e["team"] != third_entry["team"]],
    "match_probabilities": match_probabilities,
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

# Modal MC scoreline for the 3rd-place match, same silent DC fallback
# as format_ko_match()
tp_modal = _mc_modal_score(103, tp_winner)
if tp_modal is not None:
    tp_score_info = {"display_score": tp_modal}
else:
    tp_score_info = _knockout_score(tp_winner, tp_loser)
tp_wg, tp_lg = tp_score_info["display_score"]
tp_wp = max(tp_t1, tp_t2, key=lambda t: t["overall_win_pct"])["overall_win_pct"]
tp_predicted_score = f"{tp_winner} {tp_wg}-{tp_lg} {tp_loser} ({tp_wp}%)"

output["knockout_bracket"]["third_place_match_derived"] = {
    "match": 103,
    "city":  "Miami",
    "likely_winner": tp_winner,
    "predicted_score": tp_predicted_score,
    "teams": [tp_t1, tp_t2],
}
if "score_90" in tp_score_info:
    output["knockout_bracket"]["third_place_match_derived"].update({
        "score_90": tp_score_info["score_90"],
        "score_120": tp_score_info["score_120"],
        "went_to_et": tp_score_info["went_to_et"],
        "went_to_penalties": tp_score_info["went_to_penalties"],
        "et_lambda_home": tp_score_info["et_lambda_home"],
        "et_lambda_away": tp_score_info["et_lambda_away"],
    })

# Verify the four Final/3P teams are all distinct
tp_teams = {t["name"] for t in output["knockout_bracket"]["third_place_match_derived"]["teams"]}
assert fin_teams.isdisjoint(tp_teams), (
    f"Derived 3P teams {tp_teams} still overlap with Final teams {fin_teams}."
)
print(f"✓ Final teams: {fin_teams}")
print(f"✓ 3P teams:    {tp_teams}  (all distinct from Final) ✓")

def simulate_golden_boot(per_sim_scores, player_stats_path):
    import random as _rng_mod

    with open(player_stats_path) as f:
        raw_stats = json.load(f)

    valid_teams = {k: v for k, v in raw_stats.items() if isinstance(v, list)}

    # Compute proxy goals_per_match: mean over all Attacker-position entries
    # (excluding Germany stub) with appearances > 0
    attacker_rates = []
    for tname, players in valid_teams.items():
        if tname == "Germany":
            continue
        for p in players:
            if p.get("position") == "Attacker" and p.get("appearances", 0) > 0:
                attacker_rates.append(p["goals"] / p["appearances"])
    proxy_rate = sum(attacker_rates) / len(attacker_rates) if attacker_rates else 0.45
    print(f"[golden_boot] proxy goals_per_match = {proxy_rate:.4f}")

    # Compute mean goal_share at positions 1, 2, 3 across real teams (sorted desc)
    # Used to give proxy teams a realistic 3-player distribution instead of 1.0/0/0
    _share_by_pos = [[], [], []]
    for tname, players in valid_teams.items():
        if tname == "Germany":
            continue
        attackers   = sorted([p for p in players if p.get("position") == "Attacker"],
                             key=lambda x: -x["goals"])
        midfielders = sorted([p for p in players if p.get("position") == "Midfielder"],
                             key=lambda x: -x["goals"])
        sel = (attackers + midfielders)[:3]
        if len(sel) < 3:
            sel = sorted(players, key=lambda x: -x["goals"])[:3]
        total_g = sum(p["goals"] for p in sel)
        raw = [p["goals"] / total_g if total_g > 0 else 1.0 / 3 for p in sel]
        s = sum(raw)
        normed = sorted([v / s for v in raw], reverse=True)
        for pos, v in enumerate(normed[:3]):
            _share_by_pos[pos].append(v)
    mean_shares = [sum(col) / len(col) for col in _share_by_pos]
    # Renormalize so shares sum to exactly 1.0
    ms_total = sum(mean_shares)
    mean_shares = [v / ms_total for v in mean_shares]
    print(f"[golden_boot] mean_shares pos1={mean_shares[0]:.4f}  "
          f"pos2={mean_shares[1]:.4f}  pos3={mean_shares[2]:.4f}")

    _penalty_hints = {
        "Spain":       ["oyarzabal"],
        "France":      ["mbappe", "mbapp"],
        "Argentina":   ["messi"],
        "England":     ["kane"],
        "Portugal":    ["ronaldo"],
        "Netherlands": ["depay", "gakpo"],
        "Brazil":      ["firmino", "vinicius", "neymar"],
        "Morocco":     ["en-nesyri", "en nesyri"],
        "Uruguay":     ["nunez"],
        "Senegal":     ["mane"],
    }

    def _build_pool(tname, players):
        # Issue 2: prefer players with appearances >= 3; fallback to best available
        def _sort_key(p): return -p["goals"]
        q_att = sorted([p for p in players
                        if p.get("position") == "Attacker" and p.get("appearances", 0) >= 3],
                       key=_sort_key)
        q_mid = sorted([p for p in players
                        if p.get("position") == "Midfielder" and p.get("appearances", 0) >= 3],
                       key=_sort_key)
        selected = (q_att + q_mid)[:3]

        if len(selected) < 3:
            already = {id(p) for p in selected}
            fb_att  = sorted([p for p in players if p.get("position") == "Attacker"],
                             key=_sort_key)
            fb_mid  = sorted([p for p in players if p.get("position") == "Midfielder"],
                             key=_sort_key)
            fb_rest = sorted(players, key=_sort_key)
            for p in fb_att + fb_mid + fb_rest:
                if id(p) not in already:
                    selected.append(p)
                    already.add(id(p))
                if len(selected) == 3:
                    break

        if not selected:
            selected = sorted(players, key=_sort_key)[:3]

        total_g = sum(p["goals"] for p in selected)
        entries = []
        for p in selected:
            app     = p.get("appearances", 0)
            raw_gpm = p["goals"] / app if app > 0 else 0.01
            # Issue 1: Bayesian shrinkage toward proxy_rate for low-appearance players
            cred    = app / (app + 5)
            adj_gpm = cred * raw_gpm + (1 - cred) * proxy_rate
            share   = p["goals"] / total_g if total_g > 0 else 1.0 / len(selected)
            entries.append({
                "player":           p["name"],
                "team":             tname,
                "goals_per_match":  round(adj_gpm, 4),
                "goal_share":       share,
                "is_penalty_taker": False,
                "goals_raw":        p["goals"],
            })
        s = sum(e["goal_share"] for e in entries)
        if s > 0:
            for e in entries:
                e["goal_share"] /= s

        hints    = _penalty_hints.get(tname, [])
        assigned = False
        for hint in hints:
            for e in entries:
                if hint in e["player"].lower():
                    e["is_penalty_taker"] = True
                    assigned = True
                    break
            if assigned:
                break
        if not assigned:
            max(entries, key=lambda x: x["goals_raw"])["is_penalty_taker"] = True
        return entries

    player_pool = {}
    for tname, players in valid_teams.items():
        if tname == "Germany":
            continue
        player_pool[tname] = _build_pool(tname, players)

    def _proxy_entries(tname):
        # Proxy players have 0 appearances → credibility=0 → adj_gpm = proxy_rate (identity)
        return [
            {"player": f"{tname} Striker",   "team": tname, "goals_per_match": round(proxy_rate, 4),
             "goal_share": mean_shares[0], "is_penalty_taker": True,  "goals_raw": 0},
            {"player": f"{tname} Forward 2",  "team": tname, "goals_per_match": round(proxy_rate, 4),
             "goal_share": mean_shares[1], "is_penalty_taker": False, "goals_raw": 0},
            {"player": f"{tname} Forward 3",  "team": tname, "goals_per_match": round(proxy_rate, 4),
             "goal_share": mean_shares[2], "is_penalty_taker": False, "goals_raw": 0},
        ]

    # Determine all teams present in simulations; build proxy entries for missing ones
    all_sim_teams = {entry["team"] for sim in per_sim_scores for entry in sim}
    for tname in all_sim_teams - set(player_pool.keys()):
        player_pool[tname] = _proxy_entries(tname)

    # Germany: real data is a stub (goals=0) — treat as proxy
    player_pool["Germany"] = _proxy_entries("Germany")

    n_sims        = len(per_sim_scores)
    win_count     = defaultdict(float)
    goals_acc     = defaultdict(float)
    match_cnt_acc = defaultdict(int)   # team -> total matches across all sims

    for sim_record in per_sim_scores:
        team_matches = defaultdict(list)
        for entry in sim_record:
            team_matches[entry["team"]].append(entry["goals"])

        sim_goals = defaultdict(float)

        for tname, match_goals_list in team_matches.items():
            players = player_pool.get(tname)
            if not players:
                continue
            shares  = np.array([p["goal_share"] for p in players], dtype=float)
            shares /= shares.sum()
            n_p     = len(players)
            pen_idx = next((j for j, p in enumerate(players) if p["is_penalty_taker"]), 0)

            match_cnt_acc[tname] += len(match_goals_list)

            for team_goals in match_goals_list:
                dist = [0] * n_p
                for _ in range(int(team_goals)):
                    dist[np.random.choice(n_p, p=shares)] += 1

                pen_bonus = 1 if _rng_mod.random() < 0.22 else 0

                for j, p in enumerate(players):
                    bonus  = pen_bonus if j == pen_idx else 0
                    capped = min(4, dist[j] + bonus)
                    sim_goals[(p["player"], tname)] += capped

        if sim_goals:
            max_g = max(sim_goals.values())
            if max_g > 0:
                sim_winners = [k for k, g in sim_goals.items() if g == max_g]
                credit = 1.0 / len(sim_winners)
                for w in sim_winners:
                    win_count[w] += credit

        for key, g in sim_goals.items():
            goals_acc[key] += g

    _proxy_suffixes = ("Striker", "Forward 2", "Forward 3")

    results = []
    for (pname, tname), wins in win_count.items():
        mean_goals   = goals_acc[(pname, tname)] / n_sims
        mean_matches = match_cnt_acc[tname] / n_sims
        p_entry      = next((p for p in player_pool.get(tname, []) if p["player"] == pname), {})
        is_proxy     = any(pname.endswith(s) for s in _proxy_suffixes)
        display_name = f"{tname} (squad avg)" if is_proxy else pname
        results.append({
            "player":           display_name,
            "team":             tname,
            "golden_boot_pct":  round(wins / n_sims * 100, 2),
            "mean_goals":       round(mean_goals, 2),
            "expected_matches": round(mean_matches, 2),
            "is_penalty_taker": p_entry.get("is_penalty_taker", False),
            "is_proxy":         is_proxy,
        })

    results.sort(key=lambda x: -x["golden_boot_pct"])
    return results[:20]


with open(_ROOT / "predictions.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\n✓ Predicted winner : {output['predicted_winner']} ({output['predicted_winner_probability_pct']}%)")
print(f"✓ Runner-up: {output['runners_up'][0]['team']} ({output['runners_up'][0]['probability']}%)")
print(f"✓ Third place: {output['third_place'][0]['team']} ({output['third_place'][0]['probability']}%)")
print("✓ Saved to predictions.json")

# ── Golden Boot simulation ─────────────────────────────────────────────────
top20 = simulate_golden_boot(per_sim_scores, _ROOT / "player_stats.json")
with open(_ROOT / "predictions.json") as f:
    output = json.load(f)
output["golden_boot_probabilities"] = top20
with open(_ROOT / "predictions.json", "w") as f:
    json.dump(output, f, indent=2)
print(f"✓ Golden Boot top scorer: {top20[0]['player']} ({top20[0]['team']}) "
      f"{top20[0]['golden_boot_pct']}%")
