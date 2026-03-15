#!/usr/bin/env python3
"""Claude Code statusline dashboard."""

import sys
import json
import subprocess
import os
import time
import re

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
}

SEP = " | "

# ---------------------------------------------------------------------------
# Caching — user-isolated under /tmp
# ---------------------------------------------------------------------------

_CACHE_DIR = os.path.join("/tmp", f"claude-statusline-{os.getuid()}")
os.makedirs(_CACHE_DIR, exist_ok=True)

RESOURCE_CACHE = os.path.join(_CACHE_DIR, "resources.json")
RESOURCE_TTL = 60

GIT_CACHE = os.path.join(_CACHE_DIR, "git.json")
GIT_TTL = 5


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


def format_duration(ms):
    """Convert milliseconds to compact human string, omitting zero components."""
    if ms is None:
        return "--"
    total_s = int(ms) // 1000
    if total_s < 0:
        return "--"
    hours = total_s // 3600
    minutes = (total_s % 3600) // 60
    seconds = total_s % 60
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
    return "".join(parts)


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

def render_environment(data):
    """ENV: CC:{version} | Model: {model} | SK: {skills} | MCP: {mcps} | Hooks: {hooks}"""
    version = safe_get(data, "version", default="--")
    model = parse_model_name(data)
    cwd = safe_get(data, "cwd", default=None)
    counts = get_resource_counts(cwd)

    parts = [
        c("bold_cyan", "ENV:"),
        " ",
        f"CC:{c('white', version)}",
        SEP,
        f"{c('dim', 'Model:')} {c('green', model)}",
        SEP,
        f"{c('dim', 'SK:')} {c('yellow', counts['skills'])}",
        SEP,
        f"{c('dim', 'MCP:')} {c('yellow', counts['mcp'])}",
        SEP,
        f"{c('dim', 'Hooks:')} {c('yellow', counts['hooks'])}",
    ]
    return "".join(str(p) for p in parts)


def render_context_window(data):
    """CTX: {progress_bar} {pct}% of {size}"""
    pct = safe_get(data, "context_window", "used_percentage")
    window_size = safe_get(data, "context_window", "context_window_size")
    size_label = format_size(window_size) if window_size else "--"

    bar_width = 30
    if pct is not None:
        filled = round(pct / 100 * bar_width)
    else:
        filled = 0

    bar_filled = "\u2593" * filled         # ▓
    bar_empty = "\u2591" * (bar_width - filled)  # ░

    # Color threshold
    if pct is None:
        bar_color = "dim"
        pct_str = "--%"
    elif pct <= 50:
        bar_color = "green"
        pct_str = f"{pct}%"
    elif pct <= 75:
        bar_color = "yellow"
        pct_str = f"{pct}%"
    elif pct <= 90:
        bar_color = "red"
        pct_str = f"{pct}%"
    else:
        bar_color = "red"
        pct_str = f"{pct}%"

    # Build colored bar
    if pct is not None and pct > 90:
        colored_bar = f"{COLORS['red']}{COLORS['blink']}{bar_filled}{COLORS['reset']}{COLORS['dim']}{bar_empty}{COLORS['reset']}"
        colored_pct = f"{COLORS['red']}{COLORS['blink']}{pct_str}{COLORS['reset']}"
    else:
        colored_bar = f"{COLORS.get(bar_color, '')}{bar_filled}{COLORS['reset']}{COLORS['dim']}{bar_empty}{COLORS['reset']}"
        colored_pct = c(bar_color, pct_str)

    return f"{c('bold_cyan', 'CTX:')} {colored_bar} {colored_pct} of {c('white', size_label)}"


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

def fetch_git_info(cwd):
    """Gather all git info via subprocess calls."""
    if not cwd:
        return None

    # Check if it's a git repo and resolve root
    toplevel = run_cmd(["git", "-C", cwd, "rev-parse", "--show-toplevel"])
    if toplevel is None:
        return None

    repo_name = os.path.basename(toplevel)

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


def render_git(data):
    """GIT: {repo} | {branch} | Age: {age} | Mod: {dirty} | Staged: {staged} | up/down"""
    cwd = safe_get(data, "cwd")
    info = get_git_info(cwd)

    if info is None:
        return f"{c('bold_cyan', 'GIT:')} {c('dim', '(not a repo)')}"

    repo = c("bold_white", info["repo"])

    # Branch color: green if clean, yellow if dirty
    if info["dirty"] > 0:
        branch = c("yellow", info["branch"])
    else:
        branch = c("green", info["branch"])

    age = c("dim", info["age"])

    # Mod color: yellow if > 0, dim if 0
    if info["dirty"] > 0:
        mod = c("yellow", info["dirty"])
    else:
        mod = c("dim", "0")

    # Staged color: green if > 0, dim if 0
    if info["staged"] > 0:
        staged = c("green", info["staged"])
    else:
        staged = c("dim", "0")

    parts = [
        c("bold_cyan", "GIT:"),
        " ",
        repo,
        SEP,
        branch,
        SEP,
        f"{c('dim', 'Age:')} {age}",
        SEP,
        f"{c('dim', 'Mod:')} {mod}",
        SEP,
        f"{c('dim', 'Staged:')} {staged}",
    ]

    if info["has_upstream"]:
        up = info["unpushed"]
        down = info["unpulled"]
        up_str = c("yellow", f"\u2191{up}") if up > 0 else c("dim", f"\u2191{up}")
        down_str = c("red", f"\u2193{down}") if down > 0 else c("dim", f"\u2193{down}")
        parts.append(SEP)
        parts.append(f"{up_str} {down_str}")
    else:
        parts.append(SEP)
        parts.append(c("dim", "(no upstream)"))

    return "".join(str(p) for p in parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

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
