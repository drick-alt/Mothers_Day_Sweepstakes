"""
Raffle odds engine.

The key insight: "chance of winning one of 4 prizes" is NOT (my_tickets / total) * 4.
That naive formula breaks (exceeds 100%) once you own more than 1/4 of the pool.

The correct model is the HYPERGEOMETRIC distribution: 4 prizes are drawn from a
pool of N tickets WITHOUT replacement (a drawn ticket is set aside and cannot
win a second prize -- the standard raffle rule).

    P(win nothing)      = C(N-k, p) / C(N, p)
    P(win >= 1 prize)   = 1 - P(win nothing)
    P(win exactly j)    = C(k, j) * C(N-k, p-j) / C(N, p)
    E[prizes won]       = p * k / N
    P(any ONE specific prize) = k / N     (true by symmetry)

Where N = total tickets sold, k = tickets you own, p = number of prizes.

WITH-replacement mode is also supported for raffles that return the drawn
ticket to the drum (one ticket can win multiple prizes):

    P(win nothing) = ((N-k)/N) ** p
"""

from math import comb


def compute_odds(total_tickets: int, my_tickets: int, num_prizes: int = 4,
                 with_replacement: bool = False) -> dict:
    """Compute a full odds breakdown for a ticket holder.

    Returns a dict with probabilities as floats in [0.0, 1.0].
    Safe for edge cases: zero tickets, more prizes than tickets, k > N.
    """
    N = int(total_tickets)
    k = int(my_tickets)
    p = int(num_prizes)

    if N < 0 or k < 0 or p < 0:
        raise ValueError("counts must be non-negative")
    # A holder cannot own more tickets than exist.
    k = min(k, N)

    base = {
        "total_tickets": N,
        "my_tickets": k,
        "num_prizes": p,
        "with_replacement": with_replacement,
        "ownership_share": 0.0,
        "per_prize": 0.0,
        "at_least_one": 0.0,
        "win_nothing": 1.0,
        "expected_prizes": 0.0,
        "sweep_all": 0.0,
        "distribution": {},
        "one_in": None,
    }

    if N == 0 or k == 0 or p == 0:
        if p == 0:
            base["win_nothing"] = 1.0
        return base

    effective_p = min(p, N)  # can't draw more prizes than tickets in the drum

    if with_replacement:
        p_none = ((N - k) / N) ** p
        p_sweep = (k / N) ** p
        dist = {}
        for j in range(p + 1):
            dist[j] = comb(p, j) * ((k / N) ** j) * (((N - k) / N) ** (p - j))
    else:
        denom = comb(N, effective_p)
        # comb() returns 0 when the first arg < second arg, which is exactly
        # the semantics we want: if N-k < p you are guaranteed to win something.
        p_none = comb(N - k, effective_p) / denom
        p_sweep = comb(k, effective_p) / denom if k >= effective_p else 0.0
        dist = {}
        for j in range(effective_p + 1):
            dist[j] = (comb(k, j) * comb(N - k, effective_p - j)) / denom

    at_least_one = 1.0 - p_none

    return {
        "total_tickets": N,
        "my_tickets": k,
        "num_prizes": p,
        "with_replacement": with_replacement,
        "ownership_share": k / N,
        "per_prize": k / N,
        "at_least_one": at_least_one,
        "win_nothing": p_none,
        "expected_prizes": effective_p * k / N,
        "sweep_all": p_sweep,
        "distribution": dist,
        "one_in": (1.0 / at_least_one) if at_least_one > 0 else None,
    }


def marginal_ticket_value(total_tickets: int, my_tickets: int,
                          num_prizes: int = 4) -> float:
    """How many percentage points would ONE more ticket add right now?

    Used to show buyers the value of an incremental ticket.
    """
    now = compute_odds(total_tickets, my_tickets, num_prizes)["at_least_one"]
    nxt = compute_odds(total_tickets + 1, my_tickets + 1, num_prizes)["at_least_one"]
    return nxt - now


def dilution_forecast(total_tickets: int, my_tickets: int, num_prizes: int,
                      additional_sold: list) -> list:
    """Project how odds decay as OTHER people buy more tickets.

    Returns [{extra_sold, total, at_least_one}] so the UI can warn a holder
    that their odds fall as the raffle grows.
    """
    out = []
    for extra in additional_sold:
        n = total_tickets + extra
        o = compute_odds(n, my_tickets, num_prizes)
        out.append({
            "extra_sold": extra,
            "total": n,
            "at_least_one": o["at_least_one"],
        })
    return out


def pct(x: float, places: int = 2) -> str:
    """Format a probability as a percentage string."""
    if x is None:
        return "-"
    return f"{x * 100:.{places}f}%"
