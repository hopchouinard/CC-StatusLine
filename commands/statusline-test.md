---
description: Test the CC-StatusLine script with a sample payload
allowed-tools: Bash
---

Run the CC-StatusLine script with a test payload to verify it renders correctly.

First, locate the plugin install path:

```bash
python3 -c "import json, os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); e=[v[0] for k,v in d['plugins'].items() if 'cc-statusline' in k]; print(e[0]['installPath'] if e else 'NOT_FOUND')" 2>/dev/null || python -c "import json, os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); e=[v[0] for k,v in d['plugins'].items() if 'cc-statusline' in k]; print(e[0]['installPath'] if e else 'NOT_FOUND')"
```

Then run both fixtures using the resolved path. On macOS/Linux:

```bash
cat "{install_path}/test-payload.json" | python3 "{install_path}/scripts/statusline.py"
echo "--- minimal payload (optional sections absent) ---"
cat "{install_path}/test-payload-minimal.json" | python3 "{install_path}/scripts/statusline.py"
```

On Windows:

```bash
type "{install_path}\test-payload.json" | python "{install_path}\scripts\statusline.py"
echo "--- minimal payload (optional sections absent) ---"
type "{install_path}\test-payload-minimal.json" | python "{install_path}\scripts\statusline.py"
```

Show the raw output of both to the user. If either fails, show the error.

The full payload exercises every section. The minimal payload has no effort,
no rate limits, and no worktree, so those sections must be absent — check that
no line ends in a separator and that no `| |` appears anywhere.
