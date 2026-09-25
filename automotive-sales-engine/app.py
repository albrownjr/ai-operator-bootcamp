from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent
VOLUME_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
DEFAULT_DB = Path(VOLUME_DIR) / "leads.db" if VOLUME_DIR else BASE_DIR / "leads.db"
DB_PATH = Path(os.getenv("LEADS_DB_PATH", str(DEFAULT_DB)))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
CONSENT_VERSION = "2026-09-25-v1"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Vehicle Lead Capture", version="0.2.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

VEHICLE = {
    "year": 2018,
    "make": "Chevrolet",
    "model": "Tahoe",
    "trim": "LS Sport Utility 4D",
    "vin": "1GNSCAKC2JR270624",
    "stock_number": "JR270624",
    "mileage": 137069,
    "price": 17590,
    "exterior_color": "Red",
    "interior_color": "Gray",
    "engine": "5.3L V8 EcoTec3",
    "transmission": "Automatic",
    "drivetrain": "2WD",
    "location": "Spring, TX",
    "dealer": "Extreme Autoplex LLC",
}

_submissions: dict[str, deque[float]] = defaultdict(deque)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            phone_normalized TEXT NOT NULL,
            email TEXT NOT NULL,
            zip_code TEXT NOT NULL,
            trade_status TEXT NOT NULL,
            preferred_contact TEXT NOT NULL,
            consent_contact INTEGER NOT NULL,
            consent_marketing INTEGER NOT NULL DEFAULT 0,
            consent_version TEXT NOT NULL,
            consent_captured_at TEXT NOT NULL,
            ip_address TEXT,
            vehicle_vin TEXT NOT NULL,
            stock_number TEXT NOT NULL,
            vehicle_name TEXT NOT NULL,
            source TEXT,
            medium TEXT,
            campaign TEXT,
            creative TEXT,
            utm_id TEXT,
            utm_term TEXT,
            fbclid TEXT,
            gclid TEXT,
            referrer TEXT,
            landing_url TEXT,
            user_agent TEXT,
            opportunity_status TEXT NOT NULL DEFAULT 'NEW',
            next_action TEXT NOT NULL DEFAULT 'FIRST_CONTACT'
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS engine_events (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            lead_id TEXT NOT NULL,
            vehicle_vin TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            payload_json TEXT NOT NULL,
            processed_at TEXT,
            FOREIGN KEY(lead_id) REFERENCES leads(id)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone_normalized)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_vehicle ON leads(vehicle_vin)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_status ON engine_events(status, created_at)")


init_db()


class LeadIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    phone: str = Field(min_length=7, max_length=30)
    email: EmailStr
    zip_code: str = Field(min_length=5, max_length=10)
    trade_status: str
    preferred_contact: str
    consent_contact: bool
    consent_marketing: bool = False
    source: str | None = None
    medium: str | None = None
    campaign: str | None = None
    creative: str | None = None
    utm_id: str | None = None
    utm_term: str | None = None
    fbclid: str | None = None
    gclid: str | None = None
    referrer: str | None = None
    landing_url: str | None = None
    website: str | None = None

    @field_validator("trade_status")
    @classmethod
    def valid_trade(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"yes", "no", "unsure"}:
            raise ValueError("Invalid trade selection")
        return value

    @field_validator("preferred_contact")
    @classmethod
    def valid_contact(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"text", "call", "email"}:
            raise ValueError("Invalid contact preference")
        return value

    @field_validator("zip_code")
    @classmethod
    def valid_zip(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"\d{5}(?:-\d{4})?", value):
            raise ValueError("Invalid ZIP code")
        return value


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def enforce_rate_limit(ip: str) -> None:
    now = time.time()
    q = _submissions[ip]
    while q and q[0] < now - 3600:
        q.popleft()
    if len(q) >= 8:
        raise HTTPException(status_code=429, detail="Too many submissions. Please try again later.")
    q.append(now)


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise HTTPException(status_code=422, detail="Enter a valid 10-digit phone number.")
    return digits


def clean(value: str | None, limit: int) -> str:
    return (value or "").strip()[:limit]


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    return HTMLResponse('<a href="/v/JR270624">Open Tahoe lead page</a>')


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "stock_number": VEHICLE["stock_number"]}


@app.get("/v/{stock_number}")
def vehicle_page(stock_number: str) -> FileResponse:
    if stock_number.upper() != VEHICLE["stock_number"]:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return FileResponse(BASE_DIR / "index.html")


@app.get("/api/vehicle/{stock_number}")
def vehicle_data(stock_number: str) -> dict[str, Any]:
    if stock_number.upper() != VEHICLE["stock_number"]:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return VEHICLE


@app.post("/api/leads")
def create_lead(payload: LeadIn, request: Request) -> JSONResponse:
    if payload.website:
        return JSONResponse({"ok": True, "lead_id": None})
    if not payload.consent_contact:
        raise HTTPException(status_code=400, detail="Contact consent is required")

    ip = client_ip(request)
    enforce_rate_limit(ip)
    phone_normalized = normalize_phone(payload.phone)
    now = datetime.now(timezone.utc)
    created_at = now.isoformat()
    duplicate_cutoff = (now - timedelta(minutes=15)).isoformat()
    vehicle_name = f'{VEHICLE["year"]} {VEHICLE["make"]} {VEHICLE["model"]} {VEHICLE["trim"]}'

    with db() as conn:
        existing = conn.execute(
            """SELECT id FROM leads
               WHERE phone_normalized=? AND vehicle_vin=? AND created_at>=?
               ORDER BY created_at DESC LIMIT 1""",
            (phone_normalized, VEHICLE["vin"], duplicate_cutoff),
        ).fetchone()

        if existing:
            return JSONResponse({
                "ok": True,
                "lead_id": existing["id"],
                "duplicate": True,
                "opportunity_status": "NEW",
                "next_action": "FIRST_CONTACT",
            })

        lead_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())

        source = clean(payload.source, 100) or "direct"
        medium = clean(payload.medium, 100)
        campaign = clean(payload.campaign, 150)
        creative = clean(payload.creative, 150)

        conn.execute("""
        INSERT INTO leads (
            id,created_at,first_name,last_name,phone,phone_normalized,email,zip_code,
            trade_status,preferred_contact,consent_contact,consent_marketing,
            consent_version,consent_captured_at,ip_address,
            vehicle_vin,stock_number,vehicle_name,
            source,medium,campaign,creative,utm_id,utm_term,fbclid,gclid,
            referrer,landing_url,user_agent,opportunity_status,next_action
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'NEW','FIRST_CONTACT')
        """, (
            lead_id, created_at, payload.first_name.strip(), payload.last_name.strip(),
            payload.phone.strip(), phone_normalized, str(payload.email).strip().lower(),
            payload.zip_code.strip(), payload.trade_status, payload.preferred_contact,
            int(payload.consent_contact), int(payload.consent_marketing),
            CONSENT_VERSION, created_at, ip, VEHICLE["vin"], VEHICLE["stock_number"],
            vehicle_name, source, medium, campaign, creative, clean(payload.utm_id,150),
            clean(payload.utm_term,150), clean(payload.fbclid,500), clean(payload.gclid,500),
            clean(payload.referrer,500), clean(payload.landing_url,1200),
            request.headers.get("user-agent","")[:500],
        ))

        event_payload = {
            "lead_id": lead_id,
            "first_name": payload.first_name.strip(),
            "phone": payload.phone.strip(),
            "email": str(payload.email).strip().lower(),
            "trade_status": payload.trade_status,
            "preferred_contact": payload.preferred_contact,
            "vehicle": VEHICLE,
            "source": source,
            "campaign": campaign,
            "creative": creative,
            "opportunity_status": "NEW",
            "next_action": "FIRST_CONTACT",
        }

        conn.execute("""
        INSERT INTO engine_events
        (id,created_at,event_type,lead_id,vehicle_vin,status,payload_json)
        VALUES (?,?,'LEAD_CAPTURED',?,?,'PENDING',?)
        """, (event_id, created_at, lead_id, VEHICLE["vin"], json.dumps(event_payload)))

    return JSONResponse({
        "ok": True,
        "lead_id": lead_id,
        "event_id": event_id,
        "opportunity_status": "NEW",
        "next_action": "FIRST_CONTACT",
        "vehicle": {
            "vin": VEHICLE["vin"],
            "stock_number": VEHICLE["stock_number"],
            "name": vehicle_name,
        },
    }, status_code=201)


def require_admin(authorization: str | None) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="Admin access is not configured")
    if authorization != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid admin token")


@app.get("/api/admin/leads")
def list_leads(authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    require_admin(authorization)
    with db() as conn:
        rows = conn.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


@app.get("/api/admin/stats")
def stats(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(authorization)
    with db() as conn:
        leads = conn.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
        pending = conn.execute("SELECT COUNT(*) c FROM engine_events WHERE status='PENDING'").fetchone()["c"]
    return {"lead_count": leads, "pending_engine_events": pending}


@app.get("/api/admin/leads.csv")
def export_leads(authorization: str | None = Header(default=None)) -> StreamingResponse:
    require_admin(authorization)
    with db() as conn:
        rows = conn.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()

    out = io.StringIO()
    if rows:
        writer = csv.DictWriter(out, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )
