#!/usr/bin/env python3
"""Offline tests for recompute / harvester transfer gating."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import plot_butler as pb  # noqa: E402


class TestParsers(unittest.TestCase):
    def test_recompute_line_regex(self):
        line = (
            "[1784633433323] Request from 100.101.40.76 for K32 C20 "
            "took 29820.9 ms (used_gpu = 1, is_fail = 0)"
        )
        m = pb._RECOMP_LINE.search(line)
        self.assertIsNotNone(m)
        self.assertEqual(float(m.group(1)), 29820.9)
        self.assertEqual(m.group(2), "1")
        self.assertEqual(m.group(3), "0")

    def test_harvester_line_regex_trailing_period(self):
        # Farmer log puts a period after the seconds value.
        line = (
            "2026-07-21T07:40:04.877 WARNING  Looking up qualities on "
            "/media/chiamain/96/plot-k32-c20-abc.plot took: 336.4042320949957. "
            "This should be below 20 seconds"
        )
        m = pb._HARVEST_RE.search(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "/media/chiamain/96/plot-k32-c20-abc.plot")
        self.assertEqual(float(m.group(2)), 336.4042320949957)


class TestTransferGate(unittest.TestCase):
    def setUp(self):
        pb._xfer_paused = False
        pb._pause_reasons.clear()

    def test_allows_when_healthy(self):
        rc = {
            "service": "active",
            "requests_recent": 10,
            "latency_ms": {"p90": 800.0, "max": 1200.0},
        }
        hv = {
            "samples": 5,
            "latency_s": {"p90": 2.0, "max": 4.0},
            "health": "healthy",
        }
        ok, reason, paused = pb.transfer_allowed(rc, hv)
        self.assertTrue(ok)
        self.assertFalse(paused)
        self.assertIn("ok", reason)

    def test_pauses_on_slow_recompute(self):
        rc = {
            "service": "active",
            "requests_recent": 10,
            "latency_ms": {"p90": 9000.0, "max": 12000.0},
        }
        hv = {"samples": 0, "latency_s": {}, "health": "unknown"}
        ok, reason, paused = pb.transfer_allowed(rc, hv)
        self.assertFalse(ok)
        self.assertTrue(paused)
        self.assertIn("recompute", reason)

    def test_pauses_on_slow_harvester(self):
        rc = {
            "service": "active",
            "requests_recent": 10,
            "latency_ms": {"p90": 500.0, "max": 900.0},
        }
        hv = {
            "samples": 20,
            "latency_s": {"p90": 40.0, "max": 80.0},
            "health": "critical",
        }
        ok, reason, paused = pb.transfer_allowed(rc, hv)
        self.assertFalse(ok)
        self.assertTrue(paused)
        self.assertIn("harvester", reason)

    def test_hysteresis_holds_until_cool(self):
        rc = {
            "service": "active",
            "requests_recent": 10,
            "latency_ms": {"p90": 9000.0, "max": 12000.0},
        }
        hv = {"samples": 0, "latency_s": {}, "health": "unknown"}
        pb.transfer_allowed(rc, hv)
        # Still warm — should hold.
        rc["latency_ms"] = {"p90": 3000.0, "max": 4000.0}
        ok, reason, paused = pb.transfer_allowed(rc, hv)
        self.assertFalse(ok)
        self.assertTrue(paused)
        # Cool enough to resume.
        rc["latency_ms"] = {"p90": 1000.0, "max": 1500.0}
        ok, reason, paused = pb.transfer_allowed(rc, hv)
        self.assertTrue(ok)
        self.assertFalse(paused)

    def test_constants_protect_farming(self):
        self.assertEqual(pb.MAX_ACTIVE_TRANSFERS, 1)
        self.assertLessEqual(pb.RSYNC_BWLIMIT_KBPS, 20000)
        self.assertLessEqual(pb.HARVESTER_PAUSE_S, 20.0)
        self.assertLess(pb.RECOMPUTE_RESUME_P90_MS, pb.RECOMPUTE_PAUSE_P90_MS)



class TestDestinationPick(unittest.TestCase):
    def test_stall_default(self):
        self.assertGreaterEqual(pb.TRANSFER_STALL_S, 60)

    def test_pick_destination_empty(self):
        self.assertIsNone(pb.pick_destination([], set(), {}))

    def test_pick_destination_avoids_worst_mount(self):
        choices = [
            {"mount": "/media/chiamain/a", "free_gb": 100},
            {"mount": "/media/chiamain/b", "free_gb": 500},
        ]
        hv = {"worst_plot": "/media/chiamain/b/plot-x.plot"}
        d = pb.pick_destination(choices, set(), hv)
        self.assertEqual(d["mount"], "/media/chiamain/a")


if __name__ == "__main__":
    unittest.main()
