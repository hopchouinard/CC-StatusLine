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


class TestJoinSegments(unittest.TestCase):
    def test_drops_none_without_leaving_a_separator(self):
        self.assertEqual(sl.join_segments("a", None, "b"), "a | b")

    def test_drops_empty_strings(self):
        self.assertEqual(sl.join_segments("a", "", "b"), "a | b")

    def test_trailing_none_leaves_no_trailing_separator(self):
        self.assertEqual(sl.join_segments("a", None), "a")

    def test_leading_none_leaves_no_leading_separator(self):
        self.assertEqual(sl.join_segments(None, "a"), "a")

    def test_all_absent_is_empty_string(self):
        self.assertEqual(sl.join_segments(None, None), "")

    def test_single_segment(self):
        self.assertEqual(sl.join_segments("a"), "a")


class TestEffortSegment(unittest.TestCase):
    def test_absent_field(self):
        self.assertIsNone(sl.effort_segment({}))

    def test_absent_level(self):
        self.assertIsNone(sl.effort_segment({"effort": {}}))

    def test_empty_level(self):
        self.assertIsNone(sl.effort_segment({"effort": {"level": ""}}))

    def test_each_known_level_renders_its_name(self):
        for level in ("low", "medium", "high", "xhigh", "max"):
            with self.subTest(level=level):
                seg = sl.effort_segment({"effort": {"level": level}})
                self.assertEqual(plain(seg), f"Eff: {level}")

    def test_max_uses_bold_red(self):
        seg = sl.effort_segment({"effort": {"level": "max"}})
        self.assertIn(sl.COLORS["bold_red"], seg)

    def test_max_does_not_blink(self):
        seg = sl.effort_segment({"effort": {"level": "max"}})
        self.assertNotIn(sl.COLORS["blink"], seg)

    def test_xhigh_and_max_are_visually_distinct(self):
        xhigh = sl.effort_segment({"effort": {"level": "xhigh"}}).replace("xhigh", "")
        top = sl.effort_segment({"effort": {"level": "max"}}).replace("max", "")
        self.assertNotEqual(xhigh, top)

    def test_unknown_level_renders_in_white_instead_of_raising(self):
        seg = sl.effort_segment({"effort": {"level": "ultra"}})
        self.assertEqual(plain(seg), "Eff: ultra")
        self.assertIn(sl.COLORS["white"], seg)


class TestRenderEnvironment(unittest.TestCase):
    def _render(self, payload):
        return plain(sl.render_environment(payload))

    def test_effort_sits_between_model_and_skills(self):
        out = self._render({
            "version": "2.1.220",
            "model": {"id": "claude-opus-5", "display_name": "Opus"},
            "effort": {"level": "high"},
        })
        self.assertIn("| Eff: high | SK:", out)

    def test_absent_effort_leaves_model_adjacent_to_skills(self):
        out = self._render({
            "version": "2.1.220",
            "model": {"id": "claude-sonnet-5", "display_name": "Sonnet"},
        })
        self.assertNotIn("Eff:", out)
        self.assertIn("| SK:", out)
        self.assertNotIn("|  |", out)


class TestRateLimitSegment(unittest.TestCase):
    NOW = 1_800_000_000

    def _payload(self, five=None, seven=None):
        limits = {}
        if five is not None:
            limits["five_hour"] = five
        if seven is not None:
            limits["seven_day"] = seven
        return {"rate_limits": limits} if limits else {}

    def _render(self, **kw):
        return plain(sl.rate_limit_segment(self._payload(**kw), now=self.NOW))

    def test_absent_field(self):
        self.assertIsNone(sl.rate_limit_segment({}, now=self.NOW))

    def test_empty_object(self):
        self.assertIsNone(sl.rate_limit_segment({"rate_limits": {}}, now=self.NOW))

    def test_both_windows(self):
        out = self._render(
            five={"used_percentage": 42.4, "resets_at": self.NOW + 8073},
            seven={"used_percentage": 68.0, "resets_at": self.NOW + 277200},
        )
        self.assertEqual(out, "5h: 42% (2h14m) | 7d: 68% (3d5h)")

    def test_only_five_hour(self):
        out = self._render(five={"used_percentage": 42.4, "resets_at": self.NOW + 8073})
        self.assertEqual(out, "5h: 42% (2h14m)")

    def test_only_seven_day(self):
        out = self._render(seven={"used_percentage": 68.0, "resets_at": self.NOW + 277200})
        self.assertEqual(out, "7d: 68% (3d5h)")

    def test_float_percentage_is_rounded(self):
        self.assertEqual(self._render(five={"used_percentage": 42.6}), "5h: 43%")

    def test_missing_reset_drops_the_parenthetical(self):
        self.assertEqual(self._render(five={"used_percentage": 42.4}), "5h: 42%")

    def test_past_reset_drops_the_parenthetical(self):
        out = self._render(five={"used_percentage": 42.4, "resets_at": self.NOW - 10})
        self.assertEqual(out, "5h: 42%")

    def test_overage_is_reported_not_clamped(self):
        self.assertEqual(self._render(five={"used_percentage": 104.2}), "5h: 104%")

    def test_unparseable_percentage_is_skipped(self):
        self.assertIsNone(self._render(five={"used_percentage": "lots"}))

    def test_above_90_blinks(self):
        seg = sl.rate_limit_segment(
            self._payload(five={"used_percentage": 95.0}), now=self.NOW)
        self.assertIn(sl.COLORS["blink"], seg)

    def test_below_50_does_not_blink(self):
        seg = sl.rate_limit_segment(
            self._payload(five={"used_percentage": 12.0}), now=self.NOW)
        self.assertNotIn(sl.COLORS["blink"], seg)


class TestRenderContextWindowWithLimits(unittest.TestCase):
    NOW = 1_800_000_000

    def test_limits_are_appended(self):
        out = plain(sl.render_context_window({
            "context_window": {"used_percentage": 17, "context_window_size": 200000},
            "rate_limits": {"five_hour": {"used_percentage": 42.0}},
        }))
        self.assertTrue(out.endswith("of 200K | 5h: 42%"), out)

    def test_no_trailing_separator_without_limits(self):
        out = plain(sl.render_context_window(
            {"context_window": {"used_percentage": 17, "context_window_size": 200000}}))
        self.assertTrue(out.endswith("of 200K"), out)


class TestWorktreeSegment(unittest.TestCase):
    def test_absent(self):
        self.assertIsNone(sl.worktree_segment({}))

    def test_empty_workspace(self):
        self.assertIsNone(sl.worktree_segment({"workspace": {}}))

    def test_full_object_shows_origin_branch(self):
        seg = sl.worktree_segment(
            {"worktree": {"name": "feat-x", "original_branch": "main"}})
        self.assertEqual(plain(seg), "WT: feat-x ← main")

    def test_without_original_branch_shows_name_only(self):
        seg = sl.worktree_segment({"worktree": {"name": "feat-x"}})
        self.assertEqual(plain(seg), "WT: feat-x")

    def test_workspace_fallback_for_hand_made_worktrees(self):
        seg = sl.worktree_segment({"workspace": {"git_worktree": "feat-x"}})
        self.assertEqual(plain(seg), "WT: feat-x")

    def test_worktree_object_takes_precedence_over_fallback(self):
        seg = sl.worktree_segment({
            "worktree": {"name": "from-object", "original_branch": "main"},
            "workspace": {"git_worktree": "from-workspace"},
        })
        self.assertEqual(plain(seg), "WT: from-object ← main")

    def test_empty_strings_count_as_absent(self):
        self.assertIsNone(sl.worktree_segment(
            {"worktree": {"name": ""}, "workspace": {"git_worktree": ""}}))

    def test_renders_even_when_name_matches_branch(self):
        # The segment's existence is the information: it says "not the main
        # checkout", which is otherwise expensive to notice.
        seg = sl.worktree_segment({"worktree": {"name": "feat-x"}})
        self.assertIsNotNone(seg)


if __name__ == "__main__":
    unittest.main()
