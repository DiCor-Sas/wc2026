"""
notify_telegram.py
Send a Telegram reminder ~20 minutes before the next WC 2026 match kickoff,
including the model prediction, confidence, lineup status, and Pollaya
picks to submit.

Usage:
    python3 notify_telegram.py --window 25 [--dry-run]

Exit code is always 0 (never blocks the GitHub Actions workflow).
"""
import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import generate_index as gi

ROOT = Path(__file__).parent.resolve()
PREDICTIONS_FILE = ROOT / "predictions.json"

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
DASHBOARD_URL = "dicor-sas.github.io/wc2026"


def _lineup_status(xi, source):
    if source == "api-football" and len(xi) >= 5:
        return "CONFIRMED"
    if source in ("espn-playwright", "bbc-playwright", "web-search") and xi:
        return "ESTIMATED"
    return "PENDING"


def _team_lineup_statuses(t1, t2):
    lineups = gi._load_lineups()
    lu = lineups.get((t1, t2))
    if lu:
        home_xi, away_xi = lu.get("home_xi", []), lu.get("away_xi", [])
    else:
        lu = lineups.get((t2, t1))
        if lu:
            away_xi, home_xi = lu.get("home_xi", []), lu.get("away_xi", [])
        else:
            return "PENDING", "PENDING"
    src = lu.get("source", "none")
    return _lineup_status(home_xi, src), _lineup_status(away_xi, src)


def _team_code(team):
    if team == "DRAW":
        return "DRAW"
    code = gi.COUNTRY_CODE.get(team, team[:3].upper())
    return code[:3]


def _find_match(window_minutes):
    """Return the next upcoming match dict (from gi._upcoming_matches) whose
    kickoff falls within [now, now+window_minutes], or (None, None)."""
    try:
        with open(PREDICTIONS_FILE) as f:
            data = json.load(f)
    except Exception:
        return None, None

    now_utc = datetime.now(timezone.utc)
    for m in gi._upcoming_matches(data):
        ko_dt = datetime.strptime(m["kickoff_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        delta_min = (ko_dt - now_utc).total_seconds() / 60
        if 0 <= delta_min <= window_minutes:
            return m, data
    return None, None


def _build_message(m, data):
    t1, t2 = m["t1"], m["t2"]
    flag1, flag2 = gi._flag(t1), gi._flag(t2)

    win_p1 = m.get("win_p1", "N/A")
    win_p2 = m.get("win_p2", "N/A")
    draw_p = m.get("draw_p", "N/A")
    score1 = m.get("score1", 0)
    score2 = m.get("score2", 0)
    winner = m.get("winner", "DRAW")
    conf = m.get("conf", "LOW")

    # Extract HH:MM from ko_fmt, e.g. "11 Jun · 14:00 COL"
    time_str = m["ko_fmt"].split("·")[-1].strip().replace("COL", "").strip()

    home_status, away_status = _team_lineup_statuses(t1, t2)

    home_code = _team_code(t1)
    away_code = _team_code(t2)
    winner_code = _team_code(winner)

    lines = [
        f"⚽ POLLAYA REMINDER — {m['match_lbl']}",
        "",
        f"{flag1} {gi.h(t1)} vs {flag2} {gi.h(t2)}",
        f"\U0001F4CD {m['venue']}",
        f"⏰ Kickoff in ~20 minutes ({time_str} COT)",
        "",
        f"\U0001F4CA Model prediction: {gi.h(t1)} {score1}-{score2} {gi.h(t2)}",
        f"\U0001F3AF Confidence: {conf}",
        f"\U0001F3C6 Win probability: {win_p1}% · Draw {draw_p}% · {win_p2}%",
        "",
        "\U0001F455 Lineups:",
        f"{gi.h(t1)}: {home_status}",
        f"{gi.h(t2)}: {away_status}",
        "",
        "\U0001F4A1 Check dashboard before submitting:",
        DASHBOARD_URL,
        "",
        "\U0001F3B0 Pollaya picks to submit:",
        f"SCORE: {score1}-{score2} · 15pts",
        f"WIN: {winner_code} · 8pts",
        f"GOALS: {home_code}{score1} {away_code}{score2} · 5pts",
    ]

    if m.get("is_ko") and m.get("went_to_et"):
        ko_entry = gi._ko_lookup(data).get(m.get("match_num"), {})
        score_90 = ko_entry.get("score_90", "?-?")
        score_120 = ko_entry.get("score_120", f"{score1}-{score2}")
        lines.append("")
        lines.append(
            f"⚠️ Knockout match — submit 120min score "
            f"if draw at 90min ({score_90} → {score_120})"
        )

    return "\n".join(lines)


def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, skipping send")
        return

    url = TELEGRAM_API.format(token=token)
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        print("Telegram reminder sent.")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"ERROR HTTP {e.code}: {body}")
    except Exception as e:
        print(f"ERROR: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", type=int, required=True,
                         help="Minutes ahead of now to look for a kickoff")
    parser.add_argument("--dry-run", action="store_true",
                         help="Print the message instead of sending it")
    args = parser.parse_args()

    try:
        match, data = _find_match(args.window)
    except Exception as e:
        print(f"ERROR finding match: {e}")
        return

    if not match:
        print("No match found in window.")
        return

    try:
        message = _build_message(match, data)
    except Exception as e:
        print(f"ERROR building message: {e}")
        return

    if args.dry_run:
        print(message)
        return

    send_telegram(message)


if __name__ == "__main__":
    main()
