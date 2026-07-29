#!/usr/bin/env python3
"""Claude Code statusline dashboard."""

import sys
import json
import subprocess
import os
import time
import re
import getpass
import tempfile

COLORS = {
    "reset":      "\033[0m",
    "bold":       "\033[1m",
    "dim":        "\033[2m",
    "blink":      "\033[5m",
    "cyan":       "\033[36m",
    "green":      "\033[32m",
    "yellow":     "\033[33m",
    "red":        "\033[31m",
    "white":      "\033[37m",
    "bold_cyan":  "\033[1;36m",
    "bold_white": "\033[1;37m",
    "bold_red":   "\033[1;31m",
}

SEP = " | "

# U+2190. A module constant because a backslash escape inside an f-string
# replacement field is a SyntaxError before Python 3.12.
ARROW = "←"

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

# ---------------------------------------------------------------------------
# Caching — user-isolated under system temp directory
# ---------------------------------------------------------------------------

try:
    _username = getpass.getuser()
except Exception:
    _username = "unknown"

_CACHE_DIR = os.path.join(tempfile.gettempdir(), f"claude-statusline-{_username}")
os.makedirs(_CACHE_DIR, exist_ok=True)

# Windows: enable ANSI escapes and force UTF-8 stdout
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # STD_OUTPUT_HANDLE = -11, ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

RESOURCE_CACHE = os.path.join(_CACHE_DIR, "resources.json")
RESOURCE_TTL = 60

GIT_CACHE = os.path.join(_CACHE_DIR, "git.json")
GIT_TTL = 5

# Opt-in payload capture. Touch DEBUG_FLAG, trigger a render, read
# DEBUG_PAYLOAD, delete the flag. Costs one os.path.exists per render.
DEBUG_FLAG = os.path.expanduser("~/.claude/statusline-debug")
DEBUG_PAYLOAD = os.path.expanduser("~/.claude/statusline-payload.json")


def read_cache(cache_file, ttl_seconds, key=None):
    """Return cached data if fresh, else None."""
    try:
        with open(cache_file, "r") as f:
            cache = json.load(f)
        if time.time() - cache.get("_ts", 0) > ttl_seconds:
            return None
        if key is not None:
            entry = cache.get(key)
            if entry is None:
                return None
            if time.time() - entry.get("_ts", 0) > ttl_seconds:
                return None
            return entry.get("data")
        return cache.get("data")
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def write_cache(cache_file, data, key=None):
    """Write data to cache with timestamp."""
    try:
        now = time.time()
        if key is not None:
            try:
                with open(cache_file, "r") as f:
                    cache = json.load(f)
            except (OSError, json.JSONDecodeError):
                cache = {}
            cache[key] = {"data": data, "_ts": now}
            cache["_ts"] = now
        else:
            cache = {"data": data, "_ts": now}
        with open(cache_file, "w") as f:
            json.dump(cache, f)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def c(color, text):
    """Wrap text in ANSI color."""
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def join_segments(*segments):
    """Join truthy segments with SEP, dropping absent ones and their separators.

    This is what makes the absence policy structural: a section with nothing
    to say returns None and disappears, separator included. It cannot leave a
    dangling "|" behind because it never contributes one.
    """
    return SEP.join(s for s in segments if s)


def safe_get(data, *keys, default=None):
    """Safely traverse nested dict keys. Returns default only for missing keys."""
    current = data
    for k in keys:
        if isinstance(current, dict):
            if k not in current:
                return default
            current = current[k]
        else:
            return default
    return current


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


def format_size(n):
    """Format token count: 1000000 -> '1M', 200000 -> '200K', 1048576 -> '1M'."""
    if n is None:
        return "--"
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        v = n / 1_000
        return f"{v:.1f}K".replace(".0K", "K")
    return str(n)


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


def parse_model_name(data):
    """Derive a display name like 'Opus 4.6 (1M context)' from model info."""
    model_id = safe_get(data, "model", "id", default="")
    display_name = safe_get(data, "model", "display_name", default="")
    ctx_size = safe_get(data, "context_window", "context_window_size")

    # Try to parse model ID: claude-opus-4-6 -> Opus 4.6
    # Also handle claude-opus-4-6[1m] variant
    name = display_name or "--"
    clean_id = re.sub(r'\[.*\]', '', model_id)  # strip [1m] etc.
    m = re.match(r'claude-(\w+)-(\d+)-(\d+)', clean_id)
    if m:
        family = m.group(1).capitalize()
        version = f"{m.group(2)}.{m.group(3)}"
        name = f"{family} {version}"

    # Append context window info if > 200K
    if ctx_size is not None and ctx_size > 200_000:
        ctx_label = format_size(ctx_size)
        name = f"{name} ({ctx_label} context)"

    return name


def shorten_relative_time(git_age_str):
    """Shorten git relative time: '25 minutes ago' -> '25m'."""
    if not git_age_str:
        return "--"
    git_age_str = git_age_str.strip()
    units = {
        "second": "s", "seconds": "s",
        "minute": "m", "minutes": "m",
        "hour": "h", "hours": "h",
        "day": "d", "days": "d",
        "week": "w", "weeks": "w",
        "month": "mo", "months": "mo",
        "year": "y", "years": "y",
    }
    m = re.match(r"(\d+)\s+(\w+)\s+ago", git_age_str)
    if m:
        num = m.group(1)
        unit = units.get(m.group(2), m.group(2))
        return f"{num}{unit}"
    return git_age_str


def run_cmd(cmd, cwd=None, timeout=2):
    """Run a command as a list of args (no shell), return stdout or None."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=cwd, timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, OSError):
        return None


# ---------------------------------------------------------------------------
# Resource counting (cached)
# ---------------------------------------------------------------------------

def _count_files_in(directory):
    """Count all files recursively in a directory."""
    count = 0
    if os.path.isdir(directory):
        for _, _, files in os.walk(directory):
            count += len(files)
    return count


def _count_skill_dirs(directory):
    """Count skill directories (each containing a SKILL.md)."""
    count = 0
    if os.path.isdir(directory):
        for entry in os.listdir(directory):
            skill_path = os.path.join(directory, entry, "SKILL.md")
            if os.path.isfile(skill_path):
                count += 1
    return count


def _read_json(path):
    """Read and parse a JSON file, returning None on failure."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _count_hooks_in(hooks_obj):
    """Count individual hook configs in a hooks dict (event_type -> list)."""
    if isinstance(hooks_obj, dict):
        total = 0
        for v in hooks_obj.values():
            if isinstance(v, list):
                for entry in v:
                    # Plugin hooks nest: {matcher, hooks: [...]}
                    inner = entry.get("hooks", None) if isinstance(entry, dict) else None
                    if isinstance(inner, list):
                        total += len(inner)
                    else:
                        total += 1
        return total
    if isinstance(hooks_obj, list):
        return len(hooks_obj)
    return 0


def _get_installed_plugin_paths():
    """Return list of installPath values from installed_plugins.json."""
    data = _read_json(os.path.expanduser("~/.claude/plugins/installed_plugins.json"))
    if not data or not isinstance(data.get("plugins"), dict):
        return []
    paths = []
    for entries in data["plugins"].values():
        if isinstance(entries, list):
            for entry in entries:
                p = entry.get("installPath")
                if p and os.path.isdir(p):
                    paths.append(p)
    return paths


def count_skills(cwd):
    """Count skills and commands across global, project, and plugin dirs.

    Locations searched:
      ~/.claude/commands/        (global legacy commands)
      ~/.claude/skills/          (global skills)
      {cwd}/.claude/commands/    (project legacy commands)
      {cwd}/.claude/skills/      (project skills)
      {plugin}/skills/           (plugin skills)
      {plugin}/commands/         (plugin commands)
    """
    home = os.path.expanduser("~/.claude")
    count = (
        _count_files_in(os.path.join(home, "commands"))
        + _count_skill_dirs(os.path.join(home, "skills"))
    )
    if cwd:
        project = os.path.join(cwd, ".claude")
        count += (
            _count_files_in(os.path.join(project, "commands"))
            + _count_skill_dirs(os.path.join(project, "skills"))
        )
    for plugin_path in _get_installed_plugin_paths():
        count += _count_skill_dirs(os.path.join(plugin_path, "skills"))
        count += _count_files_in(os.path.join(plugin_path, "commands"))
    return count


def count_hooks(cwd=None):
    """Count total individual hook configs from settings, project, and plugins."""
    count = 0
    # Global settings hooks
    settings = _read_json(os.path.expanduser("~/.claude/settings.json"))
    if settings:
        count += _count_hooks_in(settings.get("hooks", {}))
    # Project-level settings hooks
    if cwd:
        for name in ("settings.json", "settings.local.json"):
            proj = _read_json(os.path.join(cwd, ".claude", name))
            if proj:
                count += _count_hooks_in(proj.get("hooks", {}))
    # Plugin hooks
    for plugin_path in _get_installed_plugin_paths():
        hooks_data = _read_json(os.path.join(plugin_path, "hooks", "hooks.json"))
        if hooks_data:
            count += _count_hooks_in(hooks_data.get("hooks", {}))
    return count


def count_mcp_servers(cwd=None):
    """Count MCP servers from settings, project, and plugins."""
    count = 0
    # Global settings MCP servers
    settings = _read_json(os.path.expanduser("~/.claude/settings.json"))
    if settings:
        servers = settings.get("mcpServers", {})
        count += len(servers) if isinstance(servers, dict) else 0
    # Project-level MCP servers
    if cwd:
        for name in ("settings.json", "settings.local.json"):
            proj = _read_json(os.path.join(cwd, ".claude", name))
            if proj:
                servers = proj.get("mcpServers", {})
                count += len(servers) if isinstance(servers, dict) else 0
        # Project .mcp.json
        proj_mcp = _read_json(os.path.join(cwd, ".mcp.json"))
        if isinstance(proj_mcp, dict):
            servers = proj_mcp.get("mcpServers", {})
            count += len(servers) if isinstance(servers, dict) else 0
    # Plugin MCP servers (.mcp.json at plugin root, keys = server names)
    for plugin_path in _get_installed_plugin_paths():
        mcp_data = _read_json(os.path.join(plugin_path, ".mcp.json"))
        if isinstance(mcp_data, dict):
            count += len(mcp_data)
    return count


def get_resource_counts(cwd):
    """Get skill/hook/MCP counts, with caching."""
    cached = read_cache(RESOURCE_CACHE, RESOURCE_TTL)
    if cached is not None:
        return cached
    counts = {
        "skills": count_skills(cwd),
        "hooks": count_hooks(cwd),
        "mcp": count_mcp_servers(cwd),
    }
    write_cache(RESOURCE_CACHE, counts)
    return counts


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def effort_segment(data):
    """'Eff: high' when the model reports a reasoning effort level, else None.

    Absent whenever the current model has no reasoning-effort support.
    """
    level = safe_get(data, "effort", "level")
    if not level:
        return None
    return f"{c('dim', 'Eff:')} {c(EFFORT_COLORS.get(level, 'white'), level)}"


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

    head = (
        f"{c('bold_cyan', 'CTX:')} {colored_bar} {colored_pct} "
        f"of {c('white', size_label)}"
    )
    return join_segments(head, rate_limit_segment(data))


def render_usage(data):
    """USE: ${cost} | {duration} | API: {api_duration} | +{added} -{removed} lines"""
    cost = safe_get(data, "cost", "total_cost_usd")
    duration = safe_get(data, "cost", "total_duration_ms")
    api_duration = safe_get(data, "cost", "total_api_duration_ms")
    added = safe_get(data, "cost", "total_lines_added")
    removed = safe_get(data, "cost", "total_lines_removed")

    # Cost color
    if cost is None:
        cost_str = "$--"
        cost_color = "dim"
    else:
        cost_str = f"${cost:.2f}"
        if cost < 1:
            cost_color = "green"
        elif cost <= 5:
            cost_color = "yellow"
        else:
            cost_color = "red"

    added_str = str(added) if added is not None else "--"
    removed_str = str(removed) if removed is not None else "--"

    parts = [
        c("bold_cyan", "USE:"),
        " ",
        c(cost_color, cost_str),
        SEP,
        c("white", format_duration(duration)),
        SEP,
        f"{c('dim', 'API:')} {c('white', format_duration(api_duration))}",
        SEP,
        f"{c('green', '+' + added_str)} {c('red', '-' + removed_str)} {c('dim', 'lines')}",
    ]
    return "".join(str(p) for p in parts)


# ---------------------------------------------------------------------------
# Git status (cached)
# ---------------------------------------------------------------------------

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


def fetch_git_info(cwd):
    """Gather all git info via subprocess calls."""
    if not cwd:
        return None

    # Check if it's a git repo and resolve root
    toplevel = run_cmd(["git", "-C", cwd, "rev-parse", "--show-toplevel"])
    if toplevel is None:
        return None

    repo_name = _repo_name(cwd, toplevel)

    branch = run_cmd(["git", "-C", cwd, "branch", "--show-current"])
    detached = False
    if not branch:
        branch = run_cmd(["git", "-C", cwd, "rev-parse", "--short", "HEAD"])
        detached = True

    dirty_out = run_cmd(["git", "-C", cwd, "status", "--porcelain"])
    dirty = len(dirty_out.splitlines()) if dirty_out else 0

    staged_out = run_cmd(["git", "-C", cwd, "diff", "--cached", "--numstat"])
    staged = len(staged_out.splitlines()) if staged_out else 0

    unpushed = run_cmd(["git", "-C", cwd, "rev-list", "--count", "@{upstream}..HEAD"])
    unpulled = run_cmd(["git", "-C", cwd, "rev-list", "--count", "HEAD..@{upstream}"])

    has_upstream = unpushed is not None

    age_raw = run_cmd(["git", "-C", cwd, "log", "-1", "--format=%cr"])
    age = shorten_relative_time(age_raw) if age_raw else "--"

    return {
        "repo": repo_name,
        "branch": branch or "--",
        "detached": detached,
        "dirty": dirty,
        "staged": staged,
        "unpushed": int(unpushed) if unpushed else 0,
        "unpulled": int(unpulled) if unpulled else 0,
        "has_upstream": has_upstream,
        "age": age,
        "_toplevel": toplevel,
    }


def get_git_info(cwd):
    """Get git info with caching, keyed by repo root."""
    if not cwd:
        return None
    # Resolve repo root for consistent cache key
    toplevel = run_cmd(["git", "-C", cwd, "rev-parse", "--show-toplevel"])
    if not toplevel:
        return None
    cached = read_cache(GIT_CACHE, GIT_TTL, key=toplevel)
    if cached is not None:
        return cached
    info = fetch_git_info(cwd)
    if info is not None:
        write_cache(GIT_CACHE, info, key=toplevel)
    return info


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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def maybe_dump_payload(raw):
    """Write the raw stdin payload to disk when the debug flag file exists.

    Swallows every failure. Debug tooling must never be capable of breaking
    the statusline it is meant to diagnose.
    """
    try:
        if os.path.exists(DEBUG_FLAG):
            with open(DEBUG_PAYLOAD, "w", encoding="utf-8") as f:
                f.write(raw)
    except (OSError, UnicodeError):
        pass


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    maybe_dump_payload(raw)

    try:
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        print(f"{COLORS['dim']}statusline: parse error{COLORS['reset']}")
        return

    print(render_environment(data))
    print(render_context_window(data))
    print(render_usage(data))
    print(render_git(data))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(f"{COLORS['dim']}statusline: error{COLORS['reset']}")
        sys.exit(0)
