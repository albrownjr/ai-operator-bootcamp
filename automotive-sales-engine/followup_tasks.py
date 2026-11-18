"""Action ownership and due-task evidence for the automotive sales workflow.

This module DOES NOT connect to DealerCenter, place calls, or send messages.
A CRM task must be explicitly entered/imported to be represented here.
"""
from __future__ import annotations
from datetime import datetime, timezone
from contextlib import nullcontext
from zoneinfo import ZoneInfo
import sqlite3
import uuid

STORE_TZ=ZoneInfo("America/Chicago")
CHANNELS={"CALL_TEXT","CALL_ONLY","TEXT_ONLY","EMAIL_ONLY"}
SOURCES={"ENGINE","CRM_MANUAL"}
ALLOWED_STATUS={"OPEN","CANCELLED"}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def parse_due(raw: str) -> datetime:
    dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
    if dt.tzinfo is None: raise ValueError("Due timestamp must contain timezone")
    return dt.astimezone(timezone.utc)

def init_tasks(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS sales_tasks (
      id TEXT PRIMARY KEY,
      lead_id TEXT NOT NULL REFERENCES leads(id),
      source TEXT NOT NULL CHECK(source IN ('ENGINE','CRM_MANUAL')),
      external_reference TEXT,
      objective TEXT NOT NULL,
      due_at TEXT NOT NULL,
      channel_policy TEXT NOT NULL CHECK(channel_policy IN ('CALL_TEXT','CALL_ONLY','TEXT_ONLY','EMAIL_ONLY')),
      status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','CANCELLED')),
      created_at TEXT NOT NULL,
      cancelled_at TEXT,
      cancel_reason TEXT,
      UNIQUE(source,external_reference)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_tasks_due ON sales_tasks(status,due_at)")

def create_task(conn: sqlite3.Connection, lead_id: str, due_at: str,
                objective: str, source: str="ENGINE", policy: str="CALL_TEXT",
                external_reference: str|None=None) -> dict:
    if source not in SOURCES or policy not in CHANNELS:
        raise ValueError("Invalid task source or contact channel policy")
    if not objective.strip() or len(objective)>500:
        raise ValueError("Objective required (max 500 characters)")
    if source=="CRM_MANUAL" and not (external_reference or "").strip():
        raise ValueError("CRM task requires an external reference")
    due=parse_due(due_at).isoformat()
    ident=str(uuid.uuid4())
    with nullcontext(conn):
        if not conn.execute("SELECT id FROM leads WHERE id=?",(lead_id,)).fetchone():
            raise KeyError("Unknown lead")
        try:
            conn.execute("""INSERT INTO sales_tasks
              (id,lead_id,source,external_reference,objective,due_at,channel_policy,created_at)
              VALUES(?,?,?,?,?,?,?,?)""",
              (ident,lead_id,source,external_reference,objective.strip(),due,policy,now_iso()))
        except sqlite3.IntegrityError as exc:
            if source=="CRM_MANUAL" and external_reference:
                old=conn.execute("SELECT * FROM sales_tasks WHERE source=? AND external_reference=?",
                                 (source,external_reference)).fetchone()
                if old and old["lead_id"]==lead_id:
                    return dict(old)
            raise ValueError("Task reference already in use") from exc
    return dict(conn.execute("SELECT * FROM sales_tasks WHERE id=?",(ident,)).fetchone())

def cancel_task(conn: sqlite3.Connection, task_id: str, reason: str) -> dict:
    if not reason.strip() or len(reason)>500: raise ValueError("Cancellation reason required")
    with nullcontext(conn):
        task=conn.execute("SELECT * FROM sales_tasks WHERE id=?",(task_id,)).fetchone()
        if not task: raise KeyError("Unknown task")
        if task["status"]=="CANCELLED": return dict(task)
        conn.execute("""UPDATE sales_tasks SET status='CANCELLED',cancelled_at=?,cancel_reason=?
           WHERE id=?""",(now_iso(),reason.strip(),task_id))
    return dict(conn.execute("SELECT * FROM sales_tasks WHERE id=?",(task_id,)).fetchone())

def task_state(conn: sqlite3.Connection, task: dict, at: datetime|None=None) -> dict:
    at=at or datetime.now(timezone.utc)
    if at.tzinfo is None: raise ValueError("Evaluation time must have timezone")
    due=parse_due(task["due_at"])
    local_due=due.astimezone(STORE_TZ).date()
    today=at.astimezone(STORE_TZ).date()
    # A task's personal contact can satisfy it on the due day. An overdue
    # task can be completed later, but must never be labelled on-time.
    rows=conn.execute("""SELECT event_type,actor_type,occurred_at FROM deal_history
        WHERE lead_id=? AND event_type IN ('CALL_ATTEMPTED','PHONE_CONVERSATION','TEXT_SENT','EMAIL_SENT')
        ORDER BY occurred_at""",(task["lead_id"],)).fetchall()
    valid=[r for r in rows
           if r["actor_type"] in ("salesperson","management")
           and parse_due(r["occurred_at"]) <= at.astimezone(timezone.utc)
           and local_due <= parse_due(r["occurred_at"]).astimezone(STORE_TZ).date() <= today]
    by_day={}
    for r in valid:
        day=parse_due(r["occurred_at"]).astimezone(STORE_TZ).date()
        by_day.setdefault(day,set()).add(r["event_type"])
    policy=task["channel_policy"]
    def complete(kinds):
        called=bool({"CALL_ATTEMPTED","PHONE_CONVERSATION"} & kinds)
        spoken="PHONE_CONVERSATION" in kinds
        texted="TEXT_SENT" in kinds
        emailed="EMAIL_SENT" in kinds
        return {"CALL_TEXT": called and (spoken or texted),
                "CALL_ONLY": called, "TEXT_ONLY": texted, "EMAIL_ONLY": emailed}[policy]
    done_day=next((day for day in sorted(by_day) if complete(by_day[day])),None)
    same_day=by_day.get(today,set())
    called=bool({"CALL_ATTEMPTED","PHONE_CONVERSATION"} & same_day)
    spoken="PHONE_CONVERSATION" in same_day
    texted="TEXT_SENT" in same_day
    emailed="EMAIL_SENT" in same_day
    if task["status"]=="CANCELLED": status="CANCELLED"
    elif done_day is not None: status="FULFILLED" if done_day==local_due else "FULFILLED_LATE"
    elif local_due>today: status="FUTURE"
    elif local_due<today: status="OVERDUE"
    else: status="DUE_TODAY"
    if status in ("FULFILLED","FULFILLED_LATE","CANCELLED"): action="NONE"
    elif policy=="CALL_TEXT" and called and not (spoken or texted):
        action="SEND_CONTEXTUAL_TEXT"
    elif policy in ("CALL_TEXT","CALL_ONLY"): action="PERSONAL_CALL"
    elif policy=="TEXT_ONLY": action="PERSONAL_TEXT"
    else: action="PERSONAL_EMAIL"
    return {**task,"computed_status":status,"required_action":action,
            "due_local_day":local_due.isoformat(),
            "completed_local_day":done_day.isoformat() if done_day else None,
            "personal_call_recorded_today":called,
            "meaningful_phone_conversation_recorded_today":spoken,
            "personal_text_recorded_today":texted,
            "personal_email_recorded_today":emailed,
            "note":"Personal contact must be documented; late fulfillment does not erase the missed due-day standard."}

def lead_tasks(conn: sqlite3.Connection, lead_id: str, at: datetime|None=None) -> list[dict]:
    rows=conn.execute("SELECT * FROM sales_tasks WHERE lead_id=? ORDER BY due_at,id",(lead_id,)).fetchall()
    return [task_state(conn,dict(row),at) for row in rows]

def due_queue(conn: sqlite3.Connection, at: datetime|None=None) -> list[dict]:
    rows=conn.execute("SELECT * FROM sales_tasks ORDER BY due_at,id").fetchall()
    tasks=[task_state(conn,dict(row),at) for row in rows]
    return [t for t in tasks if t["computed_status"] in ("OVERDUE","DUE_TODAY")]
