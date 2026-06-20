"""Unit tests for the pure layout logic in bin/monitor-layout.

These cover the bugs behind the v? fix:
  * fullscreen apps landing on the wrong (rotated, non-primary) screen because
    the primary was not monitor index 0;
  * a hotplug re-apply loop when an old saved layout's monitor order differed
    from a fresh canonical capture;
  * silent confusion between monitors that share an identical EDID.

No D-Bus / PyGObject needed: we load the CLI module by path and feed it recorded
GetCurrentState-shaped fixtures. Run with:  python3 -m unittest discover tests
"""

import importlib.util
import os
import unittest
from importlib.machinery import SourceFileLoader

# Load bin/monitor-layout (no .py extension) as a module via an explicit loader.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, os.pardir, "bin", "monitor-layout")
_loader = SourceFileLoader("monitor_layout", _SCRIPT)
_spec = importlib.util.spec_from_loader("monitor_layout", _loader)
ml = importlib.util.module_from_spec(_spec)
_loader.exec_module(ml)


def lm(connector, x, y, primary, transform=0, scale=1.0):
    return {
        "x": x, "y": y, "scale": scale, "transform": transform,
        "primary": primary, "monitors": [{"connector": connector, "mode_id": "m"}],
    }


def spec_monitor(connector, serial, vendor="XMI", product="Mi Monitor"):
    """A GetCurrentState monitor tuple: (spec, modes, props)."""
    spec = (connector, vendor, product, serial)
    modes = [("1920x1080@200.000", 1920, 1080, 200.0, 1.0, [1.0], {"is-current": True})]
    return (spec, modes, {})


class CanonicalOrderTests(unittest.TestCase):
    def test_primary_leads_even_when_captured_last(self):
        # The real bug: DP-5 (rotated, top, non-primary) was index 0; DP-4 was
        # primary but last. Fullscreen apps jumped to DP-5.
        lms = [
            lm("DP-5", 1920, 0, primary=False, transform=2),
            lm("DP-3", 0, 1080, primary=False),
            lm("DP-4", 1920, 1080, primary=True),
        ]
        order = [m["monitors"][0]["connector"] for m in ml.canonical_lms(lms)]
        self.assertEqual(order[0], "DP-4", "primary must be monitor index 0")
        # remaining sorted top-to-bottom, left-to-right
        self.assertEqual(order, ["DP-4", "DP-5", "DP-3"])

    def test_stable_when_already_canonical(self):
        lms = [
            lm("DP-4", 1920, 1080, primary=True),
            lm("DP-5", 1920, 0, primary=False, transform=2),
        ]
        self.assertEqual(ml.canonical_lms(lms), ml.canonical_lms(ml.canonical_lms(lms)))


class NormalizationTests(unittest.TestCase):
    def test_reordered_layouts_compare_equal(self):
        # Regression for the hotplug re-apply loop: a layout saved in the old
        # (non-primary-first) order must still equal a canonical capture.
        old_order = {"logical_monitors": [
            lm("DP-5", 1920, 0, primary=False, transform=2),
            lm("DP-3", 0, 1080, primary=False),
            lm("DP-4", 1920, 1080, primary=True),
        ]}
        new_order = {"logical_monitors": [
            lm("DP-4", 1920, 1080, primary=True),
            lm("DP-5", 1920, 0, primary=False, transform=2),
            lm("DP-3", 0, 1080, primary=False),
        ]}
        self.assertEqual(ml.normalized(old_order), ml.normalized(new_order))

    def test_int_float_and_tuple_quirks_dont_break_equality(self):
        a = {"logical_monitors": [lm("DP-4", 0, 0, primary=True, scale=1)]}
        b = {"logical_monitors": [lm("DP-4", 0, 0, primary=True, scale=1.0)]}
        self.assertEqual(ml.normalized(a), ml.normalized(b))


class CaptureTests(unittest.TestCase):
    def test_capture_from_orders_primary_first_and_keeps_modes(self):
        monitors = [spec_monitor("DP-5", "0x0"), spec_monitor("DP-4", "0x1")]
        logical = [
            (1920, 0, 1.0, 2, False, [("DP-5", "XMI", "Mi Monitor", "0x0")], {}),
            (1920, 1080, 1.0, 0, True, [("DP-4", "XMI", "Mi Monitor", "0x1")], {}),
        ]
        profile = ml.capture_from(monitors, logical)
        conns = [m["monitors"][0]["connector"] for m in profile["logical_monitors"]]
        self.assertEqual(conns[0], "DP-4")
        self.assertEqual(profile["logical_monitors"][0]["monitors"][0]["mode_id"],
                         "1920x1080@200.000")


class DuplicateIdentityTests(unittest.TestCase):
    def test_detects_shared_edid(self):
        # The actual hardware: DP-4 and DP-5 both serial 0x00000000.
        monitors = [
            spec_monitor("DP-3", "0x00000000", product="Other"),
            spec_monitor("DP-4", "0x00000000"),
            spec_monitor("DP-5", "0x00000000"),
        ]
        warning = ml.duplicate_identity_warning(monitors)
        self.assertIsNotNone(warning)
        self.assertIn("DP-4", warning)
        self.assertIn("DP-5", warning)
        self.assertNotIn("DP-3", warning)  # different product -> distinguishable

    def test_no_warning_when_all_unique(self):
        monitors = [
            spec_monitor("DP-4", "0x00000000"),
            spec_monitor("DP-5", "0x00009393"),  # the EDID override makes it unique
        ]
        self.assertIsNone(ml.duplicate_identity_warning(monitors))


if __name__ == "__main__":
    unittest.main()
