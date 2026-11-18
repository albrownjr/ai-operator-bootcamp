"""Safe staging configuration: forbid real lead collection and public admin use."""
import os
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient


class LaunchSafetyTests(unittest.TestCase):
    def test_staging_rejects_leads_without_writing_private_data(self):
        with tempfile.TemporaryDirectory() as temp:
            previous={k:os.environ.get(k) for k in
                      ("LEADS_DB_PATH","LEAD_INTAKE_ENABLED","ADMIN_TOKEN","MANAGEMENT_TOKEN")}
            try:
                os.environ["LEADS_DB_PATH"]=temp+"/staging.db"
                os.environ["LEAD_INTAKE_ENABLED"]="false"
                os.environ.pop("ADMIN_TOKEN",None)
                os.environ.pop("MANAGEMENT_TOKEN",None)
                sys.modules.pop("app",None)
                import app
                with TestClient(app.app) as client:
                    response=client.post("/api/leads",json={
                      "stock_number":"UNKNOWN","first_name":"Synthetic","last_name":"Buyer",
                      "phone":"2815550101","email":"synthetic@example.org","zip_code":"77379",
                      "trade_status":"no","preferred_contact":"text","consent_contact":True})
                    self.assertEqual(response.status_code,503)
                    self.assertFalse(client.get("/health").json()["lead_intake_enabled"])
                    self.assertEqual(client.get("/api/admin/leads").status_code,503)
                with app.db() as conn:
                    self.assertEqual(conn.execute("SELECT count(*) FROM leads").fetchone()[0],0)
            finally:
                for key,value in previous.items():
                    if value is None:os.environ.pop(key,None)
                    else:os.environ[key]=value
                sys.modules.pop("app",None)


if __name__=="__main__":
    unittest.main()
