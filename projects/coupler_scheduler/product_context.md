# Product: Coupler.io — Scheduler Feature

## What the product is

Coupler.io is a no-code data integration and analytics platform (ETL).
It connects 400+ business data sources (CRMs, ad platforms, finance tools,
project management apps) and loads data into destinations like Google Sheets,
Microsoft Excel, BigQuery, Looker Studio, and Power BI.

Primary value proposition: eliminate manual data exports and keep dashboards
and reports automatically up to date.

## Business model

Tiered subscription priced per connected account (data connection), not per user:

| Plan     | Price      | Max refresh interval |
|----------|------------|----------------------|
| Free     | Free       | Manual only          |
| Starter  | $32/mo     | Daily                |
| Active   | ~$80/mo    | Daily                |
| Pro      | $132/mo    | Hourly               |
| Agency   | $259+/mo   | Every 15 minutes     |
| Enterprise | Custom   | Every 15 minutes     |

Annual billing gives a 25% discount.

## Target audience

**Primary users:**
- Marketing analysts — consolidating ad spend, campaign metrics, GA4 data
- Finance teams — automating P&L, revenue, and accounting reports
- Operations managers — tracking project statuses across tools
- Agencies — managing multiple client data pipelines

**Technical level:** mostly non-technical; the product is explicitly marketed
as "no-code". Some power users have SQL knowledge but the majority do not.

**Mental model:** users think of Coupler.io as a "always-fresh spreadsheet"
or "automatic export" rather than a data pipeline tool.

## Feature under analysis: Automatic Data Refresh (Scheduler)

### Purpose
Allows users to configure a recurring schedule for a data flow so that
the destination (e.g., a Google Sheets dashboard) is updated automatically
without manual action.

### Where it lives in the product
Data flow → Settings tab → "Automatic data refresh" toggle → scheduler panel

### Configuration options (current)
- **Interval:** Monthly | Daily | Hourly | Every 30 min | Every 15 min
  (available options depend on plan)
- **Days of the week:** Mon–Sun multi-select buttons
- **Time preferences:** Hour picker + Minute picker
- **Timezone:** IANA timezone name dropdown (e.g., Europe/London)

### Trigger / activation
Toggle must be switched ON and the flow must be saved and run at least once.
Automatic refresh only activates after a successful manual run.

### Failure / suspension behavior (documented)
- If a data flow exceeds the plan's row limit, automatic refresh is
  **silently suspended**. An email notification is sent to the account email.
  The flow card in the UI does not visually change.
- Webhooks (incoming/outgoing) are only available on Pro and above.

### Key user goals for this feature
1. Set once, forget — dashboard stays fresh without any manual action
2. Control timing precisely (e.g., refresh before 9 AM standup)
3. Know when the next refresh will happen
4. Be alerted immediately and visibly if a refresh fails or stops
5. Support time-bounded schedules (e.g., only during a campaign period)
6. Support business-hours-only refresh to avoid wasting run quota

## Key competitors and their scheduler capabilities

- **Supermetrics:** interval-based scheduling, day-of-week selection,
  specific time; no business-hours window; similar limitations
- **Fivetran:** cron-based scheduling available on higher plans;
  full audit log; Slack alerting on enterprise
- **Coefficient.io:** per-user pricing model; daily/hourly intervals;
  similar UX simplicity to Coupler.io
- **Hightouch:** cron expression support; time-window scheduling;
  per-sync failure routing

## Glossary

- **Data flow:** a configured pipeline from one source account to one destination
- **Importer:** older term for data flow (still appears in some UI labels)
- **Run:** a single execution of a data flow
- **Interval:** how frequently the scheduler triggers a run
- **Data destination:** where data is loaded (Sheets, BigQuery, etc.)
- **Data source:** where data is pulled from (HubSpot, Google Ads, etc.)
- **Account:** a single connected service credential (e.g., one Facebook Ads account)
- **Workspace:** isolated environment within an organization (Pro+ only)
- **Run quota:** monthly limit on the number of scheduled executions
- **Row limit:** per-plan cap on rows returned per single run
