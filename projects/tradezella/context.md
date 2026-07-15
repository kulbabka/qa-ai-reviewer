# Project: TradeZella — QA Review (Railsware RPI prep)

## Scope

This project supports live-session QA practice for TradeZella, an AI-powered
trading journal product. The interview panel has indicated a strong lean
toward **UI/UX testing** (Mode 3 is the primary mode for this project), but
Mode 1 (requirement review) and Mode 2 (flow → test cases) should also be
usable if the live task calls for them.

## What we are reviewing

Any user-facing area of TradeZella that may come up in the live session,
including but not limited to:
- Trade Log / journal entry (manual add, edit, broker-synced entries)
- Dashboard and Zella Score widgets
- Broker Sync status and error states
- Backtesting screen (multi-symbol, multi-chart)
- Trade Replay
- Playbooks (creation, plan limits, adherence reporting)
- Reports / analytics screens

## What is out of scope

- Actual broker execution / order routing (TradeZella is not a broker)
- Backend calculation internals not observable from the UI
- Mobile app specifics unless explicitly shown
- Anything not visible in the screenshots/URLs provided during the session
