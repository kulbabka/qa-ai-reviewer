# Product: TradeZella — AI Trading Journal

## What the product is

TradeZella is an AI-powered trading journal and analytics platform. It is
**not a brokerage** — users execute trades through their own broker, and
TradeZella imports and analyzes that trade data. Covers stocks, options,
futures, forex, and crypto. Trusted by 100,000+ traders; 500+ supported
brokers for auto-import.

Primary value proposition: turn raw trade history into an objective,
data-backed understanding of what's working, what isn't, and why — replacing
manual spreadsheets and memory-based self-assessment.

## Business model

Tiered subscription (Basic / Essential / Premium / Pro), monthly or annual
billing (annual cheaper). No free trial. Key tier-gated features:
- Number of trading accounts
- Number of Playbooks (Basic/Essential capped at 3; Premium/Pro unlimited)
- Full session Trade Replay (Premium/Pro only; Basic/Essential can replay
  individual trades only)
- Zella AI and Prop Firm Sync (marketed, rollout status may vary)

## Target audience

**Primary users:** active retail traders (day traders, swing traders) and
proprietary-firm ("prop") traders undergoing funded-account evaluations.

**Technical level:** not necessarily technical — comfortable with trading
platforms and broker software, but the product must be usable without a
learning curve since the user's attention is on trading, not on the tool.

**Mental model:** users think of TradeZella as "the thing that tells me the
truth about my trading" — an objective mirror, not just a log. Trust in the
accuracy of every number is the core relationship with the product.

## Core modules (feature areas under analysis)

### Trade Log / Journal
Records every trade: entry/exit price, size, P&L, stop-loss/take-profit,
emotional state, notes, screenshots. Populated via broker sync, CSV upload,
or manual entry.

### Dashboard
Real-time snapshot: Zella Score, Net P&L, win rate, calendar view (day/week/
month), customizable widgets, supports single or multi-account view.

### Broker Sync
Auto-imports trades from 500+ brokers with full execution data in real time.
Manual CSV upload as fallback for unsupported brokers.

### Backtesting
Tests a strategy against historical data (back to 2014). Up to 5 symbols
simultaneously, up to 8 charts, supports market/limit/stop order simulation.
Every backtested trade is automatically logged to the journal and can be
linked to a Playbook.

### Trade Replay
Re-watches a trade's price action exactly as it printed, to review execution
quality (hesitation, early exit, level not respected).

### Playbooks
Documented strategy rules (entry/exit criteria, risk parameters). Trades and
backtest sessions link to a Playbook; TradeZella reports adherence and
performance difference between rule-following and rule-breaking trades.

### Reports / Analytics
50+ reports: Day & Time, Tags, Symbol, R-Multiple view, Strategy comparison,
etc. — filtering power to isolate a trading edge.

### Prop Firm Sync
Tracks evaluation progress against proprietary trading firm rules (max
drawdown, daily loss limits) across firms like FTMO, TopStep, Apex.

## Key user goals

1. Trust that every number (P&L, win rate, R-multiple, Zella Score) is
   accurate and reflects reality without manual reconciliation
2. Understand which setups/Playbooks are actually profitable, not guess
3. Know immediately and unambiguously whether a sync/save/backtest action
   succeeded or failed
4. Clearly distinguish real trades from simulated (backtest) trades at all
   times
5. Discover subscription-tier limits before investing time configuring
   something they can't use

## Glossary

See glossary.md for the full domain and product term list.
