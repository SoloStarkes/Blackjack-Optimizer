# Documentation

Reference documentation for the **Blackjack Optimizer** — a Monte Carlo
blackjack simulation engine built for MATH-4940 at RPI.

For setup and running instructions, see the [project README](../README.md).

---

## Table of Contents

| Document | Description |
|---|---|
| [architecture.md](architecture.md) | High-level system diagram, module responsibilities, and a complete request/response data-flow trace |
| [engine.md](engine.md) | How `Shoe`, `Hand`, and `play_round` work; splits, doubles, surrender, and dealer logic |
| [strategy.md](strategy.md) | Basic strategy table structure, rule variations (H17/S17, DAS), and all 22 Illustrious 18 + Fab 4 deviations |
| [counting.md](counting.md) | Hi-Lo system, running/true count calculation, and how `true_count_frequencies` builds the TC distribution |
| [simulator.md](simulator.md) | Monte Carlo session loop, wong-out implementation, result aggregation, and accuracy vs. `num_shoes` |
| [ev_and_risk.md](ev_and_risk.md) | Formula derivations for EV, SD, Risk of Ruin, N-0, and SCORE; analytical vs. Monte Carlo RoR; worked numeric example |
| [kelly.md](kelly.md) | Kelly Criterion theory, full vs. half vs. fixed betting tradeoffs, and the `optimal_bet_spread` function |
| [api.md](api.md) | All three API endpoints: full request/response schemas, example JSON, validation rules, and timeout guidance |
| [frontend.md](frontend.md) | UI layout and controls, debounced auto-simulation, request cancellation, and Variance Visualizer chart details |

---

## Quick Navigation by Topic

**"How does the simulator know what card to play?"**
→ [strategy.md](strategy.md) — basic strategy tables and deviation overrides

**"How is the true count calculated?"**
→ [counting.md](counting.md) — Hi-Lo system and `Counter.true_count()`

**"What does RoR = 0.84% actually mean?"**
→ [ev_and_risk.md](ev_and_risk.md) — Risk of Ruin formula and concrete example

**"Why does the UI wait 750 ms after I change a rule?"**
→ [frontend.md](frontend.md) — debounce and request cancellation

**"What happens when I set a bet to $0?"**
→ [simulator.md](simulator.md) — wong-out implementation

**"What is the POST /simulate request body?"**
→ [api.md](api.md) — full schema with constraints and examples

**"Why does splitting 8,8 vs 10 use the pair table, not the I18 deviation?"**
→ [strategy.md](strategy.md) — deviation key mapping; [simulator.md](simulator.md) — the `_deviation_key` bug fix

**"What does the SCORE number mean?"**
→ [ev_and_risk.md](ev_and_risk.md) — SCORE formula and interpretation

**"What do the coloured lines in the variance chart represent?"**
→ [frontend.md](frontend.md) — percentile curve interpretation
