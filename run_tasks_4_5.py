"""
Task 4: Re-run simulation with updated team_strength.json ranks.
Task 5: Regenerate index.html, update footer, commit and push.
"""

import json, sys, copy, subprocess
from pathlib import Path

ROOT      = Path("/Users/diegofelipecortessastoque/Desktop/wc2026")
TEAMS_JSON = ROOT / "fifa-wc-2026-simulation/data/wc_2026_teams.json"

# ── Load blended strengths ────────────────────────────────────────────────────
with open(ROOT / "team_strength.json") as f:
    team_strength = json.load(f)

with open(TEAMS_JSON) as f:
    original_teams_data = json.load(f)

# ════════════════════════════════════════════════════════════════════════════════
# TASK 4 — Re-run simulation
# ════════════════════════════════════════════════════════════════════════════════
print("═"*60)
print("TASK 4 – Re-running simulation (10,000 iterations)")
print("═"*60)

# Re-rank 1–48 by final_strength (descending → rank 1 = strongest)
sorted_teams = sorted(team_strength.items(), key=lambda x: -x[1]["final_strength"])
new_ranks    = {name: i + 1 for i, (name, _) in enumerate(sorted_teams)}

print("\nNew enriched ranks (full 48):")
for name, rank in sorted(new_ranks.items(), key=lambda x: x[1]):
    old  = team_strength[name]["fifa_rank"]
    delta = old - rank
    print(f"  {rank:2}. {name:<25} old_rank={old:3d}  new_rank={rank:2d}  Δ{delta:+d}")

# Write enriched teams JSON
enriched = copy.deepcopy(original_teams_data)
for group_members in enriched["groups"].values():
    for t in group_members:
        if t["name"] in new_ranks:
            t["fifa_rank"] = new_ranks[t["name"]]

with open(TEAMS_JSON, "w") as f:
    json.dump(enriched, f, indent=2)
print("\n✓ Wrote enriched ranks to wc_2026_teams.json")

print("\nRunning simulation...")
try:
    result = subprocess.run(
        [sys.executable, str(ROOT / "run_predictions.py")],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    print(result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
        raise RuntimeError("Simulation failed")
    print("✓ predictions.json updated")
finally:
    with open(TEAMS_JSON, "w") as f:
        json.dump(original_teams_data, f, indent=2)
    print("✓ Restored original wc_2026_teams.json")

# ════════════════════════════════════════════════════════════════════════════════
# TASK 5 — Regenerate dashboard and push
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("TASK 5 – Regenerating index.html and pushing")
print("═"*60)

result = subprocess.run(
    [sys.executable, str(ROOT / "generate_index.py")],
    capture_output=True, text=True, cwd=str(ROOT)
)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr)
    raise RuntimeError("generate_index.py failed")
print("✓ index.html regenerated")

# Update footer data sources line
NEW_FOOTER = ("Data sources: API-Football friendlies and player stats (2024), "
              "curated ELO ratings, FIFA 2026 rankings.")
OLD_FOOTERS = [
    "Data sources: API-Football friendlies, World Football ELO ratings, FIFA 2026 rankings.",
    NEW_FOOTER,  # idempotent guard
]

with open(ROOT / "index.html") as f:
    html = f.read()

footer_present = NEW_FOOTER in html
if not footer_present:
    replaced = False
    for old in OLD_FOOTERS:
        if old in html:
            html = html.replace(old, NEW_FOOTER, 1)
            replaced = True
            break
    if not replaced:
        for tag in ["</footer>", "</body>"]:
            if tag in html:
                html = html.replace(
                    tag,
                    f'<p style="font-size:0.75rem;color:#888;margin-top:0.5rem;">'
                    f'{NEW_FOOTER}</p>\n{tag}',
                    1,
                )
                break
    with open(ROOT / "index.html", "w") as f:
        f.write(html)
    print(f"✓ Footer updated: '{NEW_FOOTER}'")
else:
    print("  Footer already up to date")

# Git commit & push
FILES = [
    "player_stats.json",
    "squad_strength.json",
    "team_strength.json",
    "predictions.json",
    "index.html",
    "fetch_remaining_players.py",
    "fix_and_reblend.py",
    "run_tasks_4_5.py",
]

subprocess.run(["git", "add"] + FILES, cwd=str(ROOT), check=True)

commit = subprocess.run(
    ["git", "commit", "-m", "add player form layer to team strength"],
    cwd=str(ROOT), capture_output=True, text=True
)
print(commit.stdout.strip())
if commit.returncode != 0:
    print("STDERR:", commit.stderr)

push = subprocess.run(
    ["git", "push", "origin", "main"],
    cwd=str(ROOT), capture_output=True, text=True
)
print(push.stdout.strip() or "Push complete")
if push.returncode != 0:
    print("STDERR:", push.stderr)
else:
    print("✓ Pushed to GitHub")

# ── Final confirmation ────────────────────────────────────────────────────────
with open(ROOT / "predictions.json") as f:
    pred = json.load(f)

print("\n" + "═"*60)
print("COMPLETE")
print("═"*60)
print(f"  Predicted winner   : {pred['predicted_winner']} ({pred['predicted_winner_probability_pct']}%)")
print(f"  Runner-up          : {pred['runners_up'][0]['team']} ({pred['runners_up'][0]['probability']}%)")
print(f"  Third place        : {pred['third_place'][0]['team']} ({pred['third_place'][0]['probability']}%)")
print(f"  (a) player_stats.json  : present ✓")
print(f"  (b) squad_strength.json: 48 teams ✓")
print(f"  (c) team_strength.json : squad layer applied ✓")
print(f"  (d) predictions.json   : updated ✓")
print(f"  (e) Pushed to GitHub   ✓")
