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
- `POST /api/admin/inventory/{stock_number}/status` — explicit SOLD or reactivation
- `GET /api/admin/leads` / `GET /api/admin/leads.csv` / `GET /api/admin/stats` — protected lead operations

Admin APIs require `Authorization: Bearer $ADMIN_TOKEN`; production fails closed if the token is unset.

## Workflow
1. Open `/admin` after deployment, provide the admin token, and register a current vehicle using the dealer's public listing URL, VIN, stock, year, make, model, etc.
2. Open `/v/{stock_number}` and verify that the correct car is shown. Inbound tracking attributes are captured via `utm_source`, `utm_campaign`, `utm_content`, `fbclid`, `gclid`.
3. Submit a **synthetic/test** lead, confirm one `LEAD_CAPTURED` event and a `FIRST_CONTACT` plan; verify exact VIN/stock. Clear test records in a test environment, not production.
4. Mark the car SOLD in `/admin`: it disappears from the public inventory and no longer accepts new leads; existing lead history stays.
5. Re-observe the website listing: SOLD remains until an explicit authorized reactivation.

## First-contact sales plan
Capture interest alone does not establish purchase intent, vehicle-condition acceptance, or an approved deal. The plan asks one motivation question first, then moves to timeline and financial information when appropriate, without re-asking known facts. It is an internal action plan—not an automatic customer message. The owner's call + contextual SMS standard applies for CRM tasks due when permitted.

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
`python -m unittest -v test_inventory_registry.py test_decision_intelligence.py`
Integration tests require packages from `requirements.txt` plus `httpx`. GitHub Actions test configuration is present; success must be confirmed from workflow logs. No test pass is claimed from a mere commit.

## Production safety gates
Confirm dealership authorization for the standalone form, privacy/consent requirements, advertising copy and current full price disclosure; use actual vehicle imagery, not illustrative photography; verify backup and access control; run an end-to-end submission test; and establish a human alert/ownership workflow for `FIRST_CONTACT`.

## Next build layers
This delivery is **dynamic inventory + lead capture + first-action evidence**. It does **not** automatically discover all website listings, ingest a CRM, execute follow-up, send messages, structure financing, or sell cars without a salesperson. Those must be measured and built only after the core flow is verified.
