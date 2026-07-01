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
- **Match statistics pipeline and form modifier (2026-06-16)**: added `fetch_match_stats()` to
  `fetch_results.py` as step 1b in the pipeline. Fetches per-match stats from ESPN summary API
  (`shotsOnTarget`, `totalShots`, `possessionPct`, `passPct`, `wonCorners`, `saves`,
  `foulsCommitted`, `yellowCards`, `redCards`) for all completed WC matches. Implements
  seed-and-complement pattern so `match_stats.json` only grows, never shrinks. D+1 fallback
  handles late-night COT matches that cross the UTC date boundary (e.g. Australia vs Türkiye,
  Iran vs New Zealand). Form modifiers applied in `_strength_lambdas()` via `_form_modifiers()`
  in `generate_index.py`: exponential decay weighting (most recent match = 1.0, each older =
  0.5x) on shots on target for and against, normalized against tournament average SOT. `atk_mod`
  and `def_mod` both clamped to `[0.85, 1.15]`. Applied as:
  `lam1 = lam1 * atk_mod(team1) * def_mod(team2)`. Teams with no completed matches default to
  neutral `(1.0, 1.0)`. `match_stats.json` added to CI FILES variable so it persists across runs.
- **Sky Sports pre-match false positive guard (2026-06-16)**: `_parse_skysports_wc()` matched any
  aria-label fitting the score regex with no completion status check. Pre-match fixtures render as
  `TeamA 0 - TeamB 0` on the Sky Sports page, which the regex accepted as completed results.
  Observed live: France vs Senegal ingested as 0-0 before kickoff, corrupting ELO for both teams.
  Fixed by loading `fixtures.json` once per function call and rejecting any match where
  `datetime.now(UTC) < kickoff_utc + 110 minutes`. Graceful degradation: if `fixtures.json`
  fails to load, the guard is skipped and the function behaves as before. Knockout placeholders
  not yet in fixtures are also rejected via `ko_utc is None` check.
- **Kickoff time guard extended to all three fetch sources (2026-06-16)**:
  `worldcup26.ir` and ESPN both ingested France vs Senegal as a completed 0-0
  result while the match was still live (`worldcup26.ir` set `finished=TRUE`
  prematurely; ESPN `STATUS_FULL_TIME` fired incorrectly). The
  `fixtures.json` kickoff UTC + 110 minute guard already applied to Sky Sports
  on the same day was extended to `parse_worldcup26ir()` and
  `_fetch_espn_wc_api()`. All three sources now reject any match where
  `datetime.now(UTC) < kickoff_utc + 110 minutes` regardless of their own
  completion status field. Graceful degradation: if `fixtures.json` fails to
  load the guard is skipped and each source behaves as before.
- **Score merge priority fix (2026-06-16)**: `_merge_wc_results()` gave
  priority to whichever source reported a match first. `worldcup26.ir`
  reported France vs Senegal as 0-0 (`finished=TRUE` prematurely) and won
  the merge race over ESPN's correct 3-1. Fixed by adding a score overwrite
  rule: if the existing merged record has `home_score==0` and `away_score==0`
  and an incoming source reports a non-zero score, the non-zero score
  overwrites the 0-0. Genuine 0-0 results are safe since all sources agree
  and no overwrite triggers.
- **Form modifier null-stats fix (2026-06-17)**: `_form_modifiers()` used
  `.get('shotsOnTarget') or 0`, which coerced missing data (`None`, e.g.
  from a failed ESPN fetch) into a genuine zero, incorrectly penalizing a
  team's attacking and defensive modifiers to the 0.85 floor even when they
  had no usable stats. Observed for France/Senegal, whose `match_stats.json`
  entry had all-null fields. Fixed by skipping any match record where
  `shotsOnTarget` is `None` for either team, rather than treating it as
  zero — such teams now correctly fall through to the neutral `(1.0, 1.0)`
  default when they have no valid stats data.
- **Stateless WC ELO recomputation (2026-06-17)**: The incremental
  `wc_applied_keys` approach in `update_elo_from_results()` was structurally
  vulnerable to CI race conditions — an in-flight pipeline run that checked
  out stale data before a fix landed would faithfully push its stale output
  on top of the fix via the fetch-reset-overwrite pattern, silently reverting
  corrections. This happened three times in one day to the same 10-team ELO
  double-application bug. Replaced entirely with
  `recompute_wc_elo_from_scratch()`: every pipeline run now recomputes every
  WC team's ELO and RD from a frozen pre-tournament baseline
  (`wc_elo_baseline.json`, extracted once from commit `a0fb45d`, never
  modified afterward) by replaying all completed WC matches in chronological
  order (using `fixtures.json` canonical dates) with the same
  K=40\*decay\_weight and Glicko-1 formulas as before. `wc_applied_keys` is
  retired entirely for the WC bracket — there is nothing left to corrupt via
  a race, since the output is a pure function of `wc2026_results.json` plus
  the frozen baseline. Verified idempotent: running twice in a row with no
  new matches produces identical output. The daily-friendly ELO system
  (step0) remains architecturally separate and untouched. Also corrected:
  Iraq vs Norway score (was intermittently fetched as 1-3 from a mid-match
  ESPN snapshot; confirmed 1-4 final via ESPN/FIFA/Sky Sports/FOX Sports).
  ELO unaffected by this correction since both scores represent an Iraq loss.
- **Knockout stage business rules (2026-06-17, decided ahead of Session 4)**:
  Two rules established for handling extra time and penalty shootouts, not yet
  implemented since no knockout match has been played:
  **(1) ELO scoring** — the score stored in `wc2026_results.json` for a knockout
  match should be the full final result including extra time goals when
  applicable (e.g. a 1-1 after 90 that becomes 2-1 after extra time is stored
  as 2-1 and treated as a normal win/loss by
  `recompute_wc_elo_from_scratch()`, no special handling needed). Only when a
  match remains level after extra time and is decided by a penalty shootout
  does a special rule apply: the shootout winner is recorded as the match
  winner (`actual=1.0`) and the loser as `actual=0.0`, the same as a
  regulation win — a shootout win is treated as a full win for ELO purposes,
  not a half-credit draw, since advancing carries real momentum and
  psychological value into the next round regardless of the coin-flip nature
  of penalties. No K-factor damping was added for shootout-decided results;
  this was discussed and deliberately deferred as a possible future refinement
  if observed to matter in practice.
  **(2) Match stats and the form modifier** — ESPN's match stats for matches
  that go to extra time are expected to report cumulative 120-minute totals
  rather than 90-minute regulation-only stats (not yet explicitly verified
  against a real extra-time match). No per-90-minute normalization will be
  applied to `shotsOnTarget` before it feeds `_form_modifiers()` — extra-time
  matches are expected to be infrequent (roughly 3-5 of 16 round-of-32
  matches based on typical knockout rates) and the inflation in shot volume
  from 30 extra minutes is expected to be modest, well within the existing
  `[0.85, 1.15]` modifier clamp. This is a deliberate simplification, not an
  oversight — revisit only if a specific team's modifier looks unrealistically
  inflated after a genuine extra-time match is observed in `match_stats.json`.
- **model_accuracy.json duplicate key fix (2026-06-18)**:
  `score_prediction_accuracy()` built dedup keys from the scraper-reported
  `match_date`, the same date-shift vulnerability already fixed for
  `wc_applied_keys` and ELO. Found 10 stale duplicate entries (34 total, 24
  real matches) using the same +1-day shifted dates. Cleaned to 24 canonical
  entries; `mean_brier` and `mean_rps` corrected from 0.778/0.206 (artificially
  flattered by duplicates) to the honest 0.833/0.225. Fixed root cause by
  anchoring both the dedup key and the stored date field to fixtures.json
  canonical dates via `frozenset({home, away})` lookup, mirroring the existing
  pattern in `recompute_wc_elo_from_scratch()`. No downstream consumers of this
  file exist (confirmed: not read by `generate_index.py`, `run_predictions.py`,
  or `notify_telegram.py`), so this was a zero-risk cleanup.
- **Seed score-pinning bug (2026-06-21)**: the seed-and-complement pattern
  (2026-06-16, built to prevent history loss on source outages) had no
  mechanism to correct a stale non-zero score once written — the existing 0-0
  overwrite rule only handled the placeholder-score case. Germany 1-1 Ivory
  Coast was ingested as a stale in-progress score (real final: 2-1, Undav 68'
  and 90+4', Kessié 30') and was silently re-pinned on every subsequent run
  because, although both ESPN and worldcup26.ir independently agreed on 2-1,
  the seed's incorrect 1-1 always won the merge regardless. Confirmed isolated
  to this one match (35 others cross-checked clean against worldcup26.ir's full
  history). Fixed by replacing the 0-0-only rule with a general Option-B rule in
  `_merge_wc_results()`: past kickoff+110min (canonical fixtures.json time), if
  every live source responding in the current run unanimously agrees on a score
  differing from the seed, the live score overwrites; disagreement or an
  unsettled match keeps the seed unchanged (conservative default, avoids
  re-introducing the mid-match-snapshot false positives fixed on
  2026-06-16/17). The function signature changed to
  `_merge_wc_results(seed_matches, live_batches)` to separate the
  history-preserving seed from the live sources that may correct it. This is the
  4th distinct score-ingestion incident this tournament (France/Senegal and
  Iraq/Norway were live-source mid-match snapshots; this one was the seed itself
  permanently pinning a stale value with no self-correction path).
- **RC-1 knockout ingestion fix (2026-07-01)**: The fetch completion guard (all 3
  sources) keyed the anti-mid-match-snapshot gate on team-pair lookups in
  fixtures.json, which only stores placeholder names for knockout fixtures
  ('2ND GROUP A', '3RD PLACE (POOL)') — so every real knockout pair failed the
  lookup and was silently dropped. Zero knockout results entered
  wc2026_results.json from June 28 onward, leaving ELO, bracket advancement, and
  predictions all running on stale group-stage-only data. Fixed by adding a
  knockout branch to all three parsers that resolves fixtures by match_num
  instead of team-pair (worldcup26.ir's native id field maps 1:1 to match_num;
  ESPN uses a pair-based lookup built from worldcup26.ir's same-run results —
  exact and schedule-discrepancy-proof), then applies the identical
  canonical-kickoff + 110-min anti-snapshot gate. Sky Sports excluded from
  knockout ingestion (cannot resolve match_num or detect penalties). Also added:
  optional 'shootout': {winner, home_score, away_score} schema on
  penalty-decided matches per the locked design (§7: shootout winner gets
  actual=1.0 for ELO, stored 120-min score kept as-is for accuracy tracking per
  §2); match_num field on knockout records to anchor the Option-B
  self-correction gate (extends the Germany-incident fix to knockout stage);
  'Democratic Republic of the Congo': 'Congo DR' added to FRIENDLY_NAME_MAP.
  Dry-run verified: 7 knockout results ingested correctly including both
  shootouts (Germany-Paraguay, Netherlands-Morocco) with correct winners, group
  records untouched, ELO idempotent, override confirmed via explicit
  draw-vs-win delta comparison.

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

### PRE-DEPARTURE CHECK-IN PLAN (target: 2026-06-24 or 2026-06-25, before Diego's absence 2026-06-26 through 2026-07-01, covering group stage matchday 3 and Round of 32 kickoff 2026-06-28)

Target date: June 24-25, 2026 (before Diego departs June 26 - July 1, covering group stage matchday 3 and Round of 32 kickoff June 28)

GOAL: One final, decisive go/no-go session on the form-field expansion (SOT+totalShots+possessionPct) and the ensemble engine, using whatever real data exists by then. No new analysis design, no new hyperparameters, no new ideas — just running what already exists (backtest_ensemble.py, backtest_form_fields.py) against the larger dataset and applying these pre-agreed criteria.

═══════════════════════════════════════════
DECISION 1 — Form-field expansion (SOT-only vs SOT+totalShots+possessionPct)
═══════════════════════════════════════════

Re-run backtest_form_fields.py with whatever LOO-active match count exists by June 24-25 (expected ~24+ if matchday 2 completed everywhere by then, possibly more if some groups reach matchday 3 early).

GO criteria (all three must hold):
1. 3-field beats SOT-only on BOTH Brier and RPS across the full match set (not just active matches).
2. The improvement is NOT carried entirely by blowout/lopsided-score matches. Specifically: manually inspect the LOO-active per-match table and confirm at least one close match (decided by 1 goal or a draw) also favors the 3-field arm, not only landslide wins.
3. At least 12 LOO-active matches exist (the original ~matchday-2-everywhere threshold). Fewer than that, the result is still too thin to trust regardless of direction.

NO-GO (default): if any criterion fails, keep SOT-only in production. Do not deploy on a "probably fine" read — the cost of an unvalidated change going live during Diego's absence outweighs the upside of a marginal improvement.

If GO: implement via the same show-before-implement process as every other change this week (propose code, review, compile check, sanity test, commit while automations briefly paused, verify on origin/main, re-enable automations). This must happen IN this same June 24-25 session, not deferred — no partial deployments left mid-flight before a 5-day absence.

═══════════════════════════════════════════
DECISION 2 — Three-model ensemble (DC + NegBin + BivPois vs current Skellam)
═══════════════════════════════════════════

Re-run backtest_ensemble.py with the same updated dataset.

GO criteria (both must hold):
1. Ensemble beats baseline Skellam on BOTH Brier and RPS, using whichever form-modifier decision was just made in Decision 1 (SOT-only or 3-field, whichever is now in production).
2. loo_active is high enough that the result isn't dominated by the ~40% of matches still on matchday 1 with neutral modifiers (use judgment here — if most matches are still neutral, the ensemble has little room to differentiate and a wash is expected regardless of true merit).

NO-GO (default): keep current Skellam-only path. Same reasoning as Decision 1 — do not deploy unvalidated.

═══════════════════════════════════════════
DECISION 3 — Departure readiness check (regardless of Decisions 1 & 2 outcomes)
═══════════════════════════════════════════

Before Diego leaves, confirm explicitly:
1. GitHub Actions schedule is ENABLED and running normally (not left paused from any prior debugging session).
2. cron-job.org external backup is ENABLED.
3. No uncommitted local changes sitting on disk unpushed — origin/main reflects the true final state.
4. CLAUDE.md is fully up to date with whatever was decided in Decisions 1 and 2, so if Diego or anyone else opens a session during the trip, the documentation explains the current state without needing this conversation's context.
5. Quick sanity check: trigger one manual pipeline run, confirm Step 1 and Step 2 output look normal (matches fetched, ELO recomputed cleanly, no errors), same verification pattern used throughout this week.

If anything in Decision 3 fails, fix it before ending the session — this is the actual safety net for the 5-day unattended period, independent of which model is running underneath it.

---

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
- **Matchday-2 form-modifier expansion** (target: once every team has played
  2 group matches, expected around June 19-20): once real prior-match data
  exists for every team, re-run a leave-one-out backtest to evaluate whether
  totalShots and/or possessionPct improve prediction accuracy beyond the
  current shotsOnTarget-only form modifier. Per the 2026-06-18 field analysis,
  these were the two least-bad candidates among the 9 match_stats.json fields
  (totalShots r=0.182, possessionPct r=0.214, same-match correlation with
  goals, n=40 — below the n=40 significance threshold of |r|≈0.31, but the
  only data available at single-match depth). Only incorporate a field if it
  beats the SOT-only baseline on real held-out LOO data; do not add fields on
  a forward-looking promise the way it was deferred today. The standalone
  ensemble engine (`ensemble.py`) and prequential LOO harness
  (`backtest_ensemble.py`) built 2026-06-18 are ready to re-run for this — note
  the 2026-06-18 three-model ensemble (DC + NegBinom + Bivariate Poisson,
  adaptive Brier weights) backtested as a statistical wash vs the production
  Skellam baseline (mean Brier 0.6592 vs 0.6590, RPS tied) precisely because
  LOO neutralized all form inputs on matchday-1 data, and was therefore not
  wired live.
- **Form-field LOO comparison, first result (2026-06-19)**:
  `backtest_form_fields.py` tested SOT-only vs
  SOT+totalShots+possessionPct (averaged, each individually clamped
  [0.85,1.15]) on the 4 matches where LOO-active prior data existed
  (Czechia-South Africa, Switzerland-Bosnia, Canada-Qatar,
  Mexico-South Korea). Result: 3-field edges out SOT-only on both
  Brier (0.5997→0.5967) and RPS (0.1690→0.1676) across all 28
  matches, but 3 of 4 active matches drove the gain and all 3 were
  blowout wins by the stronger team (Switzerland 4-1, Canada 6-0,
  Mexico 1-0 vs a weakened South Korea) — exactly the cases where the
  strength confound flagged on 2026-06-19 applies most directly.
  Czechia vs South Africa (a 1-1 draw, no blowout) moved the other
  way (+0.0192 worse). With n=4 active matches, structurally 2-4
  independent units once the coupled-pair issue is accounted for, this
  is a genuine first signal but indistinguishable from 'the modifier
  is just re-encoding team strength ELO already knows' rather than
  capturing real form deviation. Combination methodology caveat from
  the same date still applies: averaging may dilute SOT's stronger
  signal with two noisier ones, so a negative OR a positive result at
  this sample size should not be over-read in either direction.
  Re-check trigger: re-run once every team has completed matchday 2
  (~12 LOO-active matches instead of 4). Only draft a production
  change if the 3-field delta survives at that depth and is not
  carried entirely by blowout/strength-confounded matches — a single
  upset or close result could flip or erase today's directional
  result entirely.
- **Form-field and ensemble progress check (2026-06-20)**: re-ran both backtests
  with 33 matches (up from 28) and 9 LOO-active matches (up from 4 on June 19,
  18 teams now have 2+ matches). Ensemble (DC+NB+BVP): still NO-GO, third
  consecutive wash across June 18/19/20 — Brier 0.5735→0.5738, RPS
  0.1727→0.1728 (both marginally worse), weights stayed near-uniform (DC=0.331,
  NB=0.334, BVP=0.334) all three times. This is now a stable pattern, not
  noise — the ensemble shows no sign of differentiating from baseline Skellam at
  current data depth. Form-field (SOT-only vs SOT+totalShots+possessionPct):
  NO-GO but trending positive — passes Criterion 1 (beats SOT-only on both
  Brier 0.5735→0.5649 and RPS 0.1727→0.1687) and partially passes Criterion 2
  (close matches split 2-2 rather than being swept by blowouts; notably Scotland
  0-1 Morocco, a non-blowout away win, favors the 3-field arm with a large
  Brier improvement 0.5901→0.3495 — the first close-match result that doesn't
  look like pure strength-confound). Still fails Criterion 3 (9 of 12 required
  LOO-active matches). Expected to clear 12 by ~June 21-22 per the fixture
  schedule, meaning the June 24-25 pre-departure check-in should have a
  genuinely decisive sample rather than being borderline. This is the most
  credible signal yet for the 3-field expansion — worth prioritizing in the
  June 24-25 session even if the ensemble result stays negative.
- **Form-field and ensemble progress check, first criteria pass (2026-06-21)**:
  re-ran both backtests with 36 matches and 12 LOO-active matches (up from 9 on
  June 20, all 24 teams with 2+ matches counted). Ensemble (DC+NB+BVP): 4th
  consecutive wash (June 18/19/20/21) — Brier 0.5795 vs 0.5795 (tied), RPS
  0.1738 vs 0.1739 (marginally worse), weights stayed near-uniform a 4th time.
  This is now a settled, stable pattern — the ensemble shows no sign of
  differentiating from baseline Skellam at any data depth reached so far.
  Expectation for June 24-25 is this stays NO-GO. Form-field (SOT-only vs
  SOT+totalShots+possessionPct): all three pre-agreed criteria pass for the first
  time — Criterion 1 (beats SOT-only on both Brier 0.5795→0.5746 and RPS
  0.1738→0.1712), Criterion 3 (12 of 12 required LOO-active matches), and
  Criterion 2 (close/1-goal/draw matches are 3-3, not swept by blowouts —
  satisfies "at least one close match favors 3-field"). IMPORTANT CAVEAT — do not
  treat this as a clean GO: the result is significantly carried by one outlier,
  Scotland 0-1 Morocco (Brier 0.5901→0.3495, a −0.2406 improvement, by far the
  largest single delta of any match). Excluding this one match, the remaining 5
  close matches roughly cancel out (2 favor 3-field modestly, 3 favor SOT-only,
  including Czechia-South Africa, Türkiye-Paraguay, and Ecuador-Curaçao all going
  the other way). The criteria were met honestly per the pre-agreed numeric
  thresholds, but the underlying signal should be considered fragile, not yet a
  confident GO. Required before deployment: re-run at the June 24-25 check-in
  with the larger expected sample (~18+ LOO-active matches). If the advantage
  holds or strengthens once diluted by more data, that's a credible deploy. If it
  collapses back toward parity once Scotland-Morocco's weight is diluted by more
  matches, the honest call is NO-GO despite today's technical pass — do not deploy
  on outlier-driven signal just because a numeric threshold was crossed.
- **Single-match sensitivity check added to backtest_form_fields.py
  (2026-06-22)**: every run now automatically reports a
  leave-one-active-match-out sensitivity analysis at the end of the output —
  for each LOO-active match, it recomputes the whole-set Brier/RPS delta with
  that one match's contribution removed, and flags FRAGILE if removing any
  single match flips the sign of either metric (meaning the result depends
  entirely on that one match), or STABLE if the sign survives every
  single-match removal. Built specifically because the June 21/22 form-field
  "pass" was driven almost entirely by one match (Scotland-Morocco) and this
  wasn't caught by the original 3 numeric criteria — this check makes that kind
  of fragility visible automatically in every future report, no manual digging
  required. At time of writing (June 22), the form-field result is correctly
  flagged FRAGILE (both Brier and RPS sign-flip on Scotland-Morocco's removal),
  meaning despite passing the original 3 criteria, the honest current verdict is
  NO-GO. Future GO decisions for this feature should require STABLE, not just a
  passing aggregate delta.
- **Pre-departure check-in, both decisions NO-GO (2026-06-25)**: ran the
  June 24-25 §9 pre-departure go/no-go on 54 matches (30 LOO-active, up from
  12 on June 21). DECISION 1 (form-field SOT-only vs
  SOT+totalShots+possessionPct): **NO-GO**. All 3 numeric criteria technically
  pass, but the aggregate advantage *collapsed* from +0.0049 Brier on June 21
  to +0.0004 Brier / +0.0004 RPS now, and the single-match sensitivity check
  still reports **FRAGILE** — Scotland-Morocco remains the sole load-bearing
  match (dropping it flips the whole-set Brier delta to −0.0041, i.e. SOT-only
  wins). The added matchday-2/3 data did not dilute Scotland-Morocco's
  dominance; it shrank the aggregate to near-zero while leaving the sign
  dependent on that one match. Per the 2026-06-22 rule (GO requires STABLE, not
  just passing numeric criteria), the honest verdict is NO-GO — the signal is
  weaker and more clearly outlier-driven than on June 21, not stronger.
  DECISION 2 (ensemble DC+NB+BVP vs Skellam): **NO-GO**, 6th consecutive wash
  (June 18/19/20/21/25) — Brier 0.5201 vs 0.5203, RPS 0.1580 vs 0.1582 (both
  marginally worse), weights still near-uniform (dc=0.331, nb=0.334,
  bvp=0.334). Settled pattern; no differentiation at any data depth reached.
  Production stays Skellam + SOT-only form modifier — nothing wired live.
  DECISION 3 (departure readiness): **GREEN**. Automation healthy (clean
  auto-commits every ~15-30 min through 15:31 UTC), working tree clean
  (no production files dirty), local == origin/main. Manual pipeline sanity
  check run as Steps 0-2 in an isolated copy (zero production impact): all 3
  WC sources used, 54 matches, stateless ELO recompute replayed 54 matches /
  48 teams with **0 teams differing from the committed elo_ratings.json**
  (deterministic, no drift). Two items left for Diego to eyeball before
  departure: confirm cron-job.org backup is enabled on its dashboard, and
  optionally fire one production workflow_dispatch from his phone via
  MANUAL_TRIGGER.md (local `gh` CLI is not installed).

## 10. WORKING AGREEMENT

- Every Claude Code response must begin with 'Diego:' as the first word. This
  is a self-control convention to confirm context is loaded correctly.
- Always **show proposed code before writing any file** and wait for approval.
- Never run `update_results.py` casually — it makes live network calls and
  takes ~10–15 minutes (full Monte Carlo simulation).
- After display/HTML changes, verify with `python3 generate_index.py`.
- Commit messages: short and descriptive.
- Owner prefers step-by-step confirmation over large unreviewed batches.
- GitHub Actions schedule and the external cron job should be paused before
  pushing any fix to `elo_ratings.json`, `wc2026_results.json`, or any file
  in the `auto_update.yml` `FILES` list, when a clean uncontested push is
  required. Re-enable only after confirming `origin/main` matches the
  expected state.
