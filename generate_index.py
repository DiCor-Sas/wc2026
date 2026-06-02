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


def build_pollaya_panel(data):
    """
    Build the Pollaya Picks HTML panel.

    Before June 11 (tournament start): show next 3 upcoming scheduled matches
    regardless of how far away they are, labelled as "Upcoming picks".
    After June 11: revert to strict 48-hour window.
    """
    sim_probs = {t["team"]: t["probability"] for t in data.get("all_teams", [])}

    now_utc = datetime.now(timezone.utc)
    now_col = (now_utc + COLOMBIA_OFFSET).replace(tzinfo=None)
    tournament_started = now_col >= TOURNAMENT_START

    if tournament_started:
        cutoff = now_col + timedelta(hours=48)
    else:
        cutoff = None  # no upper bound — show next 3 regardless of date

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
        upcoming.append({
            "date_str": date_str,
            "ko_col": ko_col,
            "team1": t1,
            "team2": t2,
            "group": group,
            "round_label": round_label,
        })

    # Before tournament starts: only show the next 3 upcoming matches
    if not tournament_started:
        upcoming = upcoming[:3]

    section_title = "&#9917; My Pollaya Picks &mdash; Next 48 Hours" if tournament_started else "&#9917; My Pollaya Picks &mdash; Upcoming"

    if not upcoming:
        return '''<section id="pollaya">
  <div class="section-title">&#9917; My Pollaya Picks</div>
  <div class="pollaya-empty">No matches in the next 48 hours. First kickoff: Jun 11 2:00 PM Colombia time.</div>
</section>'''

    cards_html = ""
    for m in upcoming:
        t1, t2 = m["team1"], m["team2"]
        p1 = sim_probs.get(t1, 1.0)
        p2 = sim_probs.get(t2, 1.0)
        total_p = p1 + p2 if (p1 + p2) > 0 else 1.0

        # Win probabilities (normalized to sum to ~1, draw not modelled explicitly)
        draw_boost = 0.25  # typical draw probability in WC group stage
        r1 = p1 / total_p
        r2 = p2 / total_p
        win_p1 = round(r1 * (1 - draw_boost) * 100, 1)
        win_p2 = round(r2 * (1 - draw_boost) * 100, 1)
        draw_p = round(100 - win_p1 - win_p2, 1)

        # Expected goals via Poisson using team_strength.json (Fix 3)
        lam1, lam2 = _strength_lambdas(t1, t2)
        score1, score2 = _most_probable_score(lam1, lam2)

        # Likely winner
        if win_p1 > win_p2:
            winner, winner_pct = t1, win_p1
        elif win_p2 > win_p1:
            winner, winner_pct = t2, win_p2
        else:
            winner, winner_pct = "Draw likely", draw_p

        # Confidence
        max_win = max(win_p1, win_p2)
        if max_win >= 60:
            conf, conf_cls = "High", "conf-high"
        elif max_win >= 45:
            conf, conf_cls = "Medium", "conf-med"
        else:
            conf, conf_cls = "Low", "conf-low"

        ko_fmt = m["ko_col"].strftime("%-d %b %H:%M")

        cards_html += f'''
<div class="pollaya-card">
  <div class="pc-head">
    <span class="pc-round">{h(m["round_label"])}</span>
    <span class="pc-time">&#128336; {ko_fmt} COL</span>
  </div>
  <div class="pc-matchup">{h(t1)} <span class="pc-vs">vs</span> {h(t2)}</div>
  <div class="pc-rows">
    <div class="pc-row"><span class="pc-lbl">&#127919; Score (15 pts)</span><span class="pc-val">{score1}&#8209;{score2}</span></div>
    <div class="pc-row"><span class="pc-lbl">&#127942; Winner (8 pts)</span><span class="pc-val">{h(winner)} &mdash; {winner_pct}%</span></div>
    <div class="pc-row"><span class="pc-lbl">&#9917; Goals {h(t1)} (5 pts)</span><span class="pc-val">{score1}</span></div>
    <div class="pc-row"><span class="pc-lbl">&#9917; Goals {h(t2)} (5 pts)</span><span class="pc-val">{score2}</span></div>
    <div class="pc-row"><span class="pc-lbl">&#128200; Confidence</span><span class="pc-val pc-conf {conf_cls}">{conf}</span></div>
  </div>
</div>'''

    return f'''<section id="pollaya">
  <div class="section-title">{section_title}</div>
  <p class="pollaya-note">Score prediction earns 15 pts &bull; Winner pick 8 pts &bull; Goals per team 5 pts each</p>
  <div class="pollaya-grid">
{cards_html}
  </div>
</section>'''


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
    kb = data["knockout_bracket"]
    today = date.today().strftime("%B %-d, %Y")

    runner = runners_up[0] if runners_up else {"team": "—", "probability": 0}
    third  = third_place[0] if third_place else {"team": "—", "probability": 0}
    golden_boot = _compute_golden_boot(data)

    # Check for pending teams
    has_pending = any("*" in t["team"] for t in all_teams)

    # ── R32 labels & cities ─────────────────────────────────────────────────
    R32_LABELS = {
        73: "2nd-A vs 2nd-B",      74: "1st-E vs 3rd(A/B/C/D/F)",
        75: "1st-F vs 2nd-C",      76: "1st-C vs 2nd-F",
        77: "1st-I vs 3rd(C/D/F/G/H)", 78: "2nd-E vs 2nd-I",
        79: "1st-A vs 3rd(C/E/F/H/I)", 80: "1st-L vs 3rd(E/H/I/J/K)",
        81: "1st-D vs 3rd(B/E/F/I/J)", 82: "1st-G vs 3rd(A/E/H/I/J)",
        83: "2nd-K vs 2nd-L",      84: "1st-H vs 2nd-J",
        85: "1st-B vs 3rd(E/F/G/I/J)", 86: "1st-J vs 2nd-H",
        87: "1st-K vs 3rd(D/E/I/J/L)", 88: "2nd-D vs 2nd-G",
    }
    R32_CITIES = {
        73: "SoFi Stadium, LA",     74: "Gillette Stadium, Boston",
        75: "Estadio BBVA, Monterrey", 76: "NRG Stadium, Houston",
        77: "MetLife Stadium, NJ",  78: "AT&T Stadium, Dallas",
        79: "Estadio Azteca, Mexico City", 80: "Mercedes-Benz Stadium",
        81: "Levi's Stadium, SF",   82: "Lumen Field, Seattle",
        83: "BMO Field, Toronto",   84: "SoFi Stadium, LA",
        85: "BC Place, Vancouver",  86: "Hard Rock Stadium, Miami",
        87: "Arrowhead Stadium, KC", 88: "AT&T Stadium, Dallas",
    }

    # ── helpers for bracket tree ────────────────────────────────────────────
    def _t(match):
        """Return (t1, t2) from a match dict's teams list."""
        teams = match.get("teams", [])
        t1 = teams[0] if len(teams) > 0 else {"name": "TBD", "overall_win_pct": 0}
        t2 = teams[1] if len(teams) > 1 else {"name": "TBD", "overall_win_pct": 0}
        return t1, t2

    # ── win-probability table ────────────────────────────────────────────────
    prob_rows = ""
    for i, item in enumerate(all_teams[:16]):
        bar_w = round(item["probability"] / winner_pct * 100)
        star = " &#9733;" if "*" in item["team"] else ""
        prob_rows += (
            f'<tr>'
            f'<td>{i+1}</td>'
            f'<td>{h(item["team"].replace(" *", ""))}{star}</td>'
            f'<td>'
            f'<div class="prob-bar-wrap"><div class="prob-bar-fill" style="width:{bar_w}%"></div>'
            f'<span class="prob-bar-lbl">{item["probability"]}%</span></div>'
            f'</td>'
            f'</tr>\n'
        )

    # ── R32 cards ────────────────────────────────────────────────────────────
    r32_left = ""
    r32_right = ""
    for idx, m in enumerate(kb["round_of_32"]):
        mn = m["match"]
        card = ko_card(m, slot_label=R32_LABELS.get(mn, ""), city=R32_CITIES.get(mn, ""))
        if idx < 8:
            r32_left += card + "\n"
        else:
            r32_right += card + "\n"

    # ── Bracket tree columns ─────────────────────────────────────────────────
    # R16 — 8 matches
    r16_html = ""
    for m in kb["round_of_16"]:
        t1, t2 = _t(m)
        r16_html += b_match(
            t1["name"], t1["overall_win_pct"],
            t2["name"], t2["overall_win_pct"],
            m.get("likely_winner", ""),
            predicted_score=m.get("predicted_score"),
        ) + '\n<div class="b-divider"></div>\n'

    # QF — 4 matches
    qf_html = ""
    for m in kb["quarter_finals"]:
        t1, t2 = _t(m)
        qf_html += b_match(
            t1["name"], t1["overall_win_pct"],
            t2["name"], t2["overall_win_pct"],
            m.get("likely_winner", ""),
            predicted_score=m.get("predicted_score"),
        ) + '\n<div class="b-divider"></div>\n'

    # SF — 2 matches
    sf_html = ""
    for m in kb["semi_finals"]:
        t1, t2 = _t(m)
        sf_html += b_match(
            t1["name"], t1["overall_win_pct"],
            t2["name"], t2["overall_win_pct"],
            m.get("likely_winner", ""),
            predicted_score=m.get("predicted_score"),
        ) + '\n<div class="b-divider"></div>\n'

    # Final
    fin = kb["final"]
    ft1, ft2 = _t(fin)
    final_html = b_match(
        ft1["name"], ft1["overall_win_pct"],
        ft2["name"], ft2["overall_win_pct"],
        fin.get("likely_winner", ""),
        predicted_score=fin.get("predicted_score"),
        winner_icon="&#127942;",
    )

    # Third place derived
    tp = kb.get("third_place_match_derived") or kb["third_place_match"]
    tp_t = tp.get("teams", [])
    tp1 = tp_t[0] if len(tp_t) > 0 else {"name": "TBD", "overall_win_pct": 0}
    tp2 = tp_t[1] if len(tp_t) > 1 else {"name": "TBD", "overall_win_pct": 0}
    tp_city = tp.get("city", "Miami")
    tp_html = b_match(
        tp1["name"], tp1["overall_win_pct"],
        tp2["name"], tp2["overall_win_pct"],
        tp.get("likely_winner", ""),
        predicted_score=tp.get("predicted_score"),
        winner_icon="&#129353;",
    )

    pending_banner = ""
    if has_pending:
        pending_banner = f'''
<div class="pending-banner">
  &#9733; {h(PENDING_NOTE)}
</div>'''

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>WC 2026 Predictions Dashboard</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg:      #0d1f0f;
      --bg2:     #152818;
      --bg3:     #1c3320;
      --card:    #1e3d22;
      --border:  #2e5c34;
      --accent:  #4caf50;
      --accent2: #81c784;
      --gold:    #ffd54f;
      --silver:  #b0bec5;
      --bronze:  #a0714f;
      --text:    #e8f5e9;
      --muted:   #a5d6a7;
      --red:     #ef5350;
      --yellow:  #ffca28;
      --radius:  8px;
    }}
    body {{
      background: var(--bg); color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh; padding-bottom: 3rem;
    }}
    header {{
      background: linear-gradient(135deg,#0a1a0c 0%,#1b3d1e 50%,#0a1a0c 100%);
      border-bottom: 2px solid var(--border);
      padding: 1.5rem 1rem; text-align: center;
    }}
    header h1 {{
      font-size: clamp(1.3rem,4vw,2rem); font-weight: 800;
      letter-spacing: .05em; color: var(--accent); text-transform: uppercase;
    }}
    header p {{ color: var(--muted); font-size: .82rem; margin-top: .3rem; }}
    .container {{ max-width: 960px; margin: 0 auto; padding: 0 1rem; }}
    section {{ margin-top: 2rem; }}
    .section-title {{
      font-size: .68rem; font-weight: 700; letter-spacing: .12em;
      text-transform: uppercase; color: var(--accent2);
      border-left: 3px solid var(--accent); padding-left: .6rem; margin-bottom: 1rem;
    }}
    /* Pending banner */
    .pending-banner {{
      background: #1a2f1a; border: 1px solid var(--yellow);
      border-radius: var(--radius); padding: .5rem .8rem;
      font-size: .72rem; color: var(--yellow); margin-bottom: 1rem;
    }}
    /* Top predictions */
    .top-grid {{ display: grid; grid-template-columns: repeat(2,1fr); gap: .75rem; }}
    @media(min-width:600px){{ .top-grid {{ grid-template-columns: repeat(4,1fr); }} }}
    .pred-card.boot::before {{ background: var(--yellow); }}
    .pred-card {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 1rem .8rem;
      text-align: center; position: relative; overflow: hidden;
    }}
    .pred-card::before {{
      content:''; position:absolute; top:0; left:0; right:0; height:3px;
    }}
    .pred-card.winner::before {{ background: var(--gold); }}
    .pred-card.runner::before {{ background: var(--silver); }}
    .pred-card.third::before  {{ background: var(--bronze); }}
    .pred-medal  {{ font-size:1.4rem; display:block; margin-bottom:.3rem; }}
    .pred-label  {{ font-size:.62rem; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:var(--muted); margin-bottom:.35rem; }}
    .pred-team   {{ font-size:1rem; font-weight:800; }}
    .pred-pct    {{ font-size:1.5rem; font-weight:900; margin-top:.25rem; line-height:1; }}
    .pred-card.winner .pred-pct {{ color: var(--gold); }}
    .pred-card.runner .pred-pct {{ color: var(--silver); }}
    .pred-card.third  .pred-pct {{ color: var(--bronze); }}
    .pred-sub {{ font-size:.68rem; color:var(--muted); margin-top:.2rem; }}
    /* Win probability table */
    .prob-table {{ width:100%; border-collapse:collapse; font-size:.78rem; margin-top:.5rem; }}
    .prob-table th {{ text-align:left; font-size:.62rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); padding:.35rem .5rem; border-bottom:1px solid var(--border); }}
    .prob-table td {{ padding:.32rem .5rem; border-bottom:1px solid var(--bg3); }}
    .prob-table tr:hover td {{ background:var(--bg3); }}
    .prob-bar-wrap {{ position:relative; height:14px; border-radius:3px; overflow:hidden; background:var(--bg); min-width:80px; display:flex; align-items:center; }}
    .prob-bar-fill {{ position:absolute; left:0; top:0; bottom:0; background:linear-gradient(90deg,var(--accent2),var(--accent)); border-radius:3px; }}
    .prob-bar-lbl {{ position:relative; z-index:1; font-size:.62rem; font-weight:700; padding-left:4px; color:var(--text); }}
    /* R32 ko-cards */
    .ko-round-label {{
      font-size:.65rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase;
      color:var(--accent); margin:1.4rem 0 .55rem;
      display:flex; align-items:center; gap:.5rem;
    }}
    .ko-round-label::after {{ content:''; flex:1; height:1px; background:var(--border); }}
    .ko-grid {{ display:grid; grid-template-columns:1fr; gap:.6rem; }}
    @media(min-width:600px){{ .ko-grid {{ grid-template-columns:1fr 1fr; }} }}
    .ko-card {{
      background:var(--card); border:1px solid var(--border);
      border-radius:var(--radius); padding:.75rem .85rem;
    }}
    .ko-card.final-card {{ border-color:var(--gold); background:#1e3020; }}
    .ko-head {{
      font-size:.6rem; font-weight:600; letter-spacing:.07em; text-transform:uppercase;
      color:var(--muted); margin-bottom:.55rem; display:flex; flex-wrap:wrap; gap:.25rem; align-items:center;
    }}
    .ko-slot {{
      background:var(--bg3); border:1px solid var(--border); border-radius:3px;
      padding:1px 5px; color:var(--accent2); font-size:.58rem; text-transform:none; letter-spacing:0;
    }}
    .ko-matchup {{ display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:.35rem; margin-bottom:.5rem; }}
    .ko-team {{ display:flex; flex-direction:column; }}
    .ko-right {{ align-items:flex-end; text-align:right; }}
    .ko-name {{ font-size:.88rem; font-weight:800; line-height:1.2; }}
    .ko-wt .ko-name {{ color:var(--accent2); }}
    .ko-stat {{ font-size:.58rem; color:var(--muted); margin-top:.15rem; line-height:1.3; }}
    .ko-vs {{ font-size:.65rem; font-weight:700; color:var(--muted); padding:0 .2rem; }}
    .ko-bar-row {{ display:flex; border-radius:4px; overflow:hidden; height:16px; margin-bottom:.45rem; }}
    .ko-bar-seg {{ display:flex; align-items:center; min-width:20px; }}
    .ko-bar-l {{ background:linear-gradient(90deg,var(--accent2),var(--accent)); justify-content:flex-end; }}
    .ko-bar-r {{ background:linear-gradient(90deg,#e57373,var(--red)); justify-content:flex-start; }}
    .ko-bar-lbl {{ font-size:.58rem; font-weight:700; padding:0 3px; color:#0d1f0f; white-space:nowrap; }}
    .ko-bar-lbl-r {{ color:#fff; }}
    .ko-predicted {{ font-size:.65rem; font-weight:700; color:var(--accent); border-top:1px solid var(--border); padding-top:.35rem; margin-top:.1rem; }}
    .final-card .ko-predicted {{ color:var(--gold); }}
    /* Bracket tree */
    .bracket-note {{ font-size:.72rem; color:var(--muted); margin-bottom:1rem; }}
    .bracket-scroll {{ overflow-x:auto; padding-bottom:.5rem; }}
    .bracket {{
      display:grid; grid-template-columns:repeat(4,minmax(148px,1fr));
      gap:0; min-width:600px;
    }}
    .b-round {{ display:flex; flex-direction:column; }}
    .b-round-title {{
      font-size:.58rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase;
      color:var(--accent2); text-align:center; padding:.4rem 0;
      background:var(--bg2); border-bottom:1px solid var(--border);
      border-right:1px solid var(--border);
    }}
    .b-round:first-child .b-round-title {{ border-left:1px solid var(--border); }}
    .b-slots {{
      flex:1; display:flex; flex-direction:column; justify-content:space-around;
      padding:.5rem .45rem; border-right:1px solid var(--border);
      border-bottom:1px solid var(--border); background:var(--bg2);
    }}
    .b-round:first-child .b-slots {{ border-left:1px solid var(--border); }}
    .b-match {{ margin:.22rem 0; }}
    .b-team {{
      background:var(--card); border:1px solid var(--border); border-radius:4px;
      padding:.28rem .48rem; font-size:.72rem; font-weight:700;
      display:flex; justify-content:space-between; align-items:center; margin-bottom:2px;
    }}
    .b-team.likely      {{ border-color:var(--accent); color:var(--accent2); }}
    .b-team.winner-team {{ border-color:var(--gold); color:var(--gold); background:#1e3322; }}
    .b-team-pct {{ font-size:.62rem; font-weight:600; color:var(--muted); }}
    .b-team.likely .b-team-pct      {{ color:var(--accent); }}
    .b-team.winner-team .b-team-pct {{ color:var(--gold); }}
    .b-score {{
      font-size:.6rem; font-weight:700; color:var(--yellow);
      text-align:center; padding:.18rem .2rem; letter-spacing:.02em;
    }}
    .b-divider {{ height:1px; background:var(--border); margin:.22rem 0; opacity:.4; }}
    .tp-card {{
      background:var(--bg2); border:1px solid var(--border);
      border-radius:var(--radius); padding:.55rem .6rem; margin-top:.8rem;
    }}
    .tp-title {{
      font-size:.58rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
      color:var(--muted); margin-bottom:.4rem; text-align:center;
    }}
    footer {{ text-align:center; margin-top:2.5rem; font-size:.68rem; color:#4a6e4d; }}
    /* ── Pollaya Picks panel ── */
    #pollaya {{ margin-top:1.5rem; }}
    .pollaya-note {{ font-size:.72rem; color:var(--muted); margin-bottom:.75rem; }}
    .pollaya-empty {{
      background:var(--card); border:1px solid var(--border); border-radius:var(--radius);
      padding:1.2rem; text-align:center; color:var(--muted); font-size:.82rem;
    }}
    .pollaya-grid {{ display:grid; grid-template-columns:1fr; gap:.75rem; }}
    @media(min-width:600px){{ .pollaya-grid {{ grid-template-columns:repeat(2,1fr); }} }}
    @media(min-width:900px){{ .pollaya-grid {{ grid-template-columns:repeat(3,1fr); }} }}
    .pollaya-card {{
      background:linear-gradient(160deg,#1a3d1e 0%,#122b15 100%);
      border:1px solid #2e7d32; border-radius:var(--radius);
      padding:.85rem .9rem; position:relative; overflow:hidden;
    }}
    .pollaya-card::before {{
      content:''; position:absolute; top:0; left:0; right:0; height:3px;
      background:linear-gradient(90deg,#4caf50,#81c784);
    }}
    .pc-head {{
      display:flex; justify-content:space-between; align-items:center;
      margin-bottom:.5rem; flex-wrap:wrap; gap:.25rem;
    }}
    .pc-round {{ font-size:.58rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:var(--accent2); }}
    .pc-time  {{ font-size:.62rem; color:var(--muted); }}
    .pc-matchup {{ font-size:.92rem; font-weight:800; text-align:center; padding:.35rem 0; color:var(--text); }}
    .pc-vs {{ color:var(--muted); font-weight:400; font-size:.78rem; margin:0 .3rem; }}
    .pc-rows {{ border-top:1px solid var(--border); padding-top:.45rem; margin-top:.1rem; }}
    .pc-row {{
      display:flex; justify-content:space-between; align-items:center;
      padding:.22rem 0; border-bottom:1px solid rgba(46,92,52,.4); font-size:.74rem;
    }}
    .pc-row:last-child {{ border-bottom:none; }}
    .pc-lbl {{ color:var(--muted); }}
    .pc-val {{ font-weight:800; color:var(--accent2); }}
    .pc-conf {{ padding:.1rem .4rem; border-radius:3px; font-size:.66rem; font-weight:700; letter-spacing:.05em; }}
    .conf-high {{ background:#1b5e20; color:#a5d6a7; }}
    .conf-med  {{ background:#e65100; color:#ffccbc; }}
    .conf-low  {{ background:#4a148c; color:#e1bee7; }}
  </style>
</head>
<body>

<header>
  <h1>&#127942; FIFA World Cup 2026 &mdash; Predictions</h1>
  <p>Monte Carlo simulation &mdash; {sims:,} runs &bull; Full 48-team format with Round of 32 &bull; {today}</p>
</header>

<div class="container">

<!-- ═══ POLLAYA PICKS (always first) ═══ -->
{build_pollaya_panel(data)}

<!-- ═══ SECTION 1 — TOP PREDICTIONS ═══ -->
<section>
  <div class="section-title">Top Predictions</div>
  {pending_banner}
  <div class="top-grid">
    <div class="pred-card winner">
      <span class="pred-medal">&#127942;</span>
      <div class="pred-label">Tournament Winner</div>
      <div class="pred-team">{h(winner)}</div>
      <div class="pred-pct">{winner_pct}%</div>
      <div class="pred-sub">{round(winner_pct/100*sims):,} / {sims:,} simulations</div>
    </div>
    <div class="pred-card runner">
      <span class="pred-medal">&#129352;</span>
      <div class="pred-label">Runner-Up</div>
      <div class="pred-team">{h(runner["team"])}</div>
      <div class="pred-pct">{runner["probability"]}%</div>
      <div class="pred-sub">Most likely finalist #2</div>
    </div>
    <div class="pred-card third">
      <span class="pred-medal">&#129353;</span>
      <div class="pred-label">Third Place</div>
      <div class="pred-team">{h(third["team"])}</div>
      <div class="pred-pct">{third["probability"]}%</div>
      <div class="pred-sub">Most likely 3rd-place finish</div>
    </div>
    <div class="pred-card boot">
      <span class="pred-medal">&#127966;</span>
      <div class="pred-label">Golden Boot</div>
      <div class="pred-team">{h(golden_boot["player"])}</div>
      <div class="pred-pct" style="color:var(--yellow);">{golden_boot["expected_goals"]}</div>
      <div class="pred-sub">{h(golden_boot["team"])} &bull; xG in tournament</div>
    </div>
  </div>
</section>

<!-- ═══ SECTION 2 — WIN PROBABILITY RANKINGS ═══ -->
<section>
  <div class="section-title">Win Probability &mdash; Top 16</div>
  <table class="prob-table">
    <thead><tr><th>#</th><th>Team</th><th>Win Probability</th></tr></thead>
    <tbody>
{prob_rows}    </tbody>
  </table>
</section>

<!-- ═══ SECTION 3 — ROUND OF 32 ═══ -->
<section>
  <div class="section-title">Round of 32 &mdash; All 16 Matches</div>
  <p style="font-size:.72rem;color:var(--muted);margin-bottom:.75rem;">
    "Reaches X%" = probability this team plays in this slot across all {sims:,} simulations.
    "Wins if reached Y%" = conditional win probability when they do play.
    Score format: Most-probable predicted scoreline.
  </p>
  <div class="ko-round-label">Left Side of Bracket (feeds Semi-Final 1)</div>
  <div class="ko-grid">
{r32_left}  </div>
  <div class="ko-round-label">Right Side of Bracket (feeds Semi-Final 2)</div>
  <div class="ko-grid">
{r32_right}  </div>
</section>

<!-- ═══ SECTION 4 — BRACKET TREE R16 → FINAL ═══ -->
<section>
  <div class="section-title">Knockout Bracket &mdash; Round of 16 through Final</div>
  <p class="bracket-note">
    Projected bracket path based on {sims:,} simulations. Percentages = probability of winning that match slot overall.
    Highlighted team is the projected winner at each stage. Predicted scoreline shown below each matchup.
    Scroll right on small screens.
  </p>
  <div class="bracket-scroll">
    <div class="bracket">

      <!-- Column 1: Round of 16 -->
      <div class="b-round">
        <div class="b-round-title">Round of 16</div>
        <div class="b-slots">
          {r16_html}
        </div>
      </div>

      <!-- Column 2: Quarter-finals -->
      <div class="b-round">
        <div class="b-round-title">Quarter-finals</div>
        <div class="b-slots">
          {qf_html}
        </div>
      </div>

      <!-- Column 3: Semi-finals -->
      <div class="b-round">
        <div class="b-round-title">Semi-finals</div>
        <div class="b-slots">
          {sf_html}
        </div>
      </div>

      <!-- Column 4: Final + 3rd place -->
      <div class="b-round">
        <div class="b-round-title">Final &middot; MetLife Stadium, NJ</div>
        <div class="b-slots">
          {final_html}
          <div class="tp-card">
            <div class="tp-title">3rd-Place Match &middot; Hard Rock Stadium, {h(tp_city)}</div>
            {tp_html}
          </div>
        </div>
      </div>

    </div>
  </div>
</section>

</div>

<footer>
  Generated {today} &bull; Monte Carlo simulation {sims:,} iterations &bull;
  Full 48-team FIFA World Cup 2026 format
  {" &bull; &#9733; = Pending FIFA confirmation" if has_pending else ""}
</footer>

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
