---
description: Test the CC-StatusLine script with a sample payload
allowed-tools: Bash
---

Run the CC-StatusLine script with a test payload to verify it renders correctly.

First, locate the plugin install path:

```bash
python3 -c "import json, os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); e=[v[0] for k,v in d['plugins'].items() if 'cc-statusline' in k]; print(e[0]['installPath'] if e else 'NOT_FOUND')" 2>/dev/null || python -c "import json, os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); e=[v[0] for k,v in d['plugins'].items() if 'cc-statusline' in k]; print(e[0]['installPath'] if e else 'NOT_FOUND')"
```

Then run the test using the resolved path. On macOS/Linux:

```bash
cat "{install_path}/test-payload.json" | python3 "{install_path}/scripts/statusline.py"
```

On Windows:

```bash
type "{install_path}\test-payload.json" | python "{install_path}\scripts\statusline.py"
```

Show the raw output to the user. If it fails, show the error.
