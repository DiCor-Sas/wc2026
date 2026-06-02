"""
Generate index.html from predictions.json.
Run after run_predictions.py produces the JSON.
"""
import json
from datetime import date

PREDICTIONS_FILE = "/Users/diegofelipecortessastoque/Desktop/wc2026/predictions.json"
OUTPUT_FILE      = "/Users/diegofelipecortessastoque/Desktop/wc2026/index.html"

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
  </style>
</head>
<body>

<header>
  <h1>&#127942; FIFA World Cup 2026 &mdash; Predictions</h1>
  <p>Monte Carlo simulation &mdash; {sims:,} runs &bull; Full 48-team format with Round of 32 &bull; {today}</p>
</header>

<div class="container">

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
    <div class="pred-card" style="border-top:3px solid var(--accent2);">
      <span class="pred-medal">&#9917;</span>
      <div class="pred-label">Simulations</div>
      <div class="pred-team" style="font-size:.85rem;">{sims:,} runs</div>
      <div class="pred-pct" style="font-size:1rem;color:var(--accent2);">48 teams</div>
      <div class="pred-sub">Full tournament MC model</div>
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
