---
description: Set up CC-StatusLine — deploy the script and configure settings
allowed-tools: Bash, Read, Edit, Write
---

Set up the CC-StatusLine plugin. Perform these steps:

1. **Detect the platform and locate the plugin** by running:

```bash
python3 -c "import sys, json, os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); e=[v[0] for k,v in d['plugins'].items() if 'cc-statusline' in k]; print(f'{sys.platform}|{e[0][\"installPath\"]}' if e else 'NOT_FOUND')" 2>/dev/null || python -c "import sys, json, os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); e=[v[0] for k,v in d['plugins'].items() if 'cc-statusline' in k]; print(f'{sys.platform}|{e[0][\"installPath\"]}' if e else 'NOT_FOUND')"
```

This prints `{platform}|{install_path}` (e.g., `darwin|/Users/user/.claude/plugins/cache/.../1.4.0` or `win32|C:\Users\user\.claude\plugins\cache\...\1.4.0`). Use the platform to choose `python3` (macOS/Linux) vs `python` (Windows). Use the install path to locate the script.

2. **Deploy the script** by copying `{install_path}/scripts/statusline.py` to `~/.claude/statusline.py`:

On macOS/Linux:

```bash
cp "{install_path}/scripts/statusline.py" ~/.claude/statusline.py
```

On Windows, use Python:

```bash
python -c "import shutil, os; shutil.copy2(r'{install_path}\scripts\statusline.py', os.path.join(os.path.expanduser('~'), '.claude', 'statusline.py'))"
```

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

On Windows, use `python` and the **full absolute path** (tilde does not expand on Windows). Resolve the home directory with `python -c "import os; print(os.path.expanduser('~'))"` and build the path:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python C:\\Users\\username\\.claude\\statusline.py",
    "padding": 2
  }
}
```

5. **If statusLine config already exists**, check that it uses the correct Python command and path for this platform. On Windows, ensure it does NOT use tilde (`~`) — replace with the absolute path if needed. On macOS/Linux, ensure it uses `python3`.

6. **Confirm**: Tell the user the setup is complete and they should restart Claude Code to see the statusline.
