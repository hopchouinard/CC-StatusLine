# CC-StatusLine

A Claude Code plugin that renders a 4-line ANSI-colored statusline dashboard showing environment info, context window usage, session cost, and git status.

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
| **CTX** | Context window usage with color-coded progress bar |
| **USE** | Session cost, wall-clock duration, API duration, lines added/removed |
| **GIT** | Repo name, branch, last commit age, modified/staged file counts, unpushed/unpulled |

## Installation

### Step 1: Install the plugin

From within Claude Code, run:

```
/plugin install cc-statusline
```

Or during development, launch with:

```bash
claude --plugin-dir /path/to/CC-StatusLine
```

### Step 2: Copy the script to a stable path

The plugin cache path changes with each update, so the statusline script needs to live at a fixed location. Copy it once after installing:

```bash
cp ~/.claude/plugins/cache/*/cc-statusline/*/scripts/statusline.py ~/.claude/statusline.py
```

> **Note:** After running `claude plugin update cc-statusline`, re-run this copy command to pick up any script changes.

### Step 3: Register the statusline

Add the following to your `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline.py",
    "padding": 2
  }
}
```

### Step 4: Restart Claude Code

The statusline appears on the next session start.

### Verify

Use the included slash command to test rendering with a sample payload:

```
/cc-statusline:statusline-test
```

## Resource Counting

Skills, MCP servers, and hooks are counted across all sources:

| Source | Skills | MCP Servers | Hooks |
|--------|--------|-------------|-------|
| **Global** (`~/.claude/`) | `commands/`, `skills/` | `settings.json` | `settings.json` |
| **Project** (`{cwd}/.claude/`) | `commands/`, `skills/` | `settings.json`, `settings.local.json`, `.mcp.json` | `settings.json`, `settings.local.json` |
| **Plugins** (`installed_plugins.json`) | `skills/`, `commands/` | `.mcp.json` | `hooks/hooks.json` |

Counts are cached for 60 seconds.

## Color Thresholds

| Metric | Green | Yellow | Red | Blinking Red |
|--------|-------|--------|-----|--------------|
| Context window | 0-50% | 51-75% | 76-90% | >90% |
| Cost | < $1 | $1-$5 | > $5 | -- |

## Requirements

- Python 3 (stdlib only)
- macOS or Linux

## Security

- **No shell injection**: All subprocess calls use argument lists (no `shell=True`)
- **User-isolated caching**: Cache files under `/tmp/claude-statusline-{uid}/`
- **Fail-safe**: Top-level try/except ensures the script never exits non-zero

## Performance

- Git results cached for 5 seconds (keyed by repo root)
- Resource counts cached for 60 seconds
- Typical execution: ~250ms

## Project Structure

```
CC-StatusLine/
├── .claude-plugin/
│   └── plugin.json            # Plugin manifest
├── scripts/
│   └── statusline.py          # Main statusline script
├── commands/
│   └── statusline-test.md     # /cc-statusline:statusline-test
├── test-payload.json          # Sample stdin for manual testing
└── README.md
```

## License

MIT
