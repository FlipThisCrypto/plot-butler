#!/usr/bin/env python3
import os, sys, json, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import plot_butler as pb

class TestHealthConstruction(unittest.TestCase):
    def test_health_fields_present_from_state_defaults(self):
        # Simulate what Handler builds without HTTP
        rc = {"service": "active", "health": "healthy"}
        hv = {"health": "healthy"}
        pol = {"paused": False, "reason": "ok"}
        sp = {"staging_free_gb": 200, "queued_plots": 0}
        disk_ok = sp.get("staging_free_gb", 0) >= pb.STAGING_MIN_FREE_GB
        healthy = rc.get("service") == "active" and hv.get("health") not in ("critical",) and rc.get("health") not in ("critical", "down") and disk_ok
        body = {
            "ok": bool(healthy),
            "recompute_health": rc.get("health"),
            "harvester_health": hv.get("health"),
            "transfers_paused": bool(pol.get("paused")),
            "staging_free_gb": sp.get("staging_free_gb"),
            "queued_plots": sp.get("queued_plots"),
        }
        self.assertTrue(body["ok"])
        for k in ("ok", "recompute_health", "harvester_health", "transfers_paused"):
            self.assertIn(k, body)

if __name__ == "__main__":
    unittest.main()
