"""Three-distribution goal-model ensemble with adaptive Brier-score weights.

Standalone and read-only w.r.t. the live pipeline: nothing here is imported by
run_predictions.py / generate_index.py, and nothing here mutates production
state. Built for the Session 4 backtest per CLAUDE.md §10.

Each component maps a pair of expected-goal rates (lh, la) to a
(P_home_win, P_draw, P_home_loss) triple. The ensemble is a convex combination
whose weights adapt to each component's past Brier score.
"""
import math

# ── Fixed hyperparameters — priors, NOT fitted on the 21 backtest matches ─────
DC_RHO    = 0.08   # Dixon-Coles low-score correction (identical to production tau)
NB_SIZE   = 8.0    # Negative-Binomial dispersion r: var = mu + mu^2/r
BVP_COV   = 0.12   # Bivariate-Poisson shared covariance lambda3 (draw inflation)
MAX_GOALS = 10     # goal-matrix truncation


def _pois_pmf(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _tau(x, y, lh, la, rho=DC_RHO):
    if x == 0 and y == 0: return 1 - lh * la * rho
    if x == 1 and y == 0: return 1 + la * rho
    if x == 0 and y == 1: return 1 + lh * rho
    if x == 1 and y == 1: return 1 - rho
    return 1.0


def _wdl_from_matrix(prob):
    """Collapse a {(g1,g2): p} joint matrix to (win, draw, loss) for the home team."""
    tot = sum(prob.values())
    win  = sum(p for (g1, g2), p in prob.items() if g1 > g2) / tot
    draw = sum(p for (g1, g2), p in prob.items() if g1 == g2) / tot
    loss = sum(p for (g1, g2), p in prob.items() if g1 < g2) / tot
    return win, draw, loss


def dc_probs(lh, la, rho=DC_RHO, max_goals=MAX_GOALS):
    """Dixon-Coles: independent Poisson marginals + low-score tau correction."""
    prob = {}
    for g1 in range(max_goals + 1):
        for g2 in range(max_goals + 1):
            prob[(g1, g2)] = _pois_pmf(lh, g1) * _pois_pmf(la, g2) * _tau(g1, g2, lh, la, rho)
    return _wdl_from_matrix(prob)


def _negbin_pmf(k, mu, r):
    """NB(mean=mu, size=r); real-valued r via lgamma. var = mu + mu^2/r."""
    p = r / (r + mu)
    log_coef = math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
    return math.exp(log_coef + r * math.log(p) + k * math.log(1 - p))


def negbin_probs(lh, la, r=NB_SIZE, max_goals=MAX_GOALS):
    """Overdispersed independent Negative-Binomial marginals."""
    h = [_negbin_pmf(k, lh, r) for k in range(max_goals + 1)]
    a = [_negbin_pmf(k, la, r) for k in range(max_goals + 1)]
    prob = {(g1, g2): h[g1] * a[g2]
            for g1 in range(max_goals + 1) for g2 in range(max_goals + 1)}
    return _wdl_from_matrix(prob)


def bivpois_probs(lh, la, cov=BVP_COV, max_goals=MAX_GOALS):
    """Karlis-Ntzoufris bivariate Poisson with shared covariance lambda3 >= 0.
    Marginal means are preserved at lh, la (lam1 = lh - lam3, lam2 = la - lam3)."""
    lam3 = min(cov, 0.8 * min(lh, la))
    lam1 = max(1e-9, lh - lam3)
    lam2 = max(1e-9, la - lam3)
    base = math.exp(-(lam1 + lam2 + lam3))

    def joint(x, y):
        s = 0.0
        for k in range(min(x, y) + 1):
            s += (math.comb(x, k) * math.comb(y, k) * math.factorial(k)
                  * (lam3 / (lam1 * lam2)) ** k)
        return base * lam1 ** x / math.factorial(x) * lam2 ** y / math.factorial(y) * s

    prob = {(x, y): joint(x, y)
            for x in range(max_goals + 1) for y in range(max_goals + 1)}
    return _wdl_from_matrix(prob)


COMPONENTS = ("dc", "nb", "bvp")


def component_probs(lh, la):
    """Return {name: (win, draw, loss)} for all three component models."""
    return {"dc": dc_probs(lh, la),
            "nb": negbin_probs(lh, la),
            "bvp": bivpois_probs(lh, la)}


def ensemble_probs(lh, la, weights):
    """Convex combination of the three components. `weights` is a dict over
    COMPONENTS; need not be pre-normalized. Returns (win, draw, loss)."""
    comp = component_probs(lh, la)
    wsum = sum(weights[m] for m in COMPONENTS)
    win  = sum(weights[m] * comp[m][0] for m in COMPONENTS) / wsum
    draw = sum(weights[m] * comp[m][1] for m in COMPONENTS) / wsum
    loss = sum(weights[m] * comp[m][2] for m in COMPONENTS) / wsum
    return win, draw, loss


def strength_lambdas(s1, s2):
    """Production strength->lambda map (run_predictions.py:133-134), capped [0.3, 3.5]."""
    lh = max(0.3, min(3.5, 1.5 * (s1 / s2) ** 2.0))
    la = max(0.3, min(3.5, 1.5 * (s2 / s1) ** 2.0))
    return lh, la
