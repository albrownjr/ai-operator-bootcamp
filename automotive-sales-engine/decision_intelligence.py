"""Evidence-gated buyer decision intelligence; no external services or PII.

Designed to assess an individual vehicle inquiry without inventing facts,
finance terms, vehicle availability, or customer intent.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

ALLOWED = {"vehicle_identity", "availability", "advertised_price",
           "total_price", "condition", "buyer_timing", "buyer_budget",
           "financing_preference", "trade", "delivery"}
DEALER_FACTS = {"availability", "advertised_price", "total_price", "condition"}
MAX_AGE = {"availability": timedelta(hours=4),
           "advertised_price": timedelta(hours=24),
           "total_price": timedelta(hours=24),
           "condition": timedelta(days=14)}
ACTIONS = {
    "availability": ("VERIFY_AVAILABILITY", "Confirm vehicle availability with an authorized dealership source"),
    "advertised_price": ("VERIFY_PRICE", "Confirm the current, compliant advertised price"),
    "total_price": ("REQUEST_APPROVED_OTD", "Obtain dealership-approved total pricing and mandatory-fee disclosure"),
    "condition": ("VERIFY_CONDITION", "Obtain actual-vehicle evidence and disclose known imperfections"),
    "buyer_timing": ("ASK_TIMELINE", "Ask when the buyer hopes to purchase"),
    "buyer_budget": ("ASK_BUDGET", "Ask for the buyer's comfortable price range"),
    "financing_preference": ("CLARIFY_FINANCING", "Ask whether the buyer plans cash or financing"),
    "trade": ("CLARIFY_TRADE", "Ask whether a trade-in is involved"),
    "delivery": ("CLARIFY_DELIVERY", "Confirm pickup or remote-delivery needs"),
}
ORDER = ["availability", "advertised_price", "total_price", "condition",
         "buyer_timing", "buyer_budget", "financing_preference", "trade", "delivery"]

@dataclass(frozen=True)
class Evidence:
    field: str
    value: Any
    observed_at: str
    source: str
    verified_by: str = ""   # approval/source identity, never inferred
    buyer_stated: bool = False

def _timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Evidence timestamps must include timezone")
    return result.astimezone(timezone.utc)

def decision_packet(stock_number: str, evidence: list[Evidence],
                    now: datetime | None = None) -> dict[str, Any]:
    """Build a safe, explainable next-action packet from evidence only."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    if not stock_number.strip():
        raise ValueError("stock_number is required")
    latest: dict[str, Evidence] = {}
    for item in evidence:
        if item.field not in ALLOWED:
            raise ValueError(f"Unknown field: {item.field}")
        if not item.source.strip():
            raise ValueError("Evidence requires a source")
        t = _timestamp(item.observed_at)
        if t > now:
            raise ValueError("Future evidence timestamp")
        previous = latest.get(item.field)
        if previous is None or t >= _timestamp(previous.observed_at):
            latest[item.field] = item
    statuses: dict[str, dict[str, Any]] = {}
    for field in ORDER:
        item = latest.get(field)
        status = "missing"
        if item is not None:
            age = now - _timestamp(item.observed_at)
            if field in DEALER_FACTS and not item.verified_by.strip():
                status = "unverified"
            elif field in MAX_AGE and age > MAX_AGE[field]:
                status = "stale"
            elif field not in DEALER_FACTS and not item.buyer_stated:
                status = "unverified"
            elif item.value is None or item.value == "":
                status = "missing"
            else:
                status = "verified"
        statuses[field] = {
            "status": status,
            "source": item.source if item else None,
            "observed_at": item.observed_at if item else None,
            "value": item.value if item and status == "verified" else None,
        }
    blockers = [field for field in ORDER if statuses[field]["status"] != "verified"]
    next_field = blockers[0] if blockers else None
    action = ACTIONS[next_field] if next_field else ("REVIEW_DEAL", "Review the approved deal with the buyer")
    safe_to_quote_price = (statuses["advertised_price"]["status"] == "verified"
                           and statuses["total_price"]["status"] == "verified")
    safe_to_claim_available = (statuses["availability"]["status"] == "verified"
                              and statuses["availability"]["value"] is True)
    return {
        "stock_number": stock_number,
        "evaluated_at": now.isoformat(),
        "facts": statuses,
        "unresolved": blockers,
        "next_action": {"code": action[0], "description": action[1]},
        "guards": {
            "can_claim_available": safe_to_claim_available,
            "can_quote_complete_price": safe_to_quote_price,
            "can_draft_unconditional_offer": safe_to_claim_available and safe_to_quote_price
                                             and statuses["condition"]["status"] == "verified",
        },
        "is_deal_ready": len(blockers) == 0,
        "note": "Information readiness only; not approval, buyer intent, or purchase probability.",
    }
