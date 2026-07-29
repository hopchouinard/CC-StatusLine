# Effort, Rate Limits, and Worktree Sections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three statusline sections — reasoning effort on ENV, 5-hour and 7-day rate limit usage on CTX, worktree name and origin branch on GIT — all sourced from payload fields Claude Code already sends, plus a fix for the repo name being wrong inside linked worktrees.

**Architecture:** Each new section is a pure function of the payload dict returning `str | None`. A shared `join_segments` helper joins the truthy ones with the separator, so a missing payload field produces no segment *and* no dangling separator. Threshold colouring is extracted from `render_context_window` into a shared `pct_color` so the three places that now need it cannot drift apart.

**Tech Stack:** Python 3 standard library only. `unittest` for tests. No third-party dependencies, no build step.

**Spec:** `Docs/superpowers/specs/2026-07-28-effort-ratelimits-worktree-design.md`

**Branch:** `feat/effort-ratelimits-worktree` (already created; the spec commit `2dd9ae0` is its tip)

## Global Constraints

- **Python 3 standard library only.** No new imports beyond `importlib`, `shutil`, `subprocess`, `tempfile`, `unittest` in the test file. The script's runtime imports must not grow.
- **Must run on macOS, Linux, and Windows.** `python3` on the former two, `python` on Windows.
- **No backslash escapes inside f-string replacement fields.** `f"{c('dim', '←')}"` is a `SyntaxError` before Python 3.12. Escapes in the *literal* portion of an f-string are fine, which is why the existing `f"↑{up}"` works. Hoist any escape used inside `{...}` to a module constant.
- **The statusline must never raise.** `main`'s blanket `try/except` is the last resort, not the design. Every new helper degrades to `None` or a fallback on bad input.
- **Git 2.31+** is required for `--path-format=absolute`. When the flag is unavailable the code falls back to today's behaviour rather than failing.
- **Every new segment builder returns `str | None`.** Never an empty string, never a pre-joined separator.
- **No `shell=True`.** All subprocess calls use argument lists, per the project's existing security posture.
- **Commit after every task.** Each task ends green.

## File Structure

| File | Status | Responsibility |
| --- | --- | --- |
| `scripts/statusline.py` | Modify | All rendering. Gains 6 helpers, 2 constants; 5 existing functions change. |
| `tests/test_statusline.py` | Create | Unit tests for the pure helpers plus git integration tests. |
| `test-payload.json` | Modify | Fixture with all optional fields **present**. |
| `test-payload-minimal.json` | Create | Fixture with all optional fields **absent**. |
| `commands/statusline-test.md` | Modify | Runs both fixtures. |
| `README.md` | Modify | Output block, sections table, conditional-sections note, debug capture, colour thresholds. |
| `.claude-plugin/plugin.json` | Modify | Version 1.5.2 → 1.6.0. |

The script stays a single file. It is 640 lines whose main virtue is being readable top to bottom, and the spec explicitly rejected splitting it into a segment registry.

---

### Task 1: Test harness and shared threshold colouring

Establishes the test file and extracts the 50/75/90/blink ladder that three sections will share. Pure refactor of `render_context_window` — output is byte-identical.

**Files:**
- Create: `tests/test_statusline.py`
- Modify: `scripts/statusline.py` (add `pct_color` after `format_size`; rewrite `render_context_window`)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `pct_color(pct) -> tuple[str, bool]` returning `(colour_name, blink)`.
  - `color_prefix(color, blink) -> str` turning that pair into an ANSI prefix. Both consumers call `color_prefix(*pct_color(pct))` so the construction exists in exactly one place.
  - The test module exposes `sl` (the loaded script module) and `plain(s)` (ANSI stripper) for all later tasks.

- [ ] **Step 1: Write the failing test**

Create `tests/test_statusline.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_statusline.py -v`
Expected: FAIL — `AttributeError: module 'statusline' has no attribute 'pct_color'` on the `TestPctColor` cases and `... has no attribute 'color_prefix'` on the `TestColorPrefix` cases. The `TestRenderContextWindowRefactor` cases should already PASS, since they describe current behaviour.

- [ ] **Step 3: Add `pct_color`**

In `scripts/statusline.py`, insert after `format_size` (currently ends around line 156), before `parse_model_name`:

```python
def pct_color(pct):
    """Map a percentage to (color_name, blink) on the shared threshold ladder.

    Used by the context bar and both rate-limit windows so the three cannot
    drift apart. Blink is reserved for the >90% alarm.
    """
    if pct is None:
        return ("dim", False)
    if pct <= 50:
        return ("green", False)
    if pct <= 75:
        return ("yellow", False)
    if pct <= 90:
        return ("red", False)
    return ("red", True)


def color_prefix(color, blink):
    """ANSI prefix for a colour name, with blink layered on when set.

    Kept separate from pct_color so the threshold ladder stays testable as
    readable ("green", False) pairs rather than opaque escape sequences,
    while the escape construction itself still lives in exactly one place.
    """
    return COLORS.get(color, "") + (COLORS["blink"] if blink else "")
```

- [ ] **Step 4: Rewrite `render_context_window` to use it**

Replace the whole of `render_context_window` (currently lines 404-444) with:

```python
def render_context_window(data):
    """CTX: {progress_bar} {pct}% of {size}"""
    pct = safe_get(data, "context_window", "used_percentage")
    window_size = safe_get(data, "context_window", "context_window_size")
    size_label = format_size(window_size) if window_size else "--"

    bar_width = 30
    filled = round(pct / 100 * bar_width) if pct is not None else 0
    filled = max(0, min(bar_width, filled))

    bar_filled = "▓" * filled                # ▓
    bar_empty = "░" * (bar_width - filled)   # ░

    prefix = color_prefix(*pct_color(pct))
    pct_str = "--%" if pct is None else f"{pct}%"

    colored_bar = (
        f"{prefix}{bar_filled}{COLORS['reset']}"
        f"{COLORS['dim']}{bar_empty}{COLORS['reset']}"
    )
    colored_pct = f"{prefix}{pct_str}{COLORS['reset']}"

    return (
        f"{c('bold_cyan', 'CTX:')} {colored_bar} {colored_pct} "
        f"of {c('white', size_label)}"
    )
```

The `max(0, min(bar_width, filled))` clamp is new. It cannot change output for any percentage between 0 and 100 — it only stops `"▓" * negative` or an over-long bar if a future payload reports out-of-range values.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 tests/test_statusline.py -v`
Expected: PASS, 18 tests.

- [ ] **Step 6: Verify the rendered output is unchanged**

Run: `cat test-payload.json | python3 scripts/statusline.py`
Expected: four lines, CTX identical to before the change — `CTX: ▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░ 17% of 200K`.

- [ ] **Step 7: Commit**

```bash
git add tests/test_statusline.py scripts/statusline.py
git commit -m "Extract pct_color and add test harness

Shared threshold ladder for the context bar and the rate-limit windows
this change is about to add. Pure refactor: rendered output is unchanged,
covered by characterisation tests."
```

---

### Task 2: Duration formatting for countdowns

`format_reset` turns a `resets_at` epoch into a countdown. It reuses `format_duration` rather than duplicating unit logic, which means `format_duration` needs two optional behaviours it does not have: a cap on how many units it emits, and a day component.

**Files:**
- Modify: `scripts/statusline.py` (`format_duration`; add `format_reset` immediately after it)
- Modify: `tests/test_statusline.py` (append two test classes)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `format_duration(ms, max_parts=None, days=False) -> str` — existing callers pass neither new argument and are bit-for-bit unaffected.
  - `format_reset(resets_at, now=None) -> str | None` — `None` for missing, unparseable, or non-future timestamps. `now` is injectable for deterministic tests.

**Note on the spec:** the spec says `format_duration` "gains an optional `max_parts` argument" and that existing callers are unaffected. Emitting `3d5h` also requires a day component, and adding days *unconditionally* would change the USE line for sessions over 24 hours (`26h5m3s` becomes `1d2h5m3s`). The `days=False` default keeps the spec's promise literally true. Do not change the default.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statusline.py`, before the `if __name__` block:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_statusline.py TestFormatDuration TestFormatReset -v`
Expected: FAIL — `TypeError: format_duration() got an unexpected keyword argument 'days'` and `AttributeError: module 'statusline' has no attribute 'format_reset'`.

- [ ] **Step 3: Extend `format_duration`**

Replace the whole of `format_duration` (currently lines 126-143) with:

```python
def format_duration(ms, max_parts=None, days=False):
    """Convert milliseconds to compact human string, omitting zero components.

    max_parts caps how many units are emitted, largest first: 8073s with
    max_parts=2 is "2h14m" rather than "2h14m33s".

    days=True emits a leading day component instead of rolling days into
    hours. Defaults to False so existing callers are unaffected.
    """
    if ms is None:
        return "--"
    total_s = int(ms) // 1000
    if total_s < 0:
        return "--"
    if days:
        day_count = total_s // 86400
        hours = (total_s % 86400) // 3600
    else:
        day_count = 0
        hours = total_s // 3600
    minutes = (total_s % 3600) // 60
    seconds = total_s % 60
    parts = []
    if day_count > 0:
        parts.append(f"{day_count}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
    if max_parts is not None:
        parts = parts[:max_parts]
    return "".join(parts)
```

- [ ] **Step 4: Add `format_reset` directly after it**

```python
def format_reset(resets_at, now=None):
    """Countdown to a unix epoch timestamp: '2h14m', '3d5h', '45s'.

    Returns None when the timestamp is missing, unparseable, or not in the
    future — a rate-limit window that has already rolled over has nothing
    useful to say, and a negative countdown would be worse than silence.
    """
    if resets_at is None:
        return None
    try:
        delta = float(resets_at) - (time.time() if now is None else now)
    except (TypeError, ValueError):
        return None
    if delta <= 0:
        return None
    if delta >= 60:
        delta = (int(delta) // 60) * 60  # whole minutes; seconds are noise here
    return format_duration(delta * 1000, max_parts=2, days=True)
```

`time` is already imported at the top of the script.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 tests/test_statusline.py -v`
Expected: PASS, 35 tests.

- [ ] **Step 6: Confirm the USE line is untouched**

Run: `cat test-payload.json | python3 scripts/statusline.py`
Expected: `USE: $0.42 | 45m12s | API: 12m3s | +156 -23 lines` — identical to before.

- [ ] **Step 7: Commit**

```bash
git add tests/test_statusline.py scripts/statusline.py
git commit -m "Add format_reset and optional max_parts/days to format_duration

Countdown formatting for rate-limit reset times. Both new format_duration
arguments default off, so the USE line renders exactly as before."
```

---

### Task 3: Effort section on the ENV line

**Files:**
- Modify: `scripts/statusline.py` (`COLORS`; add `EFFORT_COLORS`; add `join_segments` and `effort_segment`; rewrite `render_environment`)
- Modify: `tests/test_statusline.py` (append three test classes)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `join_segments(*segments) -> str` — joins truthy values with `SEP`, dropping `None` and `""` along with their separators. Used by all three renderers.
  - `effort_segment(data) -> str | None`
  - `COLORS["bold_red"]` — new entry, so `xhigh` and `max` are visually distinct.
  - `EFFORT_COLORS` — level to colour-name mapping. Always read with `.get(level, "white")`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statusline.py`, before the `if __name__` block:

```python
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
```

`render_environment` calls `get_resource_counts`, which walks real directories. That is acceptable in tests: the assertions above only inspect segment ordering, never the counts.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_statusline.py TestJoinSegments TestEffortSegment TestRenderEnvironment -v`
Expected: FAIL — `AttributeError: module 'statusline' has no attribute 'join_segments'`.

- [ ] **Step 3: Add the `bold_red` colour**

In the `COLORS` dict at the top of `scripts/statusline.py`, add one entry after `"bold_cyan"`:

```python
    "bold_red":   "\033[1;31m",
```

- [ ] **Step 4: Add `EFFORT_COLORS` below the `SEP` constant**

```python
# Effort levels, coloured by cost. `max` is bold red rather than blinking:
# blink means "about to hurt you" in this statusline and is reserved for the
# >90% context alarm. A max effort level is a choice the user made on purpose.
EFFORT_COLORS = {
    "low":    "dim",
    "medium": "green",
    "high":   "yellow",
    "xhigh":  "red",
    "max":    "bold_red",
}
```

- [ ] **Step 5: Add `join_segments` next to the other helpers**

Insert directly after the `c()` helper (currently lines 108-110):

```python
def join_segments(*segments):
    """Join truthy segments with SEP, dropping absent ones and their separators.

    This is what makes the absence policy structural: a section with nothing
    to say returns None and disappears, separator included. It cannot leave a
    dangling "|" behind because it never contributes one.
    """
    return SEP.join(s for s in segments if s)
```

- [ ] **Step 6: Add `effort_segment` above `render_environment`**

```python
def effort_segment(data):
    """'Eff: high' when the model reports a reasoning effort level, else None.

    Absent whenever the current model has no reasoning-effort support.
    """
    level = safe_get(data, "effort", "level")
    if not level:
        return None
    return f"{c('dim', 'Eff:')} {c(EFFORT_COLORS.get(level, 'white'), level)}"
```

- [ ] **Step 7: Rewrite `render_environment`**

Replace the whole function with:

```python
def render_environment(data):
    """ENV: CC:{version} | Model: {model} | Eff: {effort} | SK: {n} | MCP: {n} | Hooks: {n}"""
    version = safe_get(data, "version", default="--")
    model = parse_model_name(data)
    cwd = safe_get(data, "cwd", default=None)
    counts = get_resource_counts(cwd)

    return f"{c('bold_cyan', 'ENV:')} " + join_segments(
        f"CC:{c('white', version)}",
        f"{c('dim', 'Model:')} {c('green', model)}",
        effort_segment(data),
        f"{c('dim', 'SK:')} {c('yellow', counts['skills'])}",
        f"{c('dim', 'MCP:')} {c('yellow', counts['mcp'])}",
        f"{c('dim', 'Hooks:')} {c('yellow', counts['hooks'])}",
    )
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python3 tests/test_statusline.py -v`
Expected: PASS, 51 tests.

- [ ] **Step 9: Verify against a live payload**

```bash
python3 -c "
import json,sys
d=json.load(open('test-payload.json'))
d['effort']={'level':'high'}
json.dump(d,sys.stdout)" | python3 scripts/statusline.py
```
Expected: the ENV line contains `| Eff: high | SK:`, and the other three lines are unchanged.

- [ ] **Step 10: Commit**

```bash
git add tests/test_statusline.py scripts/statusline.py
git commit -m "Add effort section to the ENV line

Renders effort.level between Model and SK, coloured by cost. Introduces
join_segments, which makes 'omit when absent' structural rather than a
rule each renderer has to remember."
```

---

### Task 4: Rate limit section on the CTX line

**Files:**
- Modify: `scripts/statusline.py` (add `rate_limit_segment`; append it in `render_context_window`)
- Modify: `tests/test_statusline.py` (append two test classes)

**Interfaces:**
- Consumes: `pct_color` and `color_prefix` (Task 1), `format_reset` (Task 2), `join_segments` (Task 3)
- Produces: `rate_limit_segment(data, now=None) -> str | None`. `now` is injectable so tests are deterministic.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statusline.py`, before the `if __name__` block:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_statusline.py TestRateLimitSegment -v`
Expected: FAIL — `AttributeError: module 'statusline' has no attribute 'rate_limit_segment'`.

- [ ] **Step 3: Add `rate_limit_segment` above `render_context_window`**

```python
RATE_LIMIT_WINDOWS = (("five_hour", "5h"), ("seven_day", "7d"))


def rate_limit_segment(data, now=None):
    """'5h: 42% (2h14m) | 7d: 68% (3d5h)' for Claude.ai subscription limits.

    Absent for API-key users and before the session's first API response.
    Either window can appear without the other, so each is rendered
    independently. Percentages above 100 are reported rather than clamped:
    overage is real, and hiding it would fail the user at the one moment
    this segment matters.
    """
    rendered = []
    for key, label in RATE_LIMIT_WINDOWS:
        raw = safe_get(data, "rate_limits", key, "used_percentage")
        if raw is None:
            continue
        try:
            pct = round(float(raw))
        except (TypeError, ValueError):
            continue
        prefix = color_prefix(*pct_color(pct))
        text = f"{prefix}{pct}%{COLORS['reset']}"
        reset = format_reset(safe_get(data, "rate_limits", key, "resets_at"), now=now)
        if reset:
            text = f"{text} {c('dim', '(' + reset + ')')}"
        rendered.append(f"{c('dim', label + ':')} {text}")
    return join_segments(*rendered) if rendered else None
```

- [ ] **Step 4: Append the segment in `render_context_window`**

Replace the final `return` statement of `render_context_window` with:

```python
    head = (
        f"{c('bold_cyan', 'CTX:')} {colored_bar} {colored_pct} "
        f"of {c('white', size_label)}"
    )
    return join_segments(head, rate_limit_segment(data))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 tests/test_statusline.py -v`
Expected: PASS, 65 tests.

- [ ] **Step 6: Verify against a live payload**

```bash
python3 -c "
import json,sys,time
d=json.load(open('test-payload.json'))
now=int(time.time())
d['rate_limits']={'five_hour':{'used_percentage':42.4,'resets_at':now+8073},
                  'seven_day':{'used_percentage':68.0,'resets_at':now+277200}}
json.dump(d,sys.stdout)" | python3 scripts/statusline.py
```
Expected: `CTX: ... 17% of 200K | 5h: 42% (2h14m) | 7d: 68% (3d5h)`.

- [ ] **Step 7: Commit**

```bash
git add tests/test_statusline.py scripts/statusline.py
git commit -m "Add 5h and 7d rate limit usage to the CTX line

Each window renders independently since either can be absent. Reset
countdowns come from resets_at and are dropped when already past.
Overage above 100% is reported rather than clamped."
```

---

### Task 5: Worktree section on the GIT line

**Files:**
- Modify: `scripts/statusline.py` (add `ARROW`; add `worktree_segment`; rewrite `render_git`)
- Modify: `tests/test_statusline.py` (append one test class)

**Interfaces:**
- Consumes: `join_segments` (Task 3)
- Produces: `worktree_segment(data) -> str | None`, and the module constant `ARROW = "←"`.

**Why `ARROW` is a constant:** it is used inside an f-string replacement field, and a backslash escape there is a `SyntaxError` before Python 3.12. Hoisting it to a module constant sidesteps the version floor entirely.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statusline.py`, before the `if __name__` block:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_statusline.py TestWorktreeSegment -v`
Expected: FAIL — `AttributeError: module 'statusline' has no attribute 'worktree_segment'`.

- [ ] **Step 3: Add the `ARROW` constant next to `SEP`**

```python
# U+2190. A module constant because a backslash escape inside an f-string
# replacement field is a SyntaxError before Python 3.12.
ARROW = "←"
```

- [ ] **Step 4: Add `worktree_segment` above `render_git`**

```python
def worktree_segment(data):
    """'WT: feat-x ← main' when the session is inside a git worktree.

    Two payload fields cover different populations. `worktree` appears only
    for sessions Claude Code started with --worktree. `workspace.git_worktree`
    appears whenever the cwd sits inside any linked worktree, including one
    created by hand with `git worktree add`. Reading both makes the section
    work either way.

    The segment renders even when the name matches the current branch, which
    is the common case since Claude Code derives the slug from the branch.
    The presence of the segment is itself the information.
    """
    name = safe_get(data, "worktree", "name")
    origin = safe_get(data, "worktree", "original_branch")
    if not name:
        name = safe_get(data, "workspace", "git_worktree")
        origin = None
    if not name:
        return None
    text = c("cyan", name)
    if origin:
        text = f"{text} {c('dim', ARROW)} {c('dim', origin)}"
    return f"{c('dim', 'WT:')} {text}"
```

- [ ] **Step 5: Rewrite `render_git`**

Replace the whole function (currently lines 552-607) with:

```python
def render_git(data):
    """GIT: {repo} | {branch} | WT: {worktree} | Age | Mod | Staged | up/down"""
    cwd = safe_get(data, "cwd")
    info = get_git_info(cwd)

    if info is None:
        return f"{c('bold_cyan', 'GIT:')} {c('dim', '(not a repo)')}"

    dirty = info["dirty"]
    branch = c("yellow" if dirty > 0 else "green", info["branch"])
    mod = c("yellow", dirty) if dirty > 0 else c("dim", "0")
    staged = c("green", info["staged"]) if info["staged"] > 0 else c("dim", "0")

    if info["has_upstream"]:
        up = info["unpushed"]
        down = info["unpulled"]
        up_str = c("yellow", f"↑{up}") if up > 0 else c("dim", f"↑{up}")
        down_str = c("red", f"↓{down}") if down > 0 else c("dim", f"↓{down}")
        sync = f"{up_str} {down_str}"
    else:
        sync = c("dim", "(no upstream)")

    return f"{c('bold_cyan', 'GIT:')} " + join_segments(
        c("bold_white", info["repo"]),
        branch,
        worktree_segment(data),
        f"{c('dim', 'Age:')} {c('dim', info['age'])}",
        f"{c('dim', 'Mod:')} {mod}",
        f"{c('dim', 'Staged:')} {staged}",
        sync,
    )
```

The `↑` and `↓` escapes sit in the *literal* portion of their f-strings, exactly as in the current code, so they need no constant.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 tests/test_statusline.py -v`
Expected: PASS, 73 tests.

- [ ] **Step 7: Verify against the real repo**

```bash
python3 -c "
import json,sys,os
d=json.load(open('test-payload.json'))
d['cwd']=os.getcwd()
d['worktree']={'name':'feat-x','original_branch':'main'}
json.dump(d,sys.stdout)" | python3 scripts/statusline.py
```
Expected: the GIT line reads `GIT: CC-StatusLine | feat/effort-ratelimits-worktree | WT: feat-x ← main | Age: ...`.

Then confirm the section disappears cleanly:
```bash
python3 -c "
import json,sys,os
d=json.load(open('test-payload.json'))
d['cwd']=os.getcwd()
json.dump(d,sys.stdout)" | python3 scripts/statusline.py
```
Expected: no `WT:` and no doubled separator.

- [ ] **Step 8: Commit**

```bash
git add tests/test_statusline.py scripts/statusline.py
git commit -m "Add worktree section to the GIT line

Shows the worktree name and the branch it was created from, which is the
part not already on screen. Falls back to workspace.git_worktree for
worktrees created by hand rather than by --worktree."
```

---

### Task 6: Correct the repo name inside linked worktrees

`render_git` derives the repo name from `git rev-parse --show-toplevel`, which inside a linked worktree is the *worktree* directory. The new `WT:` segment puts the two side by side, making the defect obvious:

```
GIT: CC-StatusLine-feat-x | feat-x | WT: feat-x ← main | ...
```

**Files:**
- Modify: `scripts/statusline.py` (`fetch_git_info`)
- Modify: `tests/test_statusline.py` (append one test class)

**Interfaces:**
- Consumes: nothing
- Produces: no new public names. `fetch_git_info(cwd)["repo"]` becomes correct inside linked worktrees.

**Verified behaviour** (Git 2.50.1):

| Location | `--git-common-dir` | naive `basename(dirname())` | with guard |
| --- | --- | --- | --- |
| repository root | `.git` (relative) | `myrepo` | `myrepo` |
| linked worktree | `/…/myrepo/.git` | `myrepo` | `myrepo` |
| submodule | `/…/parent/.git/modules/sub` | **`modules`** | `sub` |

Two consequences, both load-bearing. The command needs `--path-format=absolute`, because the plain form returns a *relative* `.git` from the repository root. And the derived name is only trustworthy when `basename(common_dir) == ".git"` — inside a submodule the common dir points at `.git/modules/<name>` and the naive derivation yields `modules`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statusline.py`, before the `if __name__` block. Add `import shutil`, `import subprocess`, and `import tempfile` to the imports at the top of the file.

```python
def _git(*args, **kw):
    subprocess.run(["git"] + list(args), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_statusline.py TestRepoName -v`
Expected: `test_linked_worktree_reports_the_repository_name` and `test_subdirectory_of_a_linked_worktree` FAIL with `'myrepo-feat-x' != 'myrepo'`. The other three PASS.

- [ ] **Step 3: Add the corrected derivation to `fetch_git_info`**

In `fetch_git_info`, replace the single line `repo_name = os.path.basename(toplevel)` with:

```python
    repo_name = _repo_name(cwd, toplevel)
```

Then add this helper immediately above `fetch_git_info`:

```python
def _repo_name(cwd, toplevel):
    """Repository name, correct even from inside a linked worktree.

    --show-toplevel is the *worktree* directory inside a linked worktree, so
    it would report the worktree's folder name as the repo. The git common
    dir resolves to the main repository's .git from anywhere inside one.

    The result is only trustworthy when the common dir is literally named
    ".git". Inside a submodule it is ".git/modules/<name>", where taking the
    parent directory would yield "modules". In that case the toplevel
    basename is already correct.

    --path-format requires Git 2.31+. Any failure falls back to today's
    behaviour, so the worst case is no regression.
    """
    common = run_cmd(
        ["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"]
    )
    if common:
        common = common.rstrip("/\\")
        if os.path.basename(common) == ".git":
            parent = os.path.dirname(common)
            if parent:
                return os.path.basename(parent)
    return os.path.basename(toplevel)
```

This adds one `run_cmd` call to `fetch_git_info`, which is already behind the 5-second git cache, so cache hits cost nothing extra.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/test_statusline.py -v`
Expected: PASS, 78 tests.

- [ ] **Step 5: Verify against the real repo**

Run: `cat test-payload.json | python3 -c "import json,sys,os; d=json.load(sys.stdin); d['cwd']=os.getcwd(); json.dump(d,sys.stdout)" | python3 scripts/statusline.py`
Expected: the GIT line still starts `GIT: CC-StatusLine |`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_statusline.py scripts/statusline.py
git commit -m "Report the repository name correctly inside linked worktrees

--show-toplevel is the worktree directory, so the GIT line showed the
worktree folder name as the repo. Derive it from the git common dir
instead, guarded against submodules where that path ends in
.git/modules/<name> and the naive derivation yields 'modules'."
```

---

### Task 7: Payload debug capture

Rate limit data is runtime state inside Claude Code, persisted nowhere on disk. Nothing short of a live render can confirm the schema. Rather than instrument temporarily and revert, ship the capture as a small permanent feature — it also gives users a way to produce real data when reporting that a section is missing.

**Files:**
- Modify: `scripts/statusline.py` (add two constants and `maybe_dump_payload`; call it from `main`)
- Modify: `tests/test_statusline.py` (append one test class)

**Interfaces:**
- Consumes: nothing
- Produces: `maybe_dump_payload(raw) -> None`, plus module constants `DEBUG_FLAG` and `DEBUG_PAYLOAD` that tests reassign.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statusline.py`, before the `if __name__` block:

```python
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

    def test_non_utf8_safe_content_round_trips(self):
        open(self.flag, "w").close()
        sl.maybe_dump_payload('{"branch": "café ← main"}')
        with open(self.out, encoding="utf-8") as f:
            self.assertIn("café", f.read())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_statusline.py TestPayloadDebugCapture -v`
Expected: FAIL — `AttributeError: module 'statusline' has no attribute 'DEBUG_FLAG'`.

- [ ] **Step 3: Add the constants beside the cache paths**

Directly below the `GIT_TTL = 5` line:

```python
# Opt-in payload capture. Touch DEBUG_FLAG, trigger a render, read
# DEBUG_PAYLOAD, delete the flag. Costs one os.path.exists per render.
DEBUG_FLAG = os.path.expanduser("~/.claude/statusline-debug")
DEBUG_PAYLOAD = os.path.expanduser("~/.claude/statusline-payload.json")
```

- [ ] **Step 4: Add `maybe_dump_payload` above `main`**

```python
def maybe_dump_payload(raw):
    """Write the raw stdin payload to disk when the debug flag file exists.

    Swallows every failure. Debug tooling must never be capable of breaking
    the statusline it is meant to diagnose.
    """
    try:
        if os.path.exists(DEBUG_FLAG):
            with open(DEBUG_PAYLOAD, "w", encoding="utf-8") as f:
                f.write(raw)
    except OSError:
        pass
```

- [ ] **Step 5: Call it from `main`**

In `main`, immediately after the `raw = ...` try/except block and before the JSON parse:

```python
    maybe_dump_payload(raw)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 tests/test_statusline.py -v`
Expected: PASS, 82 tests.

- [ ] **Step 7: Capture a real payload**

```bash
touch ~/.claude/statusline-debug
```
Send any message in Claude Code to trigger a render, then:
```bash
python3 -m json.tool ~/.claude/statusline-payload.json
rm ~/.claude/statusline-debug
```
Expected: the payload contains `effort.level`, `rate_limits.five_hour`, and `rate_limits.seven_day`. Record the observed shape — Task 8 uses it to make the fixture realistic.

If `rate_limits` is absent, check that the session has had at least one API response and that the account is on a Claude.ai subscription rather than an API key. Absence in that case is correct behaviour, not a bug.

- [ ] **Step 8: Commit**

```bash
git add tests/test_statusline.py scripts/statusline.py
git commit -m "Add opt-in payload debug capture

Touch ~/.claude/statusline-debug and the next render writes the raw
payload to ~/.claude/statusline-payload.json. Rate limit data is runtime
state that is persisted nowhere, so this is the only way to confirm the
schema or diagnose a missing section from a bug report."
```

---

### Task 8: Fixtures, documentation, and release

**Files:**
- Modify: `test-payload.json`
- Create: `test-payload-minimal.json`
- Modify: `commands/statusline-test.md`
- Modify: `README.md`
- Modify: `.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: everything from Tasks 1-7
- Produces: nothing consumed by later tasks

- [ ] **Step 1: Update `test-payload.json` with all optional fields present**

Replace the entire file. Adjust `resets_at` values if the Task 7 capture showed a different shape.

```json
{
  "cwd": "/home/user/my-project",
  "session_id": "abc123",
  "transcript_path": "/tmp/transcript.jsonl",
  "version": "2.1.220",
  "model": {
    "id": "claude-opus-5[1m]",
    "display_name": "Opus"
  },
  "workspace": {
    "current_dir": "/home/user/my-project",
    "project_dir": "/home/user/my-project",
    "added_dirs": [],
    "git_worktree": "feat-x"
  },
  "output_style": {
    "name": "default"
  },
  "cost": {
    "total_cost_usd": 0.42,
    "total_duration_ms": 2712000,
    "total_api_duration_ms": 723000,
    "total_lines_added": 156,
    "total_lines_removed": 23
  },
  "context_window": {
    "total_input_tokens": 15234,
    "total_output_tokens": 4521,
    "context_window_size": 1000000,
    "used_percentage": 17,
    "remaining_percentage": 83,
    "current_usage": {
      "input_tokens": 8500,
      "output_tokens": 1200,
      "cache_creation_input_tokens": 5000,
      "cache_read_input_tokens": 2000
    }
  },
  "effort": {
    "level": "high"
  },
  "thinking": {
    "enabled": true
  },
  "rate_limits": {
    "five_hour": {
      "used_percentage": 42.4,
      "resets_at": 4102444800
    },
    "seven_day": {
      "used_percentage": 68.0,
      "resets_at": 4102444800
    }
  },
  "worktree": {
    "name": "feat-x",
    "path": "/home/user/my-project-feat-x",
    "branch": "feat-x",
    "original_cwd": "/home/user/my-project",
    "original_branch": "main"
  },
  "exceeds_200k_tokens": false
}
```

The `resets_at` values are far in the future (year 2100) on purpose, so the countdown never renders as `None` and the fixture stays useful indefinitely. The countdown it prints will be a large number of days — that is expected for a fixture.

- [ ] **Step 2: Create `test-payload-minimal.json`**

```json
{
  "cwd": "/home/user/my-project",
  "session_id": "abc123",
  "transcript_path": "/tmp/transcript.jsonl",
  "version": "2.1.220",
  "model": {
    "id": "claude-sonnet-5",
    "display_name": "Sonnet"
  },
  "workspace": {
    "current_dir": "/home/user/my-project",
    "project_dir": "/home/user/my-project",
    "added_dirs": []
  },
  "cost": {
    "total_cost_usd": 0.42,
    "total_duration_ms": 2712000,
    "total_api_duration_ms": 723000,
    "total_lines_added": 156,
    "total_lines_removed": 23
  },
  "context_window": {
    "total_input_tokens": 15234,
    "total_output_tokens": 4521,
    "context_window_size": 200000,
    "used_percentage": 17,
    "remaining_percentage": 83,
    "current_usage": {
      "input_tokens": 8500,
      "output_tokens": 1200,
      "cache_creation_input_tokens": 5000,
      "cache_read_input_tokens": 2000
    }
  },
  "exceeds_200k_tokens": false
}
```

- [ ] **Step 3: Run both fixtures and check for dangling separators**

```bash
cat test-payload.json | python3 scripts/statusline.py
echo "---"
cat test-payload-minimal.json | python3 scripts/statusline.py
```

Expected from the full fixture: `Eff: high` on ENV, both rate-limit windows on CTX, `WT: feat-x ← main` on GIT.
Expected from the minimal fixture: no `Eff:`, no `5h:`, no `7d:`, no `WT:`, and **no line ending in `|` and no `| |` anywhere**.

- [ ] **Step 4: Update `commands/statusline-test.md`**

Replace the block from "Then run the test using the resolved path." through the end of the file with:

````markdown
Then run both fixtures using the resolved path. On macOS/Linux:

```bash
cat "{install_path}/test-payload.json" | python3 "{install_path}/scripts/statusline.py"
echo "--- minimal payload (optional sections absent) ---"
cat "{install_path}/test-payload-minimal.json" | python3 "{install_path}/scripts/statusline.py"
```

On Windows:

```bash
type "{install_path}\test-payload.json" | python "{install_path}\scripts\statusline.py"
echo "--- minimal payload (optional sections absent) ---"
type "{install_path}\test-payload-minimal.json" | python "{install_path}\scripts\statusline.py"
```

Show the raw output of both to the user. If either fails, show the error.

The full payload exercises every section. The minimal payload has no effort,
no rate limits, and no worktree, so those sections must be absent — check that
no line ends in a separator and that no `| |` appears anywhere.
````

- [ ] **Step 5: Update the README output block**

Replace the fenced block under `## Output` (currently lines 6-12) with:

```
ENV: CC:2.1.220 | Model: Opus 5 (1M context) | Eff: high | SK: 44 | MCP: 5 | Hooks: 7
CTX: ▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░ 17% of 1M | 5h: 42% (2h14m) | 7d: 68% (3d5h)
USE: $0.42 | 45m12s | API: 12m3s | +156 -23 lines
GIT: my-project | feat-x | WT: feat-x ← main | Age: 25m | Mod: 3 | Staged: 1 | ↑2 ↓0
```

- [ ] **Step 6: Update the README sections table and add the conditional note**

Replace the `### Sections` table with:

```markdown
### Sections

| Line | Content |
|------|---------|
| **ENV** | Claude Code version, model name (with context window), reasoning effort, skill/MCP/hook counts |
| **CTX** | Context window usage with color-coded progress bar, plus 5-hour and 7-day subscription limits |
| **USE** | Session cost, wall-clock duration, API duration, lines added/removed |
| **GIT** | Repo name, branch, worktree, last commit age, modified/staged file counts, unpushed/unpulled |

### Conditional sections

Three sections appear only when Claude Code sends the data, and are omitted
entirely — separator included — when it does not:

| Section | Appears when |
|---------|--------------|
| `Eff: <level>` | the current model supports reasoning effort |
| `5h:` / `7d:` | you are on a Claude.ai subscription, after the session's first API response |
| `WT: <name>` | the current directory is inside a git worktree |

The `WT:` section shows the worktree name and the branch it was created from.
The branch checked out *in* the worktree is already the branch shown earlier on
the line.

### Debugging a missing section

If a section does not appear and you think it should, capture the raw payload
Claude Code is sending:

```bash
touch ~/.claude/statusline-debug
# send any message so the statusline re-renders
cat ~/.claude/statusline-payload.json
rm ~/.claude/statusline-debug
```

The capture only runs while the flag file exists.
```

- [ ] **Step 7: Update the README colour thresholds table**

Replace the table under `## Color Thresholds` with:

```markdown
| Metric | Green | Yellow | Red | Blinking Red |
|--------|-------|--------|-----|--------------|
| Context window | 0-50% | 51-75% | 76-90% | >90% |
| Rate limits (5h, 7d) | 0-50% | 51-75% | 76-90% | >90% |
| Cost | < $1 | $1-$5 | > $5 | -- |

Effort is colored by cost rather than alarm: `low` dim, `medium` green,
`high` yellow, `xhigh` red, `max` bold red. It never blinks — blinking is
reserved for the >90% alarms above.
```

- [ ] **Step 8: Update the README project structure and requirements**

In the `## Project Structure` block, add these two entries after the `commands/` group and update the payload line:

```
├── tests/
│   └── test_statusline.py     # Unit + git integration tests
├── test-payload.json          # Sample stdin, all optional sections present
├── test-payload-minimal.json  # Sample stdin, all optional sections absent
```

Under `## Requirements`, add a third bullet:

```markdown
- Git 2.31+ for correct repo naming inside linked worktrees (older versions fall back gracefully)
```

- [ ] **Step 9: Bump the plugin version**

In `.claude-plugin/plugin.json`, change `"version": "1.5.2"` to `"version": "1.6.0"`.

- [ ] **Step 10: Run the full test suite and both fixtures one last time**

```bash
python3 tests/test_statusline.py -v
cat test-payload.json | python3 scripts/statusline.py
cat test-payload-minimal.json | python3 scripts/statusline.py
```
Expected: 82 tests PASS, and both fixtures render as described in Step 3.

- [ ] **Step 11: Commit**

```bash
git add test-payload.json test-payload-minimal.json commands/statusline-test.md README.md .claude-plugin/plugin.json
git commit -m "Add fixtures and docs for the new sections; release 1.6.0

Two fixtures: one with every optional section present, one with none, so
the omit-when-absent path is exercised on every test run."
```

---

## Verification

After Task 8, the whole change is verified by:

1. `python3 tests/test_statusline.py -v` — 82 tests, all passing.
2. `cat test-payload.json | python3 scripts/statusline.py` — every section renders.
3. `cat test-payload-minimal.json | python3 scripts/statusline.py` — no optional section renders, no dangling separators.
4. A live session render after `/cc-statusline:setup` redeploys the script, confirming the real payload drives the real output.

## Spec coverage

| Spec section | Task |
| --- | --- |
| Data contract | 3, 4, 5 (consumed) |
| Effort output + colours + no blink on `max` | 3 |
| Rate limit output + reset countdown | 2, 4 |
| Worktree output + source precedence | 5 |
| Absence policy (`str \| None` + `join_segments`) | 3 (mechanism), 3-5 (applied) |
| `pct_color` + `color_prefix` | 1 |
| `format_duration(max_parts)`, `format_reset` | 2 |
| `join_segments` | 3 |
| Repo name derivation + submodule guard | 6 |
| Partial rate limits | 4 |
| Stale/skewed reset times | 2, 4 |
| Percentages above 100 | 4 |
| Unknown effort levels | 3 |
| Git cache unchanged | 6 |
| Non-repository directories | 5 |
| Windows / `←` encoding | 5 (`ARROW` constant) |
| Payload debug capture | 7 |
| Fixtures | 8 |
| Unit tests | 1-7 |
| Docs and version bump | 8 |
