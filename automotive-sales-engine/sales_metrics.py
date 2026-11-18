"""Sales funnel evidence and audit metrics, not a predictive lead score.

All counts derive from the application database; legacy CRM activity is excluded
unless explicitly represented here. Never label these as dealership-wide results.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
import sqlite3

CONTACT={"CALL_ATTEMPTED","PHONE_CONVERSATION","TEXT_SENT","EMAIL_SENT"}
BUYER_RESPONSE={"MOTIVATION_STATED","TIMELINE_STATED","FINANCING_STATED",
                "CONDITION_ACCEPTED","CONDITION_CONCERN","QUOTE_ACCEPTED",
                "QUOTE_CONCERN","BUYER_DECLINED","DELIVERY_PREFERENCE"}

def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(timezone.utc)

def _pct(numerator: int, denominator: int) -> float|None:
    return round(100*numerator/denominator,2) if denominator else None

def funnel_report(conn: sqlite3.Connection) -> dict:
    rows=[dict(r) for r in conn.execute(
        "SELECT id,created_at,source,medium,campaign,stock_number,opportunity_status FROM leads").fetchall()]
    history=conn.execute("""SELECT lead_id,event_type,occurred_at FROM deal_history
        ORDER BY occurred_at""").fetchall()
    event_map=defaultdict(list)
    for row in history:
        event_map[row["lead_id"]].append(dict(row))
    outcome_map={r["lead_id"]:r["outcome"] for r in conn.execute(
        "SELECT lead_id,outcome FROM deal_outcomes").fetchall()}
    groups=defaultdict(list)
    for row in rows: groups[row["source"] or "direct"].append(row)

    def summarize(subset):
        total=len(subset)
        personal_contact=engaged=condition_accepted=quote_sent=quote_accepted=confirmed=sold=lost=0
        times=[]
        for lead in subset:
            events=event_map[lead["id"]]
            kinds={e["event_type"] for e in events}
            first=next((e for e in events if e["event_type"] in CONTACT),None)
            if first:
                personal_contact+=1
                delta=(_dt(first["occurred_at"])-_dt(lead["created_at"])).total_seconds()
                if delta>=0: times.append(delta)
            engaged+=bool(kinds & BUYER_RESPONSE)
            condition_accepted+="CONDITION_ACCEPTED" in kinds
            quote_sent+="QUOTE_SENT" in kinds
            quote_accepted+="QUOTE_ACCEPTED" in kinds
            confirmed+="PURCHASE_CONFIRMED" in kinds
            sold+=outcome_map.get(lead["id"])=="SOLD"
            lost+=outcome_map.get(lead["id"])=="LOST"
        return {
          "leads":total,"personally_contacted":personal_contact,"engaged":engaged,
          "condition_accepted":condition_accepted,"quotes_presented":quote_sent,
          "quotes_accepted":quote_accepted,"purchases_confirmed":confirmed,
          "sold_delivered":sold,"lost":lost,"open":total-sold-lost,
          "lead_to_contact_pct":_pct(personal_contact,total),
          "lead_to_quote_pct":_pct(quote_sent,total),
          "lead_to_sold_pct":_pct(sold,total),
          "quote_to_sold_pct":_pct(sold,quote_sent),
          "first_personal_contact": {
            "count_with_valid_timing":len(times),
            "within_5_min":sum(t<=300 for t in times),
            "within_10_min":sum(t<=600 for t in times),
            "within_30_min":sum(t<=1800 for t in times),
            "median_seconds":round(sorted(times)[len(times)//2]) if times else None,
          }
        }
    all_metrics=summarize(rows)
    by_source={name:summarize(group) for name,group in sorted(groups.items())}
    return {
        "scope":"THIS_APPLICATION_ONLY",
        "as_of":datetime.now(timezone.utc).isoformat(),
        "overall":all_metrics,"by_source":by_source,
        "baseline":None,
        "incremental_sales_attribution":None,
        "caveats":[
            "Results exclude DealerCenter or other systems not imported into this database.",
            "Events are entered by authorized users; independent CRM/delivery reconciliation is not implemented.",
            "A recorded SOLD outcome is not proof this software caused an incremental sale.",
            "A valid before/after baseline and comparable cohorts are necessary to evaluate lift.",
            "Unverified, backdated, or missing contact timestamps can distort response-time metrics.",
            "No lead scoring or automated credit decisions are performed."
        ],
    }
