# Claude Code Status Line — Implementation Spec

**Language:** Python 3 (stdlib only, no external dependencies)
**Project directory:** `~/Developer/CC-StatusLine`
**Deliverables:** `statusline.py` + `settings-snippet.json` (config block for `~/.claude/settings.json`) + `test-payload.json` (sample stdin for testing)
**Deployment:** Manual — user will copy `statusline.py` to `~/.claude/` and merge the settings snippet into `~/.claude/settings.json` after testing

---

## Overview

Build a single-file statusline script for Claude Code. It receives a JSON payload on stdin, outputs 4 ANSI-colored lines to stdout — one per section.

Once deployed, register in `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline.py",
    "padding": 2
  }
}
```

Deliver this snippet as a separate file `settings-snippet.json` in the project root for reference.

---

## Target Output

```
ENV: CC:2.1.56 | Model: Opus 4.6 | SK: 12 | MCP: 3 | Hooks: 5
CTX: ▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░ 17% of 200K
USE: $0.42 | 45m12s | API: 12m03s | +156 -23 lines
GIT: my-project | main | Age: 25m | Mod: 3 | Staged: 1 | ↑2 ↓0
```

---

## ANSI Color Reference

```python
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
```

Use ` | ` (space-pipe-space) as the inline separator between fields.

---

## Section 1: Environment & Resource Counts

**Data sources:**

| Field | Source |
|-------|--------|
| CC version | `data["version"]` from stdin JSON |
| Model name | `data["model"]["display_name"]` from stdin JSON |
| Skill count | `find ~/.claude/commands -type f 2>/dev/null \| wc -l` |
| Hook count | Parse `~/.claude/settings.json` → count entries in `hooks` array |
| MCP count | Parse `~/.claude/settings.json` → count keys in `mcpServers` object |

**Format:** `ENV: CC:{version} | Model: {model} | SK: {skills} | MCP: {mcps} | Hooks: {hooks}`

**Colors:** Label `ENV:` → bold cyan. Version → white. Model → green. Counts → yellow numbers, dim white labels.

**Caching:** Skill/Hook/MCP counts change rarely. Cache to `/tmp/claude-statusline-resources.json` with 60-second TTL.

---

## Section 2: Context Window Usage

**Data sources (all from stdin JSON):**

| Field | Source |
|-------|--------|
| Used % | `data["context_window"]["used_percentage"]` (int 0-100, may be `null`) |
| Window size | `data["context_window"]["context_window_size"]` (200000 or 1000000) |

**Format:** `CTX: {progress_bar} {pct}% of {size}`

**Progress bar:** 30 chars wide. Filled: `▓`. Empty: `░`. Filled count = `round(pct / 100 * 30)`.

**Color thresholds:**

| Range | Bar + percentage color |
|-------|----------------------|
| 0-50% | green |
| 51-75% | yellow |
| 76-90% | red |
| 91-100% | red + blink (`\033[5m`) |

Label `CTX:` → bold cyan (always).

**Edge cases:** If `used_percentage` is `null`, show `░` × 30 with `--% of {size}`. Format size: 200000 → `200K`, 1000000 → `1M`.

---

## Section 3: Session Cost & Duration

**Data sources (all from stdin JSON):**

| Field | Source |
|-------|--------|
| Cost | `data["cost"]["total_cost_usd"]` (float) |
| Duration | `data["cost"]["total_duration_ms"]` (int, milliseconds) |
| API duration | `data["cost"]["total_api_duration_ms"]` (int, milliseconds) |
| Lines added | `data["cost"]["total_lines_added"]` (int) |
| Lines removed | `data["cost"]["total_lines_removed"]` (int) |

**Format:** `USE: ${cost} | {duration} | API: {api_duration} | +{added} -{removed} lines`

**Duration formatting:** Convert ms to human-readable, omit zero components. Examples: `2712000` → `45m12s`, `7323000` → `2h2m3s`. Never show `0h`.

**Colors:** Label `USE:` → bold cyan. Cost → green if < $1, yellow if $1-5, red if > $5. Duration → white. Lines added → green. Lines removed → red.

---

## Section 4: Git Status

**Data sources (all via `git -C {cwd}` subprocess calls, using `data["cwd"]` from stdin JSON):**

| Field | Command |
|-------|---------|
| Repo name | `basename $(git -C {cwd} rev-parse --show-toplevel)` |
| Branch | `git -C {cwd} branch --show-current` |
| Dirty count | `git -C {cwd} status --porcelain \| wc -l` |
| Staged count | `git -C {cwd} diff --cached --numstat \| wc -l` |
| Unpushed | `git -C {cwd} rev-list --count @{upstream}..HEAD 2>/dev/null` |
| Unpulled | `git -C {cwd} rev-list --count HEAD..@{upstream} 2>/dev/null` |
| Last commit age | `git -C {cwd} log -1 --format=%cr` |

**Format:** `GIT: {repo} | {branch} | Age: {age} | Mod: {dirty} | Staged: {staged} | ↑{unpushed} ↓{unpulled}`

**Colors:** Label `GIT:` → bold cyan. Repo → bold white. Branch → green if clean, yellow if dirty. Mod → yellow if > 0, dim if 0. Staged → green if > 0, dim if 0. ↑ → yellow if > 0. ↓ → red if > 0. Age → dim white.

**Edge cases:**
- Not a git repo → `GIT: (not a repo)` in dim
- Detached HEAD → show short commit hash instead of branch
- No upstream → omit ↑↓, show `(no upstream)` in dim

**Caching:** Cache git results to `/tmp/claude-statusline-git.json` with 5-second TTL, keyed by `cwd`.

---

## Performance & Error Handling

**The script is called on every render (potentially multiple times per second). It must:**

- Complete in under 200ms
- Never make network calls
- Cache expensive operations (file system scans, git commands)
- Read stdin completely even if parsing fails (prevent broken pipe)
- Never exit with non-zero code

**Error behavior:**

| Condition | Output |
|-----------|--------|
| Malformed stdin JSON | Single dim line: `statusline: parse error` |
| Git commands fail | Section 4 shows `(not a repo)` |
| Stale/corrupt cache | Regenerate silently |
| Any null/missing field | Show `--` as placeholder |

---

## Script Structure

```python
#!/usr/bin/env python3
"""Claude Code statusline dashboard."""

import sys, json, subprocess, os, time

def main():
    data = json.load(sys.stdin)
    print(render_environment(data))
    print(render_context_window(data))
    print(render_usage(data))
    print(render_git(data))

def render_environment(data): ...
def render_context_window(data): ...
def render_usage(data): ...
def render_git(data): ...

def read_cache(cache_file, ttl_seconds): ...
def write_cache(cache_file, data): ...

if __name__ == "__main__":
    main()
```

---

## Testing

Use the delivered `test-payload.json` to validate output:

```bash
cat test-payload.json | python3 statusline.py
```

Also test: null context (new session), non-git directory, missing `~/.claude/settings.json`.

---

## Stdin JSON Schema Reference

```json
{
  "cwd": "/path/to/project",
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "version": "2.1.56",
  "model": {
    "id": "claude-opus-4-6",
    "display_name": "Opus"
  },
  "workspace": {
    "current_dir": "/path/to/project",
    "project_dir": "/original/launch/dir"
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
  "exceeds_200k_tokens": false,
  "vim": { "mode": "NORMAL" },
  "agent": { "name": "agent-name" },
  "worktree": {
    "name": "feature",
    "path": "/path/to/.claude/worktrees/feature",
    "branch": "worktree-feature",
    "original_cwd": "/path/to/project",
    "original_branch": "main"
  }
}
```

**Notes:** `vim`, `agent`, `worktree` are conditionally present. `context_window.current_usage` and `used_percentage` may be `null` before the first API call.
