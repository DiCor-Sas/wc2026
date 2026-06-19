"""LOO form-FIELD comparison: SOT-only (current production modifier) vs
SOT + totalShots + possessionPct (the two matchday-2 survivors).

Standalone, read-only — a sibling of backtest_ensemble.py. Touches NO
production file and does NOT import or alter _form_modifiers(). It reimplements
the strict-LOO modifier locally (byte-identical to backtest_ensemble.py for the
SOT-only arm) and adds a generalized multi-field version. The two arms run the
same prequential loop and differ ONLY in which stat fields feed the form
modifier, so any Brier/RPS gap is attributable to the added fields alone.

Run: python3 backtest_form_fields.py
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


def field_form_mod(team, before_date, field, stats_by_pair, canon):
    """Strict-LOO single-field form modifier. ONLY match_stats strictly before
    before_date feed it. For field='shotsOnTarget' this is byte-identical to
    loo_form_mod() in backtest_ensemble.py. Returns (atk, def) clamped
    [0.85,1.15]; neutral (1.0,1.0) when the team has no usable prior data.

    Null-safe per the 2026-06-17 fix: a record is skipped unless BOTH sides
    have a non-None value for `field` (mirrors the _form_modifiers guard)."""
    recs = []
    pool = []
    for entries in stats_by_pair.values():
        for e in entries:
            ed = canon.get(frozenset([e["team1"], e["team2"]])) or e.get("date")
            if not ed or ed >= before_date:
                continue
            s1, s2 = e["team1_stats"], e["team2_stats"]
            for v in (s1.get(field), s2.get(field)):
                if v is not None:
                    pool.append(v)
            if e["team1"] == team:
                sf, sa = s1.get(field), s2.get(field)
                if sf is not None and sa is not None: recs.append((ed, sf, sa))
            elif e["team2"] == team:
                sf, sa = s2.get(field), s1.get(field)
                if sf is not None and sa is not None: recs.append((ed, sf, sa))
    if not recs or not pool or sum(pool) == 0:
        return 1.0, 1.0
    recs.sort(key=lambda r: r[0])
    n = len(recs)
    w = [0.5 ** (n - 1 - i) for i in range(n)]
    ws = sum(w)
    f_for = sum(wi * r[1] for wi, r in zip(w, recs)) / ws
    f_ag  = sum(wi * r[2] for wi, r in zip(w, recs)) / ws
    avg = sum(pool) / len(pool)
    atk = max(0.85, min(1.15, f_for / avg))
    dfn = max(0.85, min(1.15, f_ag  / avg))
    return atk, dfn


def combined_form_mod(team, before_date, fields, stats_by_pair, canon):
    """Average the per-field clamped (atk,def) across `fields`. The mean of
    values each in [0.85,1.15] is itself in [0.85,1.15] — identical adjustment
    envelope to the SOT-only modifier, so the ONLY thing that varies between
    arms is which stats inform it (not the modifier's strength). A field with
    no prior data contributes its neutral 1.0; in this dataset all three fields
    are populated together (only France/Senegal is all-null), so they fire on
    the same matches with no asymmetric dampening.

    NOTE: the defensive component for possessionPct is semantically weak
    ('possession conceded' ~ 100 - own); kept mechanically identical to the SOT
    pattern for a clean A/B, but a possession-driven result deserves caution."""
    atks, dfns = [], []
    for f in fields:
        a, d = field_form_mod(team, before_date, f, stats_by_pair, canon)
        atks.append(a)
        dfns.append(d)
    return sum(atks) / len(atks), sum(dfns) / len(dfns)


def run_arm(fields, results, fixtures, strength, stats):
    """One full prequential LOO pass. Identical to backtest_ensemble.py's loop
    except the form modifier draws from `fields`. Returns metrics + rows."""
    canon = {}
    for fx in fixtures:
        if fx.get("home") and fx.get("away"):
            canon[frozenset([fx["home"], fx["away"]])] = fx.get("date")

    stats_by_pair = defaultdict(list)
    for e in stats:
        stats_by_pair[frozenset([e["team1"], e["team2"]])].append(e)

    matches = []
    for r in results:
        pair = frozenset([r["team1"], r["team2"]])
        dt = canon.get(pair) or r.get("date")
        matches.append((dt, r["team1"], r["team2"], r["home_score"], r["away_score"]))
    matches.sort(key=lambda m: m[0])

    weights   = {m: 1.0 for m in ens.COMPONENTS}
    cum_brier = {m: 0.0 for m in ens.COMPONENTS}
    n_scored = 0
    base_b, base_r, ens_b, ens_r = [], [], [], []
    rows = []
    loo_active = 0
    pending = defaultdict(lambda: {m: 0.0 for m in ens.COMPONENTS})
    pending_n = defaultdict(int)
    last_date = None

    for dt, t1, t2, hs, as_ in matches:
        if last_date is not None and dt != last_date:
            for d in [x for x in pending if x <= last_date]:
                for m in ens.COMPONENTS:
                    cum_brier[m] += pending[d][m]
                n_scored += pending_n[d]
                del pending[d]; del pending_n[d]
            if n_scored > 0:
                weights = {m: 1.0 / (cum_brier[m] / n_scored) for m in ens.COMPONENTS}
        last_date = dt

        s1 = strength.get(t1, {}).get("final_strength", 1600.0)
        s2 = strength.get(t2, {}).get("final_strength", 1600.0)
        lh, la = ens.strength_lambdas(s1, s2)

        atk1, def1 = combined_form_mod(t1, dt, fields, stats_by_pair, canon)
        atk2, def2 = combined_form_mod(t2, dt, fields, stats_by_pair, canon)
        active = (atk1, def1, atk2, def2) != (1.0, 1.0, 1.0, 1.0)
        if active:
            loo_active += 1
        lh = max(0.3, min(3.5, lh * atk1 * def2))
        la = max(0.3, min(3.5, la * atk2 * def1))

        bw, bd, bl = skellam_wdl(lh, la)
        bb, br = brier_rps(bw, bd, bl, hs, as_)
        base_b.append(bb); base_r.append(br)

        ew, ed_, el = ens.ensemble_probs(lh, la, weights)
        eb, er = brier_rps(ew, ed_, el, hs, as_)
        ens_b.append(eb); ens_r.append(er)

        comp = ens.component_probs(lh, la)
        for m in ens.COMPONENTS:
            cb, _ = brier_rps(*comp[m], hs, as_)
            pending[dt][m] += cb
        pending_n[dt] += 1

        rows.append((dt, t1, t2, f"{hs}-{as_}", bb, eb, br, er, active))

    return dict(base_b=base_b, base_r=base_r, ens_b=ens_b, ens_r=ens_r,
                loo_active=loo_active, rows=rows, weights=weights)


def main():
    results  = _load("wc2026_results.json")
    fixtures = _load("fixtures.json")
    strength = _load("team_strength.json")
    stats    = _load("match_stats.json")

    SOT_ONLY = ["shotsOnTarget"]
    THREE    = ["shotsOnTarget", "totalShots", "possessionPct"]

    a = run_arm(SOT_ONLY, results, fixtures, strength, stats)
    b = run_arm(THREE,    results, fixtures, strength, stats)

    def mean(x): return sum(x) / len(x)

    print(f"\nForm-field LOO comparison | {len(a['rows'])} matches | "
          f"LOO-active rows: SOT-only={a['loo_active']}, 3-field={b['loo_active']}\n")

    # focused view: only the matches where the modifier is non-neutral, where
    # the two arms can possibly differ
    print("LOO-active matches only (baseline Skellam Brier under each arm):")
    print(f"{'date':11s} {'match':30s} {'res':5s} {'BS_SOT':>8s} {'BS_3fld':>8s} {'delta':>8s}")
    for (dt, t1, t2, res, bb_a, *_a, act_a), (_, _, _, _, bb_b, *_b, act_b) in zip(a['rows'], b['rows']):
        if act_a or act_b:
            d = bb_b - bb_a   # negative => 3-field lower Brier => better
            print(f"{dt:11s} {t1[:14]+' v '+t2[:11]:30s} {res:5s} "
                  f"{bb_a:8.4f} {bb_b:8.4f} {d:+8.4f}")

    print("-" * 72)
    print("WHOLE-SET MEANS (all 28 matches):")
    print(f"  Baseline Skellam  SOT-only : Brier={mean(a['base_b']):.4f}  RPS={mean(a['base_r']):.4f}")
    print(f"  Baseline Skellam  3-field  : Brier={mean(b['base_b']):.4f}  RPS={mean(b['base_r']):.4f}")
    db = mean(a['base_b']) - mean(b['base_b'])
    dr = mean(a['base_r']) - mean(b['base_r'])
    print(f"  -> delta (positive = 3-field better): Brier {db:+.4f}  RPS {dr:+.4f}")
    print(f"  Ensemble (DC+NB+BVP) SOT-only: Brier={mean(a['ens_b']):.4f}  RPS={mean(a['ens_r']):.4f}")
    print(f"  Ensemble (DC+NB+BVP) 3-field : Brier={mean(b['ens_b']):.4f}  RPS={mean(b['ens_r']):.4f}")

    print("\nVERDICT (production baseline):",
          "3-field >= SOT-only on both metrics — candidate worth deeper testing"
          if db >= 0 and dr >= 0 else
          "3-field does NOT beat SOT-only — keep production SOT-only modifier")
    print("\nNOTE: only the LOO-active matches above can differ between arms; with",
          f"{a['loo_active']} active of {len(a['rows'])}, this is directional, not conclusive.")


if __name__ == "__main__":
    main()
