# UX Review Rules — Coupler.io Scheduler

## Review focus (in priority order)

1. **Silent failures** — any case where the system stops working but the UI
   does not reflect this clearly
2. **State misrepresentation** — UI elements that communicate one state while
   the system is in another
3. **Configuration ambiguity** — settings combinations whose interaction is
   undefined or undocumented in the UI
4. **Missing controls for documented use cases** — scheduler options that
   real business users need but cannot configure
5. **Plan gate UX** — how and when plan limitations are surfaced to the user

## Evidence requirements

- Every finding must be traceable to a specific UI behavior, documented
  product behavior, or an explicit user goal in product_context.md
- Do not raise findings based on general UX best practices alone
- Do not raise findings about backend correctness unless surfaced in the UI

## Audience context

Remember the target user:
- Non-technical business analyst or marketer
- Does not read documentation before using the product
- Expects "what you configure is what you get"
- Will not notice a silent failure until a meeting goes wrong

## Findings to prioritize

- Silent suspension of automated tasks without in-app indication
- Configurations that look valid but produce undefined or unexpected behavior
- Missing feedback after saving a schedule (no confirmation of next run)
- Plan limits that are only revealed after the user has configured everything

## Findings to deprioritize

- Copy / wording improvements
- Color / typography preferences
- Generic "add more tooltips" recommendations without a specific trigger
- Backend performance concerns not visible in the UI
