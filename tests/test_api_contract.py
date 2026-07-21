#!/usr/bin/env python3
"""Contract checks for public state shape (offline defaults)."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import plot_butler as pb

class TestStateShape(unittest.TestCase):
    def test_initial_state_keys(self):
        required = {
            "name", "updated", "plot", "gpus", "recompute", "harvester",
            "drives", "temperatures", "network", "transfers", "history",
            "alerts", "transfer_policy",
        }
        self.assertTrue(required.issubset(set(pb.state)))

    def test_history_keys(self):
        self.assertIn("gpu", pb.state["history"])
        self.assertIn("transfers", pb.state["history"])
        self.assertIn("recompute_p90", pb.state["history"])

if __name__ == "__main__":
    unittest.main()
