"""Evidence-first deal execution for independent vehicle sales.

All entries represent *recorded* observations, not automated customer contact.
Actual timestamps and actor types are mandatory. The system cannot manufacture
customer agreement, lending decisions, prices or SOLD outcomes.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any
import json
import sqlite3
import uuid

CUSTOMER = {"MOTIVATION_STATED","TIMELINE_STATED","FINANCING_STATED",
            "CONDITION_ACCEPTED","CONDITION_CONCERN","QUOTE_ACCEPTED",
            "QUOTE_CONCERN","BUYER_DECLINED","DELIVERY_PREFERENCE"}
SALESPERSON = {"CALL_ATTEMPTED","TEXT_SENT","EMAIL_SENT","VIDEO_SENT",
               "HISTORY_SENT","QUOTE_SENT","PHONE_CONVERSATION","CREDIT_APPLICATION_INVITED",
               "CREDIT_APPLICATION_RECEIVED","TRADE_DETAILS_COLLECTED",
               "DELIVERY_PLAN_PRESENTED"}
MANAGEMENT = {"PRICE_APPROVED","TRADE_APPROVED","FINANCING_STRUCTURE_CONFIRMED",
              "PURCHASE_CONFIRMED","DELIVERY_COMPLETED","DEAL_LOST"}
INTERNAL = {"NOTE_ADDED"}
ALL_TYPES = CUSTOMER | SALESPERSON | MANAGEMENT | INTERNAL
TERMINAL = {"DELIVERY_COMPLETED","DEAL_LOST"}
ACTORS = {"customer","salesperson","management","workflow"}
ACTOR_RULES = {**{x:{"customer"} for x in CUSTOMER},
               **{x:{"salesperson","management"} for x in SALESPERSON},
               **{x:{"management"} for x in MANAGEMENT},
               "NOTE_ADDED":{"salesperson","management","workflow"}}

def parse_timestamp(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return dt.astimezone(timezone.utc)

def init_deal_execution(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS deal_history (
        id TEXT PRIMARY KEY,
        lead_id TEXT NOT NULL REFERENCES leads(id),
        event_type TEXT NOT NULL,
        actor_type TEXT NOT NULL,
        actor_name TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        source TEXT NOT NULL,
        statement TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        UNIQUE(lead_id,idempotency_key)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_history_lead ON deal_history(lead_id,occurred_at,recorded_at)")
    conn.execute("""CREATE TABLE IF NOT EXISTS deal_outcomes (
        lead_id TEXT PRIMARY KEY REFERENCES leads(id),
        outcome TEXT NOT NULL CHECK(outcome IN ('SOLD','LOST')),
        event_id TEXT NOT NULL UNIQUE REFERENCES deal_history(id),
        recorded_at TEXT NOT NULL
    )""")

def record_event(conn: sqlite3.Connection, lead_id: str, payload: dict[str, Any]) -> dict:
    event_type = str(payload.get("event_type","")).upper()
    actor = str(payload.get("actor_type","")).lower()
    actor_name = str(payload.get("actor_name","")).strip()
    source = str(payload.get("source","")).strip()
    statement = str(payload.get("statement","")).strip()
    key = str(payload.get("idempotency_key","")).strip()
    occurred = str(payload.get("occurred_at","")).strip()
    if event_type not in ALL_TYPES or actor not in ACTORS or actor not in ACTOR_RULES[event_type]:
        raise ValueError("Invalid event type/actor combination")
    if not (actor_name and source and statement and key and occurred):
        raise ValueError("Event must include actor name, source, statement, timestamp and idempotency key")
    if len(statement)>3000 or len(source)>300 or len(actor_name)>120 or len(key)>120:
        raise ValueError("Event field too long")
    when = parse_timestamp(occurred)
    now = datetime.now(timezone.utc)
    if when>now+timedelta(minutes=2):
        raise ValueError("Future events are not allowed")
    if actor=="customer" and source=="workflow":
        raise ValueError("Automated workflow cannot be the source of customer statements")
    with conn:
        lead = conn.execute("SELECT id,preferred_contact,stock_number FROM leads WHERE id=?",(lead_id,)).fetchone()
        if not lead:
            raise KeyError("Unknown lead")
        prior = conn.execute("SELECT id,event_type FROM deal_history WHERE lead_id=? AND idempotency_key=?",
                             (lead_id,key)).fetchone()
        if prior:
            if prior["event_type"]!=event_type:
                raise ValueError("Idempotency key reused for different event")
            return {"event_id":prior["id"],"duplicate":True}
        if conn.execute("SELECT lead_id FROM deal_outcomes WHERE lead_id=?",(lead_id,)).fetchone():
            raise ValueError("Deal closed; reopen requires a separate explicit workflow")
        history = timeline(conn,lead_id)
        previous_types = {item["event_type"] for item in history}
        if event_type == "DELIVERY_COMPLETED" and "PURCHASE_CONFIRMED" not in previous_types:
            raise ValueError("Delivery cannot be completed without documented purchase confirmation")
        if event_type == "PURCHASE_CONFIRMED" and "QUOTE_ACCEPTED" not in previous_types:
            raise ValueError("Purchase confirmation requires a documented buyer acceptance")
        if event_type == "QUOTE_ACCEPTED" and "QUOTE_SENT" not in previous_types:
            raise ValueError("Quote acceptance requires an actual quote sent event")
        if event_type == "QUOTE_SENT" and "PRICE_APPROVED" not in previous_types:
            raise ValueError("Quote cannot be recorded as sent before management price approval")
        ident = str(uuid.uuid4())
        conn.execute("""INSERT INTO deal_history
            (id,lead_id,event_type,actor_type,actor_name,occurred_at,recorded_at,source,statement,idempotency_key)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (ident,lead_id,event_type,actor,actor_name,when.isoformat(),now.isoformat(),source,statement,key))
        if event_type in TERMINAL:
            outcome = "SOLD" if event_type=="DELIVERY_COMPLETED" else "LOST"
            conn.execute("""INSERT INTO deal_outcomes(lead_id,outcome,event_id,recorded_at)
                VALUES (?,?,?,?)""",(lead_id,outcome,ident,now.isoformat()))
            conn.execute("UPDATE leads SET opportunity_status=?, next_action='NONE' WHERE id=?",
                         (outcome,lead_id))
        else:
            action = next_action(timeline(conn,lead_id),dict(lead))
            vehicle = conn.execute("SELECT availability FROM vehicles WHERE stock_number=?", (lead["stock_number"],)).fetchone()
            if vehicle and vehicle["availability"]=="SOLD":
                action = {"stage":"INTERESTED","code":"REVIEW_SOLD_VEHICLE"}
            conn.execute("UPDATE leads SET opportunity_status=?,next_action=? WHERE id=?",
                         (action["stage"],action["code"],lead_id))
    return {"event_id":ident,"duplicate":False}

def timeline(conn: sqlite3.Connection, lead_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id,event_type,actor_type,actor_name,occurred_at,recorded_at,source,statement FROM deal_history WHERE lead_id=? ORDER BY occurred_at,recorded_at,id",
        (lead_id,)).fetchall()]

def next_action(events: list[dict], lead: dict | None = None) -> dict:
    """Prefer explicit last buyer decisions; do not infer acknowledgement from delivery."""
    types = {e["event_type"] for e in events}
    last_customer = next((e for e in reversed(events) if e["actor_type"]=="customer"),None)
    if "DELIVERY_COMPLETED" in types:
        return {"stage":"SOLD","code":"NONE","objective":"Sale completed; no active sales task","reason":"Management-recorded delivery"}
    if "DEAL_LOST" in types:
        return {"stage":"LOST","code":"NONE","objective":"Record loss reason; no unsolicited pursuit","reason":"Management-recorded loss"}
    if last_customer and last_customer["event_type"] == "BUYER_DECLINED":
        return {"stage":"INTERESTED","code":"REVIEW_BUYER_DECLINE",
                "objective":"Respect the buyer's decision; decide whether any contact is appropriate",
                "reason":"Buyer explicitly declined"}
    if last_customer and last_customer["event_type"] == "QUOTE_CONCERN":
        return {"stage":"DEAL_PLANNING","code":"RESOLVE_QUOTE_CONCERN",
                "objective":"Understand the specific quote concern; obtain approved clarification",
                "reason":"Latest buyer statement identifies quote concern"}
    if last_customer and last_customer["event_type"] == "CONDITION_CONCERN":
        return {"stage":"ENGAGED","code":"RESOLVE_CONDITION_CONCERN",
                "objective":"Resolve exact condition concern with evidence",
                "reason":"Latest buyer statement identifies condition concern"}
    has_contact = bool(types & {"CALL_ATTEMPTED","PHONE_CONVERSATION","TEXT_SENT","EMAIL_SENT"})
    if not has_contact:
        return {"stage":"NEW","code":"FIRST_CONTACT",
                "objective":"Make a permitted personal contact attempt about the requested vehicle",
                "reason":"No documented personal contact attempt"}
    if lead and lead.get("preferred_contact") in {"call","text"} and "CALL_ATTEMPTED" in types and "PHONE_CONVERSATION" not in types and "TEXT_SENT" not in types:
        return {"stage":"INTERESTED","code":"SEND_CONTEXTUAL_TEXT",
                "objective":"After an unanswered personal call, send a permitted contextual personal text",
                "reason":"Call without meaningful conversation does not complete call-plus-text follow-up"}
    if "MOTIVATION_STATED" not in types:
        return {"stage":"INTERESTED","code":"DISCOVER_MOTIVATION",
                "objective":"Ask one natural question about the reason for purchasing",
                "reason":"Buying motivation is unknown"}
    if "TIMELINE_STATED" not in types:
        return {"stage":"ENGAGED","code":"DISCOVER_TIMELINE",
                "objective":"Clarify the desired buying window and reason",
                "reason":"Motivation known; timeline unknown"}
    if "FINANCING_STATED" not in types:
        return {"stage":"ENGAGED","code":"CLARIFY_PAYMENT_PATH",
                "objective":"Understand cash or financing preference, without requesting unnecessary sensitive details",
                "reason":"Motivation/timeline known; purchase funding path unknown"}
    if "CONDITION_ACCEPTED" not in types:
        return {"stage":"ENGAGED","code":"CONFIRM_CONDITION",
                "objective":"Provide actual vehicle evidence and confirm the buyer's reaction",
                "reason":"Materials sent are not acceptance of vehicle condition"}
    if "PRICE_APPROVED" not in types:
        return {"stage":"DEAL_PLANNING","code":"OBTAIN_APPROVED_NUMBERS",
                "objective":"Obtain verified dealership-approved prices and applicable terms",
                "reason":"No verified deal structure"}
    if "QUOTE_SENT" not in types:
        return {"stage":"DEAL_PLANNING","code":"PRESENT_APPROVED_NUMBERS",
                "objective":"Present verified approved numbers and confirm buyer understanding",
                "reason":"Deal numbers authorized but not yet delivered"}
    if "QUOTE_ACCEPTED" not in types:
        return {"stage":"DEAL_PLANNING","code":"CONFIRM_DEAL_REACTION",
                "objective":"Ask how the buyer feels about the actual numbers",
                "reason":"Quote delivered is not quote accepted"}
    if "PURCHASE_CONFIRMED" not in types:
        return {"stage":"DEAL_READY","code":"COORDINATE_TRANSACTION",
                "objective":"Coordinate management-approved purchase paperwork, trade and delivery",
                "reason":"Buyer accepted the quote; transaction still requires completion"}
    return {"stage":"PURCHASE_DELIVERY","code":"COMPLETE_DELIVERY",
            "objective":"Verify completed delivery or record an accurate lost outcome",
            "reason":"Management confirmed purchase; delivery not yet recorded"}

def deal_packet(conn: sqlite3.Connection, lead_id: str) -> dict:
    lead = conn.execute("""SELECT id,first_name,vehicle_name,stock_number,preferred_contact,
        trade_status,opportunity_status,next_action,created_at FROM leads WHERE id=?""",(lead_id,)).fetchone()
    if not lead: raise KeyError("Unknown lead")
    events = timeline(conn,lead_id)
    action = next_action(events,dict(lead))
    inventory = conn.execute("SELECT availability FROM vehicles WHERE stock_number=?", (lead["stock_number"],)).fetchone()
    if inventory and inventory["availability"] == "SOLD" and action["stage"] not in ("SOLD","LOST"):
        action = {"stage":"INTERESTED","code":"REVIEW_SOLD_VEHICLE",
                  "objective":"Notify buyer appropriately and review available alternatives only if desired",
                  "reason":"Salesperson explicitly marked the requested vehicle SOLD"}
    outcome = conn.execute("SELECT outcome,recorded_at FROM deal_outcomes WHERE lead_id=?",(lead_id,)).fetchone()
    return {"lead":dict(lead),"timeline":events,"recommendation":action,
            "outcome":dict(outcome) if outcome else None,
            "human_approval_required":True,
            "note":"A workflow action is a recommendation, not evidence of executed contact or an approved deal."}
