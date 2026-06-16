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
- **Step 2** — recompute `team_strength.json` from updated ELO. **Every team,
  every run**, `final_strength` is recomputed fresh from current
  `elo`/`fifa_score`/`form_score`/`squad_score_norm` — never derived from the
  previous run's `final_strength`:
  `base = ELO*0.50 + FIFA*0.30 + form*0.20`; squad layer
  `squad_elo_like = 800 + squad_score_norm * (2200-800)`; fresh blend
  `fresh_strength = (base*0.70 + squad_elo_like*0.30)`; then the RD penalty
  is applied **once** to that fresh value:
  `final_strength = round(fresh_strength * (1 - 0.0001 * rd), 2)`.
  (Past bug: the RD penalty used to be applied to the *previous*
  `final_strength` instead of a fresh recompute, compounding every pipeline
  run and collapsing values for teams with infrequent ELO updates — fixed
  2026-06-12.)
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
- `notify_telegram.py` — Telegram match-reminder bot (run by
  `.github/workflows/notify.yml`, see §5). Imports `generate_index` for
  `_upcoming_matches`/`_flag`/`COUNTRY_CODE`/`_load_lineups`/`_ko_lookup`/`h`
  to stay consistent with the dashboard's predictions/confidence/venue
  output (import is side-effect-free — `build_html()` and all file writes
  in `generate_index.py` are gated behind `if __name__ == "__main__"`).
  Flags: `--window N` (minutes ahead of now to look for a kickoff;
  exits 0 silently if none found), `--dry-run` (prints the formatted
  message instead of calling the Telegram API). Reads `TELEGRAM_BOT_TOKEN`
  and `TELEGRAM_CHAT_ID` from the environment; missing/failed
  send never causes a non-zero exit.

**Data files (JSON)**
- `wc2026_results.json` — completed WC matches (group stage underway as of
  2026-06-12; 2 matches completed so far)
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
  `"WINNER M101"`, resolved at runtime via `bracket_state.json`). All 104
  `time`/`timezone` (COT) values verified 2026-06-11 against the official
  schedule (source: `WC_Schedule.md`, see §5) — 17 distinct COT kickoff
  windows across the tournament (11:00, 12:00, 13:00, 14:00, 15:00, 15:30,
  16:00, 17:00, 18:00, 18:30, 19:00, 19:30, 20:00, 20:30, 21:00, 22:00, 23:00).
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

As of 2026-06-11, all three workflows below cover **all 17 distinct COT
kickoff windows** used across the 104 fixtures (11:00, 12:00, 13:00, 14:00,
15:00, 15:30, 16:00, 17:00, 18:00, 18:30, 19:00, 19:30, 20:00, 20:30, 21:00,
22:00, 23:00), derived from the verified source schedule (see "Source of
truth" below).

`.github/workflows/auto_update.yml`, two jobs:

- **`update`** (full pipeline): runs `update_results.py`, then commits/pushes
  `wc2026_results.json bracket_state.json elo_ratings.json team_strength.json
  predictions.json index.html version.txt daily_results.json lineups.json`.
  Triggered on `workflow_dispatch`, the cron `0 10,12,14,16,18,20,22,0,2 * * *`
  (every 2h, 10:00–02:00 UTC), and **pre-match reruns 45 min before each of
  the 17 COT kickoff windows** — UTC crons at `:15` for on-the-hour COT
  kickoffs and `:45` for the `:30` COT kickoffs (15:30, 18:30, 19:30, 20:30
  COT).
- **`lineup_fetch`**: runs `fetch_results.py --lineup-only`, commits/pushes
  `lineups.json` (and `match_adjustments.json` if present) **only if something
  actually changed** — gated by `git diff --cached --quiet`. Triggered
  **50 min before each of the 17 COT kickoff windows** — UTC crons at `:10`
  for on-the-hour COT kickoffs and `:40` for the `:30` COT kickoffs.

**Pre-match timing chain** (per kickoff window): lineup fetch fires 50 min
before kickoff (FIFA's starting-XI submission deadline is 60 min before;
ESPN/BBC publish 2-5 min later) → full pipeline rerun fires 45 min before
kickoff, picking up the just-fetched lineups and regenerating
`predictions.json`/`index.html` with lineup-adjusted simulations → Telegram
reminder (`notify.yml`) fires 20 min before kickoff, by which time
the dashboard already reflects the lineup-adjusted predictions.
- Both jobs: `actions/checkout@v4` with `secrets.GITHUB_TOKEN`, git remote
  rewritten to `x-access-token:${GITHUB_TOKEN}@github.com/...`, Python 3.11,
  Playwright + chromium install (`continue-on-error: true`).
- `update` job push uses a 3-attempt retry loop:
  `git pull --rebase && git push && break`, else sleep `10s`/`20s` between
  attempts — handles overlapping pipeline runs.
- `permissions: contents: write, pages: write, id-token: write`
- `env: PYTHONUNBUFFERED=1, FORCE_COLOR=1, FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`
  (Node.js 24 for JS actions)
- **External cron-job.org backup**: cron jobs hitting the workflow-dispatch
  endpoint on a schedule in **America/Bogota (COT)** time, as a redundancy
  layer in case GitHub's own scheduler is delayed. Auth via a fine-grained PAT
  with `Actions: write` scope, **expires 2026-07-25**.

`.github/workflows/notify.yml`, one job:

- **`send_reminder`**: runs `python3 notify_telegram.py --window 25` (25 min
  window to absorb GitHub Actions scheduling delays for a ~20-min-before-
  kickoff reminder). No pip install step — uses only stdlib `urllib` plus
  the local `generate_index` module.
- Triggers: `workflow_dispatch` plus 17 daily UTC crons, 20 min before each
  of the 17 COT kickoff windows — UTC crons at `:40` for on-the-hour COT
  kickoffs and `:10` for the `:30` COT kickoffs (15:30→20:10, 18:30→23:10,
  19:30→00:10, 20:30→01:10 UTC).
- `permissions: contents: read` (read-only — sends a message, never
  commits). `actions/checkout@v4` with `secrets.GITHUB_TOKEN`, Python 3.11,
  `env: FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`.
- Secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are already set in the
  repo's GitHub Actions secrets (values not stored anywhere in this repo).
- Test locally with: `python3 notify_telegram.py --window 9999 --dry-run`
  (prints the formatted message without calling the Telegram API).
- **External cron-job.org backup**: add cronjobs hitting
  `https://api.github.com/repos/DiCor-Sas/wc2026/actions/workflows/notify.yml/dispatches`
  (same PAT/headers/body `{"ref":"main"}` as the auto_update.yml backups),
  scheduled in America/Bogota 20 min before each of the 17 kickoff windows.

**Source of truth**: `WC_Schedule.md` (Spanish-language official schedule,
provided by owner 2026-06-11). All kickoff times use the **COL/ECU/PER**
column as COT (cross-checked against ARG/URU = COT+2). Used to correct all
104 `fixtures.json` times and derive the 17 cron windows above.

## 6. DATA SOURCES AND THEIR STATUS

- **WC results** (`fetch_results()`, `source` tag in pipeline logs is a
  `+`-joined list of every source that contributed, e.g.
  `"skysports-wc+espn-api+worldcup26.ir"`): **all three sources below are
  always queried** (no chain short-circuit), then merged via
  `_merge_wc_results()` — matches are deduplicated on the unordered
  `(team1, team2)` pair; for a given match, the first source to report it
  wins the base record, and later sources backfill missing `group`/`round`
  metadata and replace a "today" date fallback with a real event date.
  **Source 1** Sky Sports WC hub (`skysports.com/fifa-world-cup`, Playwright
  with `wait_until="domcontentloaded"` + an ad/analytics request-blocking
  route handler — `googletagmanager`, `facebook`, `analytics`, `doubleclick`,
  `googlesyndication`, `amazon-adsystem`, `rubiconproject`,
  `scorecardresearch`, `outbrain`, `taboola` — plus
  `page.wait_for_selector("a.sdc-site-fixres__match", timeout=10000)`
  instead of `networkidle`, which never resolves on this page due to
  continuous background ad/analytics requests; `_parse_skysports_wc()` then
  parses `a.sdc-site-fixres__match` `aria-label` like
  `"Mexico 2 - South Africa 0"` via regex `r"^(.+) (\d+) - (.+) (\d+)$"`. The
  page only shows a rotating subset of fixtures (not full history) and
  exposes no per-match date, so `date` falls back to today's date — source
  tag `skysports-wc`). **Source 2** ESPN JSON API (`_fetch_espn_wc_api()`,
  plain `requests.get()` against
  `https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard
  ?dates=YYYYMMDD` — note league slug is **`fifa.world`**, not
  `fifa.worldcup`; the latter's HTML scoreboard page returns ESPN's generic
  homepage/error page and was the old, now-removed Playwright source. Tries
  **today, then yesterday**; filters `competitions[0].status.type.name ==
  "STATUS_FULL_TIME"`, reads team names from `competitors[].team.displayName`
  normalized via `_fn()`, scores from `competitors[].score` — source tag
  `espn-api`). **Source 3** `worldcup26.ir/get/games` (filters
  `finished == "TRUE"`, reads team names directly from
  `home_team_name_en`/`away_team_name_en` and normalizes via `_fn()` — e.g.
  `"Czech Republic"` → `"Czechia"`; this source provides `group`/`round` and
  the real match date — source tag `worldcup26.ir`). If all three return
  empty, `wc2026_results.json` is written as `[]` and the pipeline continues
  (graceful degradation). `_scrape_espn_matches()` /
  `_parse_espn_evts_html()` (Playwright `espn.com/.../league/fifa.worldcup`
  scoreboard HTML, `evts[]` inline JSON) are **no longer used for WC
  results** but remain in place for the daily-friendlies chain below.
- **Daily friendly results** (`fetch_daily_results`): Sky Sports
  internationals page (`skysports.com/internationals-scores-fixtures`,
  embedded `data-state` JSON, plain HTML — **confirmed working**, primary) →
  Playwright ESPN date-specific scraper → FOX Sports HTML fallback.
- **Lineup fetch chain** (`fetch_lineup()` in `fetch_results.py`, threshold
  `len(xi) >= 5` per side): Source 1 API-Football → **Source 2 Rotowire**
  (`rotowire.com/soccer/lineups.php?league=WOC`, plain `requests` +
  BeautifulSoup, no Playwright — **confirmed working**, server-side rendered
  `div.lineup.is-soccer` blocks matched via `lineup__abbr` 3-letter codes,
  player names from `li.lineup__player a[title]`; team-name → Rotowire-code
  mapping is `ROTOWIRE_COUNTRY_CODE`) → Source 3 ESPN Playwright
  (scoreboard → match page) → Source 4 BBC Sport Playwright (fixtures page →
  match page) → Source 5 graceful degradation (`STARTING XI PENDING`).
  `_lineup_badge_html()` in `generate_index.py` shows `LINEUP CONFIRMED`
  (green) for sources `rotowire` and `api-football` (since API-Football
  never returns data for this tournament, Rotowire is effectively the
  confirmed source), and `LINEUP ESTIMATED` for `espn-playwright`,
  `bbc-playwright`, `web-search`.
- **Absence detection name matching** (`_name_in_xi()` in
  `fetch_results.py`, used by `_detect_key_absences()`): Rotowire XIs use
  abbreviated names (e.g. `"K. Mbappe"`) while `player_stats.json` has full
  names (e.g. `"Kylian Mbappé"`). `_name_in_xi()` tries, in order: exact
  match, last-name match, abbreviated-first-name match (xi entry's last
  token == player's last name), then bidirectional substring as a
  fallback — avoids false-positive "player absent" flags against Rotowire
  lineups.
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
- `requirements.txt` exact contents (all pinned as of 2026-06-12):
  `requests==2.32.5`, `beautifulsoup4==4.14.3`, `playwright==1.60.0`,
  `numpy==2.0.2`, `scipy==1.13.1`, `scikit-learn==1.8.0`, `pandas==2.3.3`,
  `lxml==6.1.1`, `duckdb==1.4.4`, `optuna==4.9.0`. All pinned 2026-06-12 for
  pipeline stability through end of tournament. `optuna` installed and
  pinned ahead of Session 4 ensemble work.
- **Runner-up and third place** must read from `predictions["runners_up"][0]`
  and `predictions["third_place"][0]` — **never** `all_teams[1]`/`all_teams[2]`.
  `all_teams` is ranked by champion probability, a different ordering.
  `generate_index.py` expects runner-up probability to exceed third-place
  probability; if violated it warns and auto-swaps the two entries rather
  than crashing (H5, 2026-06-12).
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
- **ELO double-counting dedup guard (2026-06-12)**: `update_elo_from_results()`
  in `fetch_results.py` had no `applied_keys`-style guard and reprocessed
  every match in `wc2026_results.json` on every pipeline run (10-17x/day),
  compounding ELO and Glicko-1 RD for affected teams with each run. Fixed by
  adding `wc_applied_keys` (persisted in `elo_ratings.json` under the key
  `wc_applied_keys`), mirroring the `applied_keys` pattern in
  `fetch_daily_results()`. A one-time reset script (`reset_elo_corruption.py`,
  completed 2026-06-12, do not re-run) restored correct post-match ELO/RD for
  the 4 affected teams (Mexico, South Korea, Czechia, South Africa) from
  pre-match baselines before the dedup guard was active.
  Note: fixes were local-only during the 2026-06-12 session. A CI run
  executed against the unpatched code and uncorrected elo_ratings.json
  before the push landed — that run's ELO outputs are superseded by the
  corrected data pushed immediately after. First clean pipeline run
  confirmed post-push.
- **`generate_index.py` hardening (2026-06-12)**: replaced the hard `assert`
  on runner-up/third-place probability ordering with a warn-and-swap guard
  (H5). All top-level `predictions.json` key accesses in `build_html()` and
  `_compute_golden_boot()` were replaced with `.get()` calls and safe
  defaults (H6) to prevent `KeyError` crashes during `predictions.json`
  schema changes in Session 4.
- **`notify_telegram.py` lineup and multi-match fixes (2026-06-12)**: added
  `"rotowire"` to the confirmed-source check in `_lineup_status()` so
  Telegram reminders correctly show `LINEUP CONFIRMED` (H1). Renamed
  `_find_match()` to `_find_matches()` and restructured it to return all
  matches in the kickoff window; `main()` now sends one reminder per match so
  simultaneous-kickoff pairs both get notified (H2).
- **GitHub Pages CDN cache-bust (2026-06-12)**: GitHub Pages ignores
  `<meta http-equiv='Cache-Control'>` tags and serves stale `index.html`
  from CDN after each deployment. Fixed by adding a version-check snippet as
  the first statement in the main `<script>` block in `generate_index.py`.
  On every page load it fetches `version.txt` with a `Date.now()` query
  string (bypassing CDN cache on that tiny file), compares it to the value
  stored in `localStorage` under `wc_version`, and calls `location.reload()`
  if they differ. This guarantees users always see the latest pipeline
  output within one page load after any deployment, with no manual cache
  clearing required.
- **Push conflict fix (2026-06-12/13)**: concurrent update runs regenerate
  `daily_results.json`, `index.html`, `predictions.json`, and `version.txt`
  with always-different content (fresh timestamps, unseeded RNG). `git pull
  --rebase` cannot auto-merge these files, causing unresolvable content
  conflicts on every concurrent push. Fixed with a
  fetch-reset-overwrite-commit-push pattern: before touching git state, the
  10 generated files are saved to a temp directory; each retry iteration does
  `git fetch` + `git reset --hard origin/main` (taking the latest remote as
  base), copies the saved files back over the top, commits, and pushes. No
  merge, no rebase, no conflict possible. A job-level concurrency guard
  (`group: pipeline-update`, `cancel-in-progress: false`) on the `update` job
  additionally serializes runs so only one update job executes at a time. The
  `lineup_fetch` job is deliberately left unguarded.
- **Concurrent-run push conflict guard (2026-06-12)**: two schedulers
  (GitHub Actions cron plus the external cron-job.org backup) could trigger
  the `update` job simultaneously, causing two full pipeline runs to
  regenerate the same files with different content and produce unresolvable
  rebase conflicts on push (observed: `daily_results.json`, `index.html`,
  `predictions.json`). Fixed with a job-level concurrency group
  (`group: pipeline-update`, `cancel-in-progress: false`) on the `update`
  job only — overlapping update runs now queue and run sequentially instead
  of colliding. The `lineup_fetch` job is deliberately left unguarded so its
  50-min-before-kickoff timing is never delayed by a queued `update` run.
  `cancel-in-progress` is false so a running pipeline is never killed
  mid-run.
- **lineup_fetch and update job isolation fix (2026-06-15)**: the `update`
  job's fetch-reset-overwrite pattern was overwriting `lineups.json` with
  its stale checkout-time snapshot, discarding fresh data committed by the
  `lineup_fetch` job. Fixed by removing `lineups.json` from the `update` job
  `FILES` variable — the `update` job never writes `lineups.json` so it
  should never save/restore it. Also wired `match_adjustments.json` into
  `_strength_lambdas()` in `generate_index.py`: absence penalties written by
  `_detect_key_absences()` now correctly reduce the displayed predicted
  score and win probability on match cards via multiplicative ratio
  application (`adjusted_lambda / base_lambda` per absent player per team).
  Previously `match_adjustments.json` was a silent dead-end with no
  downstream reader.
- **Over 2.5 and BTTS market chips added (2026-06-15)**: two new statistical
  market chips added to each group-stage match card in `generate_index.py`.
  `_over25_prob(lam1, lam2)` computes probability of 3 or more total goals
  using independent Poisson PMFs. `_btts_prob(lam1, lam2)` computes
  probability both teams score at least 1 goal:
  `(1-e^-lam1)*(1-e^-lam2)`. Both use the same `lam1`/`lam2` from
  `_strength_lambdas()` including any `match_adjustments.json` absence
  penalties. BTTS chip includes a tap-to-show tooltip reusing the existing
  `confidence-badge` CSS/JS pattern. `mc-chips` grid changed from 3-column
  fixed to `repeat(auto-fit, minmax(90px,1fr))` to accommodate 5 chips on
  mobile. Chips are scoped to the rolling upcoming/live window via
  `_match_cards_html()` — completed matches in `_results_section_html()`
  are unaffected.
- **`wc2026_results.json` history preservation (2026-06-16)**: `fetch_results.fetch_results()`
  previously rebuilt `wc2026_results.json` entirely from live sources on every run with no
  historical memory. When worldcup26.ir (the only source with full match history) was
  unreachable, all matches older than yesterday were silently wiped. Observed live on
  2026-06-16: 5 CI runs wrote only 4 matches, losing all 12 June 11–14 results. Fixed by
  seeding from the existing `wc2026_results.json` before merging live sources — the file now
  only grows, never shrinks. Live sources still enrich existing records with group/round/date
  corrections when available.
- **ELO duplicate key fix (2026-06-16)**: `update_elo_from_results()` built `wc_applied_keys`
  dedup keys from `m['date']` (scraper-reported date) which shifted between pipeline runs as
  different sources reported different dates (Sky Sports always stamps today, worldcup26.ir uses
  local COT time). When the date shifted, the old key stayed and the new date passed the dedup
  check, applying ELO a second time. Affected 5 matches and 10 teams (USA, Paraguay, Australia,
  Türkiye, Haiti, Scotland, Ivory Coast, Ecuador, Sweden, Tunisia). Fixed by anchoring the key
  to `fixtures.json` canonical COT dates via a `frozenset({team1, team2})` lookup — keys are
  now immutable regardless of scraper date. One-time reset script `reset_elo_duplicates.py`
  (completed 2026-06-16, do not re-run) restored correct single-application ELO/RD for all
  10 teams using git-history pre-match baselines.

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
  (`xi_confirmed = src in ("rotowire", "api-football") and (len(home_xi) >= 5
  or len(away_xi) >= 5)`).
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

- **June 18 (Session 4)**: three-model ensemble — Dixon-Coles + Negative
  Binomial + Bivariate Poisson, combined with adaptive Brier-score weights.
  Requires **8+ real match results** with clean ELO inputs (C1 fixed
  2026-06-12). Pre-session stabilization completed 2026-06-12: C1 ELO dedup
  fix, H1/H2 Telegram fixes, H5/H6 `generate_index.py` hardening, H8 full
  dependency pinning including `optuna==4.9.0`. Environment is stable and
  ready for Session 4. Pre-Session 4 checklist must include an end-to-end
  data flow audit: for every file written by the pipeline
  (`fetch_results.py`, `run_predictions.py`, `generate_index.py`,
  `update_results.py`), confirm at least one downstream reader consumes it.
  The `match_adjustments.json` dead-end (written by `_detect_key_absences()`
  in `fetch_results.py`, never read by `generate_index.py` or
  `run_predictions.py`) was discovered live on 2026-06-15 when Lamine
  Yamal's absence was correctly detected and lambda-adjusted in memory but
  the adjustment never reached the dashboard predicted score or win
  probability. This class of silent dead-end data flows is not detectable
  by static code audit without explicit write-to-reader tracing. Related
  training code lives in `model/` (`train.py`, `pipelines.py`,
  `expanded_model.pkl`).
- **Session 4 known inconsistency to address**: predicted score and win
  probability can contradict each other on match cards. Example observed
  2026-06-12: USA vs Paraguay showed predicted score USA 2-1 Paraguay
  (favoring USA) while win probability showed Paraguay 70% (favoring
  Paraguay). Two compounding causes: (1) for group-stage cards, the
  predicted score is computed live in `generate_index.py` via
  `_strength_lambdas()` + `_most_probable_score()` from the *current*
  `team_strength.json`, while the win probability comes from
  `predictions.json["match_probabilities"]` (Skellam), a snapshot frozen
  at the last `run_predictions.py` (step 3) run — for USA/Paraguay these
  two snapshots disagree almost completely (live lambdas favor USA 1.80
  vs 1.25; stored lambdas favor Paraguay 2.42 vs 0.93), i.e.
  `predictions.json` was stale relative to `team_strength.json`. (2) Even
  with one consistent snapshot, argmax-of-independent-Poissons (predicted
  score) and a Skellam win/draw/loss split are different statistics of the
  same distribution and can disagree near 50/50 splits — this also applies
  to knockout cards, where `run_predictions.py`'s
  `_poisson_most_probable_score()` (Dixon-Coles + random sampling + 1-1
  override) plays the analogous role. Session 4 should: (a) ensure
  `team_strength.json` and `predictions.json` are always regenerated
  together in the same pipeline run (eliminates cause 1), and (b) derive
  the displayed predicted score from the same Skellam/simulation
  distribution used for win probability, or (c) add a UI note that the two
  metrics are independent (mitigates cause 2). (b) is preferred for
  architectural consistency.

## 10. WORKING AGREEMENT

- Always **show proposed code before writing any file** and wait for approval.
- Never run `update_results.py` casually — it makes live network calls and
  takes ~10–15 minutes (full Monte Carlo simulation).
- After display/HTML changes, verify with `python3 generate_index.py`.
- Commit messages: short and descriptive.
- Owner prefers step-by-step confirmation over large unreviewed batches.
