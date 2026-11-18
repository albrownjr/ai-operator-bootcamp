# Automotive Sales & Deal-Readiness Engine — Dynamic Inventory V1

**Status:** code committed on branch `automotive-sales-engine`; **NOT deployed**. No verified live payment, lead, or sale. No DealerCenter access and no VS Code workflow required for operation.

## Purpose
Lead → understand buyer → establish trust → identify obstacle → structure approved deal → purchase decision → delivery.

Every new inquiry produces an auditable `LEAD_CAPTURED` event with an exact stock/VIN and human-owned `FIRST_CONTACT` plan. AI never independently sends communications or promises credit decisions, availability at future purchase time, payments, mandatory fees, or shipping charges.

## Inventory rules
- Inventory **candidates** are read from the **public Extreme Autoplex website** and registered by an authorized human using the built-in admin page. No website API, DealerCenter API, or automated crawling is claimed or configured.
- A registered public website listing starts `AVAILABLE`; the authorized owner's explicit SOLD status is final until explicitly changed again.
- Subsequent `observe_listing` operations update listing facts but **never** reopen a SOLD vehicle.
- Unknown or SOLD vehicle pages respond 404; new lead submissions for SOLD vehicles respond 409.
- Prior leads and attribution are retained after SOLD. Website observation timestamps and inventory status-change audit events are persisted.
- On a new SOLD transition, existing leads receive a pending `VEHICLE_SOLD_REVIEW` event and a human-owned `REVIEW_SOLD_VEHICLE` next action. Repeating SOLD does not generate duplicate review events.
- A vehicle is not registered unless its VIN, stock number and exact Extreme Autoplex HTTPS inventory URL have been supplied.
- A registered listing is an operating inventory assumption, not a guarantee it remains available at transaction time.
- Availability records are controlled by the stated owner inventory policy; price, condition, financing, total cost and approval are independent unverified facts until supported by authorized evidence.

## Public routes
- `GET /health` — process health
- `GET /api/vehicles` — registered, not-SOLD listing IDs and website links
- `GET /v/{stock_number}` — dynamic vehicle inquiry page
- `POST /api/leads` — consented lead intake; stock is validated server-side; deduplicates within 15 minutes; emits `LEAD_CAPTURED` with `sales_plan` and `decision_snapshot`

## Authorized operator routes
- `GET /admin` — browser-based inventory operator UI (token provided in session/tab, not stored)
- `GET /api/admin/inventory` — current and SOLD inventory
- `POST /api/admin/inventory` — register/refresh website observation
- `POST /api/admin/inventory/{stock_number}/status` — explicit SOLD or reactivation; response includes count of existing leads queued for review
- `GET /api/admin/leads` / `GET /api/admin/leads.csv` / `GET /api/admin/stats` — protected lead operations

Admin APIs require `Authorization: Bearer $ADMIN_TOKEN`; production fails closed if the token is unset.

## Workflow
1. Open `/admin` after deployment, provide the admin token, and register a current vehicle using the dealer's public listing URL, VIN, stock, year, make, model, etc.
2. Open `/v/{stock_number}` and verify that the correct car is shown. Inbound tracking attributes are captured via `utm_source`, `utm_campaign`, `utm_content`, `fbclid`, `gclid`.
3. Submit a **synthetic/test** lead, confirm one `LEAD_CAPTURED` event and a `FIRST_CONTACT` plan; verify exact VIN/stock. Clear test records in a test environment, not production.
4. Mark the car SOLD in `/admin`: it disappears from the public inventory and no longer accepts new leads; existing lead history stays.
5. Re-observe the website listing: SOLD remains until an explicit authorized reactivation.

## Deal Execution Engine (V1 workflow)

Protected operator desk: `GET /deal-desk`, after deployment. Enter the admin token in the browser tab, choose an actual lead, review the recommended action, and record verified events.

- `GET /api/admin/leads/{lead_id}/deal`: timestamped customer/salesperson/management history, next action and recorded outcome.
- `POST /api/admin/leads/{lead_id}/events`: append-only evidence event, requiring source, actor, actual timezone-aware timestamp, statement and idempotency key.
- Actor permissions distinguish customer statements from salesperson actions and management approvals; a workflow note cannot impersonate the customer.
- Motivation -> timeline -> financial preference -> condition acceptance -> approved quote -> buyer response -> purchase confirmation -> actual delivery. Known steps aren't re-asked.
- Sent videos are not evidence of reviewed/accepted condition. Sent quotes are not evidence of accepted terms.
- If an unanswered call is recorded and both calling and texting are permitted for that buyer, the next action is a contextual personal text; a phone conversation may replace that action.
- Buyer decline, condition concern, and pricing concern become explicit reviews rather than automatic pressure.
- Only management events can record `DELIVERY_COMPLETED` as SOLD or `DEAL_LOST` as LOST. The events are human recorded; they do not make financial or lending decisions.
- If the vehicle is marked SOLD, the deal packet requires a sold-vehicle review regardless of ordinary discovery progression.
- Current deal stage and next action update from recorded evidence, but no email, SMS, or telephone call is executed automatically.
- **Limitations:** the independent app does not yet ingest CRM due tasks, verify phone conversations, enforce real-world scheduling, execute financing, or provide real-time alerts. Due CRM tasks must still be handled manually under the existing call + text rules.

## First-contact sales plan
Capture interest alone does not establish purchase intent, vehicle-condition acceptance, or an approved deal. The plan asks one motivation question first, then moves to timeline and financial information when appropriate, without re-asking known facts. It is an internal action plan—not an automatic customer message. The owner's call + contextual SMS standard applies for CRM tasks due when permitted.

## Follow-up, chronology, and sales measurement controls

- New website leads automatically receive an `ENGINE` first-contact task. Actual CRM follow-up tasks are **not synchronized**; enter them manually through `/deal-desk` with an external reference, real due timestamp, and permitted contact policy.
- `GET /api/admin/tasks/due` shows unresolved due/overdue tasks; `GET/POST /api/admin/leads/{lead_id}/tasks` manages lead-specific entered tasks; `POST /api/admin/tasks/{task_id}/cancel` records cancellation reason. Cancellation in this engine does **not** modify DealerCenter.
- CALL_TEXT tasks require a documented personal call plus contextual text unless a meaningful phone conversation is documented. Automated workflow messages do not satisfy tasks. `FULFILLED_LATE` is distinct from timely completion.
- Buyer statements and contact attempts carry actual timezone-aware timestamps and separate recorded times. Duplicate idempotency keys may not rewrite prior statements.
- A confirmed sale requires causal management price approval → sent quote → explicit buyer acceptance → management purchase confirmation → recorded delivery, in timestamp order. A later unresolved buyer concern blocks purchase confirmation; condition/quote objections cannot disappear through unrelated statements.
- Terminal outcomes cancel only ENGINE-owned open tasks. CRM_MANUAL tasks remain visible for dealership CRM reconciliation.
- `GET /api/admin/metrics/funnel` provides recorded app-only lead-to-contact/quote/delivered-SOLD and per-source counts and timing, with **no fabricated baseline or incremental sales attribution**.
- `GET/POST /api/admin/metrics/baselines` stores append-only, manually entered historical baseline records with dates, source, counts and evidence reference. It does not verify the historical data or automatically claim that results improved.
- Transactions including new lead + engine task + capture event, SOLD status + affected buyer review events, and deal events + state updates are intended to commit as units; regression and runtime testing are required before production claims.

**Accuracy limitations:** A shared admin token does not verify manager identity or external quote approval. Event evidence is manually entered and could be inaccurate. CRM due-task lists are incomplete until manually registered. Financial terms, lending approvals and delivery are not executed by this software.

## Deployment
Source: `albrownjr/ai-operator-bootcamp`, branch `automotive-sales-engine`, service root `/automotive-sales-engine`.

On a production-capable Railway account or equivalent:
- `ADMIN_TOKEN`: secure long random secret
- `LEADS_DB_PATH=/data/leads.db`
- Persistent volume mounted at `/data`
- Start `uvicorn app:app --host 0.0.0.0 --port $PORT`; healthcheck `/health`.
- Root directory must be `/automotive-sales-engine`.

**Deployment blocker from last attempt:** Railway trial expired; no Railway project or live URL was created. A paid hosting plan or alternative hosting authorization is required. A runtime restart **without** a persistent volume will lose leads.

## Tests
`python -m unittest -v test_inventory_registry.py test_decision_intelligence.py test_deal_execution.py test_critical_controls.py`
Integration tests require packages from `requirements.txt` plus `httpx`. GitHub Actions test configuration is present; success must be confirmed from workflow logs. No test pass is claimed from a mere commit.

## Production safety gates
Confirm dealership authorization for the standalone form, privacy/consent requirements, advertising copy and current full price disclosure; use actual vehicle imagery, not illustrative photography; verify backup and access control; run an end-to-end submission test; and establish a human alert/ownership workflow for `FIRST_CONTACT`.

## Next build layers
This delivery includes **dynamic inventory + lead capture + timestamped deal-execution tracking and evidence-based next actions**. It does **not** automatically discover all website listings, ingest a CRM, execute follow-up, send messages, structure financing, or sell cars without a salesperson. Those must be measured and built only after the core flow is verified.
