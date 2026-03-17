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

### Step 1: Add the marketplace and install

```
/plugin marketplace add hopchouinard/patchoutech-plugins
/plugin install cc-statusline@patchoutech-plugins
```

### Step 2: Run setup

The plugin includes a setup command that deploys the script and configures your settings automatically:

```
/cc-statusline:setup
```

This will:
- Copy `statusline.py` to `~/.claude/statusline.py`
- Detect your OS and add the `statusLine` config to `~/.claude/settings.json` with the correct Python command (`python3` on macOS/Linux, `python` on Windows)

> **Note:** A SessionStart hook also runs automatically on each new session. It keeps the script up to date and reminds Claude to suggest setup if the config is missing.

### Step 3: Restart Claude Code

The statusline appears on the next session start.

### Updating

```
/plugin update cc-statusline@patchoutech-plugins
/reload-plugins
```

The SessionStart hook will automatically deploy the updated script to `~/.claude/statusline.py` on your next session.

### Verify

Test rendering with a sample payload:

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
- macOS, Linux, or Windows (Windows Terminal recommended for proper ANSI/Unicode rendering)

## Platform Compatibility

The plugin auto-detects the platform and adapts accordingly:

| Behavior | macOS / Linux | Windows |
|----------|---------------|---------|
| Python command | `python3` | `python` |
| statusLine path in settings | `~/.claude/statusline.py` | Absolute path (e.g., `C:\Users\user\.claude\statusline.py`) |
| Cache directory | `/var/folders/.../claude-statusline-user/` | `%TEMP%\claude-statusline-user\` |
| ANSI colors | Native support | VT processing enabled automatically |
| SessionStart hook | `python` (falls back gracefully) | `python` |

## Security

- **No shell injection**: All subprocess calls use argument lists (no `shell=True`)
- **User-isolated caching**: Cache files under `{tempdir}/claude-statusline-{user}/`
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
├── hooks/
│   ├── hooks.json             # SessionStart hook config
│   └── setup-statusline.py    # Auto-deploy on session start
├── commands/
│   ├── setup.md               # /cc-statusline:setup
│   └── statusline-test.md     # /cc-statusline:statusline-test
├── Docs/
│   ├── claude-code-statusline-spec.md
│   └── cc-statusline-plugin-spec.md
├── test-payload.json          # Sample stdin for manual testing
└── README.md
```

## License

MIT
