# Claude Code Status Line

A single-file Python 3 statusline script for [Claude Code](https://claude.ai/claude-code). It receives a JSON payload on stdin and outputs a 4-line ANSI-colored dashboard to stdout.

## Output

```
ENV: CC:2.1.56 | Model: Opus 4.6 | SK: 12 | MCP: 3 | Hooks: 5
CTX: ▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░ 17% of 200K
USE: $0.42 | 45m12s | API: 12m03s | +156 -23 lines
GIT: my-project | main | Age: 25m | Mod: 3 | Staged: 1 | ↑2 ↓0
```

### Sections

| Line | Content |
|------|---------|
| **ENV** | Claude Code version, model name, skill/MCP/hook counts |
| **CTX** | Context window usage with color-coded progress bar (green → yellow → red → blinking) |
| **USE** | Session cost, wall-clock duration, API duration, lines added/removed |
| **GIT** | Repo name, branch, last commit age, modified/staged file counts, unpushed/unpulled |

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

# Malformed input
echo 'not json' | python3 statusline.py
```

## Files

| File | Purpose |
|------|---------|
| `statusline.py` | Main statusline script |
| `settings-snippet.json` | Config block for `~/.claude/settings.json` |
| `test-payload.json` | Sample stdin payload for testing |

## License

MIT
