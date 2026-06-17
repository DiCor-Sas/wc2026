"""
update_results.py — Full pipeline runner.
Steps:
  1. fetch_results.py  → wc2026_results.json, update elo_ratings.json, bracket_state.json
  2. Recalculate team_strength.json from updated ELO (same blending formula, no changes)
  3. Rerun simulation → predictions.json
  4. Regenerate index.html from predictions.json + bracket_state.json
  5. Commit all changed files and push to GitHub
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

SQUAD_SCALE_MIN = 800
SQUAD_SCALE_MAX = 2200


def step0_fetch_daily_results():
    print("\n" + "═" * 60)
    print("STEP 0 — Fetch daily international friendly results")
    print("═" * 60)
    import fetch_results
    try:
        fetch_results.fetch_daily_results()
    except Exception as e:
        print(f"  [warn] Daily results fetch failed: {e} — continuing pipeline")


def step1_fetch_and_update():
    print("\n" + "═" * 60)
    print("STEP 1 — Fetch results / Update ELO / Update bracket state")
    print("═" * 60)
    import fetch_results
    matches, source = fetch_results.fetch_results()
    fetch_results.recompute_wc_elo_from_scratch()
    fetch_results.update_bracket_state()
    return len(matches)


def step1b_fetch_match_stats():
    print("\n" + "═" * 60)
    print("STEP 1b — Fetch ESPN match statistics")
    print("═" * 60)
    import fetch_results
    fetch_results.fetch_match_stats()


def step2_recalculate_team_strength():
    print("\n" + "═" * 60)
    print("STEP 2 — Recalculate team_strength.json with updated ELO")
    print("═" * 60)

    with open(ROOT / "elo_ratings.json") as f:
        elo_data = json.load(f)
    with open(ROOT / "team_strength.json") as f:
        ts = json.load(f)

    elo_changed = 0
    rd_penalized = 0
    for team, s in ts.items():
        if team not in elo_data:
            print(f"  [warn] {team} not in elo_ratings.json — skipping")
            continue

        new_elo = elo_data[team]["elo"]
        rd = elo_data[team].get("rd", 200.0)

        if new_elo != s["elo"]:
            s["elo"] = new_elo
            elo_changed += 1

        # Recompute: base = ELO*0.50 + FIFA*0.30 + form*0.20
        base = (s["elo"] * 0.50) + (s["fifa_score"] * 0.30) + (s["form_score"] * 0.20)

        # Squad layer: squad_elo_like = 800 + norm * 1400
        squad_elo_like = SQUAD_SCALE_MIN + s["squad_score_norm"] * (SQUAD_SCALE_MAX - SQUAD_SCALE_MIN)

        # Blend: 70% base + 30% squad, then apply RD uncertainty penalty once to the fresh value
        fresh_strength = base * 0.70 + squad_elo_like * 0.30
        s["final_strength"] = round(fresh_strength * (1 - 0.0001 * rd), 2)
        rd_penalized += 1
        print(f"  {team}: ELO={s['elo']}  rd={rd:.1f}  final_strength={s['final_strength']}")

    with open(ROOT / "team_strength.json", "w") as f:
        json.dump(ts, f, indent=2)

    print(f"  ✓ {elo_changed} ELO update(s), RD penalty applied to {rd_penalized} teams. team_strength.json saved.")


def step3_run_simulation():
    print("\n" + "═" * 60)
    print("STEP 3 — Run tournament simulation (10,000 iterations)")
    print("═" * 60)
    result = subprocess.run(
        [sys.executable, str(ROOT / "run_predictions.py")],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print("ERROR: Simulation failed.")
        sys.exit(1)
    print("✓ Simulation complete.")


def step4_regenerate_html():
    print("\n" + "═" * 60)
    print("STEP 4 — Regenerate index.html")
    print("═" * 60)
    result = subprocess.run(
        [sys.executable, str(ROOT / "generate_index.py")],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print("ERROR: HTML generation failed.")
        sys.exit(1)
    print("✓ index.html regenerated.")


def step5_commit_and_push():
    print("\n" + "═" * 60)
    print("STEP 5 — Stage files for commit (commit/push handled by CI)")
    print("═" * 60)

    subprocess.run(
        ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
        cwd=str(ROOT), check=False,
    )
    subprocess.run(
        ["git", "config", "user.name", "github-actions[bot]"],
        cwd=str(ROOT), check=False,
    )

    candidates = [
        "wc2026_results.json",
        "bracket_state.json",
        "elo_ratings.json",
        "team_strength.json",
        "predictions.json",
        "index.html",
        "version.txt",
        "daily_results.json",
        "lineups.json",
    ]
    files_to_add = [f for f in candidates if (ROOT / f).exists()]

    subprocess.run(["git", "add"] + files_to_add, cwd=str(ROOT), check=False)
    print(f"  Staged: {', '.join(files_to_add)}")
    print("  ✓ Files staged. CI workflow will commit and push.")


if __name__ == "__main__":
    print("╔" + "═" * 58 + "╗")
    print("║  WC 2026 Dashboard — Full Pipeline                      ║")
    print("╚" + "═" * 58 + "╝")

    step0_fetch_daily_results()
    n_results = step1_fetch_and_update()
    step1b_fetch_match_stats()
    step2_recalculate_team_strength()
    step3_run_simulation()
    step4_regenerate_html()
    step5_commit_and_push()

    print("\n" + "═" * 60)
    print(f"Pipeline complete. {n_results} completed match(es) processed.")
    print("═" * 60)
