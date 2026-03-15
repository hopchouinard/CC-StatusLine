# Claude Code Status Line

A single-file Python 3 statusline script for [Claude Code](https://claude.ai/claude-code). It reads a JSON payload on stdin and outputs a 4-line ANSI-colored dashboard to stdout.

## Output

```
ENV: CC:2.1.56 | Model: Opus 4.6 (1M context) | SK: 44 | MCP: 5 | Hooks: 7
CTX: ▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░ 17% of 200K
USE: $0.42 | 45m12s | API: 12m3s | +156 -23 lines
GIT: my-project | main | Age: 25m | Mod: 3 | Staged: 1 | ↑2 ↓0
```

### Sections

| Line | Content |
|------|---------|
| **ENV** | Claude Code version, model name (with context window), skill/MCP/hook counts |
| **CTX** | Context window usage with color-coded progress bar (green / yellow / red / blinking) |
| **USE** | Session cost, wall-clock duration, API duration, lines added/removed |
| **GIT** | Repo name, branch, last commit age, modified/staged file counts, unpushed/unpulled |

### Resource Counting

Skills, MCP servers, and hooks are counted across all sources:

| Source | Skills | MCP Servers | Hooks |
|--------|--------|-------------|-------|
| **Global** (`~/.claude/`) | `commands/`, `skills/` | `settings.json` → `mcpServers` | `settings.json` → `hooks` |
| **Project** (`{cwd}/.claude/`) | `commands/`, `skills/` | `settings.json`, `settings.local.json` → `mcpServers`; `.mcp.json` | `settings.json`, `settings.local.json` → `hooks` |
| **Plugins** (`installed_plugins.json`) | `skills/`, `commands/` | `.mcp.json` | `hooks/hooks.json` |

Counts are cached for 60 seconds to avoid repeated filesystem scans.

### Color Thresholds

| Metric | Green | Yellow | Red | Blinking Red |
|--------|-------|--------|-----|--------------|
| Context window | 0-50% | 51-75% | 76-90% | >90% |
| Cost | < $1 | $1-$5 | > $5 | -- |

## Requirements

- Python 3 (stdlib only, no external dependencies)
- macOS or Linux

## Installation

1. Copy `statusline.py` to `~/.claude/`:

   ```bash
   cp statusline.py ~/.claude/statusline.py
   ```

2. Merge the config from `settings-snippet.json` into `~/.claude/settings.json`:

   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "python3 ~/.claude/statusline.py",
       "padding": 2
     }
   }
   ```

3. Restart Claude Code.

## Testing

```bash
cat test-payload.json | python3 statusline.py
```

Edge case tests:

```bash
# Empty/new session
echo '{}' | python3 statusline.py

# Malformed input (graceful fallback)
echo 'not json' | python3 statusline.py

# Zero cost (renders $0.00, not $--)
echo '{"cost":{"total_cost_usd":0}}' | python3 statusline.py
```

## Security

- **No shell injection**: All git subprocess calls use argument lists (no `shell=True`)
- **User-isolated caching**: Cache files live under `/tmp/claude-statusline-{uid}/`, not shared paths
- **Fail-safe**: Top-level try/except ensures the script never exits with a non-zero code

## Performance

- Git results cached for 5 seconds (keyed by repo root, not cwd)
- Resource counts cached for 60 seconds
- Typical execution: ~250ms (dominated by Python startup + git calls)

## Files

| File | Purpose |
|------|---------|
| `statusline.py` | Main statusline script |
| `settings-snippet.json` | Config block for `~/.claude/settings.json` |
| `test-payload.json` | Sample stdin payload for testing |

## License

MIT
