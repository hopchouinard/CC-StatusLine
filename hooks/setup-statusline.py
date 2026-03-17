#!/usr/bin/env python3
"""SessionStart hook: auto-deploy statusline.py and check settings config.

Runs on each session start. Safe to re-run (idempotent).
Cross-platform: macOS, Linux, Windows.
"""

import os
import sys
import json
import shutil
import filecmp

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
CLAUDE_DIR = os.path.join(os.path.expanduser("~"), ".claude")
DEST = os.path.join(CLAUDE_DIR, "statusline.py")
SRC = os.path.join(PLUGIN_ROOT, "scripts", "statusline.py")
SETTINGS = os.path.join(CLAUDE_DIR, "settings.json")

# On Windows, python3 may not exist; tilde doesn't expand in cmd.exe/PowerShell
if sys.platform == "win32":
    PYTHON_CMD = "python"
    STATUSLINE_PATH = os.path.join(os.path.expanduser("~"), ".claude", "statusline.py")
else:
    PYTHON_CMD = "python3"
    STATUSLINE_PATH = "~/.claude/statusline.py"


def main():
    if not PLUGIN_ROOT or not os.path.isfile(SRC):
        return

    os.makedirs(CLAUDE_DIR, exist_ok=True)

    # --- Step 1: Copy/update statusline.py ---
    needs_copy = False
    if not os.path.isfile(DEST):
        needs_copy = True
    elif not filecmp.cmp(SRC, DEST, shallow=False):
        needs_copy = True

    if needs_copy:
        shutil.copy2(SRC, DEST)
        print(f"[cc-statusline] Deployed statusline.py to {DEST}")

    # --- Step 2: Check if statusLine config exists in settings ---
    if os.path.isfile(SETTINGS):
        try:
            with open(SETTINGS, "r") as f:
                settings = json.load(f)
            if "statusLine" in settings:
                return
        except (json.JSONDecodeError, OSError):
            pass

    # Settings file missing statusLine config — print instructions for Claude context
    print(f"""[cc-statusline] Setup required: The statusLine config is not yet in ~/.claude/settings.json.

The user needs to add the following to their ~/.claude/settings.json:

{{
  "statusLine": {{
    "type": "command",
    "command": "{PYTHON_CMD} {STATUSLINE_PATH}",
    "padding": 2
  }}
}}

After adding it, restart Claude Code to activate the statusline.
Suggest the user run /cc-statusline:setup if they need help.""")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
