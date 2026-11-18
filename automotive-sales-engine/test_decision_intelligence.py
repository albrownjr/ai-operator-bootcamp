import unittest
from datetime import datetime, timezone, timedelta
from decision_intelligence import Evidence, decision_packet

NOW = datetime(2026, 11, 18, 16, 0, tzinfo=timezone.utc)

def ev(field, value, hours=0, verified_by="manager", buyer_stated=False):
    return Evidence(field, value, (NOW-timedelta(hours=hours)).isoformat(),
                    "approved_record" if verified_by else "public_listing",
                    verified_by, buyer_stated)

class DecisionPacketTests(unittest.TestCase):
    def test_no_evidence_blocks_all_sales_claims(self):
        p = decision_packet("JR270624", [], NOW)
        self.assertEqual(p["next_action"]["code"], "VERIFY_AVAILABILITY")
        self.assertFalse(p["guards"]["can_claim_available"])
        self.assertFalse(p["guards"]["can_quote_complete_price"])

    def test_public_listing_is_not_dealer_verification(self):
        p = decision_packet("JR270624", [ev("availability", True, verified_by="")], NOW)
        self.assertEqual(p["facts"]["availability"]["status"], "unverified")

    def test_stale_price_not_quoteable(self):
        p = decision_packet("JR270624", [ev("availability", True),
            ev("advertised_price", 17590, hours=25),
            ev("total_price", 18700)], NOW)
        self.assertEqual(p["facts"]["advertised_price"]["status"], "stale")
        self.assertFalse(p["guards"]["can_quote_complete_price"])

    def test_latest_evidence_wins(self):
        p = decision_packet("JR270624", [ev("availability", True, hours=5),
            ev("availability", False, hours=1)], NOW)
        self.assertEqual(p["facts"]["availability"]["value"], False)
        self.assertTrue(p["guards"]["can_claim_available"])

    def test_buyer_claim_requires_buyer_source(self):
        p = decision_packet("JR270624", [ev("buyer_timing", "tomorrow",
            verified_by="", buyer_stated=False)], NOW)
        self.assertEqual(p["facts"]["buyer_timing"]["status"], "unverified")

    def test_complete_evidence_returns_review(self):
        evidence = [ev(f, "confirmed", buyer_stated=f not in
                   {"availability","advertised_price","total_price","condition"},
                   verified_by="manager" if f in
                   {"availability","advertised_price","total_price","condition"} else "")
                   for f in ["availability","advertised_price","total_price","condition",
                             "buyer_timing","buyer_budget","financing_preference","trade","delivery"]]
        p = decision_packet("JR270624", evidence, NOW)
        self.assertTrue(p["is_deal_ready"])
        self.assertEqual(p["next_action"]["code"], "REVIEW_DEAL")

    def test_rejects_naive_and_future_timestamps(self):
        with self.assertRaises(ValueError):
            decision_packet("JR270624", [Evidence("availability", True, "2026-11-18T10:00:00", "x")], NOW)
        with self.assertRaises(ValueError):
            decision_packet("JR270624", [Evidence("availability", True, "2026-11-19T10:00:00Z", "x")], NOW)

if __name__ == "__main__":
    unittest.main()
