"""
Generate index.html from predictions.json.
Run after run_predictions.py produces the JSON.
"""
import json
import math
import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

_ROOT = Path(__file__).parent.resolve()

PREDICTIONS_FILE   = _ROOT / "predictions.json"
OUTPUT_FILE        = _ROOT / "index.html"
PLAYER_STATS_FILE  = _ROOT / "player_stats.json"
TEAM_STRENGTH_FILE = _ROOT / "team_strength.json"
FIXTURES_FILE      = _ROOT / "fixtures.json"
LINEUPS_FILE       = _ROOT / "lineups.json"
MATCH_ADJUSTMENTS_FILE = _ROOT / "match_adjustments.json"
MATCH_STATS_FILE       = _ROOT / "match_stats.json"
BRACKET_STATE_FILE     = _ROOT / "bracket_state.json"
RESULTS_FILE       = _ROOT / "wc2026_results.json"

PENDING_NOTE = "* Pending FIFA confirmation — highest-ranked confederation proxy used."

NAME_MAP = {
    "Korea Republic": "South Korea",
    "South Korea": "South Korea",
    "Czech Republic": "Czechia",
    "Czechia": "Czechia",
    "Türkiye": "Türkiye",
    "Turkey": "Türkiye",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Bosnia-Herzegovina": "Bosnia-Herzegovina",
    "Ivory Coast": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "DR Congo": "Congo DR",
    "Congo DR": "Congo DR",
    "USA": "USA",
    "United States": "USA",
    "IR Iran": "Iran",
    "Iran": "Iran",
    "Cabo Verde": "Cabo Verde",
    "Cape Verde": "Cabo Verde",
    "Curaçao": "Curaçao",
    "Curacao": "Curaçao",
}

COUNTRY_CODE = {
    "Mexico": "MEX", "South Korea": "KOR",
    "South Africa": "RSA", "Czechia": "CZE",
    "Canada": "CAN", "Switzerland": "SUI",
    "Qatar": "QAT", "Bosnia-Herzegovina": "BIH",
    "Brazil": "BRA", "Morocco": "MAR",
    "Haiti": "HAI", "Scotland": "SCO",
    "USA": "USA", "Paraguay": "PAR",
    "Australia": "AUS", "Türkiye": "TUR",
    "Germany": "GER", "Curaçao": "CUW",
    "Ivory Coast": "CIV", "Ecuador": "ECU",
    "Netherlands": "NED", "Japan": "JPN",
    "Sweden": "SWE", "Tunisia": "TUN",
    "Belgium": "BEL", "Egypt": "EGY",
    "Iran": "IRN", "New Zealand": "NZL",
    "Spain": "ESP", "Cabo Verde": "CPV",
    "Saudi Arabia": "KSA", "Uruguay": "URU",
    "France": "FRA", "Senegal": "SEN",
    "Norway": "NOR", "Iraq": "IRQ",
    "Argentina": "ARG", "Algeria": "ALG",
    "Austria": "AUT", "Jordan": "JOR",
    "Portugal": "POR", "Colombia": "COL",
    "Congo DR": "COD", "Uzbekistan": "UZB",
    "England": "ENG", "Croatia": "CRO",
    "Ghana": "GHA", "Panama": "PAN",
    "Bosnia-Herzegovina": "BOSNIA-HRZ",
}

# Display name override for match cards: if value len > 3, use it instead of full name
def _card_name(team):
    code = COUNTRY_CODE.get(team, "")
    if len(code) > 3:
        return code
    return h(team).upper()


def _norm(name):
    """Normalize a team name through NAME_MAP; unknown names pass through."""
    return NAME_MAP.get(name, name)


def h(text):
    """HTML-escape a string."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

def pct_bar(left_pct, right_pct):
    total = left_pct + right_pct
    if total == 0:
        lw = rw = 50
    else:
        lw = round(left_pct / total * 100)
        rw = 100 - lw
    return (
        f'<div class="ko-bar-row">'
        f'<div class="ko-bar-seg ko-bar-l" style="width:{lw}%">'
        f'<span class="ko-bar-lbl">{left_pct}%</span></div>'
        f'<div class="ko-bar-seg ko-bar-r" style="width:{rw}%">'
        f'<span class="ko-bar-lbl ko-bar-lbl-r">{right_pct}%</span></div>'
        f'</div>'
    )

def ko_card(match_data, slot_label="", city="", is_final=False):
    teams = match_data.get("teams", [])
    likely_winner = match_data.get("likely_winner", "")
    predicted_score = match_data.get("predicted_score", "")
    mn = match_data.get("match", "")
    card_cls = "ko-card final-card" if is_final else "ko-card"

    if len(teams) >= 2:
        t1, t2 = teams[0], teams[1]
    elif len(teams) == 1:
        t1 = teams[0]
        t2 = {"name": "TBD", "reach_pct": 0, "win_if_reached_pct": 0, "overall_win_pct": 0}
    else:
        t1 = t2 = {"name": "TBD", "reach_pct": 0, "win_if_reached_pct": 0, "overall_win_pct": 0}

    t1_likely = t1["name"] == likely_winner
    t2_likely = t2["name"] == likely_winner

    city_str = f" &middot; {h(city)}" if city else ""
    slot_str = f'<span class="ko-slot">{h(slot_label)}</span>' if slot_label else ""

    lines = [
        f'<div class="{card_cls}">',
        f'  <div class="ko-head">M{mn}{city_str}{" &middot; " if slot_str else ""}{slot_str}</div>',
        f'  <div class="ko-matchup">',
        f'    <div class="ko-team{"  ko-wt" if t1_likely else ""}">',
        f'      <div class="ko-name">{h(t1["name"])}</div>',
        f'      <div class="ko-stat">Reaches&nbsp;{t1["reach_pct"]}% &bull; Wins&nbsp;if&nbsp;reached&nbsp;{t1["win_if_reached_pct"]}%</div>',
        f'    </div>',
        f'    <div class="ko-vs">vs</div>',
        f'    <div class="ko-team ko-right{"  ko-wt" if t2_likely else ""}">',
        f'      <div class="ko-name">{h(t2["name"])}</div>',
        f'      <div class="ko-stat">Reaches&nbsp;{t2["reach_pct"]}% &bull; Wins&nbsp;if&nbsp;reached&nbsp;{t2["win_if_reached_pct"]}%</div>',
        f'    </div>',
        f'  </div>',
        pct_bar(t1["overall_win_pct"], t2["overall_win_pct"]),
    ]

    if predicted_score:
        lines.append(f'  <div class="ko-predicted">&#9654;&nbsp;{h(predicted_score)}</div>')
    elif likely_winner:
        lines.append(f'  <div class="ko-predicted">&#10003;&nbsp;{h(likely_winner)} advances</div>')

    lines.append('</div>')
    return "\n".join(lines)

def b_match(t1_name, t1_pct, t2_name, t2_pct, likely_winner, predicted_score=None, winner_icon=""):
    t1_cls = "b-team likely" if t1_name == likely_winner else "b-team"
    t2_cls = "b-team likely" if t2_name == likely_winner else "b-team"
    t1_display = f"{winner_icon}&nbsp;{h(t1_name)}" if (winner_icon and t1_name == likely_winner) else h(t1_name)
    t2_display = f"{winner_icon}&nbsp;{h(t2_name)}" if (winner_icon and t2_name == likely_winner) else h(t2_name)
    score_line = ""
    if predicted_score:
        score_line = f'\n<div class="b-score">{h(predicted_score)}</div>'
    return (
        f'<div class="b-match">\n'
        f'  <div class="{t1_cls}"><span>{t1_display}</span><span class="b-team-pct">{t1_pct}%</span></div>\n'
        f'  <div class="{t2_cls}"><span>{t2_display}</span><span class="b-team-pct">{t2_pct}%</span></div>'
        f'{score_line}\n'
        f'</div>'
    )

# ── WC 2026 Group-stage schedule (Colombia time = UTC-5) ─────────────────────
# Format: (date_str YYYY-MM-DD, hour_col, minute_col, team1, team2, group, round_label)
def _load_fixtures():
    """Load fixtures from fixtures.json and return as schedule tuples."""
    try:
        with open(FIXTURES_FILE) as f:
            raw = json.load(f)
    except Exception:
        return []
    schedule = []
    for fx in raw:
        date_str = fx.get("date", "")
        time_str = fx.get("time", "00:00")
        home = _norm(fx.get("home", "TBD"))
        away = _norm(fx.get("away", "TBD"))
        match_num = fx.get("match_num")
        if match_num:
            round_label = f'{fx.get("round_name", "Knockout")} · M{match_num}'
            group = fx.get("round", "KO")
        else:
            group = fx.get("group", "?")
            md = fx.get("matchday", 1)
            round_label = f"Group {group} MD{md}"
        try:
            hour, minute = int(time_str[:2]), int(time_str[3:5])
        except Exception:
            hour, minute = 0, 0
        schedule.append((date_str, hour, minute, home, away, group, round_label, match_num))
    return sorted(schedule, key=lambda e: (e[0], e[1], e[2]))

COLOMBIA_OFFSET = timedelta(hours=-5)  # UTC-5


def _poisson_pmf(lam, k):
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _most_probable_score(lam1, lam2, max_goals=5):
    scores = {}
    for g1 in range(max_goals + 1):
        for g2 in range(max_goals + 1):
            scores[(g1, g2)] = _poisson_pmf(lam1, g1) * _poisson_pmf(lam2, g2)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    best_s = ranked[0][0]
    if best_s == (1, 1):
        total_p = sum(scores.values())
        win1 = sum(p for (g1, g2), p in scores.items() if g1 > g2) / total_p * 100
        win2 = sum(p for (g1, g2), p in scores.items() if g2 > g1) / total_p * 100
        if abs(win1 - win2) > 15:
            best_s = ranked[1][0]
    return best_s


def _over25_prob(lam1, lam2):
    """Probability that total goals > 2.5 (i.e. 3 or more)."""
    prob_under = 0.0
    for g1 in range(4):
        for g2 in range(4):
            if g1 + g2 <= 2:
                p1 = math.exp(-lam1) * (lam1**g1) / math.factorial(g1)
                p2 = math.exp(-lam2) * (lam2**g2) / math.factorial(g2)
                prob_under += p1 * p2
    return round((1 - prob_under) * 100, 1)


def _btts_prob(lam1, lam2):
    """Probability both teams score at least 1 goal."""
    p_team1_scores = 1 - math.exp(-lam1)
    p_team2_scores = 1 - math.exp(-lam2)
    return round(p_team1_scores * p_team2_scores * 100, 1)


_TEAM_STRENGTH_DATA: dict = {}


def _load_team_strength():
    global _TEAM_STRENGTH_DATA
    if not _TEAM_STRENGTH_DATA:
        try:
            with open(TEAM_STRENGTH_FILE) as f:
                _TEAM_STRENGTH_DATA = json.load(f)
        except Exception:
            pass


_MATCH_ADJUSTMENTS_DATA: dict = {}


def _load_match_adjustments():
    global _MATCH_ADJUSTMENTS_DATA
    if not _MATCH_ADJUSTMENTS_DATA:
        try:
            with open(MATCH_ADJUSTMENTS_FILE) as f:
                entries = json.load(f)
            by_match: dict = {}
            for entry in entries:
                by_match.setdefault(entry["match"], []).append(entry)
            _MATCH_ADJUSTMENTS_DATA = by_match
        except Exception:
            pass


_MATCH_STATS_DATA: dict = {}


def _load_match_stats():
    global _MATCH_STATS_DATA
    if not _MATCH_STATS_DATA:
        try:
            with open(MATCH_STATS_FILE) as f:
                entries = json.load(f)
            by_teams: dict = {}
            for entry in entries:
                key = frozenset([entry["team1"], entry["team2"]])
                by_teams.setdefault(key, []).append(entry)
            for key in by_teams:
                by_teams[key].sort(key=lambda e: e["date"])
            _MATCH_STATS_DATA = by_teams
        except Exception:
            pass


def _form_modifiers(team):
    """Return (atk_mod, def_mod) based on in-tournament shots-on-target performance.

    atk_mod: team's weighted SOT-for / tournament average — > 1 boosts their lambda.
    def_mod: team's weighted SOT-against / tournament average — > 1 boosts opponent's lambda.
    Both clamped to [0.85, 1.15]. Returns (1.0, 1.0) if no data.
    """
    if not _MATCH_STATS_DATA:
        return (1.0, 1.0)

    # Collect (date, sot_for, sot_against) for all this team's matches
    records = []
    for entries in _MATCH_STATS_DATA.values():
        for e in entries:
            if e["team1"] == team:
                sot_for = e["team1_stats"].get("shotsOnTarget")
                sot_ag  = e["team2_stats"].get("shotsOnTarget")
                if sot_for is None or sot_ag is None:
                    continue
                records.append((e["date"], sot_for, sot_ag))
            elif e["team2"] == team:
                sot_for = e["team2_stats"].get("shotsOnTarget")
                sot_ag  = e["team1_stats"].get("shotsOnTarget")
                if sot_for is None or sot_ag is None:
                    continue
                records.append((e["date"], sot_for, sot_ag))

    if not records:
        return (1.0, 1.0)

    records.sort(key=lambda r: r[0])  # oldest first
    n = len(records)

    # Exponential decay: most recent = 1.0, each older step = 0.5x
    weights = [0.5 ** (n - 1 - i) for i in range(n)]
    w_sum = sum(weights)
    weighted_sot_for     = sum(w * r[1] for w, r in zip(weights, records)) / w_sum
    weighted_sot_against = sum(w * r[2] for w, r in zip(weights, records)) / w_sum

    # Tournament-wide average SOT (all teams, all matches, no weighting — stable baseline)
    all_sot = []
    for entries in _MATCH_STATS_DATA.values():
        for e in entries:
            v1 = e["team1_stats"].get("shotsOnTarget")
            v2 = e["team2_stats"].get("shotsOnTarget")
            if v1 is not None:
                all_sot.append(v1)
            if v2 is not None:
                all_sot.append(v2)

    if not all_sot or sum(all_sot) == 0:
        return (1.0, 1.0)

    tournament_avg = sum(all_sot) / len(all_sot)

    atk_mod = max(0.85, min(1.15, weighted_sot_for     / tournament_avg))
    def_mod = max(0.85, min(1.15, weighted_sot_against / tournament_avg))
    return (atk_mod, def_mod)


def _strength_lambdas(team1, team2):
    """Return (lam1, lam2): lambda = 1.5 * (s_attack/s_defend)^2, capped [0.3, 3.5]."""
    _load_team_strength()
    s1 = _TEAM_STRENGTH_DATA.get(team1, {}).get("final_strength", 1600.0)
    s2 = _TEAM_STRENGTH_DATA.get(team2, {}).get("final_strength", 1600.0)
    lam1 = max(0.3, min(3.5, 1.5 * (s1 / s2) ** 2.0))
    lam2 = max(0.3, min(3.5, 1.5 * (s2 / s1) ** 2.0))

    _load_match_adjustments()
    adjustments = (_MATCH_ADJUSTMENTS_DATA.get(f"{team1} vs {team2}")
                   or _MATCH_ADJUSTMENTS_DATA.get(f"{team2} vs {team1}")
                   or [])
    for adj in adjustments:
        ratio = adj["adjusted_lambda"] / adj["base_lambda"]
        if adj["team"] == team1:
            lam1 *= ratio
        elif adj["team"] == team2:
            lam2 *= ratio

    lam1 = max(0.3, min(3.5, lam1))
    lam2 = max(0.3, min(3.5, lam2))

    # In-tournament form modifier: SOT-based attack/defence scaling
    _load_match_stats()
    if _MATCH_STATS_DATA:
        atk1, def1 = _form_modifiers(team1)
        atk2, def2 = _form_modifiers(team2)
        lam1 = lam1 * atk1 * def2
        lam2 = lam2 * atk2 * def1
        lam1 = max(0.3, min(3.5, lam1))
        lam2 = max(0.3, min(3.5, lam2))
    return lam1, lam2


def _ko_lookup(data):
    """Flatten knockout_bracket into {match_num: entry} for quick lookup."""
    kb = data.get("knockout_bracket", {})
    idx = {}
    for key in ("round_of_32", "round_of_16", "quarter_finals", "semi_finals"):
        for m in kb.get(key, []):
            idx[m["match"]] = m
    tp = kb.get("third_place_match_derived") or kb.get("third_place_match")
    if tp:
        idx[103] = tp
    if kb.get("final"):
        idx[104] = kb["final"]
    return idx


def _ko_bracket_key(num):
    """Map a knockout match number to its bracket_state.json slot key."""
    if 73 <= num <= 88:
        return f"R32 M{num}"
    if 89 <= num <= 96:
        return f"R16 M{num}"
    if 97 <= num <= 100:
        return f"QF M{num}"
    if 101 <= num <= 102:
        return f"SF M{num}"
    if num == 103:
        return "3P M103"
    if num == 104:
        return "Final Winner"
    return None


def _resolve_ko_slot(label, bracket):
    """Resolve a knockout fixture slot label to a confirmed real team name.

    Returns (display_name, confirmed). Slots of the form "1ST GROUP A" /
    "2ND GROUP A" resolve via bracket_state.json once that group position is
    CONFIRMED. "WINNER M.."/"LOSER M.." slots resolve via the knockout slot
    confirmed by update_bracket_state() once that match has been played.
    "3RD PLACE (POOL)" can't be resolved without the FIFA allocation table
    and stays PROJECTED. Anything else is assumed to be a real team name.
    """
    parts = label.split()
    if len(parts) == 3 and parts[1] == "GROUP" and parts[0] in ("1ST", "2ND"):
        ord_word = "1st" if parts[0] == "1ST" else "2nd"
        bk_key = f"Group {parts[2]} {ord_word}"
        slot = bracket.get(bk_key)
        if slot and slot.get("status") == "CONFIRMED":
            return _norm(slot.get("team", label)), True
        return label, False
    m = re.match(r"^(WINNER|LOSER) M(\d+)$", label)
    if m:
        bk_key = _ko_bracket_key(int(m.group(2)))
        slot = bracket.get(bk_key) if bk_key else None
        if slot and slot.get("status") == "CONFIRMED":
            team = slot.get("team") if m.group(1) == "WINNER" else slot.get("loser")
            if team:
                return _norm(team), True
        return label, False
    if label == "3RD PLACE (POOL)":
        return label, False
    return label, True


TOURNAMENT_START = datetime(2026, 6, 11, 0, 0, 0)  # midnight Col time on opening day


FLAG_EMOJI = {
    "Mexico": "🇲🇽", "Canada": "🇨🇦", "South Korea": "🇰🇷", "South Africa": "🇿🇦",
    "Czechia": "🇨🇿", "Switzerland": "🇨🇭", "Qatar": "🇶🇦", "Bosnia-Herzegovina": "🇧🇦",
    "Brazil": "🇧🇷", "Morocco": "🇲🇦", "Haiti": "🇭🇹", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "USA": "🇺🇸", "Paraguay": "🇵🇾", "Australia": "🇦🇺", "Türkiye": "🇹🇷",
    "Germany": "🇩🇪", "Curaçao": "🇨🇼", "Ivory Coast": "🇨🇮", "Ecuador": "🇪🇨",
    "Netherlands": "🇳🇱", "Japan": "🇯🇵", "Sweden": "🇸🇪", "Tunisia": "🇹🇳",
    "Belgium": "🇧🇪", "Egypt": "🇪🇬", "Iran": "🇮🇷", "New Zealand": "🇳🇿",
    "Spain": "🇪🇸", "Cabo Verde": "🇨🇻", "Saudi Arabia": "🇸🇦", "Uruguay": "🇺🇾",
    "France": "🇫🇷", "Senegal": "🇸🇳", "Norway": "🇳🇴", "Iraq": "🇮🇶",
    "Argentina": "🇦🇷", "Algeria": "🇩🇿", "Austria": "🇦🇹", "Jordan": "🇯🇴",
    "Portugal": "🇵🇹", "Colombia": "🇨🇴", "Congo DR": "🇨🇩", "Uzbekistan": "🇺🇿",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Croatia": "🇭🇷", "Ghana": "🇬🇭", "Panama": "🇵🇦",
    "TBD": "🏳️",
}

CONF_TOOLTIPS = {
    "HIGH": "Model is confident. One team has 60%+ win probability. Trust the winner pick and predicted score.",
    "MED":  "Competitive match. Favorite has a real edge but outcome is uncertain. Trust the winner pick, be cautious on exact score.",
    "LOW":  "Toss-up. Win probabilities are close. Any outcome is realistic. Consider the draw. Highest Pollaya risk.",
}

KO_ROUND_LABELS = {"R32": "ROUND OF 32", "R16": "ROUND OF 16", "QF": "QUARTERFINAL",
                   "SF": "SEMIFINAL", "3P": "THIRD PLACE", "F": "FINAL"}

R32_MATCHES = [
    {"num": 73,  "date": "Jun 28", "city": "Los Angeles",   "home": "2nd Group A", "away": "2nd Group B"},
    {"num": 74,  "date": "Jun 29", "city": "Boston",        "home": "1st Group E", "away": "best 3rd A/B/C/D/F"},
    {"num": 75,  "date": "Jun 29", "city": "Monterrey",     "home": "1st Group F", "away": "2nd Group C"},
    {"num": 76,  "date": "Jun 29", "city": "Houston",       "home": "1st Group C", "away": "2nd Group F"},
    {"num": 77,  "date": "Jun 30", "city": "New York/NJ",   "home": "1st Group I", "away": "best 3rd C/D/F/G/H"},
    {"num": 78,  "date": "Jun 30", "city": "Dallas",        "home": "2nd Group E", "away": "2nd Group I"},
    {"num": 79,  "date": "Jun 30", "city": "Mexico City",   "home": "1st Group A", "away": "best 3rd C/E/F/H/I"},
    {"num": 80,  "date": "Jul 1",  "city": "Atlanta",       "home": "1st Group L", "away": "best 3rd E/H/I/J/K"},
    {"num": 81,  "date": "Jul 1",  "city": "San Francisco", "home": "1st Group D", "away": "best 3rd B/E/F/I/J"},
    {"num": 82,  "date": "Jul 1",  "city": "Seattle",       "home": "1st Group G", "away": "best 3rd A/E/H/I/J"},
    {"num": 83,  "date": "Jul 2",  "city": "Toronto",       "home": "2nd Group K", "away": "2nd Group L"},
    {"num": 84,  "date": "Jul 2",  "city": "Los Angeles",   "home": "1st Group H", "away": "2nd Group J"},
    {"num": 85,  "date": "Jul 2",  "city": "Vancouver",     "home": "1st Group B", "away": "best 3rd E/F/G/I/J"},
    {"num": 86,  "date": "Jul 3",  "city": "Miami",         "home": "1st Group J", "away": "2nd Group H"},
    {"num": 87,  "date": "Jul 3",  "city": "Kansas City",   "home": "1st Group K", "away": "best 3rd D/E/I/J/L"},
    {"num": 88,  "date": "Jul 3",  "city": "Dallas",        "home": "2nd Group D", "away": "2nd Group G"},
]

R16_MATCHES = [
    {"num": 89, "home": "Winner M74", "away": "Winner M77"},
    {"num": 90, "home": "Winner M73", "away": "Winner M75"},
    {"num": 91, "home": "Winner M76", "away": "Winner M78"},
    {"num": 92, "home": "Winner M79", "away": "Winner M80"},
    {"num": 93, "home": "Winner M83", "away": "Winner M84"},
    {"num": 94, "home": "Winner M81", "away": "Winner M82"},
    {"num": 95, "home": "Winner M86", "away": "Winner M88"},
    {"num": 96, "home": "Winner M85", "away": "Winner M87"},
]

QF_MATCHES = [
    {"num": 97,  "home": "Winner M89", "away": "Winner M90"},
    {"num": 98,  "home": "Winner M93", "away": "Winner M94"},
    {"num": 99,  "home": "Winner M91", "away": "Winner M92"},
    {"num": 100, "home": "Winner M95", "away": "Winner M96"},
]

SF_MATCHES = [
    {"num": 101, "home": "Winner M97",  "away": "Winner M98"},
    {"num": 102, "home": "Winner M99",  "away": "Winner M100"},
]

THIRD_MATCH = {"num": 103, "home": "Loser M101",   "away": "Loser M102",   "date": "Jul 18", "city": "Miami"}
FINAL_MATCH = {"num": 104, "home": "Winner M101",  "away": "Winner M102",  "date": "Jul 19", "city": "MetLife Stadium, New York/NJ"}


def _build_match_venues():
    """Build venue lookup from fixtures.json."""
    try:
        with open(FIXTURES_FILE) as f:
            raw = json.load(f)
    except Exception:
        return {}
    venues = {}
    for fx in raw:
        home = _norm(fx.get("home", "TBD"))
        away = _norm(fx.get("away", "TBD"))
        venue = fx.get("venue", "")
        city = fx.get("city", "")
        loc = f"{venue} · {city}" if venue and city else city or venue or ""
        venues[(home, away)] = loc
    return venues

MATCH_VENUES = _build_match_venues()


def _load_lineups():
    """Load lineups.json, return dict keyed by (home_team, away_team)."""
    try:
        with open(LINEUPS_FILE) as f:
            data = json.load(f)
        if not isinstance(data, list):
            return {}
        result = {}
        for lu in data:
            match_str = lu.get("match", "")
            if " vs " in match_str:
                parts = match_str.split(" vs ", 1)
                result[(parts[0].strip(), parts[1].strip())] = lu
        return result
    except Exception:
        return {}


def _flag(team):
    return FLAG_EMOJI.get(team, "🏳️")


def _match_label(round_label, group):
    # "Group A MD1" → "GROUP A · MD 1"
    return round_label.upper().replace("MD", "· MD ")


def _upcoming_matches(data):
    """Return list of next 6 (pre-tournament) or next 48h (during) match dicts with computed stats."""
    sim_probs = {_norm(t["team"]): t["probability"] for t in data.get("all_teams", [])}
    skellam_index = {(e["home"], e["away"]): e
                     for e in data.get("match_probabilities", [])}
    ko_index = _ko_lookup(data)
    try:
        with open(BRACKET_STATE_FILE) as f:
            bracket = json.load(f)
    except Exception:
        bracket = {}

    now_utc = datetime.now(timezone.utc)
    now_col = (now_utc + COLOMBIA_OFFSET).replace(tzinfo=None)
    tournament_started = now_col >= TOURNAMENT_START
    cutoff = (now_col + timedelta(hours=48)) if tournament_started else None

    upcoming = []
    for entry in _load_fixtures():
        date_str, hour, minute, t1, t2, group, round_label, match_num = entry
        ko_col = datetime(
            int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]),
            hour, minute, 0,
        )
        if ko_col < now_col - timedelta(minutes=180):
            continue
        if cutoff is not None and ko_col > cutoff:
            continue
        upcoming.append((date_str, ko_col, t1, t2, group, round_label, match_num))

    if not tournament_started:
        upcoming = upcoming[:6]

    results = []
    for date_str, ko_col, t1_raw, t2_raw, group, round_label, match_num in upcoming:
        ko_fmt = ko_col.strftime("%-d %b · %H:%M COL")
        kickoff_utc_iso = (ko_col + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        if match_num:
            t1_disp, t1_confirmed = _resolve_ko_slot(t1_raw, bracket)
            t2_disp, t2_confirmed = _resolve_ko_slot(t2_raw, bracket)
            confirmed = t1_confirmed and t2_confirmed
            ko_entry = ko_index.get(match_num)

            result = {
                "is_ko": True,
                "match_num": match_num,
                "t1": t1_disp, "t2": t2_disp,
                "confirmed": confirmed,
                "venue": MATCH_VENUES.get((t1_disp, t2_disp), ""),
                "ko_fmt": ko_fmt, "match_lbl": _match_label(round_label, group),
                "date_str": date_str,
                "kickoff_utc": kickoff_utc_iso,
            }

            team_pcts = ({t["name"]: t["overall_win_pct"] for t in ko_entry.get("teams", [])}
                         if ko_entry else {})
            if confirmed and ko_entry and t1_disp in team_pcts and t2_disp in team_pcts:
                win_p1 = team_pcts.get(t1_disp, 0)
                win_p2 = team_pcts.get(t2_disp, 0)
                m_ = re.search(r"(\d+)-(\d+)", ko_entry.get("predicted_score", ""))
                wg, lg = (int(m_.group(1)), int(m_.group(2))) if m_ else (0, 0)
                likely_winner = ko_entry.get("likely_winner")
                if likely_winner == t1_disp:
                    score1, score2 = wg, lg
                else:
                    score1, score2 = lg, wg
                max_win = max(win_p1, win_p2)
                if max_win >= 60:
                    conf, conf_cls = "HIGH", "conf-high"
                elif max_win >= 45:
                    conf, conf_cls = "MED", "conf-med"
                else:
                    conf, conf_cls = "LOW", "conf-low"
                result.update({
                    "win_p1": win_p1, "win_p2": win_p2,
                    "score1": score1, "score2": score2,
                    "winner": likely_winner,
                    "conf": conf, "conf_cls": conf_cls,
                    "went_to_et": ko_entry.get("went_to_et", False),
                    "went_to_penalties": ko_entry.get("went_to_penalties", False),
                })
            results.append(result)
            continue

        t1 = _norm(t1_raw)
        t2 = _norm(t2_raw)
        sk = skellam_index.get((t1, t2))
        if sk:
            win_p1 = round(sk["skellam_win"]  * 100)
            win_p2 = round(sk["skellam_loss"] * 100)
            draw_p = 100 - win_p1 - win_p2
        else:
            p1 = sim_probs.get(t1, 1.0)
            p2 = sim_probs.get(t2, 1.0)
            total_p = p1 + p2 if (p1 + p2) > 0 else 1.0
            draw_boost = 0.25
            r1 = p1 / total_p
            r2 = p2 / total_p
            win_p1 = round(r1 * (1 - draw_boost) * 100)
            win_p2 = round(r2 * (1 - draw_boost) * 100)
            draw_p = 100 - win_p1 - win_p2

        lam1, lam2 = _strength_lambdas(t1, t2)
        score1, score2 = _most_probable_score(lam1, lam2)

        if win_p1 > win_p2:
            winner = t1
        elif win_p2 > win_p1:
            winner = t2
        else:
            winner = "DRAW"

        max_win = max(win_p1, win_p2)
        if max_win >= 60:
            conf, conf_cls = "HIGH", "conf-high"
        elif max_win >= 45:
            conf, conf_cls = "MED", "conf-med"
        else:
            conf, conf_cls = "LOW", "conf-low"

        venue = MATCH_VENUES.get((t1, t2), f"Group {group}")
        match_lbl = _match_label(round_label, group)

        results.append({
            "is_ko": False,
            "t1": t1, "t2": t2, "group": group,
            "win_p1": win_p1, "win_p2": win_p2, "draw_p": draw_p,
            "score1": score1, "score2": score2,
            "winner": winner,
            "conf": conf, "conf_cls": conf_cls,
            "venue": venue, "ko_fmt": ko_fmt, "match_lbl": match_lbl,
            "date_str": date_str,
            "kickoff_utc": kickoff_utc_iso,
            "skellam_win":  sk["skellam_win"]  if sk else None,
            "skellam_draw": sk["skellam_draw"] if sk else None,
            "skellam_loss": sk["skellam_loss"] if sk else None,
        })
    return results


def _lineup_badge_html(t1, t2, lineups):
    """Return lineup status badge HTML for a match card."""
    lu = lineups.get((t1, t2)) or lineups.get((t2, t1))
    if not lu:
        return '<div class="mc-lineup-badge lineup-pending">STARTING XI PENDING</div>'
    src = lu.get("source", "none")
    absences = lu.get("key_absences", [])
    home_xi = lu.get("home_xi", [])
    away_xi = lu.get("away_xi", [])
    xi_confirmed = src in ("rotowire", "api-football") and (len(home_xi) >= 5 or len(away_xi) >= 5)
    xi_estimated = src in ("espn-playwright", "bbc-playwright", "web-search") and bool(home_xi or away_xi)
    if absences:
        absent_name = absences[0]["player"].split()[-1]
        return f'<div class="mc-lineup-badge lineup-absent">&#9888; {h(absent_name)} OUT</div>'
    if xi_confirmed:
        return '<div class="mc-lineup-badge lineup-confirmed">LINEUP CONFIRMED</div>'
    if xi_estimated:
        return '<div class="mc-lineup-badge lineup-estimated">LINEUP ESTIMATED</div>'
    return '<div class="mc-lineup-badge lineup-pending">STARTING XI PENDING</div>'


def _match_cards_html(matches):
    """Render the FIFA-style match cards for the upcoming matches section."""
    from itertools import groupby
    lineups = _load_lineups()
    cards = ""
    card_index = 0
    for date_str, group_iter in groupby(matches, key=lambda m: m["date_str"]):
        match_date = datetime.strptime(date_str, "%Y-%m-%d")
        day_name = match_date.strftime("%A").upper()
        day_mon = match_date.strftime("%-d %b").upper()
        cards += f'\n<div class="date-header">{day_name} · {day_mon}</div>\n'
        cards += '<div class="matches-grid">\n'
        for m in group_iter:
            card_index += 1
            delay = card_index * 200

            if m.get("is_ko"):
                if not m["confirmed"] or "win_p1" not in m:
                    # Confirmed teams whose sim entry doesn't match reality get
                    # real names/flags but no probabilities (honest state until
                    # run_predictions is conditioned on confirmed results).
                    if m["confirmed"]:
                        name_style = ""
                        flag1 = f'<span class="mc-flag">{_flag(m["t1"])}</span>'
                        flag2 = f'<span class="mc-flag">{_flag(m["t2"])}</span>'
                    else:
                        name_style = ' style="font-style:italic;opacity:0.55"'
                        flag1 = flag2 = ""
                    cards += f'''<div class="match-card ko-pending-card" style="animation-delay:{delay}ms" data-kickoff="{m["kickoff_utc"]}">
  <div class="mc-card-header">
    <span class="mc-card-label">{h(m["match_lbl"])}</span>
  </div>
  <div class="mc-venue-row">{h(m["venue"])} · {h(m["ko_fmt"])}</div>
  <span class="countdown-timer"></span>
  <div class="teams-score-row">
    <div class="mc-team">
      {flag1}<span class="mc-name"{name_style}>{h(m["t1"])}</span>
    </div>
    <div class="mc-score-block">
      <div class="mc-score-label" style="opacity:0.55">TBD</div>
    </div>
    <div class="mc-team mc-team-right">
      {flag2}<span class="mc-name"{name_style}>{h(m["t2"])}</span>
    </div>
  </div>
</div>
'''
                else:
                    t1, t2 = m["t1"], m["t2"]
                    t1_abbr = COUNTRY_CODE.get(t1, t1[:3].upper())
                    t2_abbr = COUNTRY_CODE.get(t2, t2[:3].upper())
                    t1_abbr = t1_abbr[:3] if len(t1_abbr) > 3 else t1_abbr
                    t2_abbr = t2_abbr[:3] if len(t2_abbr) > 3 else t2_abbr
                    score_chip = f'SCORE {m["score1"]}-{m["score2"]} 15pts'
                    w_code = COUNTRY_CODE.get(m["winner"], m["winner"][:3].upper())
                    w_code = w_code[:3] if len(w_code) > 3 else w_code
                    win_chip = f'WIN {h(w_code)} 8pts'
                    goals_chip = f'{t1_abbr}{m["score1"]} {t2_abbr}{m["score2"]} 5pts'
                    extra_label = ""
                    if m.get("went_to_penalties"):
                        extra_label = '<div style="font-size:10px;color:#F59E0B;text-align:center;margin-top:4px;letter-spacing:0.05em;">MAY GO TO PENALTIES</div>'
                    elif m.get("went_to_et"):
                        extra_label = '<div style="font-size:10px;color:#C9A84C;text-align:center;margin-top:4px;letter-spacing:0.05em;">INCL. EXTRA TIME</div>'
                    cards += f'''<div class="match-card" style="animation-delay:{delay}ms" data-kickoff="{m["kickoff_utc"]}">
  <div class="mc-card-header">
    <span class="mc-card-label">{h(m["match_lbl"])}</span>
    <span class="mc-conf-badge confidence-badge {m["conf_cls"]}" data-tooltip="{CONF_TOOLTIPS[m["conf"]]}">{m["conf"]} <span style="font-size:10px;opacity:0.6;font-weight:400;">?</span></span>
  </div>
  <div class="mc-venue-row">{h(m["venue"])} · {h(m["ko_fmt"])}</div>
  <span class="countdown-timer"></span>
  <div class="teams-score-row">
    <div class="mc-team">
      <span class="mc-flag">{_flag(t1)}</span>
      <span class="mc-name">{h(t1)}</span>
      <span class="mc-prob">{m["win_p1"]}%</span>
    </div>
    <div class="mc-score-block">
      <div class="mc-score score-display" data-home="{m["score1"]}" data-away="{m["score2"]}"><span class="home-score">{m["score1"]}</span>–<span class="away-score">{m["score2"]}</span></div>
      <div class="mc-score-label">PREDICTED</div>
      <div class="live-score-display"><span class="live-dot"></span><span class="live-label">LIVE</span></div>
      {extra_label}
    </div>
    <div class="mc-team mc-team-right">
      <span class="mc-flag">{_flag(t2)}</span>
      <span class="mc-name">{h(t2)}</span>
      <span class="mc-prob">{m["win_p2"]}%</span>
    </div>
  </div>
  <div class="mc-chips">
    <div class="mc-chip chip-gold">{score_chip}</div>
    <div class="mc-chip chip-red">{win_chip}</div>
    <div class="mc-chip chip-blue">{goals_chip}</div>
  </div>
</div>
'''
                continue

            t1, t2 = m["t1"], m["t2"]
            t1_abbr = COUNTRY_CODE.get(t1, t1[:3].upper())
            t2_abbr = COUNTRY_CODE.get(t2, t2[:3].upper())
            t1_abbr = t1_abbr[:3] if len(t1_abbr) > 3 else t1_abbr
            t2_abbr = t2_abbr[:3] if len(t2_abbr) > 3 else t2_abbr
            colombia_style = ' style="border-left:3px solid #C9A84C"' if "Colombia" in (t1, t2) else ""
            lineup_badge = _lineup_badge_html(t1, t2, lineups)
            venue_time = f'{h(m["venue"])} · {h(m["ko_fmt"])}'
            sk_win  = m.get("skellam_win")
            sk_draw = m.get("skellam_draw")
            sk_loss = m.get("skellam_loss")
            if sk_win is not None:
                w_pct = round(sk_win  * 100)
                d_pct = round(sk_draw * 100)
                l_pct = max(0, 100 - w_pct - d_pct)
                w_lbl = f'{w_pct}%' if w_pct > 15 else ''
                d_lbl = f'{d_pct}%' if d_pct > 15 else ''
                l_lbl = f'{l_pct}%' if l_pct > 15 else ''
                skellam_bar = (
                    f'<div style="display:flex;height:18px;border-radius:4px;overflow:hidden;'
                    f'margin:0 12px 8px;font-size:10px;font-weight:700;letter-spacing:0.04em;">'
                    f'<div style="width:{w_pct}%;background:#22C55E;display:flex;align-items:center;'
                    f'justify-content:center;color:#fff;">{w_lbl}</div>'
                    f'<div style="width:{d_pct}%;background:#4A6080;display:flex;align-items:center;'
                    f'justify-content:center;color:#fff;">{d_lbl}</div>'
                    f'<div style="width:{l_pct}%;background:#E8002D;display:flex;align-items:center;'
                    f'justify-content:center;color:#fff;">{l_lbl}</div>'
                    f'</div>'
                )
            else:
                skellam_bar = ''
            score_chip = f'SCORE {m["score1"]}-{m["score2"]} 15pts'
            if m["winner"] == "DRAW":
                win_chip = 'DRAW 8pts'
            else:
                w_code = COUNTRY_CODE.get(m["winner"], m["winner"][:3].upper())
                w_code = w_code[:3] if len(w_code) > 3 else w_code
                win_chip = f'WIN {h(w_code)} 8pts'
            goals_chip = f'{t1_abbr}{m["score1"]} {t2_abbr}{m["score2"]} 5pts'
            lam1, lam2 = _strength_lambdas(t1, t2)
            over25 = _over25_prob(lam1, lam2)
            btts = _btts_prob(lam1, lam2)
            over25_chip = f'O2.5 {over25}%'
            btts_chip = f'BTTS {btts}%'
            cards += f'''<div class="match-card" style="animation-delay:{delay}ms"{colombia_style} data-kickoff="{m["kickoff_utc"]}">
  <div class="mc-card-header">
    <span class="mc-card-label">{h(m["match_lbl"])}</span>
    <span class="mc-conf-badge confidence-badge {m["conf_cls"]}" data-tooltip="{CONF_TOOLTIPS[m["conf"]]}">{m["conf"]} <span style="font-size:10px;opacity:0.6;font-weight:400;">?</span></span>
  </div>
  <div class="mc-venue-row">{venue_time}</div>
  <span class="countdown-timer"></span>
  <div class="mc-lineup-wrap">{lineup_badge}</div>
  <div class="teams-score-row">
    <div class="mc-team">
      <span class="mc-flag">{_flag(t1)}</span>
      <span class="mc-name">{h(t1)}</span>
      <span class="mc-prob">{m["win_p1"]}%</span>
    </div>
    <div class="mc-score-block">
      <div class="mc-score score-display" data-home="{m["score1"]}" data-away="{m["score2"]}"><span class="home-score">{m["score1"]}</span>–<span class="away-score">{m["score2"]}</span></div>
      <div class="mc-score-label">PREDICTED</div>
      <div class="live-score-display"><span class="live-dot"></span><span class="live-label">LIVE</span></div>
    </div>
    <div class="mc-team mc-team-right">
      <span class="mc-flag">{_flag(t2)}</span>
      <span class="mc-name">{h(t2)}</span>
      <span class="mc-prob">{m["win_p2"]}%</span>
    </div>
  </div>
  {skellam_bar}
  <div class="mc-chips">
    <div class="mc-chip chip-gold">{score_chip}</div>
    <div class="mc-chip chip-red">{win_chip}</div>
    <div class="mc-chip chip-blue">{goals_chip}</div>
    <div class="mc-chip chip-teal">{over25_chip}</div>
    <div class="mc-chip chip-purple confidence-badge tooltip-up"
         data-tooltip="Both Teams To Score: probability that BOTH teams finish with at least 1 goal. High % = open game, both sides likely to score. Low % = expect a clean sheet or one-sided match."
         tabindex="0">
      {btts_chip} <span style="font-size:10px;opacity:0.6;font-weight:400;">?</span>
    </div>
  </div>
</div>
'''
        cards += '</div>\n'
    return cards


def _compute_golden_boot(data):
    """
    Predict the Golden Boot winner.

    Method:
    - The winning team's players are favoured because they play the most matches.
    - Among the winner's squad, pick the forward/midfielder with the highest goals
      rate (goals per minute * expected minutes in tournament).
    - Expected tournament matches for the winner ≈ 7 (group 3 + KO 4 through Final).
    - Fallback: if no player data, use 'Top scorer' placeholder.

    Returns dict with keys: player, team, expected_goals
    """
    try:
        with open(PLAYER_STATS_FILE) as f:
            player_stats = json.load(f)
        with open(TEAM_STRENGTH_FILE) as f:
            team_strength = json.load(f)
    except Exception:
        return {"player": "—", "team": "—", "expected_goals": 0}

    winner_team = data.get("predicted_winner", "")
    # Expected matches: winner plays 7 (3 group + R32 + R16 + QF + SF + Final = 7 KO = 7 total KO, +3 group = 7)
    # Actually: 3 group + R32 + R16 + QF + SF + Final = 3 + 5 = 8 matches but we use 7 as conservative
    expected_matches = 7
    minutes_per_match = 90

    avg_strength = sum(v["final_strength"] for v in team_strength.values()) / len(team_strength)

    # Try to find attack-focused players for the winning team
    players = player_stats.get(winner_team, [])
    if not players:
        # Try close-strength teams as proxy
        for team_name, ts_data in team_strength.items():
            if team_name != winner_team and team_name in player_stats:
                players = player_stats[team_name]
                break

    best_player = None
    best_xg = 0.0

    for p in players:
        if p.get("position", "") not in ("Attacker", "Midfielder"):
            continue
        goals = p.get("goals", 0)
        minutes = p.get("minutes", 0)
        if minutes <= 0:
            continue
        goals_per_90 = goals / minutes * 90
        # Scale by team's attack strength relative to average
        team_s = team_strength.get(winner_team, {}).get("final_strength", avg_strength)
        attack_boost = team_s / avg_strength
        xg_tournament = goals_per_90 * (expected_matches * minutes_per_match / 90) * attack_boost
        if xg_tournament > best_xg:
            best_xg = xg_tournament
            best_player = p["name"]

    if not best_player:
        best_player = "Top scorer TBD"
        best_xg = 0.0

    return {
        "player": best_player,
        "team": winner_team,
        "expected_goals": round(best_xg, 1),
    }


def _bracket_section_html():
    """Build the collapsible Knockout Bracket section HTML body."""
    try:
        with open(BRACKET_STATE_FILE) as f:
            bracket = json.load(f)
    except Exception:
        bracket = {}

    confirmed_count = sum(1 for v in bracket.values() if v.get("status") == "CONFIRMED")
    total_slots = len(bracket)
    pending_count = total_slots - confirmed_count

    if confirmed_count == 0:
        phase = 1
    elif confirmed_count < 32:
        phase = 2
    else:
        phase = 3

    header_label = (
        f'KNOCKOUT BRACKET'
        f' · <span class="bracket-confirmed-count">{confirmed_count} CONFIRMED</span>'
        f' · <span style="color:#4A6080">{pending_count} PENDING</span>'
    )

    def _slot_display(slot_label):
        """Return HTML for a slot, using real team name if confirmed in bracket_state."""
        parts = slot_label.split()
        bk_key = None
        if len(parts) >= 3 and parts[0] in ("1st", "2nd") and parts[1] == "Group":
            bk_key = f"Group {parts[2]} {parts[0]}"
        is_third = slot_label.startswith("best 3rd")
        if bk_key and bk_key in bracket:
            slot_data = bracket[bk_key]
            if slot_data.get("status") == "CONFIRMED":
                team = h(slot_data.get("team", "TBD"))
                return f'<span class="bk-slot-confirmed">&#10003; {team}</span>'
        if is_third:
            groups = slot_label.replace("best 3rd ", "")
            return (
                f'<span class="bk-slot-label">BEST 3RD</span>'
                f'<span class="bk-third-pill">{h(groups)}</span>'
            )
        return f'<span class="bk-slot-label">{h(slot_label.upper())}</span>'

    def _r32_cards():
        cards = ""
        for m in R32_MATCHES:
            home_html = _slot_display(m["home"])
            away_html = _slot_display(m["away"])
            cards += (
                f'<div class="bk-r32-card">'
                f'<div class="bk-match-meta">M{m["num"]} &middot; {h(m["date"])} &middot; '
                f'<span class="bk-city">{h(m["city"])}</span></div>'
                f'<div class="bk-matchup-row">'
                f'<div class="bk-slot-cell">{home_html}</div>'
                f'<div class="bk-vs-cell">VS</div>'
                f'<div class="bk-slot-cell bk-slot-right">{away_html}</div>'
                f'</div>'
                f'</div>'
            )
        return cards

    def _later_rounds():
        def _late_team(label):
            m = re.match(r"^(Winner|Loser) M(\d+)$", label)
            if m:
                bk_key = _ko_bracket_key(int(m.group(2)))
                slot = bracket.get(bk_key) if bk_key else None
                if slot and slot.get("status") == "CONFIRMED":
                    team = slot.get("team") if m.group(1) == "Winner" else slot.get("loser")
                    if team:
                        return f'<span class="bk-slot-confirmed">&#10003; {h(team)}</span>'
            return f'<span class="bk-late-team">{h(label)}</span>'

        def _line(num, home, away, extra=""):
            return (
                f'<div class="bk-late-match">M{num} &middot; '
                f'{_late_team(home)}'
                f' <span class="bk-late-vs">vs</span> '
                f'{_late_team(away)}'
                f'{extra}</div>'
            )
        out = ""
        out += '<div class="bk-late-section"><div class="bk-late-header">ROUND OF 16</div>'
        for m in R16_MATCHES:
            out += _line(m["num"], m["home"], m["away"])
        out += '</div>'
        out += '<div class="bk-late-section"><div class="bk-late-header">QUARTERFINALS</div>'
        for m in QF_MATCHES:
            out += _line(m["num"], m["home"], m["away"])
        out += '</div>'
        out += '<div class="bk-late-section"><div class="bk-late-header">SEMIFINALS</div>'
        for m in SF_MATCHES:
            out += _line(m["num"], m["home"], m["away"])
        out += '</div>'
        tm = THIRD_MATCH
        out += '<div class="bk-late-section"><div class="bk-late-header">THIRD PLACE</div>'
        out += _line(tm["num"], tm["home"], tm["away"],
                     f' &middot; {h(tm["date"])} &middot; {h(tm["city"])}')
        out += '</div>'
        fm = FINAL_MATCH
        out += '<div class="bk-late-section"><div class="bk-late-header bk-final-header">FINAL</div>'
        out += _line(fm["num"], fm["home"], fm["away"],
                     f' &middot; {h(fm["date"])} &middot; {h(fm["city"])}')
        out += '</div>'
        return out

    r32_html = _r32_cards()

    later_html = _later_rounds()
    if phase == 1:
        note = (
            '<div class="bk-phase-note">Bracket structure is pre-defined by FIFA. '
            'Team names fill in automatically from June 24 as groups complete.</div>'
        )
        body_html = note + '<div class="bk-r32-grid">' + r32_html + '</div>' + later_html
    elif phase == 2:
        body_html = '<div class="bk-r32-grid">' + r32_html + '</div>' + later_html
    else:
        body_html = '<div class="bk-r32-grid">' + r32_html + '</div>' + later_html

    return header_label, body_html


def _build_wc_matches_json():
    """Build JS array of all match kickoff times in UTC from fixtures.json."""
    try:
        with open(FIXTURES_FILE) as f:
            raw = json.load(f)
    except Exception:
        return "[]"
    matches = []
    for fx in raw:
        date_str = fx.get("date", "")
        time_str = fx.get("time", "00:00")
        match_num = fx.get("match_num")
        try:
            hour, minute = int(time_str[:2]), int(time_str[3:5])
        except Exception:
            hour, minute = 0, 0
        ko_col = datetime(
            int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]),
            hour, minute,
        )
        ko_utc = ko_col + timedelta(hours=5)  # COT = UTC-5, so UTC = COT + 5
        utc_str = ko_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        if match_num:
            label = f'{fx.get("round", "KO")} M{match_num}'
        else:
            home = _norm(fx.get("home", "TBD"))
            away = _norm(fx.get("away", "TBD"))
            home_code = COUNTRY_CODE.get(home, home[:3].upper())
            away_code = COUNTRY_CODE.get(away, away[:3].upper())
            home_code = home_code[:3] if len(home_code) > 3 else home_code
            away_code = away_code[:3] if len(away_code) > 3 else away_code
            label = f"{home_code} vs {away_code}"
        matches.append({"label": label, "utc": utc_str})
    matches.sort(key=lambda m: m["utc"])
    return json.dumps(matches, separators=(",", ":"))


def _elo_impact_str(t1, t2, hs, as_, date_str, elo_data):
    """Estimate per-match ELO impact (same K/formula as fetch_results.py).

    elo_ratings.json only stores current ratings, so this recomputes the
    delta from them — error vs the applied delta is well under one point.
    Returns "" when either team is missing, so nothing is shown over zeros.
    """
    d1 = elo_data.get(t1, {})
    d2 = elo_data.get(t2, {})
    if "elo" not in d1 or "elo" not in d2:
        return ""
    try:
        days_ago = (date.today() - date.fromisoformat(date_str)).days
    except Exception:
        days_ago = 0
    k = 40 * math.exp(-math.log(2) / 180 * max(0, days_ago))
    e1, e2 = d1["elo"], d2["elo"]
    exp1 = 1.0 / (1.0 + 10 ** ((e2 - e1) / 400.0))
    if hs > as_:
        act1 = 1.0
    elif hs < as_:
        act1 = 0.0
    else:
        act1 = 0.5
    delta1 = k * (act1 - exp1)
    delta2 = -delta1
    c1 = COUNTRY_CODE.get(t1, t1[:3].upper())[:3]
    c2 = COUNTRY_CODE.get(t2, t2[:3].upper())[:3]
    return f"{c1} {delta1:+.1f} · {c2} {delta2:+.1f}"


def _results_section_html():
    """Build the MATCH RESULTS section from wc2026_results.json.

    Hidden entirely (display:none, no placeholder) while no completed
    matches exist; appears automatically on the first regeneration after
    the pipeline writes a result.
    """
    try:
        with open(RESULTS_FILE) as f:
            results = json.load(f)
        if not isinstance(results, list):
            results = []
    except Exception:
        results = []

    if not results:
        return '<div class="results-section" id="results-section" style="display:none"></div>'

    try:
        with open(_ROOT / "elo_ratings.json") as f:
            elo_data = json.load(f)
    except Exception:
        elo_data = {}

    # Fixture lookup for kickoff time, group and matchday
    fixture_info = {}
    fixture_by_num = {}
    try:
        with open(FIXTURES_FILE) as f:
            for fx in json.load(f):
                fixture_info[(_norm(fx.get("home", "")), _norm(fx.get("away", "")))] = fx
                if fx.get("match_num"):
                    fixture_by_num[fx["match_num"]] = fx
    except Exception:
        pass

    entries = []
    for r in results:
        t1 = _norm(r.get("team1", "TBD"))
        t2 = _norm(r.get("team2", "TBD"))
        hs = r.get("home_score", 0)
        as_ = r.get("away_score", 0)
        date_str = r.get("date", "")
        fx = (fixture_by_num.get(r.get("match_num"))
              or fixture_info.get((t1, t2)) or fixture_info.get((t2, t1)) or {})
        time_str = fx.get("time", "15:00")
        try:
            hour, minute = int(time_str[:2]), int(time_str[3:5])
        except Exception:
            hour, minute = 15, 0
        try:
            ko_col = datetime(
                int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]),
                hour, minute,
            )
        except Exception:
            ko_col = TOURNAMENT_START
        # Match end ≈ kickoff + 110 min; COT = UTC-5
        ended_utc = ko_col + timedelta(hours=5, minutes=110)
        group = r.get("group") or fx.get("group", "")
        rnd = (r.get("round") or "").upper()
        code = rnd or (group.upper() if isinstance(group, str) else "")
        if r.get("match_num") or code in ("R32", "R16", "QF", "SF", "3P"):
            label = KO_ROUND_LABELS.get(code, code or date_str)
        elif group:
            md = fx.get("matchday", "")
            label = f"GROUP {group} · MD {md}" if md else f"GROUP {group}"
        elif rnd:
            label = rnd
        else:
            label = date_str
        entries.append((ended_utc, t1, t2, hs, as_, date_str, label))

    entries.sort(key=lambda e: e[0], reverse=True)

    def _card(e):
        ended_utc, t1, t2, hs, as_, date_str, label = e
        if hs > as_:
            accent, c1, c2 = "#22C55E", "rc-win", "rc-lose"
        elif hs < as_:
            accent, c1, c2 = "#E8002D", "rc-lose", "rc-win"
        else:
            accent, c1, c2 = "#C9A84C", "rc-win", "rc-win"
        elo_line = _elo_impact_str(t1, t2, hs, as_, date_str, elo_data)
        elo_html = f'\n  <div class="rc-elo">{h(elo_line)}</div>' if elo_line else ""
        ended_iso = ended_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        return f'''<div class="result-card" style="border-left:3px solid {accent}" data-ended="{ended_iso}">
  <div class="rc-meta"><span>{h(label)}</span><span class="rc-time"></span></div>
  <div class="rc-row">
    <div class="rc-team {c1}"><span class="rc-flag">{_flag(t1)}</span><span class="rc-name">{h(t1)}</span></div>
    <div class="rc-score">{hs}–{as_}</div>
    <div class="rc-team rc-right {c2}"><span class="rc-flag">{_flag(t2)}</span><span class="rc-name">{h(t2)}</span></div>
  </div>{elo_html}
</div>'''

    visible = "\n".join(_card(e) for e in entries[:6])
    extra = ""
    toggle = ""
    if len(entries) > 6:
        extra_cards = "\n".join(_card(e) for e in entries[6:])
        extra = f'\n<div class="results-extra" id="results-extra" style="display:none">\n{extra_cards}\n</div>'
        toggle = (
            f'\n  <div class="results-show-all" id="results-show-all" '
            f'onclick="toggleAllResults()">Show all {len(entries)} results &#9662;</div>'
        )

    return f'''<div class="results-section" id="results-section">
  <div class="results-header">MATCH RESULTS<span class="results-live-dot" id="results-live-dot" style="display:none"></span></div>
  <div class="results-list">
{visible}{extra}
  </div>{toggle}
</div>'''


def build_html(data):
    sims        = data.get("simulations", 0)
    winner      = data.get("predicted_winner", "TBD")
    winner_pct  = data.get("predicted_winner_probability_pct", 0.0)
    runners_up  = data.get("runners_up", [{"team": "—", "probability": 0}])
    third_place = data.get("third_place", [{"team": "—", "probability": 0}])
    all_teams   = data.get("all_teams", [])
    now_utc = datetime.now(timezone.utc)

    # Runner-up and third place come from their dedicated lists, not all_teams rank.
    # all_teams ranks by champion probability, which differs from finishing position.
    runner = runners_up[0]   if runners_up   else {"team": "—", "probability": 0}
    third  = third_place[0]  if third_place  else {"team": "—", "probability": 0}
    winner_entry = all_teams[0] if all_teams else {}
    winner_ci_low  = round(winner_entry.get("ci_low",  winner_pct), 1)
    winner_ci_high = round(winner_entry.get("ci_high", winner_pct), 1)

    runner_prob = runner["probability"]
    third_prob  = third["probability"]
    if runner_prob <= third_prob:
        print(
            f"[WARN] Runner-Up probability ({runner['team']} "
            f"{runner_prob}%) is not greater than Third Place "
            f"({third['team']} {third_prob}%) — swapping entries "
            f"to preserve display invariant."
        )
        runners_up[0], third_place[0] = third_place[0], runners_up[0]
        runner, third = third, runner
        runner_prob, third_prob = third_prob, runner_prob
    golden_boot = _compute_golden_boot(data)

    try:
        with open(_ROOT / "elo_ratings.json") as f:
            elo_data = json.load(f)
    except Exception:
        elo_data = {}

    matches = _upcoming_matches(data)
    match_cards = _match_cards_html(matches)
    bracket_header_label, bracket_body_html = _bracket_section_html()
    results_section_html = _results_section_html()

    countdown_html = '<div class="countdown-banner" id="main-banner"><span id="banner-text">Loading...</span></div>'
    wc_matches_json = _build_wc_matches_json()

    top5_rows = ""
    for i, item in enumerate(all_teams[:5]):
        bar_w = round(item["probability"] / winner_pct * 100)
        _rd = elo_data.get(item["team"], {}).get("rd", 0)
        _rd_dot = (
            f' <span style="color:#EF9F27;font-size:10px;" '
            f'title="Rating uncertainty high — fewer matches observed">&#9679;</span>'
            if _rd > 150 else ""
        )
        top5_rows += (
            f'<div class="conf-row">'
            f'<span class="conf-rank">{i+1}</span>'
            f'<span class="conf-team">{_flag(item["team"])} {h(item["team"]).upper()}{_rd_dot}</span>'
            f'<div class="conf-bar-wrap"><div class="conf-bar-fill" style="width:{bar_w}%"></div></div>'
            f'<span class="conf-pct">{item["probability"]}%</span>'
            f'</div>\n'
        )

    import time as _time
    COT = timezone(timedelta(hours=-5))
    now_cot = datetime.now(COT)
    ts = now_cot.strftime("%Y-%m-%d %H:%M COT")
    version = int(_time.time())

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
  <meta name="theme-color" content="#0A1628" />
  <title>Pollaya 2026</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;900&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <!-- version: {version} -->
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --fifa-navy:    #0A1628;
      --fifa-red:     #E8002D;
      --fifa-white:   #FFFFFF;
      --fifa-gold:    #C9A84C;
      --fifa-dark:    #000000;
      --fifa-card:    #0A0F1A;
      --fifa-card-hover: #1A2B40;
      --fifa-border:  #1A2640;
      --fifa-text-primary:   #FFFFFF;
      --fifa-text-secondary: #8BA0BB;
      --fifa-text-muted:     #4A6080;
      --fifa-green:   #22C55E;
      --fifa-green-dim: #1A3320;
      --fifa-silver:  #A8B8C8;
      --fifa-bronze:  #A06830;
    }}
    html {{ background: var(--fifa-dark); }}
    body {{
      background: var(--fifa-dark);
      color: var(--fifa-text-primary);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      padding-bottom: 80px;
      -webkit-font-smoothing: antialiased;
      position: relative;
      overflow-x: hidden;
    }}
    body::before {{
      content: '';
      position: fixed;
      top: -50%;
      left: -50%;
      width: 200%;
      height: 200%;
      background: conic-gradient(
        from 0deg at 30% 40%,
        rgba(14, 165, 233, 0.06) 0deg,
        rgba(201, 168, 76, 0.04) 90deg,
        rgba(232, 0, 45, 0.03) 180deg,
        rgba(10, 22, 40, 0.08) 270deg,
        rgba(14, 165, 233, 0.06) 360deg
      );
      animation: auroraFlow 14s ease-in-out infinite alternate;
      z-index: 0;
      pointer-events: none;
    }}
    @keyframes auroraFlow {{
      0%   {{ transform: rotate(0deg) scale(1);   opacity: 0.6; }}
      50%  {{ transform: rotate(180deg) scale(1.1); opacity: 0.8; }}
      100% {{ transform: rotate(360deg) scale(1);  opacity: 0.6; }}
    }}
    /* ── Stadium background v2 ──
       Layer 1 (body::after, z 0): fluorescent mown-pitch stripes.
       Layer 2 (#floodlights, z 1): warm white corner beams + gold top glow.
       Layer 3 (#crowd-wave, z 1): color wash cycling red/gold/blue at the
       bottom edge. Content sections sit at z-index 2. */
    body::after {{
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      z-index: 0;
      background: repeating-linear-gradient(
        165deg,
        rgba(60, 255, 110, 0.22) 0px,
        rgba(60, 255, 110, 0.22) 60px,
        rgba(40, 230, 90, 0.12) 60px,
        rgba(40, 230, 90, 0.12) 120px
      );
      animation: pitchShimmer 3s ease-in-out infinite alternate;
    }}
    @keyframes pitchShimmer {{
      0% {{
        opacity: 0.7;
        background-position: 0 0;
      }}
      100% {{
        opacity: 1.0;
        background-position: 20px 20px;
      }}
    }}
    #floodlights {{
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      z-index: 1;
      background:
        radial-gradient(
          ellipse 55% 65% at 0% 0%,
          rgba(255, 255, 200, 0.30) 0%,
          rgba(255, 255, 200, 0.10) 40%,
          transparent 70%
        ),
        radial-gradient(
          ellipse 55% 65% at 100% 0%,
          rgba(255, 255, 200, 0.26) 0%,
          rgba(255, 255, 200, 0.09) 40%,
          transparent 70%
        ),
        radial-gradient(
          ellipse 45% 55% at 0% 100%,
          rgba(255, 255, 200, 0.18) 0%,
          transparent 60%
        ),
        radial-gradient(
          ellipse 45% 55% at 100% 100%,
          rgba(255, 255, 200, 0.18) 0%,
          transparent 60%
        ),
        radial-gradient(
          ellipse 40% 50% at 50% 0%,
          rgba(201, 168, 76, 0.24) 0%,
          rgba(201, 168, 76, 0.08) 40%,
          transparent 65%
        );
      animation: floodlightPulse 4s ease-in-out infinite alternate;
    }}
    @keyframes floodlightPulse {{
      0% {{
        opacity: 0.7;
        filter: brightness(0.9);
      }}
      50% {{
        opacity: 1.0;
        filter: brightness(1.2);
      }}
      100% {{
        opacity: 0.85;
        filter: brightness(1.0);
      }}
    }}
    #crowd-wave {{
      position: fixed;
      bottom: 0;
      left: 0;
      width: 100%;
      height: 45%;
      pointer-events: none;
      z-index: 1;
      animation: crowdWave 5s ease-in-out infinite alternate;
    }}
    @keyframes crowdWave {{
      0% {{
        opacity: 0.6;
        transform: translateY(8px);
        background: linear-gradient(
          to top,
          rgba(232, 0, 45, 0.24) 0%,
          rgba(201, 168, 76, 0.14) 35%,
          transparent 70%
        );
      }}
      33% {{
        opacity: 0.8;
        transform: translateY(-4px);
        background: linear-gradient(
          to top,
          rgba(201, 168, 76, 0.28) 0%,
          rgba(60, 255, 110, 0.12) 35%,
          transparent 70%
        );
      }}
      66% {{
        opacity: 0.7;
        transform: translateY(4px);
        background: linear-gradient(
          to top,
          rgba(14, 165, 233, 0.24) 0%,
          rgba(232, 0, 45, 0.12) 35%,
          transparent 70%
        );
      }}
      100% {{
        opacity: 0.65;
        transform: translateY(0px);
        background: linear-gradient(
          to top,
          rgba(232, 0, 45, 0.20) 0%,
          rgba(201, 168, 76, 0.14) 35%,
          transparent 70%
        );
      }}
    }}

    /* ── SECTION 1: Picks Header ── */
    .picks-header {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: var(--fifa-navy);
      border-bottom: 1px solid var(--fifa-border);
      padding: 12px 16px 0;
      animation: fadeIn 300ms ease both;
    }}
    .picks-title {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 900;
      font-size: 22px;
      letter-spacing: 0.08em;
      color: var(--fifa-gold);
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    .picks-title span {{
      font-size: 13px;
      font-family: 'Inter', sans-serif;
      font-weight: 500;
      color: var(--fifa-text-secondary);
      margin-left: 8px;
      text-transform: none;
      letter-spacing: 0.05em;
    }}
    .picks-row {{
      display: flex;
      gap: 10px;
      overflow-x: auto;
      padding-bottom: 12px;
      scrollbar-width: none;
      -ms-overflow-style: none;
    }}
    .picks-row::-webkit-scrollbar {{ display: none; }}
    .pick-mini {{
      flex: 0 0 auto;
      background: var(--fifa-card);
      border: 1px solid var(--fifa-border);
      border-radius: 8px;
      padding: 10px 14px;
      min-width: 120px;
      position: relative;
      overflow: hidden;
    }}
    .pick-mini::before {{
      content: '';
      position: absolute;
      left: 0; top: 0; bottom: 0;
      width: 3px;
    }}
    .pick-mini.gold::before   {{ background: #C9A84C; }}
    .pick-mini.silver::before {{ background: #C0C0C0; }}
    .pick-mini.bronze::before {{ background: #CD7F32; }}
    .pick-mini.green::before  {{ background: #22C55E; }}
    .pick-mini.gold   {{ background: rgba(201,168,76,0.08); }}
    .pick-mini.silver {{ background: rgba(192,192,192,0.08); }}
    .pick-mini.bronze {{ background: rgba(205,127,50,0.08); }}
    .pick-mini.green  {{ background: rgba(34,197,94,0.08); }}
    .pick-mini-label {{
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--fifa-text-muted);
      margin-bottom: 4px;
    }}
    .pick-mini-flag {{ font-size: 20px; display: block; margin-bottom: 2px; }}
    .pick-mini-team {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 15px;
      text-transform: uppercase;
      color: var(--fifa-text-primary);
      white-space: nowrap;
    }}
    .pick-mini-pct {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 900;
      font-size: 18px;
      margin-top: 2px;
    }}
    .pick-mini.gold   .pick-mini-pct {{ color: #C9A84C; }}
    .pick-mini.silver .pick-mini-pct {{ color: #C0C0C0; }}
    .pick-mini.bronze .pick-mini-pct {{ color: #CD7F32; }}
    .pick-mini.green  .pick-mini-pct {{ color: #22C55E; }}
    .pick-mini-pts {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-top: 1px;
    }}
    .pick-mini.gold   .pick-mini-pts {{ color: #C9A84C; }}
    .pick-mini.silver .pick-mini-pts {{ color: #C0C0C0; }}
    .pick-mini.bronze .pick-mini-pts {{ color: #CD7F32; }}
    .pick-mini.green  .pick-mini-pts {{ color: #22C55E; }}

    /* ── SECTION 2: Match Cards ── */
    .matches-section {{
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      max-width: 500px;
      margin: 0 auto;
      position: relative;
      z-index: 2;
    }}
    .matches-grid {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 0 12px;
    }}
    @keyframes slideUp {{
      from {{ opacity: 0; transform: translateY(24px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes fadeIn {{
      from {{ opacity: 0; }}
      to   {{ opacity: 1; }}
    }}
    .match-card {{
      background: var(--fifa-card);
      border: 1px solid var(--fifa-border);
      border-radius: 12px;
      position: relative;
      animation: slideUp 400ms ease both;
      transition: transform 150ms ease, box-shadow 150ms ease;
    }}
    @media (hover: hover) {{
      .match-card:hover {{
        transform: scale(1.02);
        box-shadow: 0 12px 40px rgba(0,0,0,0.5);
      }}
    }}
    .match-card:active {{
      transform: scale(0.98);
      box-shadow: 0 2px 8px rgba(0,0,0,0.4);
    }}
    .mc-card-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 12px 4px;
    }}
    .mc-card-label {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--fifa-text-muted);
    }}
    .mc-conf-badge {{
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.1em;
      padding: 2px 7px;
      border-radius: 4px;
      text-transform: uppercase;
    }}
    .conf-high {{ background: rgba(0,200,83,0.15); color: var(--fifa-green); border: 1px solid rgba(0,200,83,0.3); }}
    .conf-med  {{ background: rgba(255,160,0,0.15); color: #FFA000; border: 1px solid rgba(255,160,0,0.3); }}
    .conf-low  {{ background: rgba(232,0,45,0.15); color: var(--fifa-red); border: 1px solid rgba(232,0,45,0.3); }}
    .confidence-badge {{
      position: relative;
      cursor: help;
    }}
    .confidence-badge::after {{
      content: attr(data-tooltip);
      position: absolute;
      top: calc(100% + 8px);
      right: 0;
      width: 220px;
      background: #1A2B40;
      color: #F8FAFC;
      font-family: 'Inter', sans-serif;
      font-size: 12px;
      font-weight: 400;
      line-height: 1.5;
      padding: 10px 12px;
      border-radius: 8px;
      border: 1px solid #1E3050;
      box-shadow: 0 4px 16px rgba(0,0,0,0.4);
      opacity: 0;
      pointer-events: none;
      transition: opacity 200ms ease;
      z-index: 100;
      white-space: normal;
      text-align: left;
    }}
    .confidence-badge:focus::after,
    .confidence-badge:focus-within::after {{
      opacity: 1;
    }}
    .confidence-badge.tooltip-visible::after {{
      opacity: 1;
    }}
    .mc-chip.tooltip-up::after {{
      content: attr(data-tooltip);
      position: absolute;
      bottom: calc(100% + 8px);
      left: 0;
      right: auto;
      top: auto;
      width: 180px;
      background: #1A2B40;
      color: #F8FAFC;
      font-family: 'Inter', sans-serif;
      font-size: 12px;
      font-weight: 400;
      line-height: 1.5;
      padding: 10px 12px;
      border-radius: 8px;
      border: 1px solid #1E3050;
      box-shadow: 0 4px 16px rgba(0,0,0,0.4);
      opacity: 0;
      pointer-events: none;
      transition: opacity 200ms ease;
      z-index: 200;
      white-space: normal;
      text-align: left;
    }}
    .mc-chip.tooltip-up.tooltip-visible::after {{
      opacity: 1;
    }}
    .mc-venue-row {{
      font-size: 11px;
      font-weight: 500;
      color: var(--fifa-text-muted);
      padding: 0 12px 4px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .mc-lineup-wrap {{
      padding: 0 12px 4px;
      text-align: center;
    }}
    .teams-score-row {{
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 8px;
      margin: 12px 12px;
    }}
    .mc-team {{
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 4px;
    }}
    .mc-team-right {{
      align-items: flex-end;
      text-align: right;
    }}
    .mc-flag {{ font-size: 28px; line-height: 1; }}
    .mc-name {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 16px;
      text-transform: uppercase;
      color: var(--fifa-white);
      line-height: 1.1;
      word-wrap: break-word;
      overflow-wrap: break-word;
    }}
    .mc-prob {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 20px;
      color: var(--fifa-red);
      line-height: 1;
    }}
    .mc-score-block {{
      display: flex;
      flex-direction: column;
      align-items: center;
      min-width: 90px;
    }}
    .mc-score {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 900;
      font-size: 52px;
      color: var(--fifa-white);
      letter-spacing: -0.02em;
      line-height: 1;
      white-space: nowrap;
    }}
    .mc-score-label {{
      font-size: 9px;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--fifa-text-muted);
      margin-top: 2px;
    }}
    .mc-chips {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 6px;
      border-top: 1px solid var(--fifa-border);
      padding: 10px 12px 12px;
      margin-top: 4px;
    }}
    @media (min-width: 600px) {{
      .mc-chips {{
        grid-template-columns: repeat(5, 1fr);
      }}
    }}
    .mc-chip {{
      font-size: 10px;
      font-weight: 600;
      text-align: center;
      white-space: normal;
      word-break: break-word;
      padding: 5px 6px;
      border-radius: 20px;
      background: rgba(255,255,255,0.04);
      letter-spacing: 0.01em;
      line-height: 1.4;
    }}
    .chip-gold  {{ border: 1px solid rgba(201,168,76,0.5);  color: var(--fifa-gold); }}
    .chip-red   {{ border: 1px solid rgba(232,0,45,0.5);   color: #FF4060; }}
    .chip-blue  {{ border: 1px solid rgba(64,140,255,0.5); color: #60A0FF; }}
    .chip-teal   {{ border: 1px solid rgba(20,184,166,0.5);  color: #14b8a6; }}
    .chip-purple {{ border: 1px solid rgba(139,92,246,0.5); color: #a78bfa; }}

    /* ── SECTION 3: Model Confidence ── */
    .confidence-section {{
      margin: 0 16px;
      max-width: 468px;
      margin-left: auto;
      margin-right: auto;
      position: relative;
      z-index: 2;
    }}
    .confidence-toggle {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--fifa-card);
      border: 1px solid var(--fifa-border);
      border-radius: 10px;
      padding: 14px 16px;
      cursor: pointer;
      user-select: none;
      -webkit-tap-highlight-color: transparent;
      min-height: 44px;
    }}
    .confidence-toggle-label {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 13px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--fifa-gold);
    }}
    .confidence-arrow {{
      font-size: 12px;
      color: var(--fifa-text-muted);
      transition: transform 300ms ease;
    }}
    .confidence-section.open .confidence-arrow {{ transform: rotate(180deg); }}
    .confidence-section.open .confidence-toggle {{
      border-bottom-left-radius: 0;
      border-bottom-right-radius: 0;
      border-bottom-color: transparent;
    }}
    .confidence-body {{
      max-height: 0;
      overflow: hidden;
      transition: max-height 300ms ease-in-out;
      background: var(--fifa-navy);
      border: 1px solid var(--fifa-border);
      border-top: none;
      border-radius: 0 0 10px 10px;
    }}
    .confidence-section.open .confidence-body {{ max-height: 320px; }}
    .confidence-inner {{ padding: 14px 16px; }}
    .conf-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 0;
      border-bottom: 1px solid var(--fifa-border);
    }}
    .conf-row:last-child {{ border-bottom: none; }}
    .conf-rank {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 16px;
      color: var(--fifa-text-muted);
      width: 16px;
      text-align: center;
    }}
    .conf-team {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 15px;
      text-transform: uppercase;
      color: var(--fifa-text-primary);
      flex: 0 0 140px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .conf-bar-wrap {{
      flex: 1;
      height: 6px;
      background: rgba(255,255,255,0.06);
      border-radius: 3px;
      overflow: hidden;
    }}
    .conf-bar-fill {{
      height: 100%;
      background: var(--fifa-red);
      border-radius: 3px;
    }}
    .conf-pct {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 14px;
      color: var(--fifa-text-secondary);
      width: 36px;
      text-align: right;
    }}

    /* ── Countdown Banner ── */
    .countdown-banner {{
      background: #E8002D;
      color: #FFFFFF;
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 14px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      text-align: center;
      padding: 10px 16px;
      width: 100%;
      box-sizing: border-box;
      margin-bottom: 16px;
    }}

    /* ── Date Headers ── */
    .date-header {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 13px;
      letter-spacing: 0.10em;
      text-transform: uppercase;
      color: #C9A84C;
      padding: 20px 4px 8px 4px;
      border-bottom: 1px solid #1E3050;
      margin-bottom: 12px;
    }}

    /* ── Lineup Status Badge ── */
    .mc-lineup-badge {{
      display: block;
      font-size: 11px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 20px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      text-align: center;
    }}
    .lineup-confirmed {{ background: rgba(0,200,83,0.12); color: var(--fifa-green); border: 1px solid rgba(0,200,83,0.3); }}
    .lineup-estimated {{ background: rgba(255,160,0,0.12); color: #FFA000; border: 1px solid rgba(255,160,0,0.3); }}
    .lineup-absent    {{ background: rgba(255,235,59,0.12); color: #FFE000; border: 1px solid rgba(255,235,59,0.3); }}
    .lineup-pending   {{ background: rgba(100,120,140,0.10); color: var(--fifa-text-secondary); border: 1px solid rgba(100,120,140,0.25); }}

    /* ── Footer ── */
    .site-footer {{
      text-align: center;
      padding: 24px 16px;
      font-size: 12px;
      color: var(--fifa-text-muted);
      line-height: 1.6;
      position: relative;
      z-index: 2;
    }}

    /* ── Cursor and Focus States ── */
    .mc-toggle {{ cursor: pointer; }}
    .picks-mini-card {{ cursor: pointer; }}
    .match-card {{ cursor: default; }}
    .mc-toggle:focus-visible {{
      outline: 2px solid #C9A84C;
      outline-offset: 3px;
      border-radius: 4px;
    }}
    .picks-mini-card:focus-visible {{
      outline: 2px solid #C9A84C;
      outline-offset: 3px;
      border-radius: 4px;
    }}

    /* ── Countdown Timer ── */
    .countdown-timer {{
      display: block;
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 13px;
      font-weight: 700;
      color: #C9A84C;
      letter-spacing: 0.08em;
      text-align: center;
      margin: 4px 0;
    }}

    /* ── Live Match Pulse ── */
    .match-card.live-now {{
      border: 1px solid rgba(232, 0, 45, 0.6);
      box-shadow:
        0 0 0 0 rgba(232, 0, 45, 0.4),
        0 0 20px rgba(232, 0, 45, 0.1);
      animation: livePulse 2s ease-in-out infinite;
    }}
    @keyframes livePulse {{
      0%, 100% {{
        box-shadow:
          0 0 0 0 rgba(232, 0, 45, 0.4),
          0 0 20px rgba(232, 0, 45, 0.1);
      }}
      50% {{
        box-shadow:
          0 0 0 8px rgba(232, 0, 45, 0),
          0 0 30px rgba(232, 0, 45, 0.2);
      }}
    }}
    /* LIVE indicator replaces the predicted score while a match is in play */
    .live-score-display {{ display: none; }}
    .match-card.live-now .score-display,
    .match-card.live-now .mc-score-label {{ display: none; }}
    .match-card.live-now .live-score-display {{
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 52px;
    }}
    .live-dot {{
      width: 8px;
      height: 8px;
      background: #E8002D;
      border-radius: 50%;
      display: inline-block;
      animation: dotBlink 1s ease-in-out infinite;
      margin-right: 6px;
    }}
    @keyframes dotBlink {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.3; }}
    }}
    .live-label {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 18px;
      font-weight: 700;
      color: #E8002D;
      letter-spacing: 0.1em;
    }}

    /* ── Skeleton Loader ── */
    .skeleton {{
      background: linear-gradient(
        90deg,
        var(--fifa-card) 25%,
        #1A2B40 50%,
        var(--fifa-card) 75%
      );
      background-size: 200% 100%;
      animation: shimmer 1.5s infinite;
      border-radius: 4px;
    }}
    @keyframes shimmer {{
      0%   {{ background-position: 200% 0; }}
      100% {{ background-position: -200% 0; }}
    }}

    /* ── SECTION: Knockout Bracket ── */
    @keyframes countPulse {{
      0%   {{ color: #C9A84C; }}
      50%  {{ color: #FFFFFF; }}
      100% {{ color: #C9A84C; }}
    }}
    .bracket-confirmed-count {{ color: #C9A84C; }}
    @media (prefers-reduced-motion: no-preference) {{
      .bracket-confirmed-count {{ animation: countPulse 1.5s ease-in-out; }}
    }}
    .bracket-section {{
      max-width: 468px;
      margin: 8px auto 0;
      padding-top: 16px;
      border-top: 1px solid rgba(201,168,76,0.3);
      position: relative;
      z-index: 2;
    }}
    .bracket-toggle {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--fifa-card);
      border: 1px solid var(--fifa-border);
      border-radius: 10px;
      padding: 14px 16px;
      cursor: pointer;
      user-select: none;
      -webkit-tap-highlight-color: transparent;
      min-height: 44px;
    }}
    .bracket-toggle-label {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 13px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    .bracket-arrow {{
      font-size: 12px;
      color: var(--fifa-text-muted);
      transition: transform 300ms ease;
    }}
    .bracket-section.open .bracket-arrow {{ transform: rotate(180deg); }}
    .bracket-section.open .bracket-toggle {{
      border-bottom-left-radius: 0;
      border-bottom-right-radius: 0;
      border-bottom-color: transparent;
    }}
    .bracket-body {{
      max-height: 0;
      overflow: hidden;
      transition: max-height 300ms ease-in-out;
      background: var(--fifa-navy);
      border: 1px solid var(--fifa-border);
      border-top: none;
      border-radius: 0 0 10px 10px;
    }}
    .bracket-section.open .bracket-body {{ max-height: 2000px; }}
    .bracket-inner {{ padding: 14px 16px; }}
    .bracket-placeholder {{
      text-align: center;
      color: var(--fifa-text-muted);
      font-size: 14px;
      line-height: 1.6;
      padding: 20px;
      border: 1px dashed var(--fifa-border);
      border-radius: 8px;
    }}
    .bk-groups-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }}
    .bk-group-card {{
      background: var(--fifa-card);
      border: 1px solid var(--fifa-border);
      border-radius: 8px;
      padding: 10px 10px 8px;
    }}
    .bk-group-letter {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 900;
      font-size: 16px;
      color: var(--fifa-gold);
      letter-spacing: 0.08em;
      margin-bottom: 6px;
    }}
    .bk-slot {{
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 4px;
    }}
    .bk-slot-rank {{
      font-size: 11px;
      font-weight: 600;
      color: var(--fifa-text-muted);
      width: 18px;
      flex-shrink: 0;
    }}
    .bk-team-confirmed {{
      font-size: 13px;
      font-weight: 600;
      color: var(--fifa-text-primary);
    }}
    .bk-team-projected {{
      font-size: 12px;
      font-style: italic;
      color: var(--fifa-text-muted);
    }}
    .bk-team-eliminated {{
      font-size: 12px;
      color: #4A6080;
      text-decoration: line-through;
    }}
    .bk-third-note {{
      font-size: 11px;
      color: var(--fifa-text-muted);
      margin-top: 4px;
    }}
    .bk-r32-grid {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .bk-match-card {{
      background: var(--fifa-card);
      border: 1px solid var(--fifa-border);
      border-radius: 8px;
      padding: 10px 12px;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .bk-match-num {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 13px;
      color: var(--fifa-text-muted);
      width: 32px;
      flex-shrink: 0;
    }}
    .bk-matchup {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1;
    }}
    .bk-vs {{
      font-size: 11px;
      color: var(--fifa-text-muted);
      flex-shrink: 0;
    }}

    /* ── Bracket R32 Placeholder Cards ── */
    .bk-phase-note {{
      font-size: 12px;
      color: var(--fifa-text-muted);
      text-align: center;
      margin-bottom: 16px;
      line-height: 1.5;
    }}
    .bk-r32-card {{
      background: var(--fifa-card);
      border: 1px solid var(--fifa-border);
      border-radius: 8px;
      padding: 10px 14px;
      margin-bottom: 8px;
    }}
    .bk-match-meta {{
      font-size: 11px;
      color: var(--fifa-text-muted);
      margin-bottom: 6px;
      letter-spacing: 0.04em;
    }}
    .bk-city {{ font-weight: 600; }}
    .bk-matchup-row {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .bk-slot-cell {{
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 3px;
    }}
    .bk-slot-right {{ align-items: flex-end; text-align: right; }}
    .bk-vs-cell {{
      font-size: 11px;
      color: var(--fifa-text-muted);
      flex-shrink: 0;
      font-weight: 600;
    }}
    .bk-slot-label {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 13px;
      font-style: italic;
      color: var(--fifa-text-muted);
      letter-spacing: 0.04em;
    }}
    .bk-slot-confirmed {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 15px;
      color: var(--fifa-white);
    }}
    .bk-third-pill {{
      display: block;
      font-size: 10px;
      color: var(--fifa-text-muted);
      letter-spacing: 0.02em;
    }}
    /* ── Bracket Later Rounds ── */
    .bk-late-section {{
      margin-top: 16px;
      padding-top: 12px;
      border-top: 1px solid var(--fifa-border);
    }}
    .bk-late-header {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 900;
      font-size: 13px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--fifa-gold);
      margin-bottom: 8px;
    }}
    .bk-final-header {{ color: var(--fifa-red); }}
    .bk-late-match {{
      font-size: 13px;
      color: var(--fifa-text-secondary);
      padding: 4px 0;
      border-bottom: 1px solid rgba(30,48,80,0.5);
    }}
    .bk-late-match:last-child {{ border-bottom: none; }}
    .bk-late-team {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      color: var(--fifa-text-muted);
      font-style: italic;
    }}
    .bk-late-vs {{
      font-size: 11px;
      color: var(--fifa-text-muted);
      margin: 0 2px;
    }}

    /* ── SECTION: Match Results ── */
    .results-section {{
      max-width: 468px;
      margin: 24px auto 0;
      padding: 0 16px;
      position: relative;
      z-index: 2;
    }}
    .results-header {{
      display: flex;
      align-items: center;
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 13px;
      letter-spacing: 0.10em;
      text-transform: uppercase;
      color: var(--fifa-gold);
      padding: 0 4px 8px;
      border-bottom: 1px solid var(--fifa-border);
      margin-bottom: 12px;
    }}
    .results-live-dot {{
      width: 8px;
      height: 8px;
      background: #22C55E;
      border-radius: 50%;
      display: inline-block;
      margin-left: 8px;
      animation: resultsPulse 2s ease-in-out infinite;
    }}
    @keyframes resultsPulse {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50%      {{ opacity: 0.4; transform: scale(1.4); }}
    }}
    .results-list {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .results-extra {{
      flex-direction: column;
      gap: 10px;
    }}
    .result-card {{
      background: var(--fifa-card);
      border: 1px solid var(--fifa-border);
      border-radius: 12px;
      padding: 10px 12px;
    }}
    .rc-meta {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--fifa-text-muted);
      margin-bottom: 8px;
    }}
    .rc-time {{
      font-family: 'Inter', sans-serif;
      font-weight: 500;
      font-size: 10px;
      letter-spacing: 0.04em;
      text-transform: none;
      color: var(--fifa-text-muted);
    }}
    .rc-row {{
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 8px;
    }}
    .rc-team {{
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }}
    .rc-right {{
      flex-direction: row-reverse;
      text-align: right;
    }}
    .rc-flag {{ font-size: 22px; line-height: 1; }}
    .rc-name {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 15px;
      text-transform: uppercase;
      line-height: 1.1;
      overflow-wrap: break-word;
    }}
    .rc-win  .rc-name {{ color: var(--fifa-white); }}
    .rc-lose .rc-name {{ color: var(--fifa-text-secondary); }}
    .rc-score {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 900;
      font-size: 30px;
      color: var(--fifa-white);
      letter-spacing: -0.02em;
      line-height: 1;
      white-space: nowrap;
      min-width: 60px;
      text-align: center;
    }}
    .rc-elo {{
      font-size: 10px;
      color: var(--fifa-text-muted);
      letter-spacing: 0.04em;
      text-align: center;
      margin-top: 6px;
    }}
    .results-show-all {{
      text-align: center;
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 12px;
      letter-spacing: 0.10em;
      text-transform: uppercase;
      color: var(--fifa-text-secondary);
      padding: 12px;
      margin-top: 4px;
      cursor: pointer;
      user-select: none;
      -webkit-tap-highlight-color: transparent;
    }}

    /* ── Prefers-Reduced-Motion ── */
    @media (prefers-reduced-motion: reduce) {{
      *,
      *::before,
      *::after {{
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
      }}
      body::before {{ animation: none; }}
      body::after {{
        animation: none;
        opacity: 0.6;
      }}
      #floodlights {{
        animation: none;
        opacity: 0.7;
      }}
      #crowd-wave {{
        animation: none;
        opacity: 0.4;
        background: linear-gradient(
          to top,
          rgba(232, 0, 45, 0.18) 0%,
          transparent 60%
        );
      }}
      .skeleton {{ animation: none; }}
      .match-card.live-now {{ animation: none; }}
      .live-dot {{ animation: none; }}
      .results-live-dot {{ animation: none; }}
    }}
  </style>
</head>
<body>

<div id="floodlights" aria-hidden="true"></div>
<div id="crowd-wave" aria-hidden="true"></div>

<!-- ══════════════════════════════════════════
     SECTION 1 — POLLAYA PICKS HEADER (sticky)
     ══════════════════════════════════════════ -->
<div class="picks-header">
  <div class="picks-title">POLLAYA 2026 <span>Pre-tournament picks</span></div>
  <div class="picks-row">
    <div class="pick-mini gold">
      <div class="pick-mini-label">Champion</div>
      <span class="pick-mini-flag">{_flag(winner)}</span>
      <div class="pick-mini-team">{h(winner)}</div>
      <div class="pick-mini-pct">{winner_pct}%</div>
      <div style="font-size:11px;color:var(--fifa-text-secondary);margin-top:1px;">80% CI: {winner_ci_low}%–{winner_ci_high}%</div>
      <div class="pick-mini-pts">50 PTS</div>
    </div>
    <div class="pick-mini silver">
      <div class="pick-mini-label">Runner-Up</div>
      <span class="pick-mini-flag">{_flag(runner["team"])}</span>
      <div class="pick-mini-team">{h(runner["team"])}</div>
      <div class="pick-mini-pct">{runner["probability"]}%</div>
      <div class="pick-mini-pts">35 PTS</div>
    </div>
    <div class="pick-mini bronze">
      <div class="pick-mini-label">Third Place</div>
      <span class="pick-mini-flag">{_flag(third["team"])}</span>
      <div class="pick-mini-team">{h(third["team"])}</div>
      <div class="pick-mini-pct">{third["probability"]}%</div>
      <div class="pick-mini-pts">20 PTS</div>
    </div>
    <div class="pick-mini green">
      <div class="pick-mini-label">Golden Boot</div>
      <span class="pick-mini-flag">{_flag(golden_boot["team"])}</span>
      <div class="pick-mini-team">{h(golden_boot["player"])}</div>
      <div class="pick-mini-pct">{golden_boot["expected_goals"]} xG</div>
      <div class="pick-mini-pts">30 PTS</div>
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════
     SECTION 2 — UPCOMING MATCHES
     ══════════════════════════════════════════ -->
<div class="matches-section">
<div id="skeleton-overlay" style="position:relative">
  <div class="skeleton" style="height:200px; margin:12px; border-radius:8px;"></div>
  <div class="skeleton" style="height:200px; margin:12px; border-radius:8px; opacity:0.7;"></div>
</div>
{countdown_html}
{match_cards if match_cards else '<div style="color:var(--fifa-text-muted);text-align:center;padding:40px 0;font-size:14px;">No upcoming matches scheduled.</div>'}
</div>

<!-- ══════════════════════════════════════════
     SECTION 2.5 — MATCH RESULTS (auto-appears)
     ══════════════════════════════════════════ -->
{results_section_html}

<!-- ══════════════════════════════════════════
     SECTION 3 — KNOCKOUT BRACKET (collapsible)
     ══════════════════════════════════════════ -->
<div class="bracket-section" id="bracket-section">
  <div class="bracket-toggle" onclick="toggleBracket()">
    <span class="bracket-toggle-label">{bracket_header_label}</span>
    <span class="bracket-arrow" id="bracket-arrow">&#9662;</span>
  </div>
  <div class="bracket-body" id="bracket-body">
    <div class="bracket-inner">
{bracket_body_html}
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════
     SECTION 4 — MODEL CONFIDENCE (collapsible)
     ══════════════════════════════════════════ -->
<div class="confidence-section" id="conf-section">
  <div class="confidence-toggle" onclick="toggleConf()">
    <span class="confidence-toggle-label">Model Confidence</span>
    <span class="confidence-arrow" id="conf-arrow">▾</span>
  </div>
  <div class="confidence-body" id="conf-body">
    <div class="confidence-inner">
{top5_rows}    </div>
  </div>
</div>

<div class="site-footer">
  <div class="footer-text">
    <span id="footer-refreshed">Data refreshed: {ts}</span>
    <span class="footer-sep"> &middot; </span>
    <span id="footer-now"></span>
    <span class="footer-sep"> &middot; </span>
    Monte Carlo {sims:,} runs &bull; dicor-sas.github.io/wc2026
  </div>
</div>

<script>
// Cache-bust: fetch version.txt with a timestamp query string
// so CDN never caches the request. If the version has changed
// since last visit, force a hard reload to get fresh index.html.
(function() {{
  var stored = localStorage.getItem('wc_version');
  fetch('version.txt?t=' + Date.now())
    .then(function(r) {{ return r.text(); }})
    .then(function(v) {{
      v = v.trim();
      if (stored && stored !== v) {{
        localStorage.setItem('wc_version', v);
        location.reload(true);
      }} else {{
        localStorage.setItem('wc_version', v);
      }}
    }})
    .catch(function() {{}});
}})();

function toggleConf() {{
  document.getElementById('conf-section').classList.toggle('open');
}}
function toggleBracket() {{
  document.getElementById('bracket-section').classList.toggle('open');
}}

// Skeleton loader: fade out after 800ms
setTimeout(() => {{
  const sk = document.getElementById('skeleton-overlay');
  if (sk) {{
    sk.style.transition = 'opacity 400ms';
    sk.style.opacity = '0';
    setTimeout(() => sk.remove(), 400);
  }}
}}, 800);

// Score count-up reveal — fires once per card via data-animated flag
function animateScore(card) {{
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {{
    return;
  }}
  const scoreEl = card.querySelector('.score-display');
  if (!scoreEl || scoreEl.dataset.animated) return;
  scoreEl.dataset.animated = 'true';

  const homeEl = scoreEl.querySelector('.home-score');
  const awayEl = scoreEl.querySelector('.away-score');
  if (!homeEl || !awayEl) return;

  const home = parseInt(scoreEl.dataset.home || '0');
  const away = parseInt(scoreEl.dataset.away || '0');

  const label = card.querySelector('.mc-score-label');
  if (label) {{
    label.style.opacity = '0';
    label.style.transition = 'opacity 300ms ease';
    setTimeout(() => {{ label.style.opacity = '1'; }}, 700);
  }}

  const start = performance.now();
  function tick(now) {{
    const elapsed = now - start;
    const progressHome = Math.min(elapsed / 600, 1);
    const progressAway = Math.min(elapsed / 400, 1);
    const easedHome = 1 - Math.pow(1 - progressHome, 3);
    const easedAway = 1 - Math.pow(1 - progressAway, 3);
    homeEl.textContent = Math.floor(easedHome * home);
    awayEl.textContent = Math.floor(easedAway * away);
    if (progressHome < 1) {{
      requestAnimationFrame(tick);
    }}
  }}
  requestAnimationFrame(tick);
}}

// Intersection Observer: scroll-triggered card entrance
if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {{
  const cards = document.querySelectorAll('.match-card, .bracket-match-card');
  const observer = new IntersectionObserver(
    (entries) => {{
      entries.forEach(entry => {{
        if (entry.isIntersecting) {{
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'translateY(0)';
          animateScore(entry.target);
          observer.unobserve(entry.target);
        }}
      }});
    }},
    {{ threshold: 0.1 }}
  );
  cards.forEach(card => {{
    card.style.opacity = '0';
    card.style.transform = 'translateY(20px)';
    card.style.transition = 'opacity 400ms ease, transform 400ms ease';
    observer.observe(card);
  }});
}}

// Live countdown timers
function updateCountdowns() {{
  document.querySelectorAll('[data-kickoff]').forEach(card => {{
    const kickoff = new Date(card.dataset.kickoff);
    const now = new Date();
    const diff = kickoff - now;
    const el = card.querySelector('.countdown-timer');
    if (!el) return;
    const LIVE_WINDOW_MS = 150 * 60 * 1000;
    if (diff <= 0 && diff > -LIVE_WINDOW_MS) {{
      // Match in play: pulse the card and swap score for the LIVE indicator (CSS)
      card.classList.add('live-now');
      el.textContent = 'MATCH IN PROGRESS';
      el.style.color = '#22C55E';
      return;
    }}
    if (diff <= 0) {{
      // Recently ended: drop the pulse, show muted COMPLETED until the
      // pipeline ingests the result and the card moves to MATCH RESULTS
      card.classList.remove('live-now');
      el.textContent = 'COMPLETED';
      el.style.color = '#9CA3AF';
      return;
    }}
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hrs  = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    if (days > 0) {{
      el.textContent = `IN ${{days}}D ${{hrs}}H`;
    }} else if (hrs > 0) {{
      el.textContent = `IN ${{hrs}}H ${{mins}}M`;
    }} else {{
      el.textContent = `IN ${{mins}} MIN`;
      el.style.color = '#E8002D';
    }}
  }});
}}
updateCountdowns();
setInterval(updateCountdowns, 60000);

// Live banner countdown — pure JS, no hardcoded dates
const TOURNAMENT_OPEN = new Date('2026-06-11T19:00:00Z');
const WC_MATCHES = {wc_matches_json};

function formatCountdown(diffMs) {{
  const days  = Math.floor(diffMs / (1000*60*60*24));
  const hours = Math.floor((diffMs % (1000*60*60*24)) / (1000*60*60));
  const mins  = Math.floor((diffMs % (1000*60*60)) / (1000*60));
  if (days  > 0) return `${{days}}D ${{hours}}H`;
  if (hours > 0) return `${{hours}}H ${{mins}}M`;
  return `${{mins}}M`;
}}

function getNextMatch() {{
  const now = new Date();
  return WC_MATCHES.find(m => new Date(m.utc) > now);
}}

function updateBanner() {{
  const now = new Date();
  const banner   = document.getElementById('banner-text');
  const bannerEl = document.getElementById('main-banner');
  if (!banner || !bannerEl) return;
  const preTournament = TOURNAMENT_OPEN - now;
  if (preTournament > 0) {{
    bannerEl.style.background = '#E8002D';
    banner.textContent = `IN ${{formatCountdown(preTournament)}} · FIRST KICKOFF JUNE 11`;
  }} else {{
    const next = getNextMatch();
    if (!next) {{ bannerEl.style.display = 'none'; return; }}
    const diffToNext = new Date(next.utc) - now;
    if (diffToNext <= 0 && diffToNext > -150 * 60 * 1000) {{
      bannerEl.style.background = '#22C55E';
      banner.textContent = `⚽ ${{next.label}} · LIVE NOW`;
    }} else {{
      bannerEl.style.background = '#E8002D';
      banner.textContent = `NEXT: ${{next.label}} · IN ${{formatCountdown(diffToNext)}}`;
    }}
  }}
}}
updateBanner();
setInterval(updateBanner, 60000);

// Confidence badge tooltips — tap to show, tap elsewhere to dismiss
document.querySelectorAll('.confidence-badge').forEach(badge => {{
  badge.setAttribute('tabindex', '0');
  badge.addEventListener('click', (e) => {{
    e.stopPropagation();
    const isVisible = badge.classList.contains('tooltip-visible');
    document.querySelectorAll('.confidence-badge').forEach(b =>
      b.classList.remove('tooltip-visible'));
    if (!isVisible) {{
      badge.classList.add('tooltip-visible');
    }}
  }});
}});
document.addEventListener('click', () => {{
  document.querySelectorAll('.confidence-badge').forEach(b =>
    b.classList.remove('tooltip-visible'));
}});

// Match results — show-all toggle
function toggleAllResults() {{
  const extra = document.getElementById('results-extra');
  const btn = document.getElementById('results-show-all');
  if (!extra || !btn) return;
  if (!btn.dataset.allLabel) btn.dataset.allLabel = btn.textContent;
  const open = extra.style.display !== 'none';
  extra.style.display = open ? 'none' : 'flex';
  btn.textContent = open ? btn.dataset.allLabel : 'Show fewer ▴';
}}

// Match results — relative "time since ended" + recent-completion dot
function updateResultTimes() {{
  const cards = document.querySelectorAll('.result-card[data-ended]');
  if (!cards.length) return;
  const now = new Date();
  let newest = null;
  cards.forEach(c => {{
    const ended = new Date(c.dataset.ended);
    if (!newest || ended > newest) newest = ended;
    const el = c.querySelector('.rc-time');
    if (!el) return;
    const diff = now - ended;
    if (diff < 0) {{ el.textContent = ''; return; }}
    const mins = Math.floor(diff / 60000);
    const hrs = Math.floor(mins / 60);
    if (mins < 60) {{
      el.textContent = mins + 'm ago';
    }} else if (hrs < 24) {{
      el.textContent = hrs + 'h ago';
    }} else {{
      const yesterday = new Date(now);
      yesterday.setDate(yesterday.getDate() - 1);
      if (ended.toDateString() === yesterday.toDateString()) {{
        el.textContent = 'Yesterday';
      }} else {{
        el.textContent = ended.toLocaleDateString('en-GB', {{ day: 'numeric', month: 'short' }});
      }}
    }}
  }});
  const dot = document.getElementById('results-live-dot');
  if (dot && newest) {{
    const age = now - newest;
    dot.style.display = (age >= 0 && age <= 2 * 60 * 60 * 1000) ? 'inline-block' : 'none';
  }}
}}
updateResultTimes();
setInterval(updateResultTimes, 60000);
</script>

<script>
function updateFooterTime() {{
  const el = document.getElementById('footer-now');
  if (!el) return;
  const now = new Date();
  const cotString = now.toLocaleString('es-CO', {{
    timeZone: 'America/Bogota',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }});
  el.textContent = 'Now: ' + cotString.replace(',', '') + ' COT';
}}
updateFooterTime();
setInterval(updateFooterTime, 60000);
</script>

</body>
</html>"""
    return html


if __name__ == "__main__":
    with open(PREDICTIONS_FILE) as f:
        data = json.load(f)

    html = build_html(data)

    with open(OUTPUT_FILE, "w") as f:
        f.write(html)

    print(f"✓ Written {OUTPUT_FILE}")

    import time as _time
    version = int(_time.time())
    with open(_ROOT / "version.txt", "w") as f:
        f.write(str(version))
    print(f"✓ Written version.txt ({version})")

    # Count teams with asterisk
    pending = [t["team"] for t in data.get("all_teams", []) if "*" in t["team"]]
    print(f"✓ Pending teams marked with *: {pending}")
