"""Append-only declared baseline records.

An entered baseline is NOT verified by this software; source proof and matching
lead cohorts are required before concluding that sales performance improved.
"""
from __future__ import annotations
from datetime import datetime, timezone
import sqlite3
import uuid

def init_baselines(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS sales_baselines (
        id TEXT PRIMARY KEY, start_day TEXT NOT NULL, end_day TEXT NOT NULL,
        lead_source TEXT NOT NULL, leads INTEGER NOT NULL, contacted INTEGER NOT NULL,
        quotes INTEGER NOT NULL, sold INTEGER NOT NULL,
        evidence_reference TEXT NOT NULL, recorded_by TEXT NOT NULL,
        recorded_at TEXT NOT NULL, CHECK(leads >= 0),
        CHECK(contacted >= 0),CHECK(quotes >= 0),CHECK(sold >= 0)
    )""")

def record_baseline(conn: sqlite3.Connection, data: dict) -> dict:
    def date(value):
        return datetime.strptime(str(value),"%Y-%m-%d").date()
    start=date(data["start_day"]);end=date(data["end_day"])
    if end < start:raise ValueError("Baseline end must not precede start")
    if (end-start).days > 366:raise ValueError("Baseline period exceeds one year")
    source=str(data.get("lead_source","")).strip()
    reference=str(data.get("evidence_reference","")).strip()
    actor=str(data.get("recorded_by","")).strip()
    if not source or not reference or not actor:raise ValueError("Source, evidence reference and recorder required")
    if len(source)>100 or len(reference)>500 or len(actor)>120:raise ValueError("Baseline text too long")
    counts={name:int(data[name]) for name in ("leads","contacted","quotes","sold")}
    if any(n<0 for n in counts.values()) or any(n>counts["leads"] for k,n in counts.items() if k!="leads"):
        raise ValueError("Funnel counts must be nonnegative and no greater than leads")
    ident=str(uuid.uuid4())
    with conn:
        conn.execute("""INSERT INTO sales_baselines
          (id,start_day,end_day,lead_source,leads,contacted,quotes,sold,
           evidence_reference,recorded_by,recorded_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
          (ident,start.isoformat(),end.isoformat(),source,counts["leads"],
           counts["contacted"],counts["quotes"],counts["sold"],reference,actor,
           datetime.now(timezone.utc).isoformat()))
    return dict(conn.execute("SELECT * FROM sales_baselines WHERE id=?",(ident,)).fetchone())

def list_baselines(conn: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM sales_baselines ORDER BY recorded_at DESC").fetchall()]
