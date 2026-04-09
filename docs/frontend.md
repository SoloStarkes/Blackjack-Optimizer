# Frontend

`frontend/app.jsx` is a self-contained HTML file that includes the React 18 and
Recharts 2.12.7 runtimes from unpkg CDN and transpiles JSX at load-time with
Babel standalone.  No build step, no Node.js, no npm.

Open it directly in a browser, or serve it with:

```bash
python -m http.server 5500 --directory frontend
# Then visit http://localhost:5500/app.jsx
```

---

## UI Layout

The interface is modelled after CVCX, the industry-standard blackjack
simulation software.

```
┌──────────────────────────────────────────────────────────────────────┐
│  HEADER: "BLACKJACK OPTIMIZER"  ·  status pill (READY / SIMULATING)  │
├─────────────────────────┬────────────────────────────────────────────┤
│  GAME RULES panel       │  BET SPREAD panel                          │
│  (left, 270px wide)     │  (right, remaining space)                  │
│                         │                                            │
│  - Decks (dropdown)     │  Table: TRUE COUNT | BET SIZE | 2X | ×    │
│  - Penetration (slider) │  TC ≤ 0   $0       —        (wong out)     │
│  - Hits Soft 17 (toggle)│  TC +1   $25       □                       │
│  - Double After Split   │  TC +2   $50       □                       │
│  - Late Surrender       │  TC +3   $100      □                       │
│  - Re-split Aces        │  TC +4   $150      ☑ 2X → "$300 eff."     │
│  - BJ Payout (dropdown) │  TC +5   $200      ☑ 2X                   │
│  - Max Splits (dropdown)│                                            │
│                         │  [+ ADD COUNT LEVEL]                       │
├─────────────────────────┴────────────────────────────────────────────┤
│  CONTROLS BAR: Bankroll | Rounds/hr | Accuracy  [▶ RUN SIMULATION]  │
├──────────────────────────────────────────┬───────────────────────────┤
│  EV/HOUR    SD/HOUR    RISK OF RUIN    N-0 HOURS    │  📈 VARIANCE  │
│   +$96       ±$1,002     0.84%         109 hrs      │   VISUALIZER  │
├──────────────────────────────────────────────────────────────────────┤
│  STATS STRIP: SCORE | Hands | Wagered | Net P&L | EDGE BY TC         │
└──────────────────────────────────────────────────────────────────────┘
```

When the Variance Visualizer button is clicked, a modal overlays the page with
the Recharts line chart.

---

## Controls

### Game Rules Panel (left)

| Control | Type | Effect |
|---|---|---|
| Decks | Dropdown | `{1, 2, 4, 6, 8}` — changes house edge ~0.03% per deck |
| Penetration | Slider (50%–92%) | Lower pen = fewer high-count hands = lower EV |
| Hits Soft 17 | Toggle | H17 adds ~0.20% to house edge |
| Double After Split | Toggle | DAS saves ~0.14%; also changes pair splitting strategy |
| Late Surrender | Toggle | Surrender saves ~0.08% |
| Re-split Aces | Toggle | RSA saves ~0.06% |
| Blackjack Payout | Dropdown | 3:2 (1.5×) vs 6:5 (1.2×) — 6:5 adds 1.39% house edge |
| Max Splits | Dropdown | 1–4 splits allowed |

Every change triggers a debounced simulation (750 ms delay).

### Bet Spread Panel (right)

Each row represents a true-count tier:

| Column | Description |
|---|---|
| TRUE COUNT | TC threshold. Green for positive, grey for 0, red for negative. "WONG OUT" tag appears when bet = 0. |
| BET SIZE | Dollar bet for this tier. Input rounds to nearest $5. |
| 2X | Play two simultaneous hands (doubles effective exposure). Shows "= $XXX eff." when active. |
| × | Remove this tier (minimum 2 rows). |

"ADD COUNT LEVEL" appends a row at TC = max_existing + 1 with the last bet amount and 2X enabled.

### Controls Bar

| Control | Description |
|---|---|
| Bankroll | Starting capital used for RoR and N-0 calculations |
| Rounds / hr | Hands per hour — affects EV/hr, SD/hr, and N-0. Label shows inferred player count (1 player ~200, 2 ~130, etc.) |
| Accuracy | Quick (500 shoes), Standard (3k shoes), Detailed (10k shoes) |
| ▶ RUN SIMULATION | Triggers an immediate simulation (bypasses the debounce) |

---

## How the Frontend Calls the API

### Auto-debounce on parameter change

Every time the user changes any control, a `useEffect` watching `runSim` fires:

```js
useEffect(() => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(runSim, 750);   // 750 ms debounce
    return () => clearTimeout(debounce.current);
}, [runSim]);
```

This prevents a simulation from firing on every keystroke.  The 750 ms window
collapses multiple rapid changes into a single request.

### Cancellation of in-flight requests

Every call to `fetchWithTimeout` cancels the previous request for that slot
before starting:

```js
const fetchWithTimeout = async (url, options, timeoutMs, abortRef) => {
    if (abortRef.current) abortRef.current.abort();   // cancel previous
    const controller = new AbortController();
    abortRef.current = controller;

    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const resp = await fetch(url, { ...options, signal: controller.signal });
        clearTimeout(timer);
        return resp;
    } catch (e) {
        clearTimeout(timer);
        if (e.name === 'AbortError')
            throw new Error('Request timed out…');
        throw e;
    }
};
```

Two separate `AbortController` refs are maintained — `simAbort` for `/simulate`
and `vizAbort` for `/variance-visual` — so cancelling a sim does not cancel a
running variance chart and vice versa.

### Timeouts

- `/simulate`: **120 seconds**.  For 10,000 shoes, the simulation typically
  finishes in 20–40 seconds.
- `/variance-visual`: **240 seconds**.  The 10k-shoe simulation plus 1,000-hour
  random walk with 300 paths typically takes 60–120 seconds.

### Request body construction

`buildBody()` assembles the payload from React state:

```js
const buildBody = (extraShoes) => ({
    rules: {
        decks: rules.decks,
        penetration: rules.penetration,
        h17: rules.h17,
        das: rules.das,
        rsa: rules.rsa,
        max_splits: rules.maxSplits,
        surrender: rules.surrender,
        bj_payout: rules.bjPayout,
    },
    bet_spread: buildSpread(),   // {tc_string: effective_bet}
    bankroll,
    rounds_per_hour: rph,
    num_shoes: extraShoes || numShoes,
    seed: null,
});
```

`buildSpread()` converts the `betRows` array to the `{TC_string: dollar_bet}` format
required by the API, applying the 2X multiplier to produce the effective bet:

```js
const buildSpread = () => {
    const spread = {};
    let hasPos = false;
    betRows.forEach(row => {
        const eff = row.twoX && row.bet > 0 ? row.bet * 2 : row.bet;
        spread[String(row.tc)] = eff;
        if (eff > 0) hasPos = true;
    });
    return hasPos ? spread : null;   // null → don't run simulation
};
```

---

## Results Display

### Metric cards (top row)

Four metric cards are colour-coded:

| Card | Green | Orange | Red |
|---|---|---|---|
| EV/hr | EV > 0 | — | EV < 0 |
| SD/hr | — | — | — (always blue) |
| Risk of Ruin | RoR < 5% | 5–15% | > 15% |
| N-0 | — | — | — (always yellow) |

The N-0 card shows "∞" when the API returns `-1.0` (infinite N-0, meaning EV ≤ 0).

### Stats strip

A secondary strip below the metric cards shows:
- **SCORE** — the desirability index
- **Hands** — total hands simulated (played rounds, not wongs)
- **Wagered** — total dollars placed as initial bets
- **Net P&L** — total net winnings in the simulation
- **EDGE BY TC** — per-TC player edge for TC+1 through TC+7

### Error handling

If the API returns a non-2xx status, the error detail is extracted and shown in
an error tag.  Network errors (API not running) show a specific message:
`"Cannot reach backend — is it running on :8000?"`.

---

## Variance Visualizer

Clicking the **📈 VARIANCE VISUALIZER** button sends a POST to `/variance-visual`
with `hours=1000`, `num_paths=300`, `percentiles=[5,25,50,75,95]`, and
`num_shoes=10000`.  Results appear in a modal.

### Chart construction

`chartData` is built with `useMemo` from the API response:

```js
const chartData = data.hours.map((h, i) => ({
    hour: Math.round(h * 10) / 10,
    p5:  Math.max(0, Math.round(data.percentile_curves['5'][i])),
    p25: Math.max(0, Math.round(data.percentile_curves['25'][i])),
    p50: Math.max(0, Math.round(data.percentile_curves['50'][i])),
    p75: Math.max(0, Math.round(data.percentile_curves['75'][i])),
    p95: Math.max(0, Math.round(data.percentile_curves['95'][i])),
    ev:  Math.max(0, Math.round(data.ev_curve[i])),
}));
```

Values are floored at 0 because negative bankrolls are not meaningful (ruin is
modelled as clamping at $0 in the API).

### Y-axis domain

The Y domain is computed from the 5th and 95th percentile curves to avoid
compressing the middle range:

```js
const yDomain = useMemo(() => {
    const flat = [...data.percentile_curves['5'], ...data.percentile_curves['95']]
        .filter(v => v > 0);
    const lo = Math.floor(Math.min(...flat) / 5000) * 5000;
    const hi = Math.ceil(Math.max(...flat) / 5000) * 5000;
    return [Math.max(0, lo), hi];
}, [data, bankroll]);
```

### What the percentile curves mean

| Curve | Colour | Interpretation |
|---|---|---|
| 5th %ile | Red (dashed) | Only 5% of players do *worse* than this |
| 25th %ile | Orange | 25% of players finish below this |
| Median (50th) | Blue (bold) | Half of all sessions finish above/below this |
| 75th %ile | Green | 75% of players finish below this |
| 95th %ile | Purple (dashed) | Only 5% of players do *better* than this |
| EV line | Green (dotted) | Theoretical expected bankroll = start + EV × hands |

The gap between the EV line and the median is a measure of **skewness** in the
payout distribution.  Because wins include rare 3:2 blackjacks and double-downs
while losses are capped at the bet size, the distribution is slightly right-skewed:
the mean exceeds the median.

### Footer stats

| Stat | Description |
|---|---|
| RUIN PROBABILITY | Fraction of 300 paths that reached $0 (empirical RoR) |
| PATHS SIMULATED | Always 300 |
| HORIZON | Always 1,000 hours |
| SHOES SIMULATED | Always 10,000 (for EV/SD base estimate) |
| MEDIAN OUTCOME (END) | Median bankroll at the end of the 1,000-hour horizon |

### Loading state

While the `/variance-visual` request is in flight, a spinner is shown with an
elapsed-seconds counter:

```js
vizTimer.current = setInterval(() => {
    setVizElapsed(Math.floor((Date.now() - startTs) / 1000));
}, 1000);
```

The timer is cleared when the response arrives or an error occurs.

---

## CDN Dependencies

All CDN resources are loaded at parse time from `unpkg.com`:

| Library | Version | CDN URL |
|---|---|---|
| React | 18 (production) | `unpkg.com/react@18/umd/react.production.min.js` |
| ReactDOM | 18 (production) | `unpkg.com/react-dom@18/umd/react-dom.production.min.js` |
| Recharts | 2.12.7 | `unpkg.com/recharts@2.12.7/umd/Recharts.js` |
| Babel standalone | 7.23.9 | `unpkg.com/@babel/standalone@7.23.9/babel.min.js` |

Because Babel transpiles JSX in the browser, the page requires a network
connection (or locally cached CDN responses) on the first load.  Subsequent
loads use the browser cache.

**Offline use**: Download and host the four CDN files locally, then update the
`<script src>` attributes to point to your local copies.
