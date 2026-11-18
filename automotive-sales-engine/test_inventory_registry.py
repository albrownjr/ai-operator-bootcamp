"""Inventory invariants and integration smoke tests for dynamic vehicle intake."""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from inventory_registry import init_inventory, observe_listing, set_sold, get_vehicle, list_vehicles

VIN = "1GNSCAKC2JR270624"
URL = "https://www.extremeautoplex.com/inventory/chevrolet/tahoe/jr270624/"

def listing(stock="JR270624"):
    return {
        "stock_number": stock, "vin": VIN, "year": 2018,
        "make": "Chevrolet", "model": "Tahoe", "trim": "LS",
        "price": 17590, "mileage": 137069, "vehicle_url": URL,
        "source_observed_at": datetime.now(timezone.utc).isoformat(),
    }

class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_inventory(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_new_vehicle_is_available(self):
        record = observe_listing(self.conn, listing())
        self.assertEqual(record["availability"], "AVAILABLE")
        self.assertEqual(len(list_vehicles(self.conn)), 1)

    def test_sold_override_survives_website_refresh(self):
        observe_listing(self.conn, listing())
        set_sold(self.conn, "JR270624", True)
        observe_listing(self.conn, listing())
        self.assertEqual(get_vehicle(self.conn, "JR270624")["availability"], "SOLD")
        self.assertEqual(list_vehicles(self.conn), [])

    def test_only_explicit_reactivation_changes_sold_status(self):
        observe_listing(self.conn, listing())
        set_sold(self.conn, "JR270624", True)
        set_sold(self.conn, "JR270624", False)
        self.assertEqual(get_vehicle(self.conn, "JR270624")["availability"], "AVAILABLE")

    def test_stock_cannot_be_reassigned_another_vin(self):
        observe_listing(self.conn, listing())
        invalid = listing()
        invalid["vin"] = "1HGCV1F55JA122373"
        with self.assertRaises(ValueError):
            observe_listing(self.conn, invalid)

    def test_unapproved_domain_rejected(self):
        data = listing()
        data["vehicle_url"] = "https://fakeautoplex.example/inventory/car"
        with self.assertRaises(ValueError):
            observe_listing(self.conn, data)

    def test_no_phantom_inventory(self):
        self.assertIsNone(get_vehicle(self.conn, "UNKNOWN"))
        self.assertEqual(list_vehicles(self.conn), [])

    def test_audit_tracks_sold_decisions(self):
        observe_listing(self.conn, listing())
        set_sold(self.conn, "JR270624", True)
        events = self.conn.execute("SELECT event_type,details FROM inventory_audit ORDER BY id").fetchall()
        self.assertEqual([(x["event_type"], x["details"]) for x in events],
                         [("LISTING_OBSERVED", URL), ("STATUS_CHANGED", "SOLD")])

class LeadIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["LEADS_DB_PATH"] = self.tmp.name + "/leads.db"
        os.environ["ADMIN_TOKEN"] = "test-admin-token-only"
        import sys
        if "app" in sys.modules:
            del sys.modules["app"]
        from app import app, db
        from fastapi.testclient import TestClient
        self.db = db
        self.client = TestClient(app)
        self.auth = {"Authorization": "Bearer test-admin-token-only"}

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def test_vehicle_registration_and_sold_rejection(self):
        self.assertEqual(self.client.get("/v/JR270624").status_code, 404)
        self.assertEqual(self.client.post("/api/admin/inventory", json=listing(), headers=self.auth).status_code, 200)
        self.assertEqual(self.client.get("/v/JR270624").status_code, 200)
        self.assertIn("Tahoe", self.client.get("/v/JR270624").text)
        payload = dict(stock_number="JR270624",first_name="Test",last_name="Buyer",
          phone="7135550101",email="example@example.org",zip_code="77379",
          trade_status="no", preferred_contact="text", consent_contact=True)
        first = self.client.post("/api/leads", json=payload)
        self.assertEqual(first.status_code, 201, first.text)
        second = self.client.post("/api/leads", json=payload)
        self.assertTrue(second.json()["duplicate"])
        with self.db() as conn:
            lead = conn.execute("SELECT stock_number,vehicle_vin FROM leads").fetchone()
            events = conn.execute("SELECT count(*) FROM engine_events").fetchone()[0]
        self.assertEqual((lead["stock_number"],lead["vehicle_vin"]),( "JR270624", VIN))
        self.assertEqual(events, 1)
        self.assertEqual(self.client.post("/api/admin/inventory/JR270624/status",
                          json={"sold": True}, headers=self.auth).status_code, 200)
        self.assertEqual(self.client.get("/v/JR270624").status_code, 404)
        self.assertEqual(self.client.post("/api/leads",json=payload).status_code,409)
        self.assertEqual(self.client.post("/api/admin/inventory",json=listing(),headers=self.auth).json()["availability"],"SOLD")
        self.assertEqual(self.client.get("/api/vehicles").json(), [])

    def test_admin_required(self):
        self.assertEqual(self.client.post("/api/admin/inventory", json=listing()).status_code, 401)
        self.assertEqual(self.client.get("/api/admin/inventory").status_code, 401)

if __name__ == "__main__":
    unittest.main()
