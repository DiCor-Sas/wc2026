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

PENDING_NOTE = "* Pending FIFA confirmation — highest-ranked confederation proxy used."

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
WC_2026_SCHEDULE = [
    # June 11 — Opening day
    ("2026-06-11", 14, 0,  "Mexico",      "Canada",            "A", "Group A MD1"),
    ("2026-06-11", 17, 0,  "South Korea", "South Africa",      "A", "Group A MD1"),
    ("2026-06-11", 20, 0,  "Czechia",     "TBD",               "A", "Group A MD1"),
    # June 12
    ("2026-06-12", 11, 0,  "Switzerland", "Qatar",             "B", "Group B MD1"),
    ("2026-06-12", 14, 0,  "Canada",      "Bosnia-Herzegovina","B", "Group B MD1"),
    ("2026-06-12", 17, 0,  "Brazil",      "Morocco",           "C", "Group C MD1"),
    ("2026-06-12", 20, 0,  "Haiti",       "Scotland",          "C", "Group C MD1"),
    # June 13
    ("2026-06-13", 11, 0,  "USA",         "Paraguay",          "D", "Group D MD1"),
    ("2026-06-13", 14, 0,  "Australia",   "Türkiye",           "D", "Group D MD1"),
    ("2026-06-13", 17, 0,  "Germany",     "Curaçao",           "E", "Group E MD1"),
    ("2026-06-13", 20, 0,  "Ivory Coast", "Ecuador",           "E", "Group E MD1"),
    # June 14
    ("2026-06-14", 11, 0,  "Netherlands", "Japan",             "F", "Group F MD1"),
    ("2026-06-14", 14, 0,  "Sweden",      "Tunisia",           "F", "Group F MD1"),
    ("2026-06-14", 17, 0,  "Belgium",     "Egypt",             "G", "Group G MD1"),
    ("2026-06-14", 20, 0,  "Iran",        "New Zealand",       "G", "Group G MD1"),
    # June 15
    ("2026-06-15", 11, 0,  "Spain",       "Cabo Verde",        "H", "Group H MD1"),
    ("2026-06-15", 14, 0,  "Saudi Arabia","Uruguay",           "H", "Group H MD1"),
    ("2026-06-15", 17, 0,  "France",      "Senegal",           "I", "Group I MD1"),
    ("2026-06-15", 20, 0,  "Norway",      "Iraq",              "I", "Group I MD1"),
    # June 16
    ("2026-06-16", 11, 0,  "Argentina",   "Algeria",           "J", "Group J MD1"),
    ("2026-06-16", 14, 0,  "Austria",     "Jordan",            "J", "Group J MD1"),
    ("2026-06-16", 17, 0,  "Portugal",    "Colombia",          "K", "Group K MD1"),
    ("2026-06-16", 20, 0,  "Congo DR",    "Uzbekistan",        "K", "Group K MD1"),
    # June 17
    ("2026-06-17", 11, 0,  "England",     "Croatia",           "L", "Group L MD1"),
    ("2026-06-17", 14, 0,  "Ghana",       "Panama",            "L", "Group L MD1"),
]

COLOMBIA_OFFSET = timedelta(hours=-5)  # UTC-5


def _poisson_pmf(lam, k):
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _most_probable_score(lam1, lam2, max_goals=5):
    best_p, best_s = 0, (1, 1)
    for g1 in range(max_goals + 1):
        for g2 in range(max_goals + 1):
            p = _poisson_pmf(lam1, g1) * _poisson_pmf(lam2, g2)
            if p > best_p:
                best_p, best_s = p, (g1, g2)
    return best_s


_TEAM_STRENGTH_DATA: dict = {}
_TEAM_STRENGTH_AVG: float = 0.0
_STRENGTH_EXP = 3.0
_STRENGTH_BASE = 1.5  # base goals for average-strength team


def _load_team_strength():
    global _TEAM_STRENGTH_DATA, _TEAM_STRENGTH_AVG
    if not _TEAM_STRENGTH_DATA:
        try:
            with open(TEAM_STRENGTH_FILE) as f:
                _TEAM_STRENGTH_DATA = json.load(f)
            _TEAM_STRENGTH_AVG = (
                sum(v["final_strength"] for v in _TEAM_STRENGTH_DATA.values())
                / len(_TEAM_STRENGTH_DATA)
            )
        except Exception:
            pass


def _strength_lambdas(team1, team2):
    """Return (lam1, lam2) using per-team final_strength independent lambdas."""
    _load_team_strength()
    avg = _TEAM_STRENGTH_AVG or 1600.0
    s1 = _TEAM_STRENGTH_DATA.get(team1, {}).get("final_strength", avg)
    s2 = _TEAM_STRENGTH_DATA.get(team2, {}).get("final_strength", avg)
    lam1 = max(0.2, min(4.0, _STRENGTH_BASE * (s1 / avg) ** _STRENGTH_EXP))
    lam2 = max(0.2, min(4.0, _STRENGTH_BASE * (s2 / avg) ** _STRENGTH_EXP))
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

MATCH_VENUES = {
    ("Mexico", "Canada"):             "SoFi Stadium · Los Angeles",
    ("South Korea", "South Africa"):  "AT&T Stadium · Dallas",
    ("Czechia", "TBD"):               "MetLife Stadium · NJ",
    ("Switzerland", "Qatar"):         "Levi's Stadium · San Francisco",
    ("Canada", "Bosnia-Herzegovina"): "BMO Field · Toronto",
    ("Brazil", "Morocco"):            "SoFi Stadium · Los Angeles",
    ("Haiti", "Scotland"):            "NRG Stadium · Houston",
    ("USA", "Paraguay"):              "MetLife Stadium · NJ",
    ("Australia", "Türkiye"):         "Arrowhead Stadium · Kansas City",
    ("Germany", "Curaçao"):           "Lumen Field · Seattle",
    ("Ivory Coast", "Ecuador"):       "Gillette Stadium · Boston",
    ("Netherlands", "Japan"):         "Hard Rock Stadium · Miami",
    ("Sweden", "Tunisia"):            "BC Place · Vancouver",
    ("Belgium", "Egypt"):             "Mercedes-Benz Stadium · Atlanta",
    ("Iran", "New Zealand"):          "Estadio BBVA · Monterrey",
    ("Spain", "Cabo Verde"):          "Estadio Azteca · Mexico City",
    ("Saudi Arabia", "Uruguay"):      "Estadio Akron · Guadalajara",
    ("France", "Senegal"):            "AT&T Stadium · Dallas",
    ("Norway", "Iraq"):               "SoFi Stadium · Los Angeles",
    ("Argentina", "Algeria"):         "MetLife Stadium · NJ",
    ("Austria", "Jordan"):            "Hard Rock Stadium · Miami",
    ("Portugal", "Colombia"):         "NRG Stadium · Houston",
    ("Congo DR", "Uzbekistan"):       "Levi's Stadium · San Francisco",
    ("England", "Croatia"):           "Gillette Stadium · Boston",
    ("Ghana", "Panama"):              "Estadio BBVA · Monterrey",
}


def _flag(team):
    return FLAG_EMOJI.get(team, "🏳️")


def _match_label(round_label, group):
    # "Group A MD1" → "GROUP A · MD 1"
    return round_label.upper().replace("MD", "· MD ")


def _upcoming_matches(data):
    """Return list of next 3 (pre-tournament) or next 48h (during) match dicts with computed stats."""
    sim_probs = {t["team"]: t["probability"] for t in data.get("all_teams", [])}

    now_utc = datetime.now(timezone.utc)
    now_col = (now_utc + COLOMBIA_OFFSET).replace(tzinfo=None)
    tournament_started = now_col >= TOURNAMENT_START
    cutoff = (now_col + timedelta(hours=48)) if tournament_started else None

    upcoming = []
    for entry in WC_2026_SCHEDULE:
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
        upcoming = upcoming[:3]

    results = []
    for date_str, ko_col, t1, t2, group, round_label in upcoming:
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
        })
    return results


def _match_cards_html(matches):
    """Render the FIFA-style match cards for the upcoming matches section."""
    cards = ""
    for i, m in enumerate(matches):
        t1, t2 = m["t1"], m["t2"]
        delay = (i + 1) * 200
        t1_abbr = t1[:3].upper()
        t2_abbr = t2[:3].upper()
        cards += f'''
<div class="match-card" style="animation-delay:{delay}ms">
  <div class="mc-conf-badge {m["conf_cls"]}">{m["conf"]}</div>
  <div class="mc-header">
    <div class="mc-label">{h(m["match_lbl"])}</div>
    <div class="mc-venue">{h(m["venue"])}</div>
    <div class="mc-time">{h(m["ko_fmt"])}</div>
  </div>
  <div class="mc-body">
    <div class="mc-team">
      <span class="mc-flag">{_flag(t1)}</span>
      <span class="mc-name">{h(t1).upper()}</span>
      <span class="mc-prob">{m["win_p1"]}%</span>
    </div>
    <div class="mc-score-block">
      <div class="mc-score">{m["score1"]} – {m["score2"]}</div>
      <div class="mc-score-label">PREDICTED</div>
    </div>
    <div class="mc-team mc-team-right">
      <span class="mc-prob">{m["win_p2"]}%</span>
      <span class="mc-name">{h(t2).upper()}</span>
      <span class="mc-flag">{_flag(t2)}</span>
    </div>
  </div>
  <div class="mc-chips">
    <div class="chip chip-gold">EXACT SCORE: {m["score1"]}-{m["score2"]} · 15 pts</div>
    <div class="chip chip-red">WINNER: {h(m["winner"]).upper()} · 8 pts</div>
    <div class="chip chip-blue">GOALS: {t1_abbr} {m["score1"]} · {t2_abbr} {m["score2"]} · 5 pts ea</div>
  </div>
</div>'''
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


def build_html(data):
    sims = data["simulations"]
    winner = data["predicted_winner"]
    winner_pct = data["predicted_winner_probability_pct"]
    runners_up = data["runners_up"]
    third_place = data["third_place"]
    all_teams = data["all_teams"]
    now_utc = datetime.now(timezone.utc)

    runner = runners_up[0] if runners_up else {"team": "—", "probability": 0}
    third  = third_place[0] if third_place else {"team": "—", "probability": 0}
    golden_boot = _compute_golden_boot(data)

    matches = _upcoming_matches(data)
    match_cards = _match_cards_html(matches)

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

    ts = now_utc.strftime("%Y-%m-%d %H:%M UTC")

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
      --fifa-green:   #00C853;
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
      font-size: 9px;
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
      top: 12px;
      right: 12px;
      font-size: 10px;
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
      padding: 12px 14px 10px;
      border-bottom: 1px solid var(--fifa-border);
    }}
    .mc-label {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 11px;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--fifa-text-secondary);
    }}
    .mc-venue {{
      font-size: 11px;
      font-weight: 500;
      color: var(--fifa-text-muted);
      margin-top: 2px;
    }}
    .mc-time {{
      font-size: 11px;
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
      padding: 16px 14px;
      gap: 8px;
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
    .mc-flag {{ font-size: 32px; line-height: 1; }}
    .mc-name {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 18px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      color: var(--fifa-text-primary);
      line-height: 1;
    }}
    .mc-prob {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 900;
      font-size: 22px;
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
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 0 14px 14px;
    }}
    .chip {{
      font-size: 11px;
      font-weight: 600;
      padding: 5px 10px;
      border-radius: 100px;
      background: rgba(255,255,255,0.04);
      white-space: nowrap;
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

    /* ── Footer ── */
    .site-footer {{
      text-align: center;
      padding: 24px 16px;
      font-size: 11px;
      color: var(--fifa-text-muted);
      line-height: 1.6;
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
{match_cards if match_cards else '<div style="color:var(--fifa-text-muted);text-align:center;padding:40px 0;font-size:14px;">No upcoming matches scheduled.</div>'}
</div>

<!-- ══════════════════════════════════════════
     SECTION 3 — MODEL CONFIDENCE (collapsible)
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
