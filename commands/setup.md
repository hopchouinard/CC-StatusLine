---
description: Set up CC-StatusLine — deploy the script and configure settings
allowed-tools: Bash, Read, Edit, Write
---

Set up the CC-StatusLine plugin. Perform these steps:

1. **Deploy the script**: Copy the statusline script to the user's Claude config:

```bash
cp "${CLAUDE_PLUGIN_ROOT}/scripts/statusline.py" ~/.claude/statusline.py
```

2. **Check settings**: Read `~/.claude/settings.json` and check if it already has a `statusLine` key.

3. **Add config if missing**: If `statusLine` is not configured, add the following to `~/.claude/settings.json` (merge with existing content, do not overwrite other keys):

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline.py",
    "padding": 2
  }
}
```

4. **Confirm**: Tell the user the setup is complete and they should restart Claude Code to see the statusline.

If the statusLine config already exists, tell the user it's already configured and the script has been updated to the latest version.
