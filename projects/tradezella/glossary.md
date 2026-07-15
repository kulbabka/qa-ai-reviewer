# Glossary — TradeZella / Trading domain

See product_context.md for the full product description. Key terms to keep
consistent in findings:

## Trading domain terms
- **Trade** — a full round-trip position (entry to exit), may consist of
  multiple **executions** (partial fills/closes)
- **Long** — bought expecting price to rise; **Short** — sold expecting price
  to fall
- **Entry / Exit price** — price at which a position was opened / closed
- **Position size** — quantity of the asset traded
- **P&L (Profit & Loss)** — the result of a trade or period, in currency
- **Win rate** — % of trades that were profitable
- **R-multiple** — P&L expressed as a multiple of the initial risk (e.g. risked
  $100, made $300 → +3R); used to compare trades of different sizes
- **Drawdown** — decline in account equity from its peak; **max drawdown** —
  the deepest such decline over a period
- **Setup / Playbook** — a documented, repeatable strategy definition
- **Stop-loss / Take-profit** — predefined exit prices to cap loss / lock in profit

## Product-specific terms
- **Broker Sync** — automatic import of trades from a connected broker (not
  manual entry)
- **Backtesting** — simulating a strategy against historical price data
  without real capital at risk
- **Trade Replay** — re-watching how a trade's chart looked as it happened
- **Zella Score** — TradeZella's proprietary aggregate metric summarizing
  overall trading health/consistency
- **Playbook adherence** — how closely actual trades followed a Playbook's
  defined rules
- **Prop Firm Sync** — tracking evaluation progress on proprietary trading
  firm accounts (e.g. FTMO, TopStep, Apex)
