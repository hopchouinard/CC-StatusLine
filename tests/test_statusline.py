"""Unit tests for the CC-StatusLine renderer.

Run everything:      python3 tests/test_statusline.py -v
Run one class:       python3 tests/test_statusline.py TestPctColor -v
Run one test:        python3 tests/test_statusline.py TestPctColor.test_zero_is_green -v
"""

import importlib.util
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, os.pardir, "scripts", "statusline.py")

_spec = importlib.util.spec_from_file_location("statusline", _SCRIPT)
sl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sl)

_ANSI = re.compile(r"\033\[[0-9;]*m")


def plain(s):
    """Strip ANSI escapes so assertions read as plain text. None passes through."""
    return None if s is None else _ANSI.sub("", s)


class TestPctColor(unittest.TestCase):
    def test_none_is_dim_without_blink(self):
        self.assertEqual(sl.pct_color(None), ("dim", False))

    def test_zero_is_green(self):
        self.assertEqual(sl.pct_color(0), ("green", False))

    def test_boundary_50_is_green(self):
        self.assertEqual(sl.pct_color(50), ("green", False))

    def test_51_is_yellow(self):
        self.assertEqual(sl.pct_color(51), ("yellow", False))

    def test_boundary_75_is_yellow(self):
        self.assertEqual(sl.pct_color(75), ("yellow", False))

    def test_76_is_red(self):
        self.assertEqual(sl.pct_color(76), ("red", False))

    def test_boundary_90_is_red_without_blink(self):
        self.assertEqual(sl.pct_color(90), ("red", False))

    def test_91_blinks(self):
        self.assertEqual(sl.pct_color(91), ("red", True))

    def test_above_100_saturates_at_blinking_red(self):
        self.assertEqual(sl.pct_color(104), ("red", True))


class TestColorPrefix(unittest.TestCase):
    def test_plain_colour(self):
        self.assertEqual(sl.color_prefix("green", False), sl.COLORS["green"])

    def test_blink_is_layered_on(self):
        self.assertEqual(sl.color_prefix("red", True),
                         sl.COLORS["red"] + sl.COLORS["blink"])

    def test_unknown_colour_contributes_nothing(self):
        self.assertEqual(sl.color_prefix("chartreuse", False), "")

    def test_composes_with_pct_color(self):
        self.assertEqual(sl.color_prefix(*sl.pct_color(95)),
                         sl.COLORS["red"] + sl.COLORS["blink"])


class TestRenderContextWindowRefactor(unittest.TestCase):
    """The pct_color extraction must not change rendered output."""

    def _render(self, pct, size=200000):
        return plain(sl.render_context_window(
            {"context_window": {"used_percentage": pct, "context_window_size": size}}
        ))

    def test_bar_length_and_label(self):
        out = self._render(50)
        self.assertEqual(out, "CTX: " + "▓" * 15 + "░" * 15 + " 50% of 200K")

    def test_zero_percent_is_all_empty(self):
        self.assertEqual(self._render(0), "CTX: " + "░" * 30 + " 0% of 200K")

    def test_hundred_percent_is_all_filled(self):
        self.assertEqual(self._render(100), "CTX: " + "▓" * 30 + " 100% of 200K")

    def test_missing_percentage_renders_placeholder(self):
        self.assertEqual(self._render(None), "CTX: " + "░" * 30 + " --% of 200K")

    def test_missing_size_renders_placeholder(self):
        self.assertEqual(self._render(17, size=None),
                         "CTX: " + "▓" * 5 + "░" * 25 + " 17% of --")


class TestFormatDuration(unittest.TestCase):
    def test_existing_behaviour_is_unchanged(self):
        self.assertEqual(sl.format_duration(2712000), "45m12s")

    def test_none_is_placeholder(self):
        self.assertEqual(sl.format_duration(None), "--")

    def test_negative_is_placeholder(self):
        self.assertEqual(sl.format_duration(-1000), "--")

    def test_zero_is_zero_seconds(self):
        self.assertEqual(sl.format_duration(0), "0s")

    def test_days_are_rolled_into_hours_by_default(self):
        self.assertEqual(sl.format_duration(90000 * 1000), "25h")

    def test_days_flag_emits_a_day_component(self):
        self.assertEqual(sl.format_duration(90000 * 1000, days=True), "1d1h")

    def test_max_parts_caps_the_units(self):
        self.assertEqual(sl.format_duration(8073 * 1000, max_parts=2), "2h14m")

    def test_max_parts_does_not_pad_when_fewer_units_exist(self):
        self.assertEqual(sl.format_duration(45 * 1000, max_parts=2), "45s")


class TestFormatReset(unittest.TestCase):
    NOW = 1_800_000_000

    def test_missing_timestamp(self):
        self.assertIsNone(sl.format_reset(None, now=self.NOW))

    def test_past_timestamp(self):
        self.assertIsNone(sl.format_reset(self.NOW - 60, now=self.NOW))

    def test_exactly_now(self):
        self.assertIsNone(sl.format_reset(self.NOW, now=self.NOW))

    def test_unparseable_timestamp(self):
        self.assertIsNone(sl.format_reset("not-a-number", now=self.NOW))

    def test_under_a_minute_keeps_seconds(self):
        self.assertEqual(sl.format_reset(self.NOW + 45, now=self.NOW), "45s")

    def test_minutes_drop_noisy_seconds(self):
        # 2832s is 47m12s; the seconds are noise on a countdown this long.
        self.assertEqual(sl.format_reset(self.NOW + 2832, now=self.NOW), "47m")

    def test_hours_and_minutes(self):
        # 8073s is 2h14m33s.
        self.assertEqual(sl.format_reset(self.NOW + 8073, now=self.NOW), "2h14m")

    def test_days_and_hours(self):
        # 277200s is 3d5h exactly.
        self.assertEqual(sl.format_reset(self.NOW + 277200, now=self.NOW), "3d5h")

    def test_seven_days_does_not_render_as_hours(self):
        self.assertEqual(sl.format_reset(self.NOW + 7 * 86400, now=self.NOW), "7d")


if __name__ == "__main__":
    unittest.main()
