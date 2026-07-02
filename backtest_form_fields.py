"""LOO form-FIELD comparison. Originally SOT-only (current production
modifier) vs SOT + totalShots + possessionPct (NO-GO, FRAGILE, 2026-06-25).

Extended 2026-07-02 to a three-way comparison with a goals-based arm:
  A) SOT-only (production)
  B) SOT + goals
  C) goals-only
where "goals" is a strict-LOO form modifier built from actual WC2026 goals
scored/conceded in wc2026_results.json (decay-weighted, divided by the
strictly-prior tournament average goals per team per match, clamped
[0.85,1.15] — the exact pattern of the SOT modifier, with real goals as the
stat). Shootout-decided knockout matches contribute their stored 120-min
score.

Standalone, read-only — a sibling of backtest_ensemble.py. Touches NO
production file and does NOT import or alter _form_modifiers(). It reimplements
the strict-LOO modifier locally (byte-identical to backtest_ensemble.py for the
SOT-only arm) and adds a generalized multi-field version. All arms run the
same prequential loop and differ ONLY in which stats feed the form
modifier, so any Brier/RPS gap is attributable to the changed inputs alone.

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


def goals_form_mod(team, before_date, goal_matches):
    """Strict-LOO goals-based form modifier from wc2026_results.json scores.
    Same decay/average/clamp pattern as field_form_mod, with actual goals
    scored/conceded as the stat. The normalizing average is goals per team
    per match over strictly-prior matches only (converges to the ~1.47
    tournament baseline; a fixed 1.47 would leak future information into
    the LOO). Shootout matches contribute their stored 120-min score.
    Returns (atk, def) clamped [0.85,1.15]; neutral with no prior data."""
    recs = []
    pool = []
    for dt, t1, t2, hs, as_ in goal_matches:
        if not dt or dt >= before_date:
            continue
        pool.append(hs)
        pool.append(as_)
        if t1 == team:
            recs.append((dt, hs, as_))
        elif t2 == team:
            recs.append((dt, as_, hs))
    if not recs or not pool or sum(pool) == 0:
        return 1.0, 1.0
    recs.sort(key=lambda r: r[0])
    n = len(recs)
    w = [0.5 ** (n - 1 - i) for i in range(n)]
    ws = sum(w)
    g_for = sum(wi * r[1] for wi, r in zip(w, recs)) / ws
    g_ag  = sum(wi * r[2] for wi, r in zip(w, recs)) / ws
    avg = sum(pool) / len(pool)
    atk = max(0.85, min(1.15, g_for / avg))
    dfn = max(0.85, min(1.15, g_ag  / avg))
    return atk, dfn


def combined_form_mod(team, before_date, fields, stats_by_pair, canon,
                      goal_matches=None):
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
        if f == "goals":
            a, d = goals_form_mod(team, before_date, goal_matches or [])
        else:
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

        atk1, def1 = combined_form_mod(t1, dt, fields, stats_by_pair, canon,
                                       goal_matches=matches)
        atk2, def2 = combined_form_mod(t2, dt, fields, stats_by_pair, canon,
                                       goal_matches=matches)
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


def sensitivity_report(a, b, arm_name="3-field"):
    """LEAVE-ONE-ACTIVE-MATCH-OUT sensitivity on the whole-set delta.

    The whole-set delta (positive = challenger arm better) is driven entirely
    by the LOO-active matches: every inactive match scores identically under
    both arms and contributes exactly 0 to the delta. So neutralizing one
    active match ('as if its modifier had never differed from neutral') simply
    drops that match's (baseline - challenger) difference from the delta,
    keeping the whole-set denominator N. If neutralizing any single match flips
    the sign of EITHER metric's delta, the headline result rests on that one
    match — and since the GO rule needs both metrics positive, a flip on either
    breaks the verdict.
    """
    N = len(a['base_b'])
    full_db = (sum(a['base_b']) - sum(b['base_b'])) / N   # + => challenger better
    full_dr = (sum(a['base_r']) - sum(b['base_r'])) / N

    # each active match's share of the full delta (label, brier_share, rps_share)
    active = []
    for i, (dt, t1, t2, res, *_rest, act_a) in enumerate(a['rows']):
        if not (act_a or b['rows'][i][8]):
            continue
        cb = (a['base_b'][i] - b['base_b'][i]) / N
        cr = (a['base_r'][i] - b['base_r'][i]) / N
        active.append((f"{t1} v {t2}", cb, cr))

    excl_b = [(name, full_db - cb) for name, cb, _ in active]
    excl_r = [(name, full_dr - cr) for name, _, cr in active]

    bmin, bmax = min(excl_b, key=lambda x: x[1]), max(excl_b, key=lambda x: x[1])
    rmin, rmax = min(excl_r, key=lambda x: x[1]), max(excl_r, key=lambda x: x[1])

    print("\n" + "-" * 72)
    print(f"SINGLE-MATCH SENSITIVITY — {arm_name} vs SOT-only "
          "(leave-one-active-match-out on whole-set delta)")
    print(f"  Full delta (positive = {arm_name} better): "
          f"Brier {full_db:+.4f}  RPS {full_dr:+.4f}  over {len(active)} active matches")
    print(f"  Brier delta range: min {bmin[1]:+.4f} (drop {bmin[0]})  ..  "
          f"max {bmax[1]:+.4f} (drop {bmax[0]})")
    print(f"  RPS   delta range: min {rmin[1]:+.4f} (drop {rmin[0]})  ..  "
          f"max {rmax[1]:+.4f} (drop {rmax[0]})")

    # a flip = full delta and some single-exclusion delta have opposite signs
    flippers = []
    for name, ed in excl_b:
        if (full_db >= 0) != (ed >= 0):
            flippers.append(f"{name} (Brier)")
    for name, ed in excl_r:
        if (full_dr >= 0) != (ed >= 0):
            flippers.append(f"{name} (RPS)")

    if flippers:
        print(f"  FRAGILE: result sign depends on a single match "
              f"({'; '.join(flippers)}) — do not treat as a stable signal.")
    else:
        print("  STABLE: result sign survives removal of any single match — "
              "this is a more credible signal.")


def main():
    results  = _load("wc2026_results.json")
    fixtures = _load("fixtures.json")
    strength = _load("team_strength.json")
    stats    = _load("match_stats.json")

    SOT_ONLY  = ["shotsOnTarget"]
    SOT_GOALS = ["shotsOnTarget", "goals"]
    GOALS     = ["goals"]

    a = run_arm(SOT_ONLY,  results, fixtures, strength, stats)
    b = run_arm(SOT_GOALS, results, fixtures, strength, stats)
    c = run_arm(GOALS,     results, fixtures, strength, stats)

    def mean(x): return sum(x) / len(x)

    print(f"\nForm LOO three-way comparison | {len(a['rows'])} matches | "
          f"LOO-active rows: SOT-only={a['loo_active']}, "
          f"SOT+goals={b['loo_active']}, goals-only={c['loo_active']}\n")

    # focused view: only the matches where some arm's modifier is non-neutral,
    # where the arms can possibly differ
    print("LOO-active matches only (baseline Skellam Brier under each arm):")
    print(f"{'date':11s} {'match':30s} {'res':5s} {'BS_SOT':>8s} "
          f"{'BS_S+G':>8s} {'BS_G':>8s} {'dS+G':>8s} {'dG':>8s}")
    for ra, rb, rc in zip(a['rows'], b['rows'], c['rows']):
        dt, t1, t2, res, bb_a, *_x, act_a = ra
        bb_b, act_b = rb[4], rb[8]
        bb_c, act_c = rc[4], rc[8]
        if act_a or act_b or act_c:
            # negative => challenger lower Brier => better
            print(f"{dt:11s} {t1[:14]+' v '+t2[:11]:30s} {res:5s} "
                  f"{bb_a:8.4f} {bb_b:8.4f} {bb_c:8.4f} "
                  f"{bb_b-bb_a:+8.4f} {bb_c-bb_a:+8.4f}")

    print("-" * 72)
    print(f"WHOLE-SET MEANS (all {len(a['rows'])} matches):")
    print(f"  Baseline Skellam  SOT-only  : Brier={mean(a['base_b']):.4f}  RPS={mean(a['base_r']):.4f}")
    print(f"  Baseline Skellam  SOT+goals : Brier={mean(b['base_b']):.4f}  RPS={mean(b['base_r']):.4f}")
    print(f"  Baseline Skellam  goals-only: Brier={mean(c['base_b']):.4f}  RPS={mean(c['base_r']):.4f}")
    for name, arm in (("SOT+goals", b), ("goals-only", c)):
        db = mean(a['base_b']) - mean(arm['base_b'])
        dr = mean(a['base_r']) - mean(arm['base_r'])
        print(f"  -> delta (positive = {name} better): Brier {db:+.4f}  RPS {dr:+.4f}")

    print("\nVERDICTS vs production SOT-only (aggregate only; GO also requires "
          "STABLE below):")
    for name, arm in (("SOT+goals", b), ("goals-only", c)):
        db = mean(a['base_b']) - mean(arm['base_b'])
        dr = mean(a['base_r']) - mean(arm['base_r'])
        print(f"  {name:10s}:",
              "beats SOT-only on both metrics — candidate worth deeper testing"
              if db > 0 and dr > 0 else
              "does NOT beat SOT-only — keep production SOT-only modifier")

    sensitivity_report(a, b, arm_name="SOT+goals")
    sensitivity_report(a, c, arm_name="goals-only")


if __name__ == "__main__":
    main()
