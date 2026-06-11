# CLAUDE.md — WC 2026 Dashboard Project Context

## 1. PROJECT OVERVIEW

Personal FIFA World Cup 2026 prediction dashboard for the "Pollaya" friend-group
prediction poll. Owner is not a coding expert — all changes go through Claude
Code with **show-before-implement approval gates** (see §10).

- Live site: https://dicor-sas.github.io/wc2026 (GitHub Pages, auto-deploys on
  push to `main`, served from `index.html` + `.nojekyll`)
- Repo: `DiCor-Sas/wc2026`
- Local path: `/Users/diegofelipecortessastoque/Desktop/wc2026`
- Target device: Samsung Galaxy S24+, Chrome (mobile-first layout)

## 2. POLLAYA SCORING RULES

- Exact score: 15 pts
- Correct winner: 8 pts
- Correct goals for one team: 5 pts
- Champion: 50 pts
- Runner-up: 35 pts
- Third place: 20 pts
- Top scorer (Golden Boot): 30 pts

**Knockout business rule**: tied 90-minute matches are judged on the
**120-minute (extra time) score** for Pollaya scoring purposes. Penalties are
**excluded** from scoring.

**Locked pre-tournament picks** (owner's own Pollaya entry, not model output):
- Champion: Spain
- Runner-up: Argentina
- Third place: Netherlands
- Golden Boot: Mikel Oyarzabal

## 3. ARCHITECTURE AND DATA FLOW

`update_results.py` is the full pipeline (`PROJECT_ROOT = Path(__file__).parent.resolve()`):

- **Step 0** — `fetch_results.fetch_daily_results()`: fetch today's completed
  international friendlies → `daily_results.json`, opportunistic ELO nudge.
  Wrapped in try/except; failure does not abort the pipeline.
- **Step 1** — `fetch_results.fetch_results()` → `wc2026_results.json` (list of
  `{date, group, round, team1, team2, home_score, away_score}`); then
  `update_elo_from_results()` updates `elo_ratings.json`; then
  `update_bracket_state()` updates `bracket_state.json`.
- **Step 2** — recompute `team_strength.json` from updated ELO:
  `base = ELO*0.50 + FIFA*0.30 + form*0.20`; squad layer
  `squad_elo_like = 800 + squad_score_norm * (2200-800)`; final blend
  `final_strength = (base*0.70 + squad_elo_like*0.30)`, then RD penalty
  `final_strength *= (1 - 0.0001 * rd)` applied to **every** team every run.
- **Step 3** — `run_predictions.py`: 10,000-iteration Monte Carlo simulation
  (`NUM_SIMULATIONS = 10_000`) → `predictions.json`.
- **Step 4** — `generate_index.py`: regenerates `index.html` from
  `predictions.json` + `bracket_state.json` + `fixtures.json` + `lineups.json`.
- **Step 5** — `step5_commit_and_push()`: only `git add`s the candidate files
  (see §7 "single commit point"). Actual commit/push is done by the GitHub
  Actions workflow, not this script.

**Simulation engine** — `engine/` package at repo root (`Team`, `Match`,
`Group`, `Competition`, `STAGE`, host-city/venue data, group-stage and
knockout bracket schedules R32→Final).

**Model details**:
- Dixon-Coles Poisson with low-score correction `tau(x,y,lh,la,rho=0.08)`
  (`run_predictions.py`)
- Skellam distribution for group-stage win/draw/loss probabilities
  (`scipy.stats.skellam`)
- Wilson score 80% confidence interval, `z=1.282` (`wilson_ci()`)
- ELO: K = `40 * decay_weight`, time-decay half-life = 180 days
  (`_decay_weight()` in `fetch_results.py`); standard logistic expected score
- Glicko-1 RD (rating deviation) tracked per team, updated symmetrically each
  match, clamped to `[30, 350]`
- Team strength formula: see Step 2 above (exact weights)
- Golden Boot: player-level simulation in `simulate_golden_boot()`
  (`run_predictions.py`), built from `player_stats.json` / `squad_strength.json`
- Extra-time fatigue: knockout draws after 90' get extra-time lambdas scaled
  by **0.28x** (`_extra_time_score()`, `et_lh = lh * 0.28`)

## 4. FILE MAP

**Pipeline / data scripts**
- `update_results.py` — orchestrates the 5-step pipeline (entry point for CI)
- `fetch_results.py` — all live data fetching: WC results, daily friendlies,
  ELO update, bracket state update, lineup fetch (`--lineup-only`)
- `run_predictions.py` — Monte Carlo simulation, Golden Boot, predictions JSON
- `generate_index.py` — builds `index.html` from JSON data
- `enrich_and_simulate.py` — original ELO/FIFA/form/squad blending pipeline
  (one-time enrichment, not part of the live cron pipeline)
- `fix_and_reblend.py`, `fetch_remaining_players.py`, `player_pipeline.py`,
  `run_tasks_4_5.py`, `backfill_check.py`, `test_lineup.py`, `test_scraper.py` —
  one-off / maintenance scripts, not run by CI

**Data files (JSON)**
- `wc2026_results.json` — completed WC matches (currently `[]`, pre-tournament)
- `daily_results.json` — completed friendly results for ELO nudges
- `elo_ratings.json` — per-team `{elo, rd, volatility}`
- `team_strength.json` — per-team `{elo, fifa_score, form_score,
  squad_score_norm, final_strength}`
- `predictions.json` — simulation output (winner, runners-up, third place,
  all_teams, group-stage win/draw/loss, Golden Boot, etc.)
- `bracket_state.json` — per-slot (e.g. `"Group A 1st"`, `"3rd Place Best 1"`)
  state: `status` (`CONFIRMED` or `PROJECTED`), `team`, `probability`,
  `qualified_via`, `result`, `display` (color/icon/label/style for UI)
- `fixtures.json` — 104 entries (`id` 1–104). 1–72 = group stage (with `group`,
  `home`, `away`, real team names). 73–104 = knockout (`match_num`, `round`
  R32/R16/QF/SF/3P/F, `home`/`away` as placeholders like `"2ND GROUP A"` /
  `"WINNER M101"`, resolved at runtime via `bracket_state.json`)
- `friendlies.json`, `squad_strength.json`, `player_stats.json`,
  `model_accuracy.json`, `lineups.json` — supporting data
- `version.txt` — unix timestamp, used as cache-bust / footer "last updated"

**Other**
- `index.html` — the live dashboard (generated, do not hand-edit)
- `dashboard.html` — old/legacy standalone file, not the live site, not
  referenced by the pipeline
- `.github/workflows/auto_update.yml` — CI automation (§5)
- `MANUAL_TRIGGER.md` — phone instructions for manually firing the workflow
- `CLAUDE.md` — this file
- `engine/` — simulation engine package (§3)
- `model/` — future ensemble-model training code (Session 4 roadmap, §9), not
  yet wired into the live pipeline
- `fifa-wc-2026-simulation/` — separate/vendored sub-project, not part of the
  live pipeline

## 5. AUTOMATION AND SCHEDULES

`.github/workflows/auto_update.yml`, two jobs:

- **`update`** (full pipeline): runs `update_results.py`, then commits/pushes
  `wc2026_results.json bracket_state.json elo_ratings.json team_strength.json
  predictions.json index.html version.txt daily_results.json lineups.json`.
  Triggered only on `workflow_dispatch` or the cron
  `0 10,12,14,16,18,20,22,0,2 * * *` (every 2h, 10:00–02:00 UTC).
- **`lineup_fetch`**: runs `fetch_results.py --lineup-only`, commits/pushes
  `lineups.json` (and `match_adjustments.json` if present) **only if something
  actually changed** — gated by `git diff --cached --quiet`. Triggered by all
  other schedule entries: June 11 specific kickoff triggers
  (`45 17 11 6 *` = Match 1 14:00 COT/19:00 UTC; `45 0 12 6 *` = Match 2 21:00
  COT/02:00 UTC Jun 12) plus general pre-match windows June 12–July 19
  (`45 10/13/16/17/19/22/23 * * *` UTC, covering 12:00/15:00/18:00/19:00/21:00/
  00:00/01:00 COT kickoffs respectively).
- Both jobs: `actions/checkout@v4` with `secrets.GITHUB_TOKEN`, git remote
  rewritten to `x-access-token:${GITHUB_TOKEN}@github.com/...`, Python 3.11,
  Playwright + chromium install (`continue-on-error: true`).
- `update` job push uses a 3-attempt retry loop:
  `git pull --rebase && git push && break`, else sleep `10s`/`20s` between
  attempts — handles overlapping pipeline runs.
- `permissions: contents: write, pages: write, id-token: write`
- `env: PYTHONUNBUFFERED=1, FORCE_COLOR=1, FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`
  (Node.js 24 for JS actions)
- **External cron-job.org backup**: 8 cron jobs hitting the workflow-dispatch
  endpoint on a schedule in **America/Bogota (COT)** time, as a redundancy
  layer in case GitHub's own scheduler is delayed. Auth via a fine-grained PAT
  with `Actions: write` scope, **expires 2026-07-25**.

## 6. DATA SOURCES AND THEIR STATUS

- **WC results**: `openfootball/worldcup.json` (primary) → `worldcup26.ir/get/games`
  (fallback) → Playwright ESPN WC scoreboard scraper (last resort, only
  attempted after June 11).
- **Daily friendly results** (`fetch_daily_results`): Sky Sports
  internationals page (`skysports.com/internationals-scores-fixtures`,
  embedded `data-state` JSON, plain HTML — **confirmed working**, primary) →
  Playwright ESPN date-specific scraper → FOX Sports HTML fallback.
- **Sky Sports WC-specific URL**: returned 404 pre-tournament — **to be
  re-tested June 11** and added as a WC-results fallback if live (see §9).
- **worldfootball.net**: BLOCKED by Cloudflare 403 — do not retry.
- **Sofascore**: BLOCKED 403 — do not retry.
- **API-Football** (`v3.football.api-sports.io`, header `x-apisports-key`):
  free tier blocks the 2026 season — do not use for live WC data. (Historical
  2024-season data was used one-time for squad/player enrichment via
  `enrich_and_simulate.py`, `player_pipeline.py`, etc.)

## 7. CRITICAL CONVENTIONS AND PAST BUGS

- Never hardcode absolute paths — always
  `ROOT = Path(__file__).parent.resolve()`.
- `scikit-learn==1.8.0` pinned in `requirements.txt` for pickle compatibility
  with `model/expanded_model.pkl` — do not upgrade.
- `requirements.txt` exact contents: `requests`, `beautifulsoup4`,
  `playwright`, `numpy==2.0.2`, `scipy==1.13.1`, `scikit-learn==1.8.0`,
  `pandas`, `lxml`, `duckdb`, `optuna`.
- **Runner-up and third place** must read from `predictions["runners_up"][0]`
  and `predictions["third_place"][0]` — **never** `all_teams[1]`/`all_teams[2]`.
  `all_teams` is ranked by champion probability, a different ordering
  (asserted in `generate_index.py`: runner-up probability must exceed
  third-place probability).
- **Single commit point**: `update_results.py` step 5 only `git add`s files —
  it never commits or pushes. Only the GitHub Actions workflow commits/pushes.
- All UI animations must have `prefers-reduced-motion` guards (both CSS
  `@media (prefers-reduced-motion: reduce)` and JS
  `window.matchMedia('(prefers-reduced-motion: reduce)')` checks).
- No external assets or CDN dependencies beyond Google Fonts.
- Dark theme palette: body `#000000`, `--fifa-card: #0A0F1A`,
  `--fifa-border: #1A2640`, gold `--fifa-gold: #C9A84C`, red
  `--fifa-red: #E8002D`.
- **Git workflow note**: remote receives concurrent automation pushes;
  `index.html`/`version.txt` rebase conflicts are resolved by re-running
  `python3 generate_index.py` and re-`git add`-ing the regenerated files —
  never by manual merge.
- ELO per-match deltas are **not persisted** — only current ratings — so
  dashboard "ELO impact" lines (`_elo_impact_str`) are recomputed estimates
  from current values, not historical deltas.

## 8. DASHBOARD STRUCTURE

`index.html` (generated by `generate_index.py`), key pieces:

- Countdown banner (`#main-banner` / `#banner-text`), driven by
  `updateBanner()` and the `WC_MATCHES` array (label + UTC kickoff time for
  all 104 fixtures, group stage through Final).
- `updateCountdowns()`: per-match-card countdown; adds `.live-now` class when
  `now` is within `LIVE_WINDOW_MS = 110 * 60 * 1000` (110 min) after kickoff;
  `.live-now` hides `.score-display`/`.mc-score-label` and shows
  `.live-score-display`.
- `animateScore(card)`: score count-up reveal on scroll, hooked into an
  `IntersectionObserver`, gated by `data-animated` flag and
  `prefers-reduced-motion`.
- Stadium background: `body::before` = aurora layer (untouched), `body::after`
  = fluorescent pitch-stripe shimmer (`pitchShimmer`), `#floodlights` and
  `#crowd-wave` fixed divs at `z-index: 1`; content sections at `z-index: 2`.
- Match cards: confidence badges (LOW/MED/HIGH) with tap-to-show tooltips
  (`.tooltip-visible`, `data-tooltip` attr); lineup badge shows
  `STARTING XI PENDING` until `lineups.json` has a confirmed XI
  (`xi_confirmed = src == "api-football" and len(xi) >= 5` for both teams).
- Knockout cards (`_bracket_section_html`, `ko_card`): show `CONFIRMED` team
  names or `PROJECTED <slot> <prob>%` (muted style, `~` icon) per
  `bracket_state.json`. For matches that may go to extra time/penalties:
  `INCL. EXTRA TIME` (gold) or `MAY GO TO PENALTIES` (amber) labels under the
  predicted score.
- Results section (`_results_section_html`, `#results-section`): hidden
  (`display:none`) until `wc2026_results.json` is non-empty; shows up to 6
  results plus a "show all" toggle (`#results-show-all`, `#results-extra`);
  match considered "ended" at kickoff + 110 min (COT = UTC-5).
- Predicted-pick mini cards: Champion/Runner-up/Third/Golden Boot
  (`.pick-mini`, `.pick-mini.gold` for Golden Boot).

## 9. PENDING ITEMS AND ROADMAP

- **June 11**: re-test the Sky Sports World Cup-specific URL (was 404
  pre-tournament); if live, add as a WC-results fallback source.
- **June 13+ (Session 4)**: three-model ensemble — Dixon-Coles + Negative
  Binomial + Bivariate Poisson, combined with adaptive Brier-score weights.
  Needs **8+ real match results** before it can be calibrated. Related
  training code lives in `model/` (`train.py`, `pipelines.py`,
  `expanded_model.pkl`).
- Knockout kickoff times in `fixtures.json` (M73–M104, all `"time": "14:00"`,
  `"timezone": "COT"`) are **placeholders** pending FIFA's official knockout
  schedule confirmation — update once announced.

## 10. WORKING AGREEMENT

- Always **show proposed code before writing any file** and wait for approval.
- Never run `update_results.py` casually — it makes live network calls and
  takes ~10–15 minutes (full Monte Carlo simulation).
- After display/HTML changes, verify with `python3 generate_index.py`.
- Commit messages: short and descriptive.
- Owner prefers step-by-step confirmation over large unreviewed batches.
