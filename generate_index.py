"""
Generate index.html from predictions.json.
Run after run_predictions.py produces the JSON.
"""
import json
import math
from datetime import date, datetime, timezone, timedelta

PREDICTIONS_FILE   = "/Users/diegofelipecortessastoque/Desktop/wc2026/predictions.json"
OUTPUT_FILE        = "/Users/diegofelipecortessastoque/Desktop/wc2026/index.html"
PLAYER_STATS_FILE  = "/Users/diegofelipecortessastoque/Desktop/wc2026/player_stats.json"
TEAM_STRENGTH_FILE = "/Users/diegofelipecortessastoque/Desktop/wc2026/team_strength.json"
FIXTURES_FILE      = "/Users/diegofelipecortessastoque/Desktop/wc2026/fixtures.json"
LINEUPS_FILE       = "/Users/diegofelipecortessastoque/Desktop/wc2026/lineups.json"
BRACKET_STATE_FILE = "/Users/diegofelipecortessastoque/Desktop/wc2026/bracket_state.json"

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
        group = fx.get("group", "?")
        md = fx.get("matchday", 1)
        round_label = f"Group {group} MD{md}"
        try:
            hour, minute = int(time_str[:2]), int(time_str[3:5])
        except Exception:
            hour, minute = 0, 0
        schedule.append((date_str, hour, minute, home, away, group, round_label))
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


_TEAM_STRENGTH_DATA: dict = {}


def _load_team_strength():
    global _TEAM_STRENGTH_DATA
    if not _TEAM_STRENGTH_DATA:
        try:
            with open(TEAM_STRENGTH_FILE) as f:
                _TEAM_STRENGTH_DATA = json.load(f)
        except Exception:
            pass


def _strength_lambdas(team1, team2):
    """Return (lam1, lam2): lambda = 1.5 * (s_attack/s_defend)^2, capped [0.3, 3.5]."""
    _load_team_strength()
    s1 = _TEAM_STRENGTH_DATA.get(team1, {}).get("final_strength", 1600.0)
    s2 = _TEAM_STRENGTH_DATA.get(team2, {}).get("final_strength", 1600.0)
    lam1 = max(0.3, min(3.5, 1.5 * (s1 / s2) ** 2.0))
    lam2 = max(0.3, min(3.5, 1.5 * (s2 / s1) ** 2.0))
    return lam1, lam2


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

    now_utc = datetime.now(timezone.utc)
    now_col = (now_utc + COLOMBIA_OFFSET).replace(tzinfo=None)
    tournament_started = now_col >= TOURNAMENT_START
    cutoff = (now_col + timedelta(hours=48)) if tournament_started else None

    upcoming = []
    for entry in _load_fixtures():
        date_str, hour, minute, t1, t2, group, round_label = entry
        ko_col = datetime(
            int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]),
            hour, minute, 0,
        )
        if ko_col < now_col:
            continue
        if cutoff is not None and ko_col > cutoff:
            continue
        upcoming.append((date_str, ko_col, t1, t2, group, round_label))

    if not tournament_started:
        upcoming = upcoming[:6]

    results = []
    for date_str, ko_col, t1_raw, t2_raw, group, round_label in upcoming:
        t1 = _norm(t1_raw)
        t2 = _norm(t2_raw)
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
        ko_fmt = ko_col.strftime("%-d %b · %H:%M COL")
        match_lbl = _match_label(round_label, group)

        results.append({
            "t1": t1, "t2": t2, "group": group,
            "win_p1": win_p1, "win_p2": win_p2, "draw_p": draw_p,
            "score1": score1, "score2": score2,
            "winner": winner,
            "conf": conf, "conf_cls": conf_cls,
            "venue": venue, "ko_fmt": ko_fmt, "match_lbl": match_lbl,
            "date_str": date_str,
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
    xi_confirmed = src == "api-football" and len(home_xi) >= 5 and len(away_xi) >= 5
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
            t1, t2 = m["t1"], m["t2"]
            card_index += 1
            delay = card_index * 200
            t1_abbr = COUNTRY_CODE.get(t1, t1[:3].upper())
            t2_abbr = COUNTRY_CODE.get(t2, t2[:3].upper())
            colombia_style = ' style="border-left:3px solid #C9A84C"' if "Colombia" in (t1, t2) else ""
            lineup_badge = _lineup_badge_html(t1, t2, lineups)
            cards += f'''<div class="match-card" style="animation-delay:{delay}ms"{colombia_style}>
  <div class="mc-conf-badge {m["conf_cls"]}">{m["conf"]}</div>
  <div class="mc-header">
    <div class="mc-label">{h(m["match_lbl"])}</div>
    <div class="mc-venue">{h(m["venue"])}</div>
    <div class="mc-time">{h(m["ko_fmt"])}</div>
    {lineup_badge}
  </div>
  <div class="mc-body">
    <div class="mc-team">
      <span class="mc-flag">{_flag(t1)}</span>
      <span class="mc-name">{_card_name(t1)}</span>
      <span class="mc-prob">{m["win_p1"]}%</span>
    </div>
    <div class="mc-score-block">
      <div class="mc-score">{m["score1"]} – {m["score2"]}</div>
      <div class="mc-score-label">PREDICTED</div>
    </div>
    <div class="mc-team mc-team-right">
      <span class="mc-prob">{m["win_p2"]}%</span>
      <span class="mc-name">{_card_name(t2)}</span>
      <span class="mc-flag">{_flag(t2)}</span>
    </div>
  </div>
  <div class="mc-chips">
    <div class="chip chip-gold">EXACT SCORE: {m["score1"]}-{m["score2"]} · 15 pts</div>
    <div class="chip chip-red">WINNER: {h(m["winner"]).upper()} · 8 pts</div>
    <div class="chip chip-blue">GOALS: {t1_abbr} {m["score1"]} · {t2_abbr} {m["score2"]} · 5 pts ea</div>
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

    winner_team = data["predicted_winner"]
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

    # Phase detection
    if confirmed_count == 0:
        phase = 1
    elif confirmed_count < 32:
        phase = 2
    else:
        phase = 3

    # Header counts
    header_label = (
        f'KNOCKOUT BRACKET'
        f' · <span style="color:#C9A84C">{confirmed_count} CONFIRMED</span>'
        f' · <span style="color:#4A6080">{pending_count} PENDING</span>'
    )

    # Body content
    if phase == 1:
        body_html = (
            '<div class="bracket-placeholder">'
            'Bracket will fill in as group stage results are confirmed.'
            ' Check back from June 24 onward.'
            '</div>'
        )
    elif phase == 2:
        # Collect groups A–L
        groups = {}
        for slot_key, slot_val in bracket.items():
            # Only group-stage slots: "Group X 1st" / "Group X 2nd"
            parts = slot_key.split()
            if len(parts) == 3 and parts[0] == "Group" and parts[2] in ("1st", "2nd"):
                grp_letter = parts[1]
                rank = parts[2]
                groups.setdefault(grp_letter, {})[rank] = slot_val

        group_cards = ""
        for grp_letter in sorted(groups.keys()):
            slots = groups[grp_letter]
            cards_html = ""
            for rank in ("1st", "2nd"):
                slot_val = slots.get(rank)
                if slot_val:
                    status = slot_val.get("status", "PROJECTED")
                    team = slot_val.get("team", "TBD")
                    prob = slot_val.get("probability", 0)
                    prob_pct = round(prob * 100)
                    if status == "CONFIRMED":
                        team_html = f'<span class="bk-team-confirmed">&#10003; {h(team)}</span>'
                    else:
                        team_html = f'<span class="bk-team-projected">{h(team)} ({prob_pct}%)</span>'
                else:
                    team_html = '<span class="bk-team-projected">TBD</span>'
                cards_html += (
                    f'<div class="bk-slot">'
                    f'<span class="bk-slot-rank">{rank}</span>'
                    f'{team_html}'
                    f'</div>'
                )
            group_cards += (
                f'<div class="bk-group-card">'
                f'<div class="bk-group-letter">GROUP {h(grp_letter)}</div>'
                f'{cards_html}'
                f'<div class="bk-third-note">Best 3rd place pool</div>'
                f'</div>'
            )
        body_html = f'<div class="bk-groups-grid">{group_cards}</div>'
    else:
        # Phase 3: Round of 32 matchup cards
        r32_slots = {k: v for k, v in bracket.items() if "Round of 32" in k or "R32" in k}
        # Fallback: match slots M73–M88
        matchup_keys = [k for k in bracket if k.startswith("M") and k[1:].isdigit()]
        matchup_keys.sort(key=lambda k: int(k[1:]))

        cards_html = ""
        match_num_start = 73
        for i in range(16):
            match_num = match_num_start + i
            home_key = f"M{match_num} home"
            away_key = f"M{match_num} away"
            home_slot = bracket.get(home_key, {})
            away_slot = bracket.get(away_key, {})

            def _team_display(slot):
                if not slot:
                    return '<span class="bk-team-projected">TBD</span>'
                status = slot.get("status", "PROJECTED")
                team = slot.get("team", "TBD")
                prob = slot.get("probability", 0)
                prob_pct = round(prob * 100)
                if status == "ELIMINATED":
                    return f'<span class="bk-team-eliminated">&#10007; {h(team)}</span>'
                elif status == "CONFIRMED":
                    return f'<span class="bk-team-confirmed">&#10003; {h(team)}</span>'
                else:
                    return f'<span class="bk-team-projected">{h(team)} ({prob_pct}%)</span>'

            cards_html += (
                f'<div class="bk-match-card">'
                f'<div class="bk-match-num">M{match_num}</div>'
                f'<div class="bk-matchup">'
                f'{_team_display(home_slot)}'
                f'<span class="bk-vs">vs</span>'
                f'{_team_display(away_slot)}'
                f'</div>'
                f'</div>'
            )
        body_html = f'<div class="bk-r32-grid">{cards_html}</div>'

    return header_label, body_html


def build_html(data):
    sims = data["simulations"]
    winner = data["predicted_winner"]
    winner_pct = data["predicted_winner_probability_pct"]
    runners_up = data["runners_up"]
    third_place = data["third_place"]
    all_teams = data["all_teams"]
    now_utc = datetime.now(timezone.utc)

    runner = all_teams[1] if len(all_teams) > 1 else {"team": "—", "probability": 0}
    third  = all_teams[2] if len(all_teams) > 2 else {"team": "—", "probability": 0}

    runner_prob = runner["probability"]
    third_prob  = third["probability"]
    assert runner_prob > third_prob, (
        f"Runner-Up must have higher win probability than Third Place "
        f"({runner['team']} {runner_prob}% vs {third['team']} {third_prob}%)"
    )
    golden_boot = _compute_golden_boot(data)

    matches = _upcoming_matches(data)
    match_cards = _match_cards_html(matches)
    bracket_header_label, bracket_body_html = _bracket_section_html()

    today = date.today()
    kickoff_date = date(2026, 6, 11)
    days_until = (kickoff_date - today).days
    if days_until > 0:
        countdown_text = f"TOURNAMENT STARTS IN {days_until} DAYS · FIRST KICKOFF JUNE 11"
        countdown_html = f'<div class="countdown-banner">{countdown_text}</div>'
    elif days_until == 0:
        countdown_html = '<div class="countdown-banner">TOURNAMENT STARTS TODAY · FIRST KICKOFF 14:00 COT</div>'
    else:
        countdown_html = '<div class="countdown-banner" style="display:none"></div>'

    top5_rows = ""
    for i, item in enumerate(all_teams[:5]):
        bar_w = round(item["probability"] / winner_pct * 100)
        top5_rows += (
            f'<div class="conf-row">'
            f'<span class="conf-rank">{i+1}</span>'
            f'<span class="conf-team">{_flag(item["team"])} {h(item["team"]).upper()}</span>'
            f'<div class="conf-bar-wrap"><div class="conf-bar-fill" style="width:{bar_w}%"></div></div>'
            f'<span class="conf-pct">{item["probability"]}%</span>'
            f'</div>\n'
        )

    COT = timezone(timedelta(hours=-5))
    now_cot = datetime.now(COT)
    ts = now_cot.strftime("%Y-%m-%d %H:%M COT")

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
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --fifa-navy:    #0A1628;
      --fifa-red:     #E8002D;
      --fifa-white:   #FFFFFF;
      --fifa-gold:    #C9A84C;
      --fifa-dark:    #060E1A;
      --fifa-card:    #111D2E;
      --fifa-card-hover: #1A2B40;
      --fifa-border:  #1E3050;
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
      letter-spacing: 0;
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
    .pick-mini.gold::before   {{ background: var(--fifa-gold); }}
    .pick-mini.silver::before {{ background: var(--fifa-silver); }}
    .pick-mini.bronze::before {{ background: var(--fifa-bronze); }}
    .pick-mini.green::before  {{ background: var(--fifa-green); }}
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
    .pick-mini.gold   .pick-mini-pct {{ color: var(--fifa-gold); }}
    .pick-mini.silver .pick-mini-pct {{ color: var(--fifa-silver); }}
    .pick-mini.bronze .pick-mini-pct {{ color: var(--fifa-bronze); }}
    .pick-mini.green  .pick-mini-pct {{ color: var(--fifa-green); }}

    /* ── SECTION 2: Match Cards ── */
    .matches-section {{
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      max-width: 500px;
      margin: 0 auto;
    }}
    .matches-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
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
      overflow: hidden;
      position: relative;
      animation: slideUp 400ms ease both;
      transition: transform 200ms ease, box-shadow 200ms ease;
    }}
    @media (hover: hover) {{
      .match-card:hover {{
        transform: scale(1.02);
        box-shadow: 0 12px 40px rgba(0,0,0,0.5);
      }}
    }}
    .mc-conf-badge {{
      position: absolute;
      top: 8px;
      right: 8px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.1em;
      padding: 3px 8px;
      border-radius: 4px;
      text-transform: uppercase;
    }}
    .conf-high {{ background: rgba(0,200,83,0.15); color: var(--fifa-green); border: 1px solid rgba(0,200,83,0.3); }}
    .conf-med  {{ background: rgba(255,160,0,0.15); color: #FFA000; border: 1px solid rgba(255,160,0,0.3); }}
    .conf-low  {{ background: rgba(232,0,45,0.15); color: var(--fifa-red); border: 1px solid rgba(232,0,45,0.3); }}
    .mc-header {{
      padding: 10px 10px 8px;
      border-bottom: 1px solid var(--fifa-border);
    }}
    .mc-label {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 12px;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--fifa-text-secondary);
    }}
    .mc-venue {{
      font-size: 12px;
      font-weight: 500;
      color: var(--fifa-text-muted);
      margin-top: 2px;
    }}
    .mc-time {{
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--fifa-text-secondary);
      margin-top: 2px;
    }}
    .mc-body {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 10px;
      gap: 4px;
    }}
    .mc-team {{
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      flex: 1;
      gap: 4px;
    }}
    .mc-team-right {{
      align-items: flex-end;
      text-align: right;
    }}
    .mc-flag {{ font-size: 22px; line-height: 1; }}
    .mc-name {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      color: var(--fifa-text-primary);
      line-height: 1;
      word-break: break-word;
    }}
    .mc-prob {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 900;
      font-size: 16px;
      color: var(--fifa-red);
      line-height: 1;
    }}
    .mc-score-block {{
      display: flex;
      flex-direction: column;
      align-items: center;
      flex: 0 0 auto;
    }}
    .mc-score {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 900;
      font-size: 32px;
      color: var(--fifa-white);
      letter-spacing: -0.02em;
      line-height: 1;
      white-space: nowrap;
    }}
    .mc-score-label {{
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--fifa-text-muted);
      margin-top: 2px;
    }}
    .mc-chips {{
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 0 10px 10px;
    }}
    .chip {{
      font-size: 12px;
      font-weight: 600;
      padding: 4px 8px;
      border-radius: 100px;
      background: rgba(255,255,255,0.04);
      white-space: normal;
      word-break: break-word;
      letter-spacing: 0.02em;
    }}
    .chip-gold  {{ border: 1px solid rgba(201,168,76,0.5);  color: var(--fifa-gold); }}
    .chip-red   {{ border: 1px solid rgba(232,0,45,0.5);   color: #FF4060; }}
    .chip-blue  {{ border: 1px solid rgba(64,140,255,0.5); color: #60A0FF; }}

    /* ── SECTION 3: Model Confidence ── */
    .confidence-section {{
      margin: 0 16px;
      max-width: 468px;
      margin-left: auto;
      margin-right: auto;
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
      display: inline-block;
      font-size: 12px;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-top: 5px;
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

    /* ── SECTION: Knockout Bracket ── */
    .bracket-section {{
      margin: 14px 16px 0;
      max-width: 468px;
      margin-left: auto;
      margin-right: auto;
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
      padding: 16px 0;
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
    }}
  </style>
</head>
<body>

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
    </div>
    <div class="pick-mini silver">
      <div class="pick-mini-label">Runner-Up</div>
      <span class="pick-mini-flag">{_flag(runner["team"])}</span>
      <div class="pick-mini-team">{h(runner["team"])}</div>
      <div class="pick-mini-pct">{runner["probability"]}%</div>
    </div>
    <div class="pick-mini bronze">
      <div class="pick-mini-label">Third Place</div>
      <span class="pick-mini-flag">{_flag(third["team"])}</span>
      <div class="pick-mini-team">{h(third["team"])}</div>
      <div class="pick-mini-pct">{third["probability"]}%</div>
    </div>
    <div class="pick-mini green">
      <div class="pick-mini-label">Golden Boot</div>
      <span class="pick-mini-flag">{_flag(golden_boot["team"])}</span>
      <div class="pick-mini-team">{h(golden_boot["player"])}</div>
      <div class="pick-mini-pct">{golden_boot["expected_goals"]} xG</div>
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════
     SECTION 2 — UPCOMING MATCHES
     ══════════════════════════════════════════ -->
<div class="matches-section">
{countdown_html}
{match_cards if match_cards else '<div style="color:var(--fifa-text-muted);text-align:center;padding:40px 0;font-size:14px;">No upcoming matches scheduled.</div>'}
</div>

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
  Updated {ts} &bull; Monte Carlo {sims:,} runs &bull; dicor-sas.github.io/wc2026
</div>

<script>
function toggleConf() {{
  document.getElementById('conf-section').classList.toggle('open');
}}
function toggleBracket() {{
  document.getElementById('bracket-section').classList.toggle('open');
}}
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
    # Count teams with asterisk
    pending = [t["team"] for t in data["all_teams"] if "*" in t["team"]]
    print(f"✓ Pending teams marked with *: {pending}")
