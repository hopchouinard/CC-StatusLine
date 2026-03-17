---
description: Set up CC-StatusLine — deploy the script and configure settings
allowed-tools: Bash, Read, Edit, Write
---

Set up the CC-StatusLine plugin. Perform these steps:

1. **Deploy the script**: Copy the statusline script to the user's Claude config:

```bash
cp "${CLAUDE_PLUGIN_ROOT}/scripts/statusline.py" ~/.claude/statusline.py
```

On Windows, use:

```bash
copy "%CLAUDE_PLUGIN_ROOT%\scripts\statusline.py" "%USERPROFILE%\.claude\statusline.py"
```

2. **Check settings**: Read `~/.claude/settings.json` and check if it already has a `statusLine` key.

3. **Detect the platform and add config if missing**: If `statusLine` is not configured, add the following to `~/.claude/settings.json` (merge with existing content, do not overwrite other keys).

On macOS/Linux, use `python3`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline.py",
    "padding": 2
  }
}
```

On Windows, use `python` and the Windows-style path:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python ~/.claude/statusline.py",
    "padding": 2
  }
}
```

Detect the OS by checking for the existence of `/bin/bash` (Unix) vs `C:\Windows` (Windows), or by running `python3 -c "import sys; print(sys.platform)"`.

4. **Confirm**: Tell the user the setup is complete and they should restart Claude Code to see the statusline.

If the statusLine config already exists, tell the user it's already configured and the script has been updated to the latest version.
