"""Validate the odds engine against brute-force Monte Carlo simulation."""

import random
from odds import compute_odds, marginal_ticket_value, pct

FAILS = []


def check(label, got, want, tol=1e-9):
    ok = abs(got - want) <= tol
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: got={got:.10f} want={want:.10f}")
    if not ok:
        FAILS.append(label)


def montecarlo(N, k, p, trials=400_000, seed=42):
    """Brute force: physically simulate drawing p tickets from N without replacement."""
    rng = random.Random(seed)
    tickets = list(range(N))
    mine = set(range(k))  # I own tickets 0..k-1
    wins_at_least_one = 0
    total_prizes_won = 0
    for _ in range(trials):
        drawn = rng.sample(tickets, min(p, N))
        hits = sum(1 for d in drawn if d in mine)
        if hits:
            wins_at_least_one += 1
        total_prizes_won += hits
    return wins_at_least_one / trials, total_prizes_won / trials


print("=" * 70)
print("TEST 1 - Analytic formula vs Monte Carlo simulation")
print("=" * 70)
for (N, k, p) in [(100, 1, 4), (100, 10, 4), (500, 25, 4), (50, 20, 4), (1000, 3, 4)]:
    o = compute_odds(N, k, p)
    sim_atleast, sim_expected = montecarlo(N, k, p)
    print(f"\nN={N} tickets, k={k} mine, p={p} prizes")
    check("  P(at least one)", o["at_least_one"], sim_atleast, tol=0.004)
    check("  E[prizes won]", o["expected_prizes"], sim_expected, tol=0.01)

print()
print("=" * 70)
print("TEST 2 - Naive formula is WRONG (this is why we use hypergeometric)")
print("=" * 70)
N, k, p = 10, 4, 4
naive = (k / N) * p
correct = compute_odds(N, k, p)["at_least_one"]
print(f"  N={N}, k={k}, p={p}")
print(f"  Naive  (k/N)*p     = {naive:.4f}  -> {pct(naive)}  <-- 160%, IMPOSSIBLE")
print(f"  Correct hypergeom  = {correct:.4f}  -> {pct(correct)}  <-- valid")
check("naive exceeds 1.0 (proving it is broken)", 1.0 if naive > 1.0 else 0.0, 1.0)
check("correct stays <= 1.0", 1.0 if correct <= 1.0 else 0.0, 1.0)

print()
print("=" * 70)
print("TEST 3 - Edge cases")
print("=" * 70)
o = compute_odds(0, 0, 4)
check("no tickets sold -> win_nothing=1", o["win_nothing"], 1.0)
o = compute_odds(100, 0, 4)
check("own zero tickets -> at_least_one=0", o["at_least_one"], 0.0)
o = compute_odds(4, 4, 4)
check("own ALL tickets -> at_least_one=1", o["at_least_one"], 1.0)
check("own ALL tickets -> sweep_all=1", o["sweep_all"], 1.0)
o = compute_odds(3, 1, 4)
check("more prizes than tickets -> guaranteed win", o["at_least_one"], 1.0)
o = compute_odds(100, 200, 4)
check("k>N is clamped to N", o["my_tickets"], 100.0)

print()
print("=" * 70)
print("TEST 4 - Distribution sums to 1.0")
print("=" * 70)
for (N, k, p) in [(100, 10, 4), (50, 7, 4), (20, 5, 4)]:
    o = compute_odds(N, k, p)
    s = sum(o["distribution"].values())
    check(f"N={N},k={k} distribution sums to 1", s, 1.0, tol=1e-9)

print()
print("=" * 70)
print("TEST 5 - Odds DECAY as others buy (the dilution the user asked for)")
print("=" * 70)
prev = 1.1
mono = True
for N in [10, 50, 100, 500, 1000, 5000]:
    a = compute_odds(N, 5, 4)["at_least_one"]
    print(f"  5 tickets, pool grows to {N:>5}: {pct(a):>8}")
    if a > prev:
        mono = False
    prev = a
check("odds strictly decrease as pool grows", 1.0 if mono else 0.0, 1.0)

print()
print("=" * 70)
print("TEST 6 - With-replacement mode")
print("=" * 70)
o = compute_odds(100, 1, 4, with_replacement=True)
expected = 1 - (99 / 100) ** 4
check("with-replacement matches 1-((N-k)/N)^p", o["at_least_one"], expected)

print()
print("=" * 70)
print("TEST 7 - Marginal ticket value")
print("=" * 70)
m = marginal_ticket_value(100, 5, 4)
print(f"  6th ticket in pool of 100 adds: {pct(m)}")
check("marginal value is positive", 1.0 if m > 0 else 0.0, 1.0)

print()
print("=" * 70)
if FAILS:
    print(f"RESULT: {len(FAILS)} FAILURES -> {FAILS}")
    raise SystemExit(1)
print("RESULT: ALL TESTS PASSED")
print("=" * 70)
