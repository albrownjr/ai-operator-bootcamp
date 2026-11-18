"""End-to-end tests: lead capture -> buyer evidence -> transaction outcome.

Uses a temporary SQLite file, mock leads and authorized admin API calls.
No messages are sent to customers.
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

VIN="1GNSCAKC2JR270624"
STOCK="JR270624"
URL="https://www.extremeautoplex.com/inventory/chevrolet/tahoe/jr270624/"

class DealExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        os.environ["LEADS_DB_PATH"]=self.tmp.name+"/test.db"
        os.environ["ADMIN_TOKEN"]="integration-test-admin-only"
        if "app" in sys.modules:
            del sys.modules["app"]
        import app
        self.appmod=app
        self.client=TestClient(app.app)
        self.auth={"Authorization":"Bearer integration-test-admin-only"}
        listing={"stock_number":STOCK,"vin":VIN,"year":2018,"make":"Chevrolet",
                 "model":"Tahoe","trim":"LS","vehicle_url":URL}
        result=self.client.post("/api/admin/inventory",json=listing,headers=self.auth)
        self.assertEqual(result.status_code,200,result.text)
        lead={"stock_number":STOCK,"first_name":"Example","last_name":"Buyer",
              "phone":"7135550101","email":"test@example.org","zip_code":"77379",
              "trade_status":"no","preferred_contact":"text","consent_contact":True}
        created=self.client.post("/api/leads",json=lead)
        self.assertEqual(created.status_code,201,created.text)
        self.lead_id=created.json()["lead_id"]
        self.sequence=0

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def packet(self):
        r=self.client.get(f"/api/admin/leads/{self.lead_id}/deal",headers=self.auth)
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def event(self,event_type,actor_type,statement=None,occurred_at=None,key=None):
        self.sequence+=1
        when=occurred_at or (datetime.now(timezone.utc)-timedelta(minutes=5-self.sequence/20)).isoformat()
        data={"event_type":event_type,"actor_type":actor_type,
              "actor_name":"Test actor","occurred_at":when,
              "source":"in-person conversation" if actor_type=="customer" else "CRM manual record",
              "statement":statement or event_type,"idempotency_key":key or f"event-{self.sequence}"}
        return self.client.post(f"/api/admin/leads/{self.lead_id}/events",json=data,headers=self.auth)

    def test_first_contact_to_sale(self):
        self.assertEqual(self.packet()["recommendation"]["code"],"FIRST_CONTACT")
        self.assertEqual(self.event("CALL_ATTEMPTED","salesperson").status_code,200)
        self.assertEqual(self.packet()["recommendation"]["code"],"SEND_CONTEXTUAL_TEXT")
        self.assertEqual(self.event("TEXT_SENT","salesperson").status_code,200)
        self.assertEqual(self.packet()["recommendation"]["code"],"DISCOVER_MOTIVATION")
        self.event("MOTIVATION_STATED","customer","Replacing family SUV")
        self.assertEqual(self.packet()["recommendation"]["code"],"DISCOVER_TIMELINE")
        self.event("TIMELINE_STATED","customer","Next week")
        self.assertEqual(self.packet()["recommendation"]["code"],"CLARIFY_PAYMENT_PATH")
        self.event("FINANCING_STATED","customer","Cash")
        self.assertEqual(self.packet()["recommendation"]["code"],"CONFIRM_CONDITION")
        self.event("VIDEO_SENT","salesperson")
        self.assertEqual(self.packet()["recommendation"]["code"],"CONFIRM_CONDITION")
        self.event("CONDITION_ACCEPTED","customer","Condition acceptable")
        self.assertEqual(self.packet()["recommendation"]["code"],"OBTAIN_APPROVED_NUMBERS")
        self.event("PRICE_APPROVED","management","Approved complete quote")
        self.assertEqual(self.packet()["recommendation"]["code"],"PRESENT_APPROVED_NUMBERS")
        self.event("QUOTE_SENT","salesperson")
        self.assertEqual(self.packet()["recommendation"]["code"],"CONFIRM_DEAL_REACTION")
        self.event("QUOTE_ACCEPTED","customer","Numbers acceptable")
        self.assertEqual(self.packet()["recommendation"]["code"],"COORDINATE_TRANSACTION")
        self.event("PURCHASE_CONFIRMED","management")
        self.assertEqual(self.packet()["recommendation"]["code"],"COMPLETE_DELIVERY")
        done=self.event("DELIVERY_COMPLETED","management","Signed and delivered")
        self.assertEqual(done.status_code,200,done.text)
        self.assertEqual(self.packet()["outcome"]["outcome"],"SOLD")
        self.assertEqual(self.packet()["recommendation"]["code"],"NONE")
        self.assertEqual(self.event("NOTE_ADDED","salesperson").status_code,422)

    def test_customer_claim_cannot_be_workflow_event(self):
        data={"event_type":"MOTIVATION_STATED","actor_type":"workflow",
              "actor_name":"automation","occurred_at":datetime.now(timezone.utc).isoformat(),
              "source":"workflow","statement":"Customer wants to buy","idempotency_key":"bad"}
        r=self.client.post(f"/api/admin/leads/{self.lead_id}/events",json=data,headers=self.auth)
        self.assertEqual(r.status_code,422)

    def test_duplicate_is_idempotent(self):
        t=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
        r=self.event("CALL_ATTEMPTED","salesperson",key="call-1",occurred_at=t)
        self.assertEqual(r.status_code,200,r.text)
        again=self.event("CALL_ATTEMPTED","salesperson",key="call-1",occurred_at=t)
        self.assertEqual(again.status_code,200)
        self.assertTrue(again.json()["duplicate"])
        self.assertEqual(len(self.packet()["timeline"]),1)

    def test_idempotency_key_cannot_rewrite_a_statement(self):
        t=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
        self.assertEqual(self.event("CALL_ATTEMPTED","salesperson",key="call-fixed",
                                    occurred_at=t,statement="No answer").status_code,200)
        changed=self.event("CALL_ATTEMPTED","salesperson",key="call-fixed",
                           occurred_at=t,statement="Talked for 20 minutes")
        self.assertEqual(changed.status_code,422)
        self.assertEqual(len(self.packet()["timeline"]),1)

    def test_sold_inventory_overrides_deal_next_action(self):
        r=self.client.post(f"/api/admin/inventory/{STOCK}/status",
                           json={"sold":True},headers=self.auth)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.packet()["recommendation"]["code"],"REVIEW_SOLD_VEHICLE")

    def test_lost_outcome_requires_management(self):
        self.assertEqual(self.event("DEAL_LOST","salesperson").status_code,422)
        self.assertEqual(self.event("DEAL_LOST","management","Buyer declined purchase").status_code,200)
        self.assertEqual(self.packet()["outcome"]["outcome"],"LOST")

    def test_timestamp_required_timezone(self):
        result=self.event("CALL_ATTEMPTED","salesperson",occurred_at="2026-11-18T10:00:00")
        self.assertEqual(result.status_code,422)

    def test_public_cannot_read_deal(self):
        r=self.client.get(f"/api/admin/leads/{self.lead_id}/deal")
        self.assertEqual(r.status_code,401)

if __name__=="__main__":
    unittest.main()
