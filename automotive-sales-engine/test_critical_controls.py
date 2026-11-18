"""Regression cases for four critical real-sales controls.

Synthetic-only records; no outreach or lender access.
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

STOCK="TESTA1"
VIN="1HGCV1F55JA122373"
URL="https://www.extremeautoplex.com/inventory/honda/accord/testa1/"

class SalesCriticalControls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        os.environ["LEADS_DB_PATH"]=self.tmp.name+"/test.db"
        os.environ["ADMIN_TOKEN"]="integration-admin-token"
        sys.modules.pop("app",None)
        import app
        self.db=app.db
        self.client=TestClient(app.app)
        self.auth={"Authorization":"Bearer integration-admin-token"}
        vehicle={"stock_number":STOCK,"vin":VIN,"year":2018,"make":"Honda",
                 "model":"Accord","trim":"EX-L","vehicle_url":URL}
        r=self.client.post("/api/admin/inventory",json=vehicle,headers=self.auth)
        self.assertEqual(r.status_code,200,r.text)
        customer={"stock_number":STOCK,"first_name":"Test","last_name":"Shopper",
                  "phone":"2815550101","email":"test@example.org","zip_code":"77379",
                  "trade_status":"no","preferred_contact":"text","consent_contact":True,
                  "source":"synthetic_suite"}
        r=self.client.post("/api/leads",json=customer)
        self.assertEqual(r.status_code,201,r.text)
        self.lead=r.json()["lead_id"]
        self.t=datetime.now(timezone.utc)-timedelta(minutes=2)
        self.n=0

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def event(self,etype,actor=None,when=None,text=None):
        self.n+=1
        actors={
          "PRICE_APPROVED":"management","PURCHASE_CONFIRMED":"management",
          "DELIVERY_COMPLETED":"management","DEAL_LOST":"management",
          "QUOTE_ACCEPTED":"customer","QUOTE_CONCERN":"customer",
          "CONDITION_CONCERN":"customer","CONDITION_ACCEPTED":"customer",
          "MOTIVATION_STATED":"customer","TIMELINE_STATED":"customer"}
        actor=actor or actors.get(etype,"salesperson")
        when=when or (self.t+timedelta(seconds=self.n)).isoformat()
        body={"event_type":etype,"actor_type":actor,
              "actor_name":"Recorded Test Actor","occurred_at":when,
              "source":"synthetic CRM evidence",
              "statement":text or etype,"idempotency_key":f"critical-{self.n}"}
        return self.client.post(f"/api/admin/leads/{self.lead}/events",
                                json=body,headers=self.auth)

    def packet(self):
        r=self.client.get(f"/api/admin/leads/{self.lead}/deal",headers=self.auth)
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def test_no_phantom_sale_without_purchase(self):
        self.assertEqual(self.event("DELIVERY_COMPLETED").status_code,422)
        self.assertIsNone(self.packet()["outcome"])
        self.assertEqual(self.event("PURCHASE_CONFIRMED").status_code,422)

    def test_unresolved_latest_quote_objection_blocks_sale(self):
        self.assertEqual(self.event("PRICE_APPROVED").status_code,200)
        self.assertEqual(self.event("QUOTE_SENT").status_code,200)
        self.assertEqual(self.event("QUOTE_ACCEPTED").status_code,200)
        self.assertEqual(self.event("QUOTE_CONCERN").status_code,200)
        self.assertEqual(self.event("PURCHASE_CONFIRMED").status_code,422)
        self.assertEqual(self.packet()["deal_progress_action"]["code"],"RESOLVE_QUOTE_CONCERN")
        self.assertEqual(self.event("QUOTE_ACCEPTED").status_code,200)
        self.assertEqual(self.event("PURCHASE_CONFIRMED").status_code,200)
        earlier=(self.t-timedelta(minutes=10)).isoformat()
        self.assertEqual(self.event("DELIVERY_COMPLETED",when=earlier).status_code,422)
        self.assertEqual(self.event("DELIVERY_COMPLETED").status_code,200)
        self.assertEqual(self.packet()["outcome"]["outcome"],"SOLD")

    def test_objection_persists_across_unrelated_customer_comment(self):
        self.assertEqual(self.event("CONDITION_CONCERN").status_code,200)
        self.assertEqual(self.event("TIMELINE_STATED").status_code,200)
        self.assertEqual(self.packet()["deal_progress_action"]["code"],"RESOLVE_CONDITION_CONCERN")
        self.assertEqual(self.event("CONDITION_ACCEPTED").status_code,200)
        self.assertNotEqual(self.packet()["deal_progress_action"]["code"],"RESOLVE_CONDITION_CONCERN")

    def test_actual_crm_task_requires_personal_call_and_text(self):
        today=datetime.now(timezone.utc)
        task={"due_at":today.isoformat(),"objective":"Call customer about selected car",
              "source":"CRM_MANUAL","external_reference":"test-crm-42",
              "channel_policy":"CALL_TEXT"}
        create=self.client.post(f"/api/admin/leads/{self.lead}/tasks",
                                json=task,headers=self.auth)
        self.assertEqual(create.status_code,200,create.text)
        r=self.client.get("/api/admin/tasks/due",headers=self.auth)
        self.assertEqual(r.status_code,200)
        self.assertTrue(any(t["external_reference"]=="test-crm-42" for t in r.json()))
        self.assertEqual(self.event("CALL_ATTEMPTED",when=today.isoformat()).status_code,200)
        pending=self.packet()["tasks"]
        crm=[t for t in pending if t["source"]=="CRM_MANUAL"][0]
        self.assertEqual(crm["computed_status"],"DUE_TODAY")
        self.assertEqual(crm["required_action"],"SEND_CONTEXTUAL_TEXT")
        self.assertEqual(self.event("TEXT_SENT",when=today.isoformat()).status_code,200)
        crm=[t for t in self.packet()["tasks"] if t["source"]=="CRM_MANUAL"][0]
        self.assertEqual(crm["computed_status"],"FULFILLED")

    def test_overdue_task_can_be_completed_late_without_erasing_missed_day(self):
        past=datetime.now(timezone.utc)-timedelta(days=3)
        task={"due_at":past.isoformat(),"objective":"Respond to actual buyer question",
              "source":"CRM_MANUAL","external_reference":"late-task-8",
              "channel_policy":"CALL_TEXT"}
        r=self.client.post(f"/api/admin/leads/{self.lead}/tasks",json=task,headers=self.auth)
        self.assertEqual(r.status_code,200,r.text)
        original=[t for t in self.packet()["tasks"] if t["external_reference"]=="late-task-8"][0]
        self.assertEqual(original["computed_status"],"OVERDUE")
        today=datetime.now(timezone.utc).isoformat()
        self.assertEqual(self.event("CALL_ATTEMPTED",when=today).status_code,200)
        self.assertEqual(self.event("TEXT_SENT",when=today).status_code,200)
        updated=[t for t in self.packet()["tasks"] if t["external_reference"]=="late-task-8"][0]
        self.assertEqual(updated["computed_status"],"FULFILLED_LATE")
        self.assertEqual(updated["required_action"],"NONE")

    def test_funnel_does_not_invent_baseline(self):
        r=self.client.get("/api/admin/metrics/funnel",headers=self.auth)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()["scope"],"THIS_APPLICATION_ONLY")
        self.assertIsNone(r.json()["baseline"])
        self.assertEqual(r.json()["overall"]["leads"],1)
        self.assertEqual(r.json()["overall"]["sold_delivered"],0)
        self.assertEqual(r.json()["by_source"]["synthetic_suite"]["leads"],1)
        self.assertEqual(self.event("DELIVERY_COMPLETED").status_code,422)
        self.assertEqual(self.client.get("/api/admin/metrics/funnel",
                             headers=self.auth).json()["overall"]["sold_delivered"],0)

    def test_metrics_and_tasks_are_admin_only(self):
        self.assertEqual(self.client.get("/api/admin/metrics/funnel").status_code,401)
        self.assertEqual(self.client.get("/api/admin/tasks/due").status_code,401)

if __name__=="__main__":
    unittest.main()
