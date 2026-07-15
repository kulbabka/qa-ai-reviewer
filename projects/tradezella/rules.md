# UX Review Rules — TradeZella

## Review focus (in priority order)

1. **Silent failures** — anything that stops working (broker sync drops,
   backtest session fails to save) without the UI clearly reflecting it
2. **Ambiguous state** — a trade or sync status that looks the same in the UI
   whether it succeeded, is pending, or failed
3. **Data integrity surfaced in UI** — P&L, win rate, R-multiple, or Zella
   Score that could be miscalculated or inconsistent between screens
   (dashboard vs trade log vs reports)
4. **Missing feedback** — no confirmation after a user action (manual trade
   add, Playbook save, backtest run) that the action succeeded
5. **Plan gate UX** — how and when subscription-tier limits (e.g. 3 Playbooks
   on Basic/Essential) are surfaced — ideally before the user configures
   everything, not after
6. **Confusing behavior** — unclear boundaries between modes, especially
   backtest/simulated trades vs real trades in the journal

## Evidence requirements

- Every finding must be traceable to a specific UI behavior, documented
  product behavior, or an explicit user goal in product_context.md
- Do not raise findings based on general UX best practices alone
- Do not raise findings about backend/broker execution logic unless it
  surfaces as a UI symptom

## Audience context

Remember the target user:
- Active or prop-firm trader, moderately tech-comfortable but focused on
  trading, not on learning software
- Makes real financial decisions based on the data shown — trusts the numbers
- Will not tolerate ambiguity in P&L or trade status; this is the core trust
  surface of the product

## Findings to prioritize

- Any UI state where a real trade could be confused with a simulated
  (backtest) one
- Any sync/save action without a clear success/failure signal
- Plan limits discovered only after the user has already configured
  something (e.g. hits the 3-Playbook cap mid-setup)
- Metrics displayed without a clear time-period label

## Findings to deprioritize

- Copy / wording preferences
- Color / typography preferences
- Generic "add more tooltips" suggestions without a specific trigger
- Broker-side execution/routing issues not visible in TradeZella's UI
