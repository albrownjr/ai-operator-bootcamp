"""Synthetic-only HTTP transaction rehearsal against a LOCAL temporary container.

Never run on a public/production host. Requires explicit ALLOW_SYNTHETIC_SMOKE=1.
Uses fake contact details and writes test vehicle, lead and delivery records.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

assert os.environ.get("ALLOW_SYNTHETIC_SMOKE") == "1", "Synthetic smoke opt-in required"
BASE = os.environ.get("SALES_SMOKE_BASE_URL", "http://127.0.0.1:18000").rstrip("/")
assert BASE in {"http://127.0.0.1:18000", "http://localhost:18000"}, "Only local isolated containers permitted"
ADMIN = {"Authorization": "Bearer ci-operator-only"}
MANAGER = {**ADMIN, "X-Management-Token": "ci-manager-only"}

def api(path, body=None, headers=None, expected=200):
    request = Request(
        BASE+path,
        data=(json.dumps(body).encode("utf-8") if body is not None else None),
        headers={**(headers or {}), **({"Content-Type": "application/json"} if body is not None else {})},
        method=("POST" if body is not None else "GET"))
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        status = exc.code
        try: result = json.loads(exc.read().decode("utf-8"))
        except Exception: result = {}
    assert status == expected, f"{path} expected HTTP {expected}, got {status}: {result}"
    return result

stock = "CISMOKE"
vehicle = {
    "stock_number":stock,
    "vin":"1HGCV1F55JA122373",
    "year":2018,"make":"Honda","model":"Accord","trim":"EX-L",
    "vehicle_url":"https://www.extremeautoplex.com/inventory/honda/accord/cismoke/"
}
registered = api("/api/admin/inventory", vehicle, ADMIN)
assert registered["availability"] == "AVAILABLE"
lead = api("/api/leads",{
    "stock_number":stock,"first_name":"Synthetic","last_name":"CI-Buyer",
    "phone":"2815550101","email":"synthetic@example.org","zip_code":"77379",
    "trade_status":"no","preferred_contact":"text","consent_contact":True,
    "source":"synthetic_ci"
},expected=201)
lead_id = lead["lead_id"]
assert lead["vehicle"]["stock_number"] == stock
path = f"/api/admin/leads/{lead_id}/events"

# A fake delivery alone may not become a sale.
def event(kind,actor,manager=False,number=0,expect=200):
    return api(path,{
        "event_type":kind,"actor_type":actor,
        "actor_name":"Synthetic CI Tester","source":"synthetic_isolated_container",
        "occurred_at":datetime.now(timezone.utc).isoformat(),
        "statement":f"synthetic {kind} recorded solely for automated test",
        "idempotency_key":f"{kind}:{number}"
    }, MANAGER if manager else ADMIN, expected=expect)

event("DELIVERY_COMPLETED","management",False,number=99,expect=403)
event("DELIVERY_COMPLETED","management",True,number=98,expect=422)
event("CALL_ATTEMPTED","salesperson")
event("TEXT_SENT","salesperson")
event("MOTIVATION_STATED","customer")
event("TIMELINE_STATED","customer")
event("FINANCING_STATED","customer")
event("VIDEO_SENT","salesperson")
event("CONDITION_ACCEPTED","customer")
event("PRICE_APPROVED","management",True)
event("QUOTE_SENT","salesperson")
event("QUOTE_ACCEPTED","customer")
event("PURCHASE_CONFIRMED","management",True)
delivered = event("DELIVERY_COMPLETED","management",True)
assert delivered["deal"]["outcome"]["outcome"] == "SOLD"
assert delivered["deal"]["recommendation"]["code"] == "NONE"
assert all(t["status"] == "CANCELLED" for t in delivered["deal"]["tasks"] if t["source"] == "ENGINE")
metrics = api("/api/admin/metrics/funnel",headers=ADMIN)
assert metrics["overall"]["leads"] == 1
assert metrics["overall"]["sold_delivered"] == 1
assert metrics["by_source"]["synthetic_ci"]["sold_delivered"] == 1
assert metrics["incremental_sales_attribution"] is None

marked = api(f"/api/admin/inventory/{stock}/status",{"sold":True},ADMIN)
assert marked["availability"] == "SOLD"
api("/v/"+stock,expected=404)
print("PASS: isolated HTTP inquiry -> evidence -> approved purchase -> delivered SOLD -> source metrics -> SOLD inventory block")
print("Synthetic records only. Zero real customer contacts, zero real sales.")
