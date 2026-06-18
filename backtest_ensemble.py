"""Prequential leave-one-out backtest: production Skellam baseline vs the
three-model adaptive ensemble, on the 21 completed WC matches.

Read-only. Touches no pipeline state, writes no files — prints a side-by-side
report. Run: python3 backtest_ensemble.py
"""
import json
from collections import defaultdict
from pathlib import Path

from scipy.stats import skellam as sp_skellam

import ensemble as ens

ROOT = Path(__file__).parent.resolve()


def _load(name):
    with open(ROOT / name) as f:
        return json.load(f)


def brier_rps(p_win, p_draw, p_loss, hs, as_):
    """Exact Brier and RPS definitions from fetch_results.py:734-737."""
    aw = 1.0 if hs > as_ else 0.0
    ad = 1.0 if hs == as_ else 0.0
    al = 1.0 if hs < as_ else 0.0
    brier = (p_win - aw) ** 2 + (p_draw - ad) ** 2 + (p_loss - al) ** 2
    cum_p = [p_win, p_win + p_draw]
    cum_a = [aw, aw + ad]
    rps = 0.5 * sum((cum_p[i] - cum_a[i]) ** 2 for i in range(2))
    return brier, rps


def skellam_wdl(lh, la):
    """Production baseline w/d/l (run_predictions.py:429-437)."""
    sk = sp_skellam(mu1=lh, mu2=la)
    return float(1 - sk.cdf(0)), float(sk.pmf(0)), float(sk.cdf(-1))


def main():
    results   = _load("wc2026_results.json")
    fixtures  = _load("fixtures.json")
    strength  = _load("team_strength.json")
    stats     = _load("match_stats.json")

    # canonical kickoff date per matchup (immutable, from fixtures.json)
    canon = {}
    for fx in fixtures:
        if fx.get("home") and fx.get("away"):
            canon[frozenset([fx["home"], fx["away"]])] = fx.get("date")

    # match_stats indexed by matchup for the LOO form hook
    stats_by_pair = defaultdict(list)
    for e in stats:
        stats_by_pair[frozenset([e["team1"], e["team2"]])].append(e)

    # build chronological match list, canonical date first
    matches = []
    for r in results:
        pair = frozenset([r["team1"], r["team2"]])
        dt = canon.get(pair) or r.get("date")
        matches.append((dt, r["team1"], r["team2"], r["home_score"], r["away_score"]))
    matches.sort(key=lambda m: m[0])

    def loo_form_mod(team, before_date):
        """Strict LOO form modifier: ONLY match_stats strictly before before_date.
        Returns (atk_mod, def_mod) clamped [0.85, 1.15]; neutral if no prior data.
        Mirrors generate_index._form_modifiers but date-gated."""
        recs = []
        all_sot = []
        for entries in stats_by_pair.values():
            for e in entries:
                ed = canon.get(frozenset([e["team1"], e["team2"]])) or e.get("date")
                if not ed or ed >= before_date:
                    continue
                s1, s2 = e["team1_stats"], e["team2_stats"]
                for v in (s1.get("shotsOnTarget"), s2.get("shotsOnTarget")):
                    if v is not None:
                        all_sot.append(v)
                if e["team1"] == team:
                    sf, sa = s1.get("shotsOnTarget"), s2.get("shotsOnTarget")
                    if sf is not None and sa is not None: recs.append((ed, sf, sa))
                elif e["team2"] == team:
                    sf, sa = s2.get("shotsOnTarget"), s1.get("shotsOnTarget")
                    if sf is not None and sa is not None: recs.append((ed, sf, sa))
        if not recs or not all_sot or sum(all_sot) == 0:
            return 1.0, 1.0
        recs.sort(key=lambda r: r[0])
        n = len(recs)
        w = [0.5 ** (n - 1 - i) for i in range(n)]
        ws = sum(w)
        sot_for = sum(wi * r[1] for wi, r in zip(w, recs)) / ws
        sot_ag  = sum(wi * r[2] for wi, r in zip(w, recs)) / ws
        avg = sum(all_sot) / len(all_sot)
        atk = max(0.85, min(1.15, sot_for / avg))
        dfn = max(0.85, min(1.15, sot_ag  / avg))
        return atk, dfn

    # prequential loop, weights batched by date
    weights = {m: 1.0 for m in ens.COMPONENTS}     # equal start
    cum_brier = {m: 0.0 for m in ens.COMPONENTS}   # per-component, strictly-earlier only
    n_scored = 0

    base_b, base_r, ens_b, ens_r = [], [], [], []
    rows = []
    loo_active = 0
    pending = defaultdict(lambda: {m: 0.0 for m in ens.COMPONENTS})  # date -> component brier
    pending_n = defaultdict(int)
    last_date = None

    for dt, t1, t2, hs, as_ in matches:
        # fold in all matches from strictly-earlier dates before predicting this one
        if last_date is not None and dt != last_date:
            for d in [x for x in pending if x <= last_date]:
                for m in ens.COMPONENTS:
                    cum_brier[m] += pending[d][m]
                n_scored += pending_n[d]
                del pending[d]; del pending_n[d]
            if n_scored > 0:
                inv = {m: 1.0 / (cum_brier[m] / n_scored) for m in ens.COMPONENTS}
                weights = inv
        last_date = dt

        s1 = strength.get(t1, {}).get("final_strength", 1600.0)
        s2 = strength.get(t2, {}).get("final_strength", 1600.0)
        lh, la = ens.strength_lambdas(s1, s2)

        # LOO form modifier (neutral for all 21 on current data — proves discipline)
        atk1, def1 = loo_form_mod(t1, dt)
        atk2, def2 = loo_form_mod(t2, dt)
        if (atk1, def1, atk2, def2) != (1.0, 1.0, 1.0, 1.0):
            loo_active += 1
        lh = max(0.3, min(3.5, lh * atk1 * def2))
        la = max(0.3, min(3.5, la * atk2 * def1))

        # baseline (production Skellam)
        bw, bd, bl = skellam_wdl(lh, la)
        bb, br = brier_rps(bw, bd, bl, hs, as_)
        base_b.append(bb); base_r.append(br)

        # ensemble (current adaptive weights)
        ew, ed_, el = ens.ensemble_probs(lh, la, weights)
        eb, er = brier_rps(ew, ed_, el, hs, as_)
        ens_b.append(eb); ens_r.append(er)

        # accumulate this match's per-component Brier for FUTURE weight updates
        comp = ens.component_probs(lh, la)
        for m in ens.COMPONENTS:
            cb, _ = brier_rps(*comp[m], hs, as_)
            pending[dt][m] += cb
        pending_n[dt] += 1

        rows.append((dt, t1, t2, f"{hs}-{as_}", bb, eb, br, er))

    # ── report ────────────────────────────────────────────────────────────────
    def mean(x): return sum(x) / len(x)
    print(f"\nBacktest set: {len(matches)} matches | LOO form-modifier non-neutral: {loo_active}\n")
    print(f"{'date':11s} {'match':28s} {'res':5s} {'BS_base':>8s} {'BS_ens':>8s} {'RPS_base':>9s} {'RPS_ens':>9s}")
    for dt, t1, t2, res, bb, eb, br, er in rows:
        print(f"{dt:11s} {t1[:13]+' v '+t2[:11]:28s} {res:5s} {bb:8.4f} {eb:8.4f} {br:9.4f} {er:9.4f}")
    print("-" * 90)
    print(f"{'MEAN':11s} {'':28s} {'':5s} {mean(base_b):8.4f} {mean(ens_b):8.4f} {mean(base_r):9.4f} {mean(ens_r):9.4f}")
    print(f"\nBaseline (production Skellam):  mean Brier={mean(base_b):.4f}  mean RPS={mean(base_r):.4f}")
    print(f"Adaptive ensemble (DC+NB+BVP):  mean Brier={mean(ens_b):.4f}  mean RPS={mean(ens_r):.4f}")
    db = mean(base_b) - mean(ens_b)
    dr = mean(base_r) - mean(ens_r)
    print(f"\nDelta (positive = ensemble better):  Brier {db:+.4f}   RPS {dr:+.4f}")
    print(f"Final adaptive weights: " +
          ", ".join(f"{m}={weights[m]/sum(weights.values()):.3f}" for m in ens.COMPONENTS))
    print("\nVERDICT:", "ensemble >= baseline on both metrics — eligible to wire live"
          if db >= 0 and dr >= 0 else
          "ensemble does NOT beat baseline — DO NOT wire live")


if __name__ == "__main__":
    main()
