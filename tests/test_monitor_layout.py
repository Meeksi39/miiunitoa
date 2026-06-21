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


def lm_id(connector, x, y, primary, serial, vendor="XMI", product="Mi Monitor",
          transform=0):
    """A logical-monitor dict carrying EDID identity, as a layout saved by the
    identity-aware capture() would store it."""
    m = lm(connector, x, y, primary, transform=transform)
    m["monitors"][0].update(vendor=vendor, product=product, serial=serial)
    return m


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


class IdentityCaptureTests(unittest.TestCase):
    def test_capture_records_edid_identity(self):
        monitors = [spec_monitor("DP-5", "0x0")]
        logical = [(1920, 0, 1.0, 2, True,
                    [("DP-5", "XMI", "Mi Monitor", "0x0")], {})]
        m = ml.capture_from(monitors, logical)["logical_monitors"][0]["monitors"][0]
        self.assertEqual((m["vendor"], m["product"], m["serial"]),
                         ("XMI", "Mi Monitor", "0x0"))

    def test_normalized_ignores_identity_so_old_equals_new(self):
        # A layout saved before identities existed must still equal a fresh
        # capture of the same geometry — otherwise the hotplug no-op check breaks.
        old = {"logical_monitors": [lm("DP-4", 0, 0, primary=True)]}
        new = {"logical_monitors": [lm_id("DP-4", 0, 0, True, "0x1")]}
        self.assertEqual(ml.normalized(old), ml.normalized(new))


class RemapTests(unittest.TestCase):
    def _layout_345(self):
        # Three identical panels on DP-3/4/5, as the dock first enumerated them.
        return {"logical_monitors": [
            lm_id("DP-4", 1920, 1080, True, "0x0"),
            lm_id("DP-5", 1920, 0, False, "0x0", transform=2),
            lm_id("DP-3", 0, 1080, False, "0x0"),
        ]}

    def test_remaps_onto_renamed_connectors_in_chain_order(self):
        # Dock came back as DP-6/7/8; remap should preserve sorted (chain) order.
        monitors = [spec_monitor("DP-6", "0x0"),
                    spec_monitor("DP-7", "0x0"),
                    spec_monitor("DP-8", "0x0")]
        out = ml.remap_connectors(self._layout_345(), monitors)
        by_pos = {(lm_["x"], lm_["y"]): lm_["monitors"][0]["connector"]
                  for lm_ in out["logical_monitors"]}
        # sorted old [DP-3,DP-4,DP-5] -> sorted present [DP-6,DP-7,DP-8]
        self.assertEqual(by_pos[(0, 1080)], "DP-6")     # was DP-3
        self.assertEqual(by_pos[(1920, 1080)], "DP-7")  # was DP-4 (primary)
        self.assertEqual(by_pos[(1920, 0)], "DP-8")     # was DP-5
        # geometry/primary untouched
        primary = [l for l in out["logical_monitors"] if l["primary"]][0]
        self.assertEqual((primary["x"], primary["y"]), (1920, 1080))

    def test_applicable_prefers_exact_when_connectors_present(self):
        monitors = [spec_monitor("DP-3", "0x0"), spec_monitor("DP-4", "0x0"),
                    spec_monitor("DP-5", "0x0")]
        layout = self._layout_345()
        self.assertIs(ml.applicable_profile(layout, monitors), layout)

    def test_applicable_remaps_when_connectors_renamed(self):
        monitors = [spec_monitor("DP-6", "0x0"), spec_monitor("DP-7", "0x0"),
                    spec_monitor("DP-8", "0x0")]
        out = ml.applicable_profile(self._layout_345(), monitors)
        self.assertIsNotNone(out)
        self.assertEqual(ml.connectors_of(out), {"DP-6", "DP-7", "DP-8"})

    def test_no_remap_for_pre_identity_layout(self):
        old = {"logical_monitors": [lm("DP-3", 0, 0, primary=True)]}  # no identity
        monitors = [spec_monitor("DP-6", "0x0")]
        self.assertIsNone(ml.remap_connectors(old, monitors))

    def test_no_remap_when_too_few_present(self):
        monitors = [spec_monitor("DP-6", "0x0"), spec_monitor("DP-7", "0x0")]  # only 2
        self.assertIsNone(ml.remap_connectors(self._layout_345(), monitors))

    def test_mixed_identities_map_unique_directly(self):
        # Laptop (unique) + two identical panels; only the panels get renamed.
        layout = {"logical_monitors": [
            lm_id("eDP-1", 0, 0, True, "0xLAP", vendor="SDC", product="Panel"),
            lm_id("DP-3", 1920, 0, False, "0x0"),
            lm_id("DP-4", 3840, 0, False, "0x0"),
        ]}
        monitors = [spec_monitor("eDP-1", "0xLAP", vendor="SDC", product="Panel"),
                    spec_monitor("DP-7", "0x0"), spec_monitor("DP-8", "0x0")]
        out = ml.remap_connectors(layout, monitors)
        conns = ml.connectors_of(out)
        self.assertIn("eDP-1", conns)            # unique identity preserved
        self.assertEqual(conns, {"eDP-1", "DP-7", "DP-8"})

    def test_remap_summary_lists_only_changed(self):
        saved = self._layout_345()
        monitors = [spec_monitor("DP-6", "0x0"), spec_monitor("DP-7", "0x0"),
                    spec_monitor("DP-8", "0x0")]
        applied = ml.remap_connectors(saved, monitors)
        summary = ml.remap_summary(saved, applied)
        self.assertIn("DP-3->DP-6", summary)
        self.assertIn("DP-5->DP-8", summary)


if __name__ == "__main__":
    unittest.main()
