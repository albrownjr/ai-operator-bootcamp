# Framework-to-Code Readiness Audit — November 18, 2026

## Scope and evidence standard
Source of truth: complete locked 28-area Automotive Sales & Deal-Readiness framework, buyer-advancement addendum (Nov 17), customer-communication addendum (Nov 18), plus repository source at `automotive-sales-engine/`.

Statuses describe **source-level implementation**, not production readiness. A GitHub commit alone does not prove runtime tests passed, that the app is deployed, that DealerCenter is connected, or that any additional vehicle was sold.

**Mission:** Lead → Understand → Trust → Resolve → Structure Deal → Purchase Decision → Delivery. Appointments are supporting steps, not the main goal. Keep system unnamed and single-dealership-first.

## 28-area traceability

| # | Framework area | Source-level status | Evidence / most important gap |
|---|---|---|---|
| 1 | Traffic acquisition | Not implemented | Campaign attribution recorded; no ad buying or organic traffic operation |
| 2 | Content engine | Not implemented | No actual vehicle photo/video campaign production or publishing |
| 3 | Lead capture | Partial | VIN/stock form, consent, UTM fields; no external source integrations |
| 4 | Buyer profile completion | Not implemented | Customer fields stored; no verified field-completion engine |
| 5 | Customer state | Partial | Deal event stages exist; state logic does not support every buyer path |
| 6 | Primary blocker | Partial | Condition/quote concern and SOLD detection; not full blocker matrix |
| 7 | Speed-to-lead | Partial | First personal attempt timing in `sales_metrics.py`; no live alerts |
| 8 | Lead entry friction | Partial | Browser lead capture and manual event input; no CRM conversation importer |
| 9 | AI Sales Assistant | Partial | Deterministic next-action plans; no complete evidence-grounded LLM analysis/drafting |
| 10 | Dealership rules layer | Partial | Restricted event actors and price/transaction gates; management identity not independently authenticated |
| 11 | Mechanical message safeguards | Not implemented | Draft content scanning + approval workflow not yet built |
| 12 | Remote trust system | Not implemented | No per-VIN proof package or validated condition materials |
| 13 | Remote buyer journey | Partial | Generic deal timeline; remote-specific verified steps not fully implemented |
| 14 | Remote transaction capabilities | Discovery incomplete | Store policies, shipping/title, lender/e-signing approvals unknown |
| 15 | Local buyer journey | Partial | Generic buyer discovery and deal events; local delivery workflow incomplete |
| 16 | Remote trade workflow | Not implemented | One trade-status field and manually noted trade events only |
| 17 | Deal intelligence | Partial | Management quote gates and buyer acceptance; no structured approved OTD/trade/finance terms |
| 18 | Objection intelligence | Partial | Latest unresolved quote/condition objections; no full taxonomy or historical learning |
| 19 | Next-best-action | Partial | `deal_execution.py` + mandatory task prioritization; not independently validated against real buyer outcomes |
| 20 | Follow-up intelligence | Partial | `followup_tasks.py`: explicit due queue, channel rules, overdue/late tracking; no DealerCenter sync, contact automation or real alerting |
| 21 | KPI system | Partial | `sales_metrics.py`: app lead-to-contact, quote, sold, source metrics; not dealership-wide |
| 22 | Data flywheel | Not implemented | Historic events stored, no outcomes-based model/evaluation loop |
| 23 | Phase 0 dealership discovery | Incomplete | Operational permissions and actual approval paths not yet fully documented |
| 24 | Phase 0 baseline | Incomplete | No verified monthly lead volume, closing rate, remote completion, or gross baseline |
| 25 | V1 buyer profile / assistant | Partial | Basic form, buyer timeline, next-action packet; no full conversation drafting/rules |
| 26 | V2 sales intelligence | Partial prototype | Event chronology, follow-up and objection logic; not yet proven operational |
| 27 | V3 measurement and proof | Partial prototype | App funnel report; baseline and causal comparison missing |
| 28 | Future CRM/multi-store | Deferred intentionally | Not appropriate before single-store sales lift is measured |

## Critical gap repairs in this batch

### 1. False sales progression
**Previously:** a privileged API user could record `DELIVERY_COMPLETED` directly, producing a SOLD outcome without purchase confirmation. Gate and chronology also failed to account for later buyer objections.

**Changed:** `deal_execution.py` now requires management-recorded price approval before a quote can be logged as sent, a sent quote before acceptance, buyer quote acceptance before purchase confirmation, and purchase confirmation before delivery. Event timestamps must respect these dependencies, and the latest buyer quote objection/decline blocks purchase/delivery until buyer acceptance is recorded again. No automatic lender approval is inferred.

**Residual risk:** the single shared admin token and user-entered `actor_type=management` do NOT authenticate a manager's identity or validate a dealer-generated approval document. A production-grade approval workflow is still required.

### 2. Incomplete follow-up enforcement
**Previously:** there was only a suggested text after an unanswered call; due CRM tasks and actual same-day attempt requirements were not modeled.

**Changed:** `followup_tasks.py` creates an ENGINE-owned first contact task per captured lead, supports explicit CRM_MANUAL task records with unique references and due times, distinguishes OPEN, CANCELLED, DUE_TODAY, FUTURE, OVERDUE, FULFILLED and FULFILLED_LATE, enforces call + contextual text without a meaningful conversation when allowed, exposes due queues and integrates task priority into the deal packet and browser desk.

**Residual risk:** no DealerCenter API access. If a CRM task is not manually entered, the engine cannot know it exists. A recorded call/text is entered by a human and not independently verified against phone or messaging logs. An actual due task continues to require a personal call/text outside this app.

### 3. Chronology and changed buyer decisions
**Previously:** early QUOTE_CONCERN, CONDITION_CONCERN or BUYER_DECLINED flags could improperly persist or disappear as unrelated events were added; causal purchase events could be backdated.

**Changed:** event history is ordered by actual timezone-aware timestamp; the most recent relevant condition and pricing decision determines whether its issue remains open. Unrelated statements do not silently resolve concerns. Explicit re-engagement after a decline is distinguishable from a continuing decline. Purchase/delivery dependency checks compare actual timestamps, not only event counts.

**Residual risk:** this is a constrained event vocabulary and user-entered history, not an automatic natural-language understanding of every CRM conversation. No cross-source identity or message signature verification.

### 4. Missing performance proof
**Previously:** SOLD/LOST entries existed without an honest store-to-sale conversion view.

**Changed:** `sales_metrics.py` exposes per-source and overall lead, personal contact, engagement, condition-accepted, quoted, quote-accepted, confirmed, delivered-SOLD, LOST, response-time and conversion counts at protected `GET /api/admin/metrics/funnel`. Desk shows current funnel and due/overdue counts. Response times exclude negative timestamps rather than silently treating backdated data as fast contact.

**Residual risk:** no verified comparison baseline and no dealership-wide reconciliation. The report deliberately sets `baseline=null` and `incremental_sales_attribution=null`. It cannot yet prove that the software caused additional sales.

## Additional quality repairs
- Task status now distinguishes late fulfillment from same-day completion so an overdue task can be cleared honestly without erasing a missed due date.
- A duplicate event idempotency key with different statement/source/actor/timestamp is rejected rather than silently replacing or accepting conflicting evidence.
- Completing a deal cancels only the engine's own open first-contact tasks; explicitly entered CRM tasks require human reconciliation.
- Database helpers no longer commit in the middle of enclosing lead/SOLD/deal workflows; the lead submission now rechecks stock status under a write lock before saving the lead.
- `performance_baseline.py` adds append-only manual baselines with recorded dates, source, numerator/denominator counts and evidence reference. There is no auto-generated lift claim.
- Deal desk now includes a recorded funnel pulse, due/overdue counts, and manual CRM task entry/review; no calls, SMS, emails or DealerCenter changes are performed.
- `test_critical_controls.py` adds negative-path regression cases for phantom sales, event chronology, unresolved buyer concerns, CRM personal contact and reported funnel totals.
- **Testing remains unverified** until the configured CI workflows return passing results and a deployed app passes end-to-end tests.

## Release gates — do not declare sales production ready without evidence

- [ ] CI passes all `test_inventory_registry.py`, `test_decision_intelligence.py`, `test_deal_execution.py`, `test_critical_controls.py`
- [ ] Conduct actual cloud smoke test, including auth failure, duplicate lead, sold stock, contact/task status, and legal consent flow
- [ ] Establish secure, long random admin token, persistent storage, backups, authorization and stronger permission separation for management approvals
- [ ] Obtain dealership sign-off on advertised total prices, actual vehicle photos, privacy/consent and financing/remote deal workflows
- [ ] Import/record approved currently listed inventory; no more stale Tahoe campaign assumptions
- [ ] Determine reliable operational method to register/refresh website inventory
- [ ] Add at least one verified pre-system performance baseline (same lead source and similar time window)
- [ ] Validate a real (consented) buyer journey through sale/loss and reconcile it with the CRM/delivery outcome
- [ ] Confirm real same-day CRM follow-up compliance; avoid treating engine tasks as a CRM replacement
- [ ] Observe improvement in lead-to-contact and lead-to-SOLD rates before scaling spend or claiming competitive advantage

## Highest ROI next implementation, in order

1. **Execution correctness and trust:** complete CI/synthetic tests, correct any failures, protect PII and approved deal values. In progress.
2. **Actual personal follow-up:** reliable alerts and CRM reconciliation for all due tasks using approved access.
3. **Verified buyer decision evidence:** easy ingestion of real timestamped CRM histories; exact requested vehicle, condition response, local/remote path.
4. **Approved deal structure:** real manager pricing/financing/trade/shipping verification rather than text-only management assertions.
5. **Source-to-SOLD measurement:** baseline, cohort reporting, consistent sale definitions and reconciliation; monitor outcome lift.
6. **Acquisition optimization:** only after the execution funnel can reliably work a real buyer; market verified available vehicles.

## Deployment status

Repo `albrownjr/ai-operator-bootcamp`, branch `automotive-sales-engine`. Committed code does not mean successfully deployed or tested. Railway project creation was blocked earlier by expired trial billing; a working live environment has not been independently verified. No DealerCenter integration or direct customer outreach occurred in this batch.

**Project rule:** Every feature must answer: *Does this move the customer closer to being able to buy?*
