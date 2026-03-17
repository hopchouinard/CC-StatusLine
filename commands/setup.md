---
description: Set up CC-StatusLine — deploy the script and configure settings
allowed-tools: Bash, Read, Edit, Write
---

Set up the CC-StatusLine plugin. Perform these steps:

1. **Detect the platform** by running:

```bash
python3 -c "import sys; print(sys.platform)" 2>/dev/null || python -c "import sys; print(sys.platform)"
```

Use this result to determine macOS/Linux (`darwin`/`linux`) vs Windows (`win32`).

2. **Deploy the script** using Python (works on all platforms):

```bash
python3 -c "import shutil, os; shutil.copy2(os.path.join(os.environ['CLAUDE_PLUGIN_ROOT'], 'scripts', 'statusline.py'), os.path.join(os.path.expanduser('~'), '.claude', 'statusline.py'))"
```

On Windows, use `python` instead of `python3`.

3. **Check settings**: Read `~/.claude/settings.json` and check if it already has a `statusLine` key.

4. **Add config if missing**: If `statusLine` is not configured, add the following to `~/.claude/settings.json` (merge with existing content, do not overwrite other keys).

On macOS/Linux:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline.py",
    "padding": 2
  }
}
```

On Windows, use `python` and the **full absolute path** (tilde does not expand on Windows). Resolve the path by running `python -c "import os; print(os.path.join(os.path.expanduser('~'), '.claude', 'statusline.py'))"` and use the result:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python C:\\Users\\username\\.claude\\statusline.py",
    "padding": 2
  }
}
```

5. **Confirm**: Tell the user the setup is complete and they should restart Claude Code to see the statusline.

If the statusLine config already exists, tell the user it's already configured and the script has been updated to the latest version.
