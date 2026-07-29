"""Unit tests for the CC-StatusLine renderer.

Run everything:      python3 tests/test_statusline.py -v
Run one class:       python3 tests/test_statusline.py TestPctColor -v
Run one test:        python3 tests/test_statusline.py TestPctColor.test_zero_is_green -v
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
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

    def test_infinite_duration_is_placeholder_not_an_exception(self):
        self.assertEqual(sl.format_duration(float("inf")), "--")

    def test_nan_duration_is_placeholder_not_an_exception(self):
        self.assertEqual(sl.format_duration(float("nan")), "--")

    def test_unparseable_duration_is_placeholder(self):
        self.assertEqual(sl.format_duration("soon"), "--")


class TestFormatDurationInteriorZero(unittest.TestCase):
    """max_parts must stop at an interior zero rather than close the gap.

    3d0h5m collapsed to "3d5m" sits next to the legitimate "3d5h" and is read
    as hours. A 7-day rate-limit window spends about an hour a day in it.
    """

    def test_interior_zero_truncates_instead_of_promoting(self):
        ms = (3 * 86400 + 0 * 3600 + 5 * 60) * 1000
        self.assertEqual(sl.format_duration(ms, max_parts=2, days=True), "3d")

    def test_interior_zero_hours_with_only_seconds_left(self):
        ms = (3 * 86400 + 7) * 1000
        self.assertEqual(sl.format_duration(ms, max_parts=2, days=True), "3d")

    def test_documented_countdowns_are_unchanged(self):
        cases = {
            45: "45s",
            2820: "47m",
            8040: "2h14m",
            277200: "3d5h",
            604800: "7d",
        }
        for seconds, expected in cases.items():
            with self.subTest(seconds=seconds):
                self.assertEqual(
                    sl.format_duration(seconds * 1000, max_parts=2, days=True),
                    expected,
                )

    def test_use_line_call_shape_is_bit_for_bit_unchanged(self):
        # render_usage calls format_duration(ms) with no kwargs. Every one of
        # these has an interior zero somewhere; none may be truncated.
        cases = {
            0: "0s",
            2712000: "45m12s",
            (25 * 3600 + 7) * 1000: "25h7s",           # zero minutes
            (2 * 3600 + 0 * 60 + 0) * 1000: "2h",
            (90 * 3600 + 0 * 60 + 30) * 1000: "90h30s",
            723000: "12m3s",
        }
        for ms, expected in cases.items():
            with self.subTest(ms=ms):
                self.assertEqual(sl.format_duration(ms), expected)

    def test_use_line_renders_an_interior_zero_duration_in_full(self):
        out = plain(sl.render_usage({"cost": {"total_duration_ms": (25 * 3600 + 7) * 1000}}))
        self.assertIn("25h7s", out)


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

    def test_infinity_is_absent_not_an_exception(self):
        # json.loads accepts a bare Infinity literal, so this is reachable.
        self.assertIsNone(sl.format_reset(float("inf"), now=self.NOW))

    def test_nan_is_absent_not_an_exception(self):
        self.assertIsNone(sl.format_reset(float("nan"), now=self.NOW))

    def test_negative_infinity_is_absent(self):
        self.assertIsNone(sl.format_reset(float("-inf"), now=self.NOW))


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

    def test_non_string_levels_are_absent_not_a_crash(self):
        # A dict is unhashable: EFFORT_COLORS.get would raise TypeError and
        # take down every line of the statusline, not just this segment.
        for level in ({"name": "high"}, ["high"], 3, True, 1.5):
            with self.subTest(level=level):
                self.assertIsNone(sl.effort_segment({"effort": {"level": level}}))


class TestParseModelName(unittest.TestCase):
    def test_two_digit_groups_render_dotted_version(self):
        out = sl.parse_model_name({
            "model": {"id": "claude-opus-4-6", "display_name": "Opus"},
        })
        self.assertEqual(out, "Opus 4.6")

    def test_single_digit_group_renders_bare_version(self):
        out = sl.parse_model_name({
            "model": {"id": "claude-opus-5", "display_name": "Opus"},
        })
        self.assertEqual(out, "Opus 5")

    def test_bracket_suffix_and_large_context_window(self):
        out = sl.parse_model_name({
            "model": {"id": "claude-opus-5[1m]", "display_name": "Opus"},
            "context_window": {"context_window_size": 1000000},
        })
        self.assertEqual(out, "Opus 5 (1M context)")

    def test_sonnet_single_digit_group(self):
        out = sl.parse_model_name({
            "model": {"id": "claude-sonnet-5", "display_name": "Sonnet"},
        })
        self.assertEqual(out, "Sonnet 5")

    def test_unrecognisable_id_falls_back_to_display_name(self):
        out = sl.parse_model_name({
            "model": {"id": "totally-unrecognisable", "display_name": "Mystery Model"},
        })
        self.assertEqual(out, "Mystery Model")


class TestRenderEnvironment(unittest.TestCase):
    def setUp(self):
        # The real get_resource_counts reads AND WRITES the shared
        # {tempdir}/claude-statusline-{user}/resources.json that the developer's
        # own running statusline uses. Calling it here would walk the entire
        # installed-plugin tree and then poison that cache with counts computed
        # for cwd=None (project-level resources skipped), leaving the real
        # statusline under-reporting for a full TTL.
        _orig = sl.get_resource_counts
        self.addCleanup(setattr, sl, "get_resource_counts", _orig)
        sl.get_resource_counts = lambda cwd: {"skills": 1, "mcp": 2, "hooks": 3}

    def _render(self, payload):
        return plain(sl.render_environment(payload))

    def test_the_stub_is_actually_in_effect(self):
        out = self._render({"version": "2.1.220"})
        self.assertIn("SK: 1 | MCP: 2 | Hooks: 3", out)

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

    def test_infinite_percentage_is_skipped_not_an_exception(self):
        self.assertIsNone(self._render(five={"used_percentage": float("inf")}))

    def test_nan_percentage_is_skipped_not_an_exception(self):
        self.assertIsNone(self._render(five={"used_percentage": float("nan")}))

    def test_infinite_reset_drops_the_parenthetical(self):
        out = self._render(
            five={"used_percentage": 42.4, "resets_at": float("inf")})
        self.assertEqual(out, "5h: 42%")


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

    def test_non_string_name_is_absent_not_a_python_repr(self):
        for name in ({"a": 1}, ["feat-x"], 42, 3.5):
            with self.subTest(name=name):
                self.assertIsNone(sl.worktree_segment({"worktree": {"name": name}}))

    def test_non_string_workspace_fallback_is_absent(self):
        self.assertIsNone(
            sl.worktree_segment({"workspace": {"git_worktree": {"a": 1}}}))

    def test_non_string_original_branch_drops_the_arrow_only(self):
        seg = sl.worktree_segment(
            {"worktree": {"name": "feat-x", "original_branch": {"a": 1}}})
        self.assertEqual(plain(seg), "WT: feat-x")


# The ambient git config is not ours to depend on. A global commit.gpgsign
# fails every commit here; a global core.hooksPath pointing at a hook that
# reads stdin would hang forever on an inherited terminal. GIT_CONFIG_GLOBAL
# and GIT_CONFIG_SYSTEM (Git 2.32+) neutralise both; the feature under test
# already requires 2.31+.
_GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(*args, **kw):
    kw.setdefault("env", _GIT_ENV)
    # capture_output rather than DEVNULL: CalledProcessError.stderr is the
    # only thing that makes a failure here diagnosable.
    subprocess.run(["git"] + list(args), check=True, timeout=30,
                   stdin=subprocess.DEVNULL, capture_output=True, **kw)


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class TestRepoName(unittest.TestCase):
    """The repo name must survive linked worktrees and submodules."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def _new_repo(self, name):
        path = os.path.join(self.root, name)
        os.makedirs(path)
        _git("init", "-q", "-b", "main", path)
        _git("-C", path, "commit", "-q", "--allow-empty", "-m", "init")
        return path

    def test_plain_repository(self):
        repo = self._new_repo("myrepo")
        self.assertEqual(sl.fetch_git_info(repo)["repo"], "myrepo")

    def test_subdirectory_of_a_plain_repository(self):
        # The most common real-world position, and the one that needs
        # --path-format=absolute: from a subdirectory of a plain repo the bare
        # --git-common-dir answers a RELATIVE "../../.git", whose parent's
        # basename is the literal string "..".
        repo = self._new_repo("myrepo")
        deep = os.path.join(repo, "sub", "deep")
        os.makedirs(deep)
        self.assertEqual(sl.fetch_git_info(deep)["repo"], "myrepo")

    def test_linked_worktree_reports_the_repository_name(self):
        repo = self._new_repo("myrepo")
        wt = os.path.join(self.root, "myrepo-feat-x")
        _git("-C", repo, "worktree", "add", "-q", "-b", "feat-x", wt)
        self.assertEqual(sl.fetch_git_info(wt)["repo"], "myrepo")

    def test_subdirectory_of_a_linked_worktree(self):
        repo = self._new_repo("myrepo")
        wt = os.path.join(self.root, "myrepo-feat-x")
        _git("-C", repo, "worktree", "add", "-q", "-b", "feat-x", wt)
        deep = os.path.join(wt, "sub", "deep")
        os.makedirs(deep)
        self.assertEqual(sl.fetch_git_info(deep)["repo"], "myrepo")

    def test_submodule_reports_its_own_name_not_modules(self):
        child = self._new_repo("child")
        parent = self._new_repo("parent")
        _git("-C", parent, "-c", "protocol.file.allow=always",
             "submodule", "add", "-q", child, "sub")
        _git("-C", parent, "commit", "-q", "-m", "add sub")
        self.assertEqual(sl.fetch_git_info(os.path.join(parent, "sub"))["repo"], "sub")

    def test_branch_is_still_the_worktree_branch(self):
        repo = self._new_repo("myrepo")
        wt = os.path.join(self.root, "myrepo-feat-x")
        _git("-C", repo, "worktree", "add", "-q", "-b", "feat-x", wt)
        self.assertEqual(sl.fetch_git_info(wt)["branch"], "feat-x")


class TestRepoNameNeverEmpty(unittest.TestCase):
    """An empty repo name is not dropped by join_segments — it is coloured.

    c("bold_white", "") is "\\033[1;37m\\033[0m": non-empty, therefore truthy,
    therefore kept, therefore "GIT:  | main | ...". The `if parent:` check this
    replaces looked like it guarded the case and did not, because the empty
    string appears one step later, at basename("/").
    """

    def _repo_name(self, common_dir, toplevel):
        _orig = sl.run_cmd
        self.addCleanup(setattr, sl, "run_cmd", _orig)
        sl.run_cmd = lambda cmd, **kw: common_dir
        return sl._repo_name("/anywhere", toplevel)

    def test_repository_at_a_filesystem_root_falls_back_to_toplevel(self):
        # dirname("/.git") is "/", and basename("/") is "".
        self.assertEqual(self._repo_name("/.git", "/srv/checkout"), "checkout")

    def test_normal_common_dir_still_wins_over_toplevel(self):
        self.assertEqual(self._repo_name("/home/u/myrepo/.git", "/home/u/wt"),
                         "myrepo")


class TestShippedFixturesRenderCleanly(unittest.TestCase):
    """Pipe the shipped fixtures through main() exactly as Claude Code does.

    The "no dangling separator" rule is this branch's central design
    invariant and was asserted only as English prose in
    commands/statusline-test.md. Here it is executable.
    """

    def _render(self, fixture):
        with open(os.path.join(_ROOT, fixture), encoding="utf-8") as f:
            payload = f.read()
        # Redirect HOME and the temp dir so the child neither reads the
        # developer's ~/.claude tree nor overwrites the resource cache that
        # their own running statusline depends on.
        sandbox = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, sandbox, True)
        env = {
            **os.environ,
            "HOME": sandbox, "USERPROFILE": sandbox,
            "TMPDIR": sandbox, "TEMP": sandbox, "TMP": sandbox,
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
        }
        proc = subprocess.run(
            [sys.executable, _SCRIPT], input=payload, text=True,
            capture_output=True, timeout=30, cwd=_ROOT, env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("statusline: error", proc.stdout)
        self.assertNotIn("statusline: parse error", proc.stdout)
        return [plain(line).strip() for line in proc.stdout.splitlines()]

    def test_both_fixtures_render_four_clean_lines(self):
        for fixture in ("test-payload.json", "test-payload-minimal.json"):
            with self.subTest(fixture=fixture):
                lines = self._render(fixture)
                self.assertEqual(len(lines), 4, lines)
                for line in lines:
                    self.assertFalse(line.endswith("|"), line)
                    self.assertFalse(line.startswith("|"), line)
                    self.assertNotIn("| |", line)

    def test_the_full_fixture_exercises_every_optional_section(self):
        out = "\n".join(self._render("test-payload.json"))
        self.assertIn("Eff:", out)
        self.assertIn("5h:", out)
        self.assertIn("7d:", out)
        self.assertIn("WT:", out)

    def test_the_minimal_fixture_omits_every_optional_section(self):
        out = "\n".join(self._render("test-payload-minimal.json"))
        for absent in ("Eff:", "5h:", "7d:", "WT:"):
            self.assertNotIn(absent, out)


class TestMainNeverRaisesOnHostilePayloads(unittest.TestCase):
    """Payload shapes that used to reach the last-resort handler in __main__.

    json.loads accepts bare Infinity and NaN literals, and nothing validates
    the types inside the payload, so each of these arrived as a live value.
    """

    HOSTILE = {
        "effort_level_is_a_dict": {"effort": {"level": {"name": "high"}}},
        "worktree_name_is_a_dict": {"worktree": {"name": {"a": 1}}},
        "original_branch_is_a_dict":
            {"worktree": {"name": "feat-x", "original_branch": {"a": 1}}},
        "duration_is_a_string": {"cost": {"total_duration_ms": "soon"}},
    }

    RAW_HOSTILE = {
        # Written as raw text: these literals have no Python-side equivalent
        # that survives json.dumps.
        "infinite_reset":
            '{"cwd":".","rate_limits":{"five_hour":'
            '{"used_percentage":42,"resets_at":Infinity}}}',
        "nan_reset":
            '{"cwd":".","rate_limits":{"five_hour":'
            '{"used_percentage":42,"resets_at":NaN}}}',
        "infinite_percentage":
            '{"cwd":".","rate_limits":{"five_hour":{"used_percentage":Infinity}}}',
    }

    def _assert_four_normal_lines(self, raw):
        sandbox = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, sandbox, True)
        env = {**os.environ, "HOME": sandbox, "USERPROFILE": sandbox,
               "TMPDIR": sandbox, "TEMP": sandbox, "TMP": sandbox}
        proc = subprocess.run(
            [sys.executable, _SCRIPT], input=raw, text=True,
            capture_output=True, timeout=30, cwd=_ROOT, env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("statusline: error", proc.stdout)
        self.assertEqual(len(proc.stdout.splitlines()), 4, proc.stdout)

    def test_typed_payloads(self):
        for name, payload in self.HOSTILE.items():
            with self.subTest(name=name):
                payload = {"cwd": ".", **payload}
                self._assert_four_normal_lines(json.dumps(payload))

    def test_non_finite_json_literals(self):
        for name, raw in self.RAW_HOSTILE.items():
            with self.subTest(name=name):
                self._assert_four_normal_lines(raw)


class TestPayloadDebugCapture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.flag = os.path.join(self._tmp.name, "statusline-debug")
        self.out = os.path.join(self._tmp.name, "statusline-payload.json")
        original = (sl.DEBUG_FLAG, sl.DEBUG_PAYLOAD)
        sl.DEBUG_FLAG, sl.DEBUG_PAYLOAD = self.flag, self.out
        self.addCleanup(lambda: setattr(sl, "DEBUG_PAYLOAD", original[1]))
        self.addCleanup(lambda: setattr(sl, "DEBUG_FLAG", original[0]))

    def test_writes_the_payload_when_the_flag_exists(self):
        open(self.flag, "w").close()
        sl.maybe_dump_payload('{"a": 1}')
        with open(self.out, encoding="utf-8") as f:
            self.assertEqual(f.read(), '{"a": 1}')

    def test_writes_nothing_without_the_flag(self):
        sl.maybe_dump_payload('{"a": 1}')
        self.assertFalse(os.path.exists(self.out))

    def test_unwritable_destination_never_raises(self):
        open(self.flag, "w").close()
        sl.DEBUG_PAYLOAD = os.path.join(self.out, "nope", "payload.json")
        sl.maybe_dump_payload('{"a": 1}')  # must not raise

    def test_surrogate_escaped_payload_never_raises(self):
        open(self.flag, "w").close()
        sl.maybe_dump_payload('hello \udcff world')  # must not raise

    def test_non_utf8_safe_content_round_trips(self):
        open(self.flag, "w").close()
        sl.maybe_dump_payload('{"branch": "café ← main"}')
        with open(self.out, encoding="utf-8") as f:
            self.assertIn("café", f.read())


if __name__ == "__main__":
    unittest.main()
