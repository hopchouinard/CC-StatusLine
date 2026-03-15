#!/usr/bin/env bash
# SessionStart hook: auto-deploy statusline.py and check settings config.
# Runs on each session start. Safe to re-run (idempotent).

set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
DEST="$HOME/.claude/statusline.py"
SRC="$PLUGIN_ROOT/scripts/statusline.py"
SETTINGS="$HOME/.claude/settings.json"

if [ -z "$PLUGIN_ROOT" ] || [ ! -f "$SRC" ]; then
    exit 0
fi

mkdir -p "$HOME/.claude"

# --- Step 1: Copy/update statusline.py ---
needs_copy=false

if [ ! -f "$DEST" ]; then
    needs_copy=true
elif ! cmp -s "$SRC" "$DEST"; then
    needs_copy=true
fi

if [ "$needs_copy" = true ]; then
    cp "$SRC" "$DEST"
    echo "[cc-statusline] Deployed statusline.py to $DEST"
fi

# --- Step 2: Check if statusLine config exists in settings ---
if [ -f "$SETTINGS" ]; then
    if grep -q '"statusLine"' "$SETTINGS" 2>/dev/null; then
        exit 0
    fi
fi

# Settings file missing statusLine config — print instructions for Claude context
cat <<'MSG'
[cc-statusline] Setup required: The statusLine config is not yet in ~/.claude/settings.json.

The user needs to add the following to their ~/.claude/settings.json:

{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline.py",
    "padding": 2
  }
}

After adding it, restart Claude Code to activate the statusline.
Suggest the user run /cc-statusline:setup if they need help.
MSG
