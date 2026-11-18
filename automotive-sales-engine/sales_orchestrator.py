"""First sales action from a captured vehicle inquiry.

Buyer-first sequencing: motivation -> timeline -> finances; vehicle verification
and explicit buyer requests may run in parallel. Never send automatically.
"""
from decision_intelligence import Evidence, decision_packet


def first_contact_plan(lead: dict, vehicle: dict) -> dict:
    name = " ".join(str(vehicle.get(k) or "").strip() for k in ("year","make","model","trim")).strip()
    channel = lead.get("preferred_contact", "text")
    evidence = [Evidence("availability", vehicle["availability"] == "AVAILABLE",
                         vehicle["source_observed_at"], "extremeautoplex.com",
                         verified_by="owner_inventory_rule")]
    decision = decision_packet(vehicle["stock_number"], evidence)
    return {
        "decision_snapshot": decision,
        "stage": "INTERESTED",
        "owner": "salesperson",
        "action": "FIRST_CONTACT",
        "objective": "Establish the buyer's motivation for this purchase, unless already known.",
        "reason": "A vehicle inquiry establishes interest, not acceptance of condition, price, or financing.",
        "first_question": "What are you hoping to accomplish with your next vehicle purchase?",
        "customer_vehicle": {"stock_number": vehicle["stock_number"],"vin":vehicle["vin"],"name":name},
        "preferred_channel": channel,
        "approval_required": True,
        "automated_outreach": False,
        "next_if_answered": "Record exact customer statement/time; determine timeline next, then finances if appropriate.",
        "next_if_no_response": "Follow dealership CRM due-task rules and permitted contact channels; no fabricated urgency.",
        "facts_known": ["Vehicle selected", "Contact preference", "Trade selection"],
        "facts_unknown": ["Buying motivation", "Purchase timeline", "Condition acceptance", "Deal acceptance"],
    }
