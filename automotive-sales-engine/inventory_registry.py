"""Inventory registry for independently operated lead capture.

The public dealership website is the source for candidate listing details.
An explicit salesperson SOLD override always wins over future website observations.
No DealerCenter access, scraping, or implied live dealer-feed integration.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from contextlib import nullcontext
from urllib.parse import urlparse

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
STOCK_RE = re.compile(r"^[A-Z0-9-]{2,32}$")
ALLOWED_HOSTS = {"www.extremeautoplex.com", "extremeautoplex.com"}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_inventory(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS vehicles (
        stock_number TEXT PRIMARY KEY,
        vin TEXT NOT NULL UNIQUE,
        year INTEGER NOT NULL,
        make TEXT NOT NULL,
        model TEXT NOT NULL,
        trim TEXT NOT NULL DEFAULT '',
        price INTEGER,
        mileage INTEGER,
        vehicle_url TEXT NOT NULL,
        availability TEXT NOT NULL DEFAULT 'AVAILABLE'
            CHECK(availability IN ('AVAILABLE','SOLD')),
        source_observed_at TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        status_changed_at TEXT,
        status_actor TEXT,
        CHECK(year BETWEEN 1900 AND 2100),
        CHECK(price IS NULL OR price >= 0),
        CHECK(mileage IS NULL OR mileage >= 0)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS inventory_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_number TEXT NOT NULL,
        event_type TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        actor TEXT NOT NULL,
        details TEXT NOT NULL
    )""")


def _normalize(data: dict) -> dict:
    stock = str(data.get("stock_number", "")).strip().upper()
    vin = str(data.get("vin", "")).strip().upper()
    if not STOCK_RE.fullmatch(stock):
        raise ValueError("Invalid stock number")
    if not VIN_RE.fullmatch(vin):
        raise ValueError("Invalid VIN")
    url = str(data.get("vehicle_url", "")).strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or not parsed.path.startswith("/inventory/"):
        raise ValueError("Listing URL must be a public Extreme Autoplex inventory URL")
    year = int(data["year"])
    if not 1900 <= year <= 2100:
        raise ValueError("Invalid year")
    for key in ("make", "model"):
        if not str(data.get(key, "")).strip():
            raise ValueError(f"Missing {key}")
    price = data.get("price")
    mileage = data.get("mileage")
    price = None if price in (None, "") else int(price)
    mileage = None if mileage in (None, "") else int(mileage)
    if price is not None and price < 0 or mileage is not None and mileage < 0:
        raise ValueError("Price/mileage cannot be negative")
    observed = str(data.get("source_observed_at", "")).strip() or timestamp()
    dt = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Observation timestamp requires a timezone")
    if dt > datetime.now(timezone.utc):
        raise ValueError("Observation timestamp cannot be in the future")
    return {
        "stock_number": stock, "vin": vin, "year": year,
        "make": str(data["make"]).strip()[:80],
        "model": str(data["model"]).strip()[:80],
        "trim": str(data.get("trim") or "").strip()[:100],
        "price": price, "mileage": mileage,
        "vehicle_url": url, "source_observed_at": observed,
    }


def observe_listing(conn: sqlite3.Connection, data: dict, actor: str = "admin") -> dict:
    """Upsert observed listing, never reopening an explicitly SOLD vehicle."""
    item = _normalize(data)
    now = timestamp()
    with nullcontext(conn):
        existing = conn.execute("SELECT vin,availability,source_observed_at FROM vehicles WHERE stock_number=?",
                                (item["stock_number"],)).fetchone()
        if existing and existing["vin"] != item["vin"]:
            raise ValueError("Stock number belongs to a different VIN")
        if existing and datetime.fromisoformat(existing["source_observed_at"].replace("Z","+00:00")) > datetime.fromisoformat(item["source_observed_at"].replace("Z","+00:00")):
            raise ValueError("Stale listing observation")
        if existing:
            conn.execute("""UPDATE vehicles SET year=:year,make=:make,model=:model,trim=:trim,
                price=:price,mileage=:mileage,vehicle_url=:vehicle_url,
                source_observed_at=:source_observed_at,recorded_at=:recorded_at
                WHERE stock_number=:stock_number""", {**item,"recorded_at":now})
        else:
            conn.execute("""INSERT INTO vehicles
                (stock_number,vin,year,make,model,trim,price,mileage,vehicle_url,source_observed_at,recorded_at)
                VALUES (:stock_number,:vin,:year,:make,:model,:trim,:price,:mileage,:vehicle_url,:source_observed_at,:recorded_at)""",
                {**item,"recorded_at":now})
        conn.execute("""INSERT INTO inventory_audit(stock_number,event_type,occurred_at,actor,details)
                VALUES (?,?,?,?,?)""",
                (item["stock_number"], "LISTING_OBSERVED", now, actor, item["vehicle_url"]))
    return get_vehicle(conn, item["stock_number"])


def set_sold(conn: sqlite3.Connection, stock_number: str, sold: bool, actor: str = "salesperson") -> dict:
    """Only an explicit authorized admin operation changes SOLD/AVAILABLE state."""
    stock = stock_number.strip().upper()
    new_status = "SOLD" if sold else "AVAILABLE"
    now = timestamp()
    with nullcontext(conn):
        current = conn.execute("SELECT stock_number FROM vehicles WHERE stock_number=?", (stock,)).fetchone()
        if not current:
            raise KeyError("Unknown stock number")
        old_status = conn.execute("SELECT availability FROM vehicles WHERE stock_number=?", (stock,)).fetchone()["availability"]
        if old_status == new_status:
            return get_vehicle(conn, stock)
        conn.execute("""UPDATE vehicles SET availability=?, status_changed_at=?, status_actor=?
            WHERE stock_number=?""", (new_status,now,actor,stock))
        conn.execute("""INSERT INTO inventory_audit(stock_number,event_type,occurred_at,actor,details)
            VALUES (?,?,?,?,?)""", (stock,"STATUS_CHANGED",now,actor,new_status))
    return get_vehicle(conn,stock)


def get_vehicle(conn: sqlite3.Connection, stock_number: str) -> dict | None:
    row = conn.execute("SELECT * FROM vehicles WHERE stock_number=?", (stock_number.strip().upper(),)).fetchone()
    return dict(row) if row else None


def list_vehicles(conn: sqlite3.Connection, include_sold: bool = False) -> list[dict]:
    sql = "SELECT * FROM vehicles" + ("" if include_sold else " WHERE availability='AVAILABLE'") + " ORDER BY year DESC,make,model"
    return [dict(row) for row in conn.execute(sql).fetchall()]
