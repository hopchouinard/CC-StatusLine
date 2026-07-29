# Design: Effort, Rate Limits, and Worktree Sections

**Date:** 2026-07-28
**Status:** Approved
**Target version:** cc-statusline 1.6.0

## Summary

Add three sections to the statusline, all sourced from fields Claude Code already
sends in the status line payload:

- `Eff: <level>` on the ENV line, between Model and SK.
- `5h: <pct>% (<reset>) | 7d: <pct>% (<reset>)` at the end of the CTX line.
- `WT: <name> ← <origin branch>` on the GIT line, after the branch.

It also fixes an adjacent defect the worktree section exposes: the GIT line
reports the worktree directory name instead of the repository name when the
current directory is inside a linked worktree.

## Background

Claude Code 2.1.220 sends all three facts in the status line payload. This was
verified against the payload-construction function in the installed binary
(`~/.local/share/claude/versions/2.1.220`) and against the schema documentation
embedded in the same binary and fed to the built-in `statusline-setup` agent.

No new data source is required. The only new subprocess call in this change
belongs to the repo-name fix, and it lands inside the existing cached git
lookup.

The repository's `test-payload.json` predates these fields, which is why they
were not already visible.

## Data contract

All fields arrive on stdin as JSON.

| Field | Type | Absent when |
| --- | --- | --- |
| `effort.level` | `"low" \| "medium" \| "high" \| "xhigh" \| "max"` | the current model does not support reasoning effort |
| `rate_limits.five_hour.used_percentage` | float, 0–100 | not a Claude.ai subscriber, or before the session's first API response |
| `rate_limits.five_hour.resets_at` | unix epoch seconds | as above |
| `rate_limits.seven_day.used_percentage` | float, 0–100 | independently absent from `five_hour` |
| `rate_limits.seven_day.resets_at` | unix epoch seconds | as above |
| `worktree.name` | string | the session was not started with `--worktree` |
| `worktree.branch` | string, optional | as above, or the worktree has no branch |
| `worktree.original_branch` | string, optional | as above, or no branch was checked out beforehand |
| `workspace.git_worktree` | string (name only) | the current directory is not inside a linked worktree |

Three properties of this contract drive the implementation:

1. `rate_limits.*.used_percentage` is a float, unlike `context_window.used_percentage`,
   which is an integer. Display requires rounding.
2. `five_hour` and `seven_day` are independently optional. Either may appear
   without the other.
3. `worktree` and `workspace.git_worktree` cover different populations.
   `worktree` appears only for sessions Claude Code created via `--worktree`.
   `workspace.git_worktree` appears whenever the current directory sits inside
   any linked worktree, including one created by hand with `git worktree add`.
   Reading both makes the feature work in either case.

## Output specification

```
ENV: CC:2.1.220 | Model: Opus 5 (1M context) | Eff: high | SK: 210 | MCP: 12 | Hooks: 8
CTX: ▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░ 17% of 1M | 5h: 42% (2h14m) | 7d: 68% (3d5h)
USE: $0.42 | 45m12s | API: 12m3s | +156 -23 lines
GIT: CC-StatusLine | feat-x | WT: feat-x ← main | Age: 2m | Mod: 3 | Staged: 0 | ↑1 ↓0
```

### Effort

Label `Eff:` in dim, level in a colour that tracks cost:

| Level | Colour |
| --- | --- |
| `low` | dim |
| `medium` | green |
| `high` | yellow |
| `xhigh` | red |
| `max` | bold red |

`xhigh` and `max` must be visually distinct, so `max` uses bold red. This adds
one entry to the module `COLORS` table, which currently has `bold_cyan` and
`bold_white` but no `bold_red`.

`max` is deliberately not set to blink. Blink is reserved in this statusline for
alarms — currently context usage above 90 percent, a condition that is about to
cause a problem. A `max` effort level is a choice the user made on purpose.
Blinking it would erode the meaning of the one signal that needs to cut through.

### Rate limits

Appended to the CTX line after the context window size label.

Percentages are rounded to integers. Reset times are rendered as a compact
countdown derived from `resets_at - now`, capped at two units: `2h14m`, `3d5h`,
`47m`. `format_reset` produces this by calling
`format_duration(delta_ms, max_parts=2)`, so the countdown reuses the existing
unit logic rather than duplicating it.

Colours use the same threshold ladder as the context bar, including blink above
90 percent. The alarm semantics apply here: a weekly limit above 90 percent is a
condition that is about to cause a problem.

### Worktree

Inserted immediately after the branch, so the pair reads as "branch, and the
worktree context for it."

Label `WT:` in dim, name in cyan, `←` in dim, origin branch in dim.

Source precedence:

1. `worktree.name` with `worktree.original_branch` → `WT: feat-x ← main`
2. `worktree.name` without `original_branch` → `WT: feat-x`
3. `workspace.git_worktree` only → `WT: feat-x`
4. Neither → segment omitted

The segment renders even when the worktree name matches the current branch,
which is the common case because Claude Code derives the slug from the branch.
The presence of the segment is itself the information: it says the session is
not in the main checkout, which is otherwise expensive to notice.

## Absence policy

A field that is missing produces no segment and no separator. Lines get shorter
rather than accumulating placeholders.

This is enforced structurally rather than by convention. Each segment builder
returns `str | None`, and the join step drops the `None` values along with their
separators. A segment cannot leave a dangling `|` behind because it never
contributes one.

## Components

### New

```python
pct_color(pct)                       -> tuple[str, bool]   # (colour name, blink)
format_reset(resets_at)              -> str | None         # epoch -> "2h14m"
effort_segment(data)                 -> str | None
rate_limit_segment(data)             -> str | None
worktree_segment(data)               -> str | None
join_segments(*segments)             -> str                # SEP.join of truthy values
```

Plus one module constant, `EFFORT_COLORS`.

The three `*_segment` functions are pure functions of the payload dict. They
perform no I/O, run no subprocesses, and are testable without parsing ANSI
output.

### Modified

| Function | Change |
| --- | --- |
| `format_duration` | gains an optional `max_parts` argument capping how many units are emitted; existing callers pass nothing and are unaffected |
| `render_environment` | splices `effort_segment(data)` between Model and SK |
| `render_context_window` | rewritten to use `pct_color`; appends `rate_limit_segment(data)` |
| `render_git` | splices `worktree_segment(data)` after the branch; uses the corrected repo name |
| `fetch_git_info` | derives the repo name via git common dir (see below) |
| `main` | writes the raw payload to a debug file when the debug flag file exists |

Extracting `pct_color` is load-bearing rather than cosmetic. The
50/75/90/blink ladder exists inline in `render_context_window` today and this
change needs it in three places. Three hand-copied ladders is how a statusline
ends up showing yellow at 74 percent in one segment and green at 74 percent in
another.

## Repo name derivation

`render_git` currently derives the repository name as
`basename(git rev-parse --show-toplevel)`. Inside a linked worktree,
`--show-toplevel` is the worktree directory, so the line reads:

```
GIT: CC-StatusLine-feat-x | feat-x | WT: feat-x ← main | ...
```

The correct source is the git common directory, which resolves to the main
repository's `.git` from anywhere inside a linked worktree.

Behaviour was verified empirically against Git 2.50.1:

| Location | `--git-common-dir` | `basename(dirname())` | with guard |
| --- | --- | --- | --- |
| repository root | `.git` (relative) | `myrepo` | `myrepo` |
| linked worktree | `/…/myrepo/.git` | `myrepo` | `myrepo` |
| submodule | `/…/parent/.git/modules/sub` | `modules` | `sub` |

Two consequences:

1. The command must be `git rev-parse --path-format=absolute --git-common-dir`.
   The plain form returns a relative `.git` from the repository root.
   `--path-format` requires Git 2.31 or newer.
2. The derived name is only trustworthy when `basename(common_dir) == ".git"`.
   Otherwise the current directory is inside a submodule, where the common dir
   points at `.git/modules/<name>` and the naive derivation yields `modules`.

Algorithm:

```
common = git rev-parse --path-format=absolute --git-common-dir
if common and basename(common) == ".git":
    repo = basename(dirname(common))
else:
    repo = basename(toplevel)
```

If the command fails outright — older Git, unusual layout — the fallback is
`basename(toplevel)`, which is today's behaviour. Worst case is no regression.

The result is stored in the existing cached git info dict, so cache hits cost no
additional subprocess calls.

## Error handling and edge cases

`main` already wraps everything in a blanket handler that prints a dim
`statusline: error` and exits 0. The statusline cannot break the terminal. The
cases below are about degrading gracefully before that net is needed.

**Partial rate limits.** `five_hour` and `seven_day` render independently. If
`rate_limits` is present but both children are missing, the segment returns
`None`.

**Stale or skewed reset times.** `resets_at - now` can be negative from clock
skew or a cached payload. A delta at or below zero drops the parenthetical and
keeps the percentage: `5h: 42%`, never a negative duration.

**Percentages above 100.** Overage is a real state for accounts with extra usage
enabled. Display the actual value rather than clamping, because `104%` is
information and suppressing it would fail the user at the exact moment the
segment matters. Colour saturates at the top of the ladder.

**Unknown effort levels.** Use `EFFORT_COLORS.get(level, "white")`. A future
sixth tier renders in plain white rather than raising `KeyError` and blanking
all four lines.

**Git cache.** Entries are keyed on `toplevel`, which differs per worktree, so
worktrees already receive independent cache entries. No change is required.

**Non-repository directories.** The GIT line is unchanged and no worktree
segment appears.

**Windows.** The new `←` (U+2190) joins `▓ ░ ↑ ↓`, already covered by the
existing `sys.stdout.reconfigure(encoding="utf-8")` call. No new surface.

## Payload debug capture

Rate limit data is runtime state inside Claude Code and is persisted nowhere on
disk, so no amount of file inspection can confirm the schema. Rather than a
temporary instrumentation hack, ship the capture as a permanent feature:

> When `~/.claude/statusline-debug` exists, `main` writes the raw stdin payload
> to `~/.claude/statusline-payload.json` before rendering.

Usage is `touch` the flag file, trigger a render, read the payload, delete the
flag file. The cost is one `os.path.exists` call per render, negligible beside
the git subprocesses already running.

This serves two purposes: it verifies this change against a live payload, and it
gives users a way to produce real data when reporting that a section is missing.

Failures during the debug write are swallowed. Debug tooling must never be able
to break the statusline.

## Testing

**Fixtures.** `test-payload.json` is updated to a realistic 2.1.220 payload with
all three new fields present. A new `test-payload-minimal.json` covers the
absent path — a model without effort support, no rate limits, no worktree —
because "omit the segment entirely" is the rule most likely to regress into a
trailing separator. `commands/statusline-test.md` runs both and shows the
output.

**Unit tests.** A new `tests/test_statusline.py` using the standard library
`unittest` module, with no third-party dependencies. It covers the pure helpers
directly rather than parsing rendered ANSI:

- `pct_color` at the exact boundaries 50, 75, and 90, and on `None`
- `format_reset` for future, past, zero, and missing timestamps
- `format_duration` with and without `max_parts`
- `rate_limit_segment` with both windows, one window, neither, and a value above 100
- `effort_segment` for each known level, an unknown level, and a missing field
- `worktree_segment` for all four source-precedence cases
- `join_segments` dropping `None` values without leaving separators

## Delivery

- `scripts/statusline.py` — implementation
- `tests/test_statusline.py` — new
- `test-payload.json` — updated
- `test-payload-minimal.json` — new
- `commands/statusline-test.md` — runs both fixtures
- `README.md` — Output block, Sections table, a note on conditional sections and
  why they may not appear, and the debug capture procedure
- `.claude-plugin/plugin.json` — version 1.5.2 → 1.6.0

The change is additive and backward compatible. Older Claude Code versions that
omit these fields render exactly as they do today.

## Rejected alternatives

**Placeholder text for absent fields.** Showing `Eff: --` and `5h: --%` keeps
lines structurally identical between runs, and the existing code already does
this for cost and duration. Rejected because these fields are absent for
structural reasons rather than transient ones. An API-key user would carry a
permanent `5h: --%` that can never populate, spending width on a promise the
setup cannot keep.

**Rendering `worktree.branch` in the worktree segment.** This was the original
request. Rejected because the current directory is the worktree, so
`git branch --show-current` already returns that exact string and the GIT line
would print it twice. The worktree name and the origin branch are the facts that
are not otherwise on screen.

**A declarative segment registry.** A table of `(label, extractor, colour, line)`
tuples rendered generically. Rejected as premature. The whole statusline is
about twenty segments in a single 640-line script whose main virtue is being
readable top to bottom. The indirection would cost more than it saves at this
size.

**Blink on effort `max`.** Rejected to preserve blink as an alarm signal. See
the Effort section above.
